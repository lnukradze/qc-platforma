"""T-031: field-facing labels across HTML, API and queued mail.

Intentionally red on main until both UI and backend implementations arrive.
Only synthetic records in conftest's temporary database; never sends mail.
"""
import datetime as dt
from html import unescape
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app import domain as D
from app.main import app
from app.models import PreqcCheck
from app.services import notify
from app.workflow import apply as workflow_apply
from conftest import make_item, make_user


FIELD = [("sv", D.SURVEYOR), ("mgr", D.FIELD_MANAGER)]
QC_ROLES = (D.QC_OPERATOR, D.QC_MANAGER, D.ADMIN)


def apply(db, item, user, role, action, form):
    """Use the real version/token contract when T-019 is integrated too."""
    form = {**form, "version": item.version}
    if action == "comment":
        form["once"] = uuid.uuid4().hex
    event = workflow_apply(db, item, user, role, action, form)
    db.commit()
    return event


# Stems catch Georgian inflections, e.g. მენეჯერთან / ოპერატორს.
FORBIDDEN = tuple(dict.fromkeys([
    *(D.ROLE_SHORT[r].rstrip("ი") for r in (D.QC_OPERATOR, D.QC_MANAGER)),
    *(D.ROLE_LABELS[r].rstrip("ი") for r in (D.QC_OPERATOR, D.QC_MANAGER)),
    "კონტროლის მენეჯერ", "კონტროლის ოპერატორ", "ოპერატორის შეცდომა",
]))


def clean(text):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", text)).split())


def assert_neutral(text, where):
    # Raw HTML also covers attributes / hidden text, normalized text catches
    # labels split across tags or escaped as HTML entities.
    text = unescape(text) + " " + clean(text)
    leaked = [s for s in FORBIDDEN if s in text]
    assert not leaked, f"{where}: forbidden role labels: {leaked}"


def client(user, role):
    c = TestClient(app)
    r = c.post("/login/demo", data={"user_id": user.id, "role": role},
               headers={"origin": "http://testserver"}, follow_redirects=False)
    assert r.status_code == 303 and "err=" not in r.headers["location"]
    return c


@pytest.fixture()
def neutral_world(db, monkeypatch):
    monkeypatch.setattr(notify, "SMTP_HOST", "")

    def no_send(_msg):
        pytest.fail("SMTP must never be called")

    monkeypatch.setattr(notify, "_send", no_send)
    p = {key: make_user(db, f"Synthetic {key}", role, email=f"{key}@example.com")
         for key, role in [("op", D.QC_OPERATOR), ("qcm", D.QC_MANAGER),
                           ("admin", D.ADMIN), *FIELD]}
    # A second field-only surveyor is required by make_item's default team.
    p["sv2"] = make_user(db, "Synthetic second", D.SURVEYOR)
    db.commit()
    items, events = {}, {}
    for n, decision in enumerate((None, "qcm_stand", "qcm_field_right", "qcm_both_right"), 1):
        i = make_item(db, p, protocol=f"931000{n}", cad=f"202.51.12.40.999.00{n}")
        apply(db, i, p["op"], D.QC_OPERATOR, "send",
              {"verdict": D.RECOMMENDATION, "qc_comment": "Synthetic initial note"})
        apply(db, i, p["qcm"], D.QC_MANAGER, "change_verdict",
              {"new_verdict": D.NEGATIVE, "comment": "Synthetic change"})
        apply(db, i, p["sv"], D.SURVEYOR, "field_respond",
              {"response": D.R_DISAGREE, "comment": "Synthetic response"})
        apply(db, i, p["mgr"], D.FIELD_MANAGER, "manager_approve", {})
        key = decision or "awaiting"
        if decision:
            events[decision] = apply(db, i, p["qcm"], D.QC_MANAGER, decision,
                                     {"confirm_positive": "on", "comment": "Synthetic decision"})
        events[f"comment_{key}"] = apply(db, i, p["admin"], D.ADMIN, "comment",
                                         {"comment": "Synthetic admin comment"})
        items[key] = i
    # Non-empty sporadic and returned-manager tabs exercise their row macros too.
    items["qcm_stand"].kind = D.SPORADIC
    i = make_item(db, p, protocol="9310005", cad="202.51.12.40.999.005")
    apply(db, i, p["op"], D.QC_OPERATOR, "send",
          {"verdict": D.NEGATIVE, "qc_comment": "Synthetic manager note"})
    apply(db, i, p["sv"], D.SURVEYOR, "field_respond",
          {"response": D.R_DISAGREE, "comment": "Synthetic response"})
    items["manager"] = i
    check = PreqcCheck(surveyor_id=p["sv"].id, field_manager_id=p["mgr"].id,
                       protocol_number="9310099", protocol_date=dt.date.today(),
                       checked_on=dt.date.today(), status="fail", score=40)
    db.add(check)
    db.commit()
    assert items["awaiting"].state == D.AWAITING_QCM
    assert items["qcm_field_right"].qc_error
    return p, items, events, check


PAGES = ("/", "/field", "/field?tab=sporadic", "/field?tab=manager",
         "/field?tab=cc", "/stats", "/preqc", "/preqc/{check}",
         "/items/{awaiting}", "/items/{qcm_stand}",
         "/items/{qcm_field_right}", "/items/{qcm_both_right}")


@pytest.mark.parametrize("who,role", FIELD)
@pytest.mark.parametrize("path", PAGES)
def test_field_pages_have_neutral_labels(db, neutral_world, who, role, path):
    p, items, _, check = neutral_world
    url = path.format(check=check.id, **{k: i.id for k, i in items.items()})
    with client(p[who], role) as c:
        r = c.get(url)
    assert r.status_code == 200, url
    # Whole response, not only author divs (the T-029 false-positive gap).
    assert_neutral(r.text, url)
    if path.startswith("/items/"):
        key = path.removeprefix("/items/{").removesuffix("}")
        i = items[key]
        assert i.protocol_number in r.text and "Synthetic change" in r.text
        assert D.labels(role)["EVENT_LABELS"]["verdict_changed"] in r.text
        if i.qcm_decision:
            assert D.labels(role)["QCM_DECISION_LABELS"][i.qcm_decision] in r.text
    if path == "/field":
        assert items["awaiting"].protocol_number in r.text
        assert D.labels(role)["STATE_LABELS"][D.AWAITING_QCM] in r.text


@pytest.mark.parametrize("who,role", FIELD)
def test_field_api_state_labels(db, neutral_world, who, role):
    p, items, _, _ = neutral_world
    with client(p[who], role) as c:
        r = c.get("/api/items")
    assert r.status_code == 200
    rows = {row["id"]: row for row in r.json()["items"]}
    assert items["awaiting"].id in rows
    for row in rows.values():
        assert row["state_label"] == D.labels(role)["STATE_LABELS"][row["state"]]
        assert_neutral(row["state_label"], "/api/items")


@pytest.mark.parametrize("who,role", FIELD)
@pytest.mark.parametrize("key", ["awaiting", "qcm_stand", "qcm_field_right", "qcm_both_right"])
def test_field_api_history_hides_qc_roles(db, neutral_world, who, role, key):
    p, items, _, _ = neutral_world
    with client(p[who], role) as c:
        r = c.get(f"/api/items/{items[key].id}")
    assert r.status_code == 200
    data = r.json()
    assert data["history"] and any(e["action"] == "verdict_changed" for e in data["history"])
    assert data["state_label"] == D.labels(role)["STATE_LABELS"][data["state"]]
    assert_neutral(data["state_label"], "detail state_label")
    for event in data["history"]:
        assert event.get("role") not in QC_ROLES, event
    assert any(e.get("role") == D.SURVEYOR for e in data["history"])


@pytest.mark.parametrize("kind", ["qcm_stand", "qcm_field_right", "qcm_both_right", "comment"])
@pytest.mark.parametrize("dual_role", [False, True])
def test_queued_mail_uses_field_labels(db, neutral_world, kind, dual_role):
    p, items, events, _ = neutral_world
    if dual_role:
        from app.models import UserRole
        p["mgr"].roles.append(UserRole(role=D.QC_MANAGER))
        db.commit()
    key = kind if kind != "comment" else "qcm_stand"
    ev = events[kind] if kind != "comment" else events["comment_qcm_stand"]
    sender = p["qcm"] if kind != "comment" else p["admin"]
    msg = notify.queue(db, items[key], ev, sender, kind, base_url="http://example.com")
    assert msg is not None and msg.status == "preview"
    assert msg.to_user_id == p["mgr"].id
    for body in (msg.html, msg.text):
        assert_neutral(body, f"mail {kind}")
        assert items[key].protocol_number in body and ev.comment in body
        assert D.QC_ANON_LABEL in body
        assert D.labels(D.FIELD_MANAGER)["EVENT_LABELS"][ev.action] in body
    assert_neutral(msg.subject, "mail subject")


@pytest.mark.parametrize("who,role", FIELD)
def test_about_is_an_explicit_exception(db, neutral_world, who, role):
    p, _, _, _ = neutral_world
    with client(p[who], role) as c:
        r = c.get("/about")
    assert r.status_code == 200
    # This exception must not trigger a global replacement of QC role labels.
    assert D.ROLE_SHORT[D.QC_MANAGER] in r.text


def test_qc_manager_keeps_full_labels_and_history(db, neutral_world):
    p, items, _, _ = neutral_world
    with client(p["qcm"], D.QC_MANAGER) as c:
        for key in ("awaiting", "qcm_stand", "qcm_field_right", "qcm_both_right"):
            i = items[key]
            r = c.get(f"/items/{i.id}")
            assert r.status_code == 200 and i.protocol_number in r.text
            assert p["qcm"].full_name in r.text
            assert D.labels(D.QC_MANAGER)["EVENT_LABELS"]["verdict_changed"] in r.text
            if i.qcm_decision:
                assert D.labels(D.QC_MANAGER)["QCM_DECISION_LABELS"][i.qcm_decision] in r.text
            data = c.get(f"/api/items/{i.id}").json()
            assert data["state_label"] == D.labels(D.QC_MANAGER)["STATE_LABELS"][i.state]
            assert any(e.get("role") == D.QC_MANAGER for e in data["history"])
            assert any(e.get("role") == D.ADMIN for e in data["history"])
        home = c.get("/")
        assert home.status_code == 200
        assert D.ROLE_SHORT[D.QC_MANAGER] in home.text

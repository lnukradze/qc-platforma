# -*- coding: utf-8 -*-
"""
T-031 (ნაწილი ბ, backend) — ველს QC-ის როლი არ უჩანს: render()-ის წარწერები მნახველის როლით,
API-ის state_label და ისტორიის role, წერილის წარწერები. QA-ის რეგრესია (ნაწილი გ) — ცალკე.
ფორმებს version / once აქვს — T-019-თან შერწყმის შემდეგაც იმუშავებს. მონაცემი გამოგონილია.
"""
import pytest
from fastapi.testclient import TestClient

from app import domain as D
from app.main import app
from app.models import QcEvent
from app.services import notify
from app.workflow import apply
from conftest import make_item, make_user

ORIGIN = {"origin": "http://testserver"}
FIELD = [("sv", D.SURVEYOR), ("mgr", D.FIELD_MANAGER)]
QC_SIDE = [("op", D.QC_OPERATOR), ("qcm", D.QC_MANAGER), ("admin", D.ADMIN), ("coord", D.COORDINATOR)]


@pytest.fixture(autouse=True)
def no_smtp(monkeypatch):
    monkeypatch.setattr(notify, "SMTP_HOST", "")

    def _boom(msg):
        raise AssertionError("SMTP-ზე გაგზავნა ტესტში არ უნდა მოხდეს")
    monkeypatch.setattr(notify, "_send", _boom)


def _do(db, it, user, role, action, **form):
    form.setdefault("version", it.version)
    if action == "comment":
        form.setdefault("once", f"t031-{it.id}-{it.version}-{user.id}")
    ev = apply(db, it, user, role, action, form)
    db.commit()
    return ev


@pytest.fixture()
def w(db, people):
    """ოქმი QC მენეჯერთან (awaiting_qcm): გაგზავნა → „არ ვეთანხმები“ → მენეჯერის დადასტურება."""
    it = make_item(db, people)
    _do(db, it, people["op"], D.QC_OPERATOR, "send", verdict=D.NEGATIVE, qc_comment="ფოტო აკლია (ტესტი)")
    _do(db, it, people["sv"], D.SURVEYOR, "field_respond", response=D.R_DISAGREE, comment="არ ვეთანხმები")
    _do(db, it, people["mgr"], D.FIELD_MANAGER, "manager_approve")
    assert it.state == D.AWAITING_QCM
    return it


def client(user, role):
    c = TestClient(app)
    r = c.post("/login/demo", data={"user_id": str(user.id), "role": role}, headers=ORIGIN,
               follow_redirects=False)
    assert r.status_code == 303 and "err=" not in r.headers["location"]
    return c


# ── 1. render() — წარწერები მნახველის როლით ─────────────────────────────
@pytest.mark.parametrize("who,role", FIELD)
@pytest.mark.parametrize("path", ["/items/{id}", "/"])
def test_render_field_gets_neutral_labels(db, people, w, who, role, path):
    r = client(people[who], role).get(path.format(id=w.id))
    assert r.status_code == 200
    assert r.context["STATE_LABELS"] is D.FIELD_STATE_LABELS
    assert r.context["EVENT_LABELS"] is D.FIELD_EVENT_LABELS
    assert r.context["QCM_DECISION_LABELS"] is D.FIELD_QCM_DECISION_LABELS


@pytest.mark.parametrize("who,role", QC_SIDE)
def test_render_qc_side_keeps_full_labels(db, people, w, who, role):
    r = client(people[who], role).get(f"/items/{w.id}")
    assert r.status_code == 200
    assert r.context["STATE_LABELS"] is D.STATE_LABELS
    assert r.context["EVENT_LABELS"] is D.EVENT_LABELS
    assert r.context["QCM_DECISION_LABELS"] is D.QCM_DECISION_LABELS


def test_render_explicit_kwarg_wins(db, people, monkeypatch):
    """გვერდს თავისი მნიშვნელობის გადაცემა შეუძლია — render() kw-ს არ გადაფარავს."""
    from starlette.requests import Request
    from app.routes import common
    from conftest import ctx
    seen = {}
    monkeypatch.setattr(common.templates, "TemplateResponse",
                        lambda request, name, context, status_code=200: seen.update(context))
    req = Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": []})
    common.render(req, ctx(people["sv"], D.SURVEYOR), "x.html", STATE_LABELS={"x": "y"})
    assert seen["STATE_LABELS"] == {"x": "y"} and seen["EVENT_LABELS"] is D.FIELD_EVENT_LABELS


# ── 2. API ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("who,role", FIELD)
def test_api_field_state_label_and_history_role(db, people, w, who, role):
    c = client(people[who], role)
    items = c.get("/api/items").json()["items"]
    row = next(i for i in items if i["id"] == w.id)
    assert row["state_label"] == D.FIELD_STATE_LABELS[D.AWAITING_QCM] != D.STATE_LABELS[D.AWAITING_QCM]
    d = c.get(f"/api/items/{w.id}").json()
    assert d["state_label"] == D.FIELD_STATE_LABELS[D.AWAITING_QCM]
    roles = [h.get("role") for h in d["history"]]
    assert not set(roles) & set(D.QC_ROLES)                       # QC-ის როლი არცერთ ჩანაწერში
    sent = next(h for h in d["history"] if h["action"] == "sent")
    assert "role" not in sent                                     # QC-ის ავტორი — როლის გარეშე
    resp = next(h for h in d["history"] if h["action"] == "field_responded")
    assert resp["role"] == D.SURVEYOR                             # ველის ავტორი — როლით


def test_api_field_hides_role_when_actor_role_missing(db, people, w):
    """ძველი ჩანაწერი actor_role-ის გარეშე: QC მომხმარებელი — როლი მაინც არ ჩანს (anon-ის წესი)."""
    ev = db.query(QcEvent).filter_by(item_id=w.id, action="sent").one()
    ev.actor_role = None
    db.commit()
    d = client(people["sv"], D.SURVEYOR).get(f"/api/items/{w.id}").json()
    assert "role" not in next(h for h in d["history"] if h["action"] == "sent")


def test_api_history_edge_cases(db, people, w):
    """ავტორის გარეშე ძველი ჩანაწერი; ორმაგი როლი ველის როლით; ადმინი ველის მხარეს."""
    sent = db.query(QcEvent).filter_by(item_id=w.id, action="sent").one()
    sent.actor_id, sent.actor_role = None, None                   # ძველი იმპორტი — ავტორი უცნობია
    resp = db.query(QcEvent).filter_by(item_id=w.id, action="field_responded").one()
    dual = make_user(db, "Mari Multi-Theta", D.QC_OPERATOR, D.SURVEYOR)
    resp.actor_id = dual.id                                       # ორმაგი როლი, მოქმედებდა ამზომველად
    appr = db.query(QcEvent).filter_by(item_id=w.id, action="manager_approved").one()
    appr.actor_id, appr.actor_role = people["admin"].id, D.ADMIN  # ადმინი ველის მხარეს
    db.commit()
    d = client(people["sv"], D.SURVEYOR).get(f"/api/items/{w.id}").json()
    h = {x["action"]: x for x in d["history"]}
    assert h["sent"].get("role") is None                          # არც შეცდომა, არც როლი
    assert h["field_responded"]["role"] == D.SURVEYOR
    assert "role" not in h["manager_approved"]
    assert not {x.get("role") for x in d["history"]} & set(D.QC_ROLES)


FORBIDDEN = ("QC მენეჯერ", "QC ოპერატორ", "კონტროლის მენეჯერ", "კონტროლის ოპერატორ", "ოპერატორის შეცდომა")
FIELD_ACTIONS = ("field_respond", "manager_approve", "manager_reject", "manager_respond", "comment")


def test_flash_messages_for_field_actions_are_neutral():
    from app.routes.items import FIELD_MESSAGES, MESSAGES
    for act in FIELD_ACTIONS:
        text = {**MESSAGES, **FIELD_MESSAGES}[act]
        assert not [x for x in FORBIDDEN if x in text], act
    assert "QC მენეჯერს" in MESSAGES["manager_approve"]              # QC მხარეს (ადმინს) — უცვლელი


def test_manager_approve_flash_neutral_for_field_manager(db, people):
    from urllib.parse import parse_qs, urlparse
    it = make_item(db, people, protocol="6100009")
    _do(db, it, people["op"], D.QC_OPERATOR, "send", verdict=D.NEGATIVE, qc_comment="x")
    _do(db, it, people["sv"], D.SURVEYOR, "field_respond", response=D.R_DISAGREE, comment="არა")
    r = client(people["mgr"], D.FIELD_MANAGER).post(
        f"/items/{it.id}/action", headers=ORIGIN, follow_redirects=False,
        data={"action": "manager_approve", "version": it.version})
    ok = parse_qs(urlparse(r.headers["location"]).query)["ok"][0]
    assert "დადასტურდა" in ok and not [x for x in FORBIDDEN if x in ok]


@pytest.mark.parametrize("who,role", [("qcm", D.QC_MANAGER), ("admin", D.ADMIN), ("op", D.QC_OPERATOR)])
def test_api_qc_side_unchanged(db, people, w, who, role):
    d = client(people[who], role).get(f"/api/items/{w.id}").json()
    assert d["state_label"] == D.STATE_LABELS[D.AWAITING_QCM]
    sent = next(h for h in d["history"] if h["action"] == "sent")
    assert sent["role"] == D.QC_OPERATOR


# ── 3. წერილი — ყოველთვის ნეიტრალური წარწერები ──────────────────────────
def _capture(monkeypatch):
    seen = []
    real = notify.env.get_template

    class Probe:
        def __init__(self, t):
            self.t = t

        def render(self, **kw):
            seen.append(kw)
            return self.t.render(**kw)
    monkeypatch.setattr(notify.env, "get_template", lambda name: Probe(real(name)))
    return seen


@pytest.mark.parametrize("dual", [False, True])
def test_email_context_neutral_labels(db, people, w, monkeypatch, dual):
    if dual:                                                      # ორმაგი როლის ადრესატი
        mgr = people["mgr"]
        u = make_user(db, "Rati Dual-Fm", D.FIELD_MANAGER, D.QC_MANAGER, email="dual@example.com")
        w.field_manager_id = u.id
        db.commit()
        assert mgr.id != u.id
    ev = _do(db, w, people["qcm"], D.QC_MANAGER, "qcm_stand", comment="ხარვეზი რჩება")
    seen = _capture(monkeypatch)
    msg = notify.queue(db, w, ev, people["qcm"], "qcm_stand", base_url="http://x/")
    assert msg is not None and len(seen) == 2                     # HTML და ტექსტი
    for kw in seen:
        assert kw["EVENT_LABELS"] is D.FIELD_EVENT_LABELS
        assert kw["STATE_LABELS"] is D.FIELD_STATE_LABELS
        assert kw["QCM_DECISION_LABELS"] is D.FIELD_QCM_DECISION_LABELS
    for subject in notify.SUBJECTS.values():                      # თემა უკვე ნეიტრალურია
        for word in ("QC მენეჯერ", "QC ოპერატორ", "კონტროლის მენეჯერ", "კონტროლის ოპერატორ",
                     "ოპერატორის შეცდომა"):
            assert word not in subject

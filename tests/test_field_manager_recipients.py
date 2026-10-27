# -*- coding: utf-8 -*-
"""
T-030 — პასუხისმგებელი მენეჯერი და წერილის ადრესატი: მხოლოდ აქტიური მომხმარებელი საველე მენეჯერის
როლით (ორმაგი როლი — დასაშვებია). backend-ის ტესტები; QA-ის T-028-ის რეგრესიები — ცალკე ფაილში.
სახელები გამოგონილია და ლათინურია.
"""
import logging
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import domain as D
from app.config import DATABASE_URL
from app.main import app
from app.models import EmailMessage, ItemPerson, QcEvent, QcItem
from app.services import notify
from app.workflow import WorkflowError, apply, is_field_manager
from conftest import make_item, make_user

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_field_managers  # noqa: E402

ORIGIN = {"origin": "http://testserver"}
NOTICE = "✉ წერილი არ შეიქმნა — ოქმს საველე მენეჯერი არ ჰყავს."


@pytest.fixture(autouse=True)
def no_smtp(monkeypatch):
    monkeypatch.setattr(notify, "SMTP_HOST", "")

    def _boom(msg):
        raise AssertionError("SMTP-ზე გაგზავნა ტესტში არ უნდა მოხდეს")
    monkeypatch.setattr(notify, "_send", _boom)


@pytest.fixture()
def u(db, people):
    x = {
        "qc_only": make_user(db, "Zura Qc-Only", D.QC_OPERATOR, email="qconly@example.com"),
        "qcm_only": make_user(db, "Lika Qcm-Only", D.QC_MANAGER, email="qcmonly@example.com"),
        "no_role": make_user(db, "Gela No-Role", email="norole@example.com"),
        "inactive": make_user(db, "Maka Inactive-Fm", D.FIELD_MANAGER, email="inactive@example.com"),
        "dual": make_user(db, "Rati Dual-Fm", D.FIELD_MANAGER, D.QC_OPERATOR, email="dual@example.com"),
        "dual_admin": make_user(db, "Tako Dual-Admin", D.FIELD_MANAGER, D.ADMIN, email="dadm@example.com"),
    }
    x["inactive"].active = False
    db.commit()
    return x


def _sent(db, people, protocol="6300001"):
    it = make_item(db, people, protocol=protocol)
    apply(db, it, people["op"], D.QC_OPERATOR, "send",
          {"version": it.version, "verdict": D.NEGATIVE, "qc_comment": "ფოტო აკლია (ტესტი)"})
    db.commit()
    return it


def _set_managers(db, it, primary, *others):
    """პირდაპირ ბაზაში — ძველი / იმპორტირებული არასწორი მიკუთვნების იმიტაცია."""
    it.field_manager_id = primary.id if primary else None
    for p in list(it.managers):
        it.people.remove(p)
    for n, m in enumerate(([primary] if primary else []) + list(others)):
        it.people.append(ItemPerson(kind=D.P_MANAGER, user_id=m.id, position=n, is_primary=n == 0))
    db.commit()
    db.refresh(it)


# ── წესი ერთ ადგილას ─────────────────────────────────────────────────────
def test_is_field_manager(db, people, u):
    assert is_field_manager(people["mgr"]) and is_field_manager(u["dual"]) and is_field_manager(u["dual_admin"])
    for k in ("qc_only", "qcm_only", "no_role", "inactive"):
        assert not is_field_manager(u[k]), k
    assert not is_field_manager(None)


# ── 1. assign_manager — სერვერული ვალიდაცია ─────────────────────────────
@pytest.mark.parametrize("bad", ["qc_only", "qcm_only", "no_role", "inactive"])
def test_assign_manager_rejects(db, people, u, bad):
    it = _sent(db, people)
    before = it.field_manager_id
    with pytest.raises(WorkflowError, match="აირჩიეთ საველე მენეჯერი"):
        apply(db, it, people["qcm"], D.QC_MANAGER, "assign_manager",
              {"version": it.version, "manager_id": str(u[bad].id)})
    db.rollback()
    db.refresh(it)
    assert it.field_manager_id == before
    assert all(p.user_id != u[bad].id for p in it.managers)


@pytest.mark.parametrize("good", ["mgr2", "dual", "dual_admin"])
def test_assign_manager_accepts(db, people, u, good):
    who = people.get(good) or u[good]
    it = _sent(db, people)
    apply(db, it, people["qcm"], D.QC_MANAGER, "assign_manager",
          {"version": it.version, "manager_id": str(who.id)})
    db.commit()
    db.refresh(it)
    assert it.field_manager_id == who.id


def test_assign_manager_http_rejects_qc_user(db, people, u):
    it = _sent(db, people)
    c = _client(people["qcm"], D.QC_MANAGER)
    r = c.post(f"/items/{it.id}/action", headers=ORIGIN, follow_redirects=False,
               data={"action": "assign_manager", "version": it.version, "manager_id": str(u["qc_only"].id)})
    q = _query(r)
    assert "აირჩიეთ საველე მენეჯერი" in q.get("err", [""])[0]
    db.expire_all()
    assert db.get(QcItem, it.id).field_manager_id == people["mgr"].id


# ── 2. recipients() / queue() ─────────────────────────────────────────────
def test_recipients_filters_cc(db, people, u):
    it = _sent(db, people)
    _set_managers(db, it, people["mgr"], u["qc_only"], u["inactive"], people["mgr2"], u["dual"])
    to, cc = notify.recipients(db, it)
    assert to.id == people["mgr"].id
    assert [x.id for x in cc] == [people["mgr2"].id, u["dual"].id]


def test_recipients_invalid_primary_falls_back_to_first_valid_cc(db, people, u):
    it = _sent(db, people)
    _set_managers(db, it, u["qc_only"], u["no_role"], people["mgr2"], u["dual"])
    to, cc = notify.recipients(db, it)
    assert to.id == people["mgr2"].id and [x.id for x in cc] == [u["dual"].id]


@pytest.mark.parametrize("bad", ["qc_only", "no_role", "inactive"])
def test_recipients_none_valid(db, people, u, bad):
    it = _sent(db, people)
    _set_managers(db, it, u[bad], u["qcm_only"])
    assert notify.recipients(db, it) == (None, [])


def test_recipients_dual_role_is_allowed_to(db, people, u):
    it = _sent(db, people)
    _set_managers(db, it, u["dual"])
    to, _ = notify.recipients(db, it)
    assert to.id == u["dual"].id
    ev = db.query(QcEvent).filter_by(item_id=it.id).first()
    msg = notify.queue(db, it, ev, people["op"], "sent", base_url="http://x/")
    assert msg is not None and msg.to_user_id == u["dual"].id


def test_queue_guard_even_if_recipients_bypassed(db, people, u, monkeypatch, caplog):
    it = _sent(db, people)
    ev = db.query(QcEvent).filter_by(item_id=it.id).first()
    monkeypatch.setattr(notify, "recipients", lambda db, item: (u["qc_only"], [people["mgr2"]]))
    with caplog.at_level(logging.WARNING, logger=notify.__name__):
        assert notify.queue(db, it, ev, people["op"], "sent", base_url="http://x/") is None
    db.commit()
    assert db.query(EmailMessage).count() == 0
    assert str(it.id) in caplog.text and "Zura" not in caplog.text and "Qc-Only" not in caplog.text


def test_queue_guard_drops_invalid_cc(db, people, u, monkeypatch):
    it = _sent(db, people)
    ev = db.query(QcEvent).filter_by(item_id=it.id).first()
    monkeypatch.setattr(notify, "recipients", lambda db, item: (people["mgr"], [u["qc_only"], people["mgr2"]]))
    msg = notify.queue(db, it, ev, people["op"], "sent", base_url="http://x/")
    assert msg.to_user_id == people["mgr"].id and msg.cc == ["mgr2@example.com"]


# ── HTTP: მოქმედება სრულდება, წერილი არა, შეტყობინება ჩანს ──────────────
def _client(user, role):
    c = TestClient(app)
    r = c.post("/login/demo", data={"user_id": str(user.id), "role": role}, headers=ORIGIN,
               follow_redirects=False)
    assert r.status_code == 303 and "err=" not in r.headers["location"]
    return c


def _query(r):
    assert r.status_code == 303
    return parse_qs(urlparse(r.headers["location"]).query)


@pytest.mark.parametrize("action,extra", [
    ("comment", {"comment": "გთხოვთ გაასწოროთ"}),
    ("edit", {"qc_comment": "დაზუსტებული შენიშვნა"}),        # NOTIFY_ACTIONS-ში არ არის — შეტყობინება არა
])
def test_http_no_valid_recipient(db, people, u, action, extra):
    it = _sent(db, people)
    _set_managers(db, it, u["qc_only"], u["inactive"])
    c = _client(people["op"], D.QC_OPERATOR)
    form = {"action": action, "notify": "on", **extra}
    if action == "comment":
        form["once"] = c.get(f"/items/{it.id}").context["once"]
    else:
        form["version"] = it.version
    q = _query(c.post(f"/items/{it.id}/action", headers=ORIGIN, follow_redirects=False, data=form))
    assert "err" not in q
    ok = q["ok"][0]
    assert (NOTICE in ok) == (action == "comment")
    db.expire_all()
    assert db.query(EmailMessage).filter_by(item_id=it.id).count() == 0
    done = "comment" if action == "comment" else "edited"
    assert db.query(QcEvent).filter_by(item_id=it.id, action=done).count() == 1   # მოქმედება შესრულდა


def test_http_valid_recipient_still_gets_email(db, people, u):
    it = _sent(db, people)
    _set_managers(db, it, u["dual"])
    c = _client(people["op"], D.QC_OPERATOR)
    once = c.get(f"/items/{it.id}").context["once"]
    q = _query(c.post(f"/items/{it.id}/action", headers=ORIGIN, follow_redirects=False,
                      data={"action": "comment", "comment": "x", "notify": "on", "once": once}))
    assert NOTICE not in q["ok"][0] and "✉" in q["ok"][0]
    db.expire_all()
    assert db.query(EmailMessage).filter_by(item_id=it.id, to_user_id=u["dual"].id).count() == 1


# ── 3. check_field_managers.py — მხოლოდ კითხვა, სახელების გარეშე ─────────
def test_check_script_read_only_no_names(db, people, u, capsys):
    bad = _sent(db, people, "6300101")
    _set_managers(db, bad, u["qc_only"], people["mgr2"])
    cc_bad = _sent(db, people, "6300102")
    _set_managers(db, cc_bad, people["mgr"], u["inactive"])
    _sent(db, people, "6300103")                                   # სწორი
    db.close()
    path = Path(DATABASE_URL.split(":///", 1)[1])
    before = os.stat(path).st_mtime_ns
    assert check_field_managers.main([]) == 0
    out = capsys.readouterr().out
    assert os.stat(path).st_mtime_ns == before
    first, second = out.split("მიკუთვნებული")[0], out.split("მიკუთვნებული")[1]
    assert "6300101" in first and "6300102" not in first and ": 1" in first
    assert "6300101" in second and "6300102" in second and "6300103" not in out
    names = [x.full_name for x in (*people.values(), *u.values())]
    assert not [n for n in names if n in out]

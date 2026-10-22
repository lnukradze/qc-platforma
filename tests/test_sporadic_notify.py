# -*- coding: utf-8 -*-
"""სპორადულის სია, მეილის შეტყობინება და Google-ით შესვლა."""
import base64
import datetime as dt
import json
import time

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app import domain as D
from app.models import EmailMessage, QcItem, Team, TeamMember
from app.services import notify, sporadic
from app.workflow import apply
from conftest import make_item


def _xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["FLD_PAPER_ID", "CADCODE", "SURVEY_DAY", "CALL_STATUS", "ST_NAME", "TR_NAME",
               "USER_REAL_NAME", "APPLICS"])
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_sporadic_file_and_filters(db, people, tmp_path, monkeypatch):
    t = Team(name="t", kind="field", manager_id=people["mgr"].id, active=True)
    db.add(t)
    db.flush()
    db.add(TeamMember(team_id=t.id, user_id=people["sv"].id))
    db.commit()
    today = dt.date(2026, 10, 21)
    y = dt.datetime(2026, 10, 20)
    f = tmp_path / "s.xlsx"
    _xlsx(f, [
        ["6200001", "202.71.56.11.001.001", y, sporadic.COMPLETED, "დასრულებულია საველე წარმოება", "ადგილზე დათვალიერება", "დამგეგმავი", "🔐 01001010101 - განმცხადებელი 599000000"],
        ["6200002", "202.71.56.11.001.002", y, "შეთანხმება მიღწეულია", "დასრულებულია საველე წარმოება", "ადგილზე დათვალიერება", "დამგეგმავი", ""],
        ["6200003", "202.71.56.11.001.003", dt.datetime(2026, 9, 1), sporadic.COMPLETED, "", "", "", ""],
    ])
    rows = sporadic.read_file(f)
    assert all("APPLICS" not in r and "applics" not in r for r in rows)     # პირადი მონაცემი არ შემოდის
    monkeypatch.setattr(sporadic.source, "lookup_protocols", lambda ids: {
        "6200001": [{"cadcode": "202.71.56.11.001.001", "oqmi": "სისტემური სერვისი",
                     "moxaz": "ამზომველი F", "status": "", "created": "2026-10-19"}]})
    pv = sporadic.prepare(db, rows, {"operators": {str(people["op"].id): ""}}, today=today)
    assert pv["counts"]["day_ok"] == 2 and pv["counts"]["call_status"] == 1
    assert pv["counts"]["assigned"] == 1
    r = pv["rows"][0]
    assert r["manager_id"] == people["mgr"].id and r["creator"] == "ამზომველი F"
    imp = sporadic.confirm(db, pv["token"], people["qcm"], D.QC_MANAGER)
    it = db.query(QcItem).filter_by(protocol_number="6200001").one()
    assert it.kind == D.SPORADIC and it.operator_id == people["op"].id and imp.item_count == 1
    assert it.sporadic_meta["survey_day"] == "2026-10-20"


def test_notify_queues_preview_for_primary_manager(db, people):
    it = make_item(db, people, managers=("mgr", "mgr2"))
    ev = apply(db, it, people["op"], D.QC_OPERATOR, "send", {"verdict": D.NEGATIVE, "qc_comment": "ფოტო აკლია"})
    msg = notify.queue(db, it, ev, people["op"], "comment", base_url="http://x/")
    db.commit()
    assert msg.to_user_id == people["mgr"].id and msg.cc == ["mgr2@example.com"]
    assert msg.status == "preview" and it.protocol_number in msg.html and "ფოტო აკლია" in msg.text
    assert db.query(EmailMessage).count() == 1


def _jwt(claims):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"


@pytest.mark.parametrize("email,ok", [("mgr@example.com", True), ("nobody@example.com", False)])
def test_google_login_only_for_registered_email(db, people, monkeypatch, email, ok):
    from app.main import app
    from app.routes import google_auth as G
    monkeypatch.setattr(G, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(G, "GOOGLE_CLIENT_SECRET", "secret")
    c = TestClient(app)
    r = c.get("/auth/google", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith(G.AUTH_URL)
    state = dict(x.split("=", 1) for x in r.headers["location"].split("?", 1)[1].split("&"))["state"]
    saved = G._signer.loads(r.cookies.get(G.OIDC_COOKIE) or c.cookies.get(G.OIDC_COOKIE))

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id_token": _jwt({"iss": "https://accounts.google.com", "aud": "cid",
                                      "exp": time.time() + 60, "nonce": saved["n"],
                                      "email": email, "email_verified": True})}
    monkeypatch.setattr(G.requests, "post", lambda *a, **k: Resp())
    r = c.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    if ok:
        assert r.headers["location"] == "/" and c.get("/api/me").json()["id"] == people["mgr"].id
    else:
        assert r.headers["location"].endswith("err=not_registered")

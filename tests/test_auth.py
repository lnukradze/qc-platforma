# -*- coding: utf-8 -*-
"""შესვლა — LAN-ზე ჩვენებისას დემო შესვლა მხოლოდ PIN-ით."""
from fastapi.testclient import TestClient

from app.main import app
from app.routes import auth

ORIGIN = {"origin": "http://testserver"}


def test_demo_login_requires_pin_when_set(db, people, monkeypatch):
    monkeypatch.setattr(auth, "DEMO_PIN", "4821")
    c = TestClient(app)
    page = c.get("/login").text
    assert "დემო კოდი" in page and "ოპერატორი ერთი" not in page      # სია PIN-მდე არ ჩანს

    form = {"user_id": str(people["op"].id), "role": "qc_operator", "next": "/"}
    r = c.post("/login/demo", data=form, headers=ORIGIN, follow_redirects=False)
    assert r.headers["location"].endswith("err=pin")

    r = c.post("/login/pin", data={"pin": "0000"}, headers=ORIGIN, follow_redirects=False)
    assert r.headers["location"].endswith("err=pin")

    r = c.post("/login/pin", data={"pin": "4821"}, headers=ORIGIN, follow_redirects=False)
    assert auth.PIN_COOKIE in r.cookies
    assert "ოპერატორი ერთი" in c.get("/login").text

    r = c.post("/login/demo", data=form, headers=ORIGIN, follow_redirects=False)
    assert r.status_code == 303 and "err" not in r.headers["location"]
    assert c.get("/api/me").json()["role"] == "qc_operator"


def test_demo_login_without_pin_unchanged(db, people):
    c = TestClient(app)
    assert "ოპერატორი ერთი" in c.get("/login").text
    r = c.post("/login/demo", data={"user_id": str(people["sv"].id), "role": "surveyor"},
               headers=ORIGIN, follow_redirects=False)
    assert r.status_code == 303 and "err" not in r.headers["location"]


def test_cross_site_post_is_rejected(db, people):
    c = TestClient(app)
    r = c.post("/login/demo", data={"user_id": str(people["op"].id)},
               headers={"origin": "http://evil.example"}, follow_redirects=False)
    assert r.status_code == 403

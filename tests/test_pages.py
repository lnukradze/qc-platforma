# -*- coding: utf-8 -*-
"""გვერდები იხსნება ყველა როლით (შაბლონის შეცდომების დასაჭერად) და უფლებები სწორია."""
import pytest
from fastapi.testclient import TestClient

from app import domain as D
from app.main import app
from app.workflow import apply
from conftest import make_item

ORIGIN = {"origin": "http://testserver"}


def login(c, user, role):
    r = c.post("/login/demo", data={"user_id": str(user.id), "role": role}, headers=ORIGIN,
               follow_redirects=False)
    assert r.status_code == 303


@pytest.fixture()
def world(db, people):
    a = make_item(db, people, protocol="6100001")
    b = make_item(db, people, protocol="6100002", cad="202.51.12.40.001.002", managers=("mgr", "mgr2"))
    apply(db, b, people["op"], D.QC_OPERATOR, "send", {"version": b.version, "verdict": D.NEGATIVE, "qc_comment": "ფოტო აკლია"})
    apply(db, b, people["sv"], D.SURVEYOR, "field_respond", {"version": b.version, "response": D.R_DISAGREE, "comment": "x"})
    apply(db, b, people["mgr"], D.FIELD_MANAGER, "manager_approve", {"version": b.version})
    db.commit()
    return {"a": a, "b": b}


PAGES = {
    D.QC_OPERATOR: ("op", ["/", "/qc", "/qc?tab=returned", "/qc?tab=sent", "/qc?tab=closed", "/stats",
                           "/api/stats", "/items/{a}?queue=1", "/items/{b}"]),
    D.QC_MANAGER: ("qcm", ["/", "/qc", "/qc/disagreements", "/qc/requests", "/items/{b}", "/distribution",
                           "/distribution/sporadic", "/stats", "/api/stats", "/checked"]),
    D.FIELD_MANAGER: ("mgr", ["/", "/field", "/field?tab=manager", "/items/{b}", "/stats", "/preqc"]),
    D.SURVEYOR: ("sv", ["/", "/field", "/items/{b}", "/stats", "/preqc"]),
    D.COORDINATOR: ("coord", ["/", "/checked", "/items/{b}", "/stats", "/api/stats"]),
    D.HEAD_OF_SERVICE: ("head", ["/", "/stats", "/api/stats"]),
    D.ADMIN: ("admin", ["/", "/qc", "/items/{a}", "/items/{b}", "/admin", "/admin/settings",
                        "/admin/emails", "/admin/teams", "/about"]),
}
FORBIDDEN = {
    D.QC_OPERATOR: ["/preqc", "/field", "/distribution", "/qc/disagreements"],
    D.QC_MANAGER: ["/preqc"],
    D.ADMIN: ["/preqc"],
    D.COORDINATOR: ["/preqc", "/qc", "/distribution"],
    D.HEAD_OF_SERVICE: ["/preqc", "/qc", "/checked", "/items/{b}"],
    D.SURVEYOR: ["/qc", "/items/{a}"],
}


@pytest.mark.parametrize("role", list(PAGES))
def test_pages_open(db, people, world, role):
    who, pages = PAGES[role]
    c = TestClient(app)
    login(c, people[who], role)
    for url in pages:
        u = url.format(a=world["a"].id, b=world["b"].id)
        r = c.get(u)
        assert r.status_code == 200, (role, u, r.status_code, r.text[:300])
    for url in FORBIDDEN.get(role, []):
        u = url.format(a=world["a"].id, b=world["b"].id)
        assert c.get(u).status_code in (403, 404), (role, u)


def test_head_of_service_stats_without_operator_sections(db, people, world):
    c = TestClient(app)
    login(c, people["head"], D.HEAD_OF_SERVICE)
    d = c.get("/api/stats").json()
    assert "operators" not in d and "restricted" not in d and "managers" in d


def test_secondary_manager_sees_cc_but_cannot_confirm(db, people, world):
    c = TestClient(app)
    login(c, people["mgr2"], D.FIELD_MANAGER)
    page = c.get(f"/items/{world['b'].id}").text
    assert "CC-ში" in page and "„არ ვეთანხმები“ — დადასტურება" not in page

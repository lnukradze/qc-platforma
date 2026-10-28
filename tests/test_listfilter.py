# -*- coding: utf-8 -*-
"""
T-011 — ერთიანი ფილტრი ოთხივე სიაში (`/qc`, `/field`, `/qc/disagreements`, `/checked`) და
`GET /api/filters/surveyors`. მონაცემი გამოგონილია; შაბლონის context — `render`-ის გავლით.
"""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app import domain as D
from app.main import app
from app.models import QcItem, Team, TeamMember
from conftest import make_item

ORIGIN = {"origin": "http://testserver"}
FLT_KEYS = {"values", "managers", "surveyors", "operators", "show_operator", "show_status", "limited",
            "per", "empty_range"}
VALUE_KEYS = {"protocol", "cad", "date_from", "date_to", "zone", "sector", "manager", "surveyor",
              "operator", "verdict", "response", "kind"}
LISTS = ("/qc?tab=sent", "/qc/disagreements", "/checked")      # QC მენეჯრით; /field — საველე მენეჯრით
SENT = dt.datetime(2026, 1, 5, 9, 0)


@pytest.fixture()
def seen(monkeypatch):
    from app.routes import common
    out = {}
    orig = common.templates.TemplateResponse

    def spy(request, name, context, status_code=200):
        out.clear()
        out.update(context)
        return orig(request, name, context, status_code=status_code)
    monkeypatch.setattr(common.templates, "TemplateResponse", spy)
    return out


def login(user, role):
    c = TestClient(app)
    r = c.post("/login/demo", data={"user_id": str(user.id), "role": role}, headers=ORIGIN,
               follow_redirects=False)
    assert r.status_code == 303 and "err=" not in r.headers["location"]
    return c


def mk(db, people, protocol, drawing=dt.datetime(2026, 1, 1, 10, 0), zone="51", sector=None,
       state=D.AWAITING_QCM, verdict=D.NEGATIVE, kind=D.SYSTEMATIC, **kw):
    i = make_item(db, people, protocol=protocol, cad=f"202.{zone}.12.40.001.{protocol[-3:]}", **kw)
    i.zone, i.sector, i.drawing_date, i.kind = zone, sector or f"{zone}.12", drawing, kind
    i.state, i.verdict = state, verdict
    i.first_sent_at = i.sent_at = SENT
    if state == D.CLOSED:
        i.close_reason = D.CR_CORRECTED
    db.commit()
    return i


def ctx_of(c, seen, url, **headers):
    r = c.get(url, headers=headers)
    assert r.status_code == 200, (url, r.status_code)
    return dict(seen)


def protocols(c, seen, url):
    return {i.protocol_number for i in ctx_of(c, seen, url)["rows"]}


def sep(url):
    return "&" if "?" in url else "?"


@pytest.fixture()
def qcm(people):
    return login(people["qcm"], D.QC_MANAGER)


# ── 1. თარიღი — ნახაზის შეტანა, „დან“ ჩათვლით, „მდე“ — არა ─────────────
@pytest.fixture()
def dated(db, people):
    mk(db, people, "7100001", drawing=dt.datetime(2026, 1, 1, 10, 0))     # 01.01
    mk(db, people, "7100002", drawing=dt.datetime(2026, 1, 2, 0, 0))      # 02.01 00:00
    mk(db, people, "7100003", drawing=dt.datetime(2025, 12, 31, 23, 59))  # 31.12


@pytest.mark.parametrize("url", LISTS)
def test_date_range_excludes_to(db, people, dated, qcm, seen, url):
    q = sep(url)
    assert protocols(qcm, seen, f"{url}{q}date_from=2026-01-01&date_to=2026-01-02") == {"7100001"}
    assert seen["flt"]["empty_range"] is False
    assert protocols(qcm, seen, f"{url}{q}date_from=2026-01-01") == {"7100001", "7100002"}
    assert protocols(qcm, seen, f"{url}{q}date_to=2026-01-02") == {"7100001", "7100003"}


@pytest.mark.parametrize("url", LISTS)
@pytest.mark.parametrize("rng", ["date_from=2026-01-01&date_to=2026-01-01",
                                 "date_from=2026-01-02&date_to=2026-01-01"])
def test_empty_range(db, people, dated, qcm, seen, url, rng):
    c = ctx_of(qcm, seen, f"{url}{sep(url)}{rng}")
    assert c["rows"] == [] and c["total"] == 0 and c["flt"]["empty_range"] is True


def test_field_date_uses_drawing_date_not_sent(db, people, dated, seen):
    c = login(people["mgr"], D.FIELD_MANAGER)
    # გაგზავნა ყველას 05.01 — ძველი წესით (sent_at) ცარიელი იქნებოდა
    assert protocols(c, seen, "/field?date_from=2026-01-01&date_to=2026-01-02") == {"7100001"}
    assert ctx_of(c, seen, "/field?date_from=2026-01-01&date_to=2026-01-01")["flt"]["empty_range"]


def test_invalid_date_ignored(db, people, dated, qcm, seen):
    c = ctx_of(qcm, seen, "/checked?date_from=01.01.2026&date_to=xx")
    assert len(c["rows"]) == 3 and c["flt"]["values"]["date_from"] == "" and not c["flt"]["empty_range"]


# ── 2. ზონა და სექტორი ─────────────────────────────────────────────────
@pytest.fixture()
def zoned(db, people):
    mk(db, people, "7200050", zone="50", sector="50.39")
    mk(db, people, "7200073", zone="73", sector="73.39")
    mk(db, people, "7200043", zone="43", sector="43.39")
    mk(db, people, "7200005", zone="05", sector="05.01")
    mk(db, people, "7200044", zone="43", sector="43.40")


@pytest.mark.parametrize("url", LISTS)
@pytest.mark.parametrize("zone", ["50, 73", "50,73", "50 73", " 50 ,  73 "])
def test_multi_zone(db, people, zoned, qcm, seen, url, zone):
    assert protocols(qcm, seen, f"{url}{sep(url)}zone={zone}") == {"7200050", "7200073"}
    assert seen["flt"]["values"]["zone"] == "50, 73"


def test_zone_zfill(db, people, zoned, qcm, seen):
    assert protocols(qcm, seen, "/checked?zone=5") == {"7200005"}


@pytest.mark.parametrize("url", LISTS)
def test_sector_needs_zone(db, people, zoned, qcm, seen, url):
    q = sep(url)
    assert len(protocols(qcm, seen, f"{url}{q}sector=39")) == 5                 # ზონის გარეშე — იგნორდება
    assert seen["flt"]["values"]["sector"] == ""
    assert len(protocols(qcm, seen, f"{url}{q}sector=43.39")) == 5              # სრული ფორმითაც
    assert protocols(qcm, seen, f"{url}{q}zone=43&sector=39") == {"7200043"}
    assert protocols(qcm, seen, f"{url}{q}zone=43&sector=43.39") == {"7200043"}
    assert protocols(qcm, seen, f"{url}{q}zone=43&sector=39, 40") == {"7200043", "7200044"}
    assert protocols(qcm, seen, f"{url}{q}zone=50, 73&sector=39") == {"7200050", "7200073"}


# ── 3. ოპერატორი — ველის როლზე იგნორდება ───────────────────────────────
@pytest.fixture()
def two_ops(db, people):
    mk(db, people, "7300001")
    i = mk(db, people, "7300002")
    i.operator_id = people["op2"].id
    db.commit()


@pytest.mark.parametrize("who,role", [("sv", D.SURVEYOR), ("mgr", D.FIELD_MANAGER)])
def test_operator_ignored_for_field(db, people, two_ops, seen, who, role):
    c = login(people[who], role)
    ctx = ctx_of(c, seen, f"/field?operator={people['op2'].id}")
    assert {i.protocol_number for i in ctx["rows"]} == {"7300001", "7300002"}
    f = ctx["flt"]
    assert f["operators"] == [] and f["show_operator"] is False and f["values"]["operator"] == ""


@pytest.mark.parametrize("url", LISTS)
def test_operator_filters_for_qc(db, people, two_ops, qcm, seen, url):
    assert protocols(qcm, seen, f"{url}{sep(url)}operator={people['op2'].id}") == {"7300002"}
    f = seen["flt"]
    assert f["show_operator"] is True
    assert {n for _, n in f["operators"]} == {people["op"].full_name, people["op2"].full_name}


# ── 4. ოთხივე სია — ერთნაირი შედეგი ────────────────────────────────────
def test_same_params_same_result_in_all_lists(db, people, seen):
    mk(db, people, "7400001", zone="50", sector="50.39", drawing=dt.datetime(2026, 1, 1, 8))
    mk(db, people, "7400002", zone="73", sector="73.39", drawing=dt.datetime(2026, 1, 1, 9))
    mk(db, people, "7400003", zone="73", sector="73.40", drawing=dt.datetime(2026, 1, 1, 9))
    mk(db, people, "7400004", zone="50", sector="50.39", drawing=dt.datetime(2026, 1, 3, 9))
    mk(db, people, "7400005", zone="61", sector="61.39", drawing=dt.datetime(2026, 1, 1, 9))
    params = (f"zone=50, 73&sector=39&date_from=2026-01-01&date_to=2026-01-02"
              f"&manager={people['mgr'].id}&surveyor=ამზომველი&verdict={D.NEGATIVE}&kind={D.SYSTEMATIC}")
    want = {"7400001", "7400002"}
    qcm = login(people["qcm"], D.QC_MANAGER)
    for url in LISTS:
        assert protocols(qcm, seen, f"{url}{sep(url)}{params}") == want, url
    fm = login(people["mgr"], D.FIELD_MANAGER)
    assert protocols(fm, seen, f"/field?{params}") == want
    coord = login(people["coord"], D.COORDINATOR)
    assert protocols(coord, seen, f"/checked?{params}") == want


# ── 5. გვერდის ზომა ────────────────────────────────────────────────────
@pytest.mark.parametrize("per,want", [("5", 10), ("99", 30), (None, 10), ("abc", 10), ("20", 20)])
@pytest.mark.parametrize("url", LISTS + ("/field",))
def test_page_size(db, people, seen, per, want, url):
    for n in range(35):
        mk(db, people, f"75{n:05d}")
    c = login(people["mgr"], D.FIELD_MANAGER) if url == "/field" else login(people["qcm"], D.QC_MANAGER)
    ctx = ctx_of(c, seen, url + (f"{sep(url)}per={per}" if per else ""))
    assert ctx["flt"]["per"] == want and len(ctx["rows"]) == want and ctx["total"] == 35
    assert ctx["pages"] == -(-35 // want)
    if per:
        assert f"per={per}" in ctx["qs"](page=2)                 # pager-ის ბმული ზომას ინარჩუნებს


# ── 6. ამზომველების API ─────────────────────────────────────────────────
@pytest.fixture()
def teams(db, people):
    t1 = Team(name="გუნდი 1", manager_id=people["mgr"].id)
    t1.members = [TeamMember(user_id=people["sv"].id),
                  TeamMember(user_id=people["sv2"].id, valid_to=dt.date(2026, 1, 1))]  # წასული
    t2 = Team(name="გუნდი 2", manager_id=people["mgr2"].id)
    t2.members = [TeamMember(user_id=people["other"].id)]
    db.add_all([t1, t2])
    db.commit()


def api(c, manager):
    r = c.get(f"/api/filters/surveyors?manager={manager}")
    assert r.status_code == 200
    return r.json()


def test_api_surveyors_access(db, people, teams):
    own = [{"id": people["sv"].id, "name": people["sv"].full_name}]
    other = [{"id": people["other"].id, "name": people["other"].full_name}]
    fm = login(people["mgr"], D.FIELD_MANAGER)
    assert api(fm, people["mgr"].id) == own
    assert api(fm, people["mgr2"].id) == []                      # სხვისი გუნდი
    for who, role in [("qcm", D.QC_MANAGER), ("op", D.QC_OPERATOR), ("admin", D.ADMIN),
                      ("coord", D.COORDINATOR)]:
        c = login(people[who], role)
        assert api(c, people["mgr2"].id) == other, role
        assert api(c, people["mgr"].id) == own, role
    for who, role in [("sv", D.SURVEYOR), ("head", D.HEAD_OF_SERVICE)]:
        assert api(login(people[who], role), people["mgr"].id) == [], role
    qcm = login(people["qcm"], D.QC_MANAGER)
    assert api(qcm, "abc") == [] and api(qcm, "") == [] and api(qcm, "999999") == []


def test_api_surveyors_needs_login(db, people, teams):
    r = TestClient(app).get(f"/api/filters/surveyors?manager={people['mgr'].id}", follow_redirects=False)
    assert r.status_code in (303, 401, 403)


# ── 7. მენეჯერი / ამზომველი — id, ტექსტი, გუნდით შევიწროება, დუბლიკატი არა ──
def test_manager_narrows_surveyors(db, people, teams, qcm, seen):
    mk(db, people, "7700001")                                    # ამზომველები: sv, sv2
    mk(db, people, "7700002", managers=("mgr2",), surveyors=("other",))
    f = ctx_of(qcm, seen, "/checked")["flt"]
    assert {i for i, _ in f["surveyors"]} == {people["sv"].id, people["sv2"].id, people["other"].id}
    assert {i for i, _ in f["managers"]} == {people["mgr"].id, people["mgr2"].id}
    f = ctx_of(qcm, seen, f"/checked?manager={people['mgr'].id}")["flt"]
    assert f["surveyors"] == [(people["sv"].id, people["sv"].full_name)]      # sv2 — გუნდიდან წასული
    f = ctx_of(qcm, seen, f"/checked?manager={people['mgr2'].id}")["flt"]
    assert f["surveyors"] == [(people["other"].id, people["other"].full_name)]


def test_manager_and_surveyor_by_id_and_text(db, people, qcm, seen):
    mk(db, people, "7710001")
    mk(db, people, "7710002", managers=("mgr2", "mgr"), surveyors=("other", "sv2"))   # mgr — CC
    mk(db, people, "7710003", managers=("mgr2",), surveyors=("other",))
    assert protocols(qcm, seen, f"/checked?manager={people['mgr'].id}") == {"7710001", "7710002"}
    assert protocols(qcm, seen, "/checked?manager=სხვა მენეჯ") == {"7710002", "7710003"}
    assert protocols(qcm, seen, f"/checked?surveyor={people['sv2'].id}") == {"7710001", "7710002"}
    assert protocols(qcm, seen, "/checked?surveyor=ამზომველი G") == {"7710001", "7710002"}


def test_people_filters_no_duplicates(db, people, qcm, seen):
    mk(db, people, "7720001", managers=("mgr", "mgr2"), surveyors=("sv", "sv2", "other"))
    for q in ("surveyor=ამზომველი", "manager=მენეჯერი", f"manager={people['mgr'].id}"):
        c = ctx_of(qcm, seen, f"/checked?{q}")
        assert c["total"] == 1 and len(c["rows"]) == 1, q


# ── 8. QC „გასავლელი“: სტატუსი იგნორდება; ოპერატორს — მხოლოდ ოქმის# / კოდი ──
def test_qc_todo_ignores_verdict(db, people, qcm, seen):
    mk(db, people, "7800001", state=D.PENDING, verdict=None)
    c = ctx_of(qcm, seen, f"/qc?tab=todo&verdict={D.NEGATIVE}")
    assert [i.protocol_number for i in c["rows"]] == ["7800001"]
    assert c["flt"]["show_status"] is False and c["flt"]["values"]["verdict"] == ""
    assert c["flt"]["limited"] is False
    assert ctx_of(qcm, seen, "/qc?tab=sent")["flt"]["show_status"] is True


def test_operator_todo_limited(db, people, seen):
    mk(db, people, "7810001", state=D.PENDING, verdict=None, zone="50")
    mk(db, people, "7810002", state=D.PENDING, verdict=None, zone="73")
    op = login(people["op"], D.QC_OPERATOR)
    c = ctx_of(op, seen, f"/qc?tab=todo&zone=50&manager={people['mgr'].id}&date_from=2026-01-01"
                         "&date_to=2026-01-01")
    assert {i.protocol_number for i in c["rows"]} == {"7810001", "7810002"}   # ზონა / თარიღი — იგნორდება
    f = c["flt"]
    assert f["limited"] is True and f["show_status"] is False and not f["empty_range"]
    assert f["managers"] == f["surveyors"] == f["operators"] == []
    assert f["values"]["zone"] == f["values"]["manager"] == f["values"]["date_from"] == ""
    assert protocols(op, seen, "/qc?tab=todo&protocol=7810002") == {"7810002"}
    assert protocols(op, seen, "/qc?tab=todo&cad=202.73") == {"7810002"}
    assert ctx_of(op, seen, "/qc?tab=sent")["flt"]["limited"] is False


# ── 9. ველი: საბოლოოდ დადასტურებული — მხოლოდ ფილტრით / ძებნით ───────────
def test_field_closed_only_with_filter(db, people, seen):
    mk(db, people, "7900001")
    mk(db, people, "7900002", state=D.CLOSED)
    c = login(people["sv"], D.SURVEYOR)
    assert protocols(c, seen, "/field") == {"7900001"}
    assert protocols(c, seen, "/field?page=1&per=20&zone=51&kind=systematic") == {"7900001"}
    assert protocols(c, seen, "/field?state=open") == {"7900001"}
    assert protocols(c, seen, f"/field?state={D.CLOSED}") == {"7900002"}
    assert protocols(c, seen, "/field?protocol=79000") == {"7900001", "7900002"}
    assert protocols(c, seen, "/field?cad=202.51") == {"7900001", "7900002"}
    assert protocols(c, seen, f"/field?verdict={D.NEGATIVE}") == {"7900001", "7900002"}
    assert protocols(c, seen, "/field?date_from=2026-01-01") == {"7900001", "7900002"}


# ── 10. scope: ფილტრი სხვის ოქმს არ აჩენს ──────────────────────────────
def test_filters_do_not_bypass_scope(db, people, seen):
    mk(db, people, "7950001")                                                   # mgr / sv
    mk(db, people, "7950002", managers=("mgr2",), surveyors=("other",))        # mgr2 / other
    fm = login(people["mgr"], D.FIELD_MANAGER)
    assert protocols(fm, seen, f"/field?manager={people['mgr2'].id}") == set()
    assert protocols(fm, seen, f"/field?surveyor={people['other'].id}") == set()
    assert protocols(fm, seen, "/field?protocol=7950002") == set()
    f = seen["flt"]
    assert {i for i, _ in f["managers"]} == {people["mgr"].id}
    assert people["other"].id not in {i for i, _ in f["surveyors"]}
    sv = login(people["other"], D.SURVEYOR)
    assert protocols(sv, seen, "/field?surveyor=ამზომველი F") == set()
    op2 = login(people["op2"], D.QC_OPERATOR)
    assert protocols(op2, seen, f"/qc?tab=sent&operator={people['op'].id}") == set()


def test_sql_injection_like_input_is_data(db, people, qcm, seen):
    mk(db, people, "7960001")
    for q in ("protocol=' OR 1=1 --", "zone=50') OR ('1'='1", "manager=%' OR '1'='1", "sector=1;DROP"):
        assert protocols(qcm, seen, f"/checked?{q}&zone=50" if "zone" not in q else f"/checked?{q}") == set(), q
    assert protocols(qcm, seen, "/checked") == {"7960001"}


# ── 11. კონტრაქტი: გასაღებები, ტიპები, HTMX ─────────────────────────────
@pytest.mark.parametrize("who,role,url", [("qcm", D.QC_MANAGER, "/qc"), ("qcm", D.QC_MANAGER, "/qc?tab=sent"),
                                          ("qcm", D.QC_MANAGER, "/qc/disagreements"),
                                          ("coord", D.COORDINATOR, "/checked"),
                                          ("mgr", D.FIELD_MANAGER, "/field"), ("sv", D.SURVEYOR, "/field"),
                                          ("op", D.QC_OPERATOR, "/qc")])
def test_flt_contract(db, people, seen, who, role, url):
    mk(db, people, "7970001")
    c = login(people[who], role)
    for headers in ({}, {"hx-request": "true"}):
        f = ctx_of(c, seen, url, **headers)["flt"]
        assert isinstance(f, dict) and set(f) == FLT_KEYS
        assert set(f["values"]) == VALUE_KEYS and all(isinstance(v, str) for v in f["values"].values())
        for k in ("managers", "surveyors", "operators"):
            assert isinstance(f[k], list) and all(isinstance(x, tuple) and len(x) == 2 for x in f[k])
        for k in ("show_operator", "show_status", "limited", "empty_range"):
            assert isinstance(f[k], bool)
        assert isinstance(f["per"], int) and D.PAGE_SIZE_MIN <= f["per"] <= D.PAGE_SIZE_MAX
        assert f["show_operator"] is (role not in D.FIELD_ROLES)
        if role in D.FIELD_ROLES:
            assert f["operators"] == []


def test_field_page_has_no_operator_names(db, people):
    mk(db, people, "7980001")
    for who, role in [("sv", D.SURVEYOR), ("mgr", D.FIELD_MANAGER)]:
        html = login(people[who], role).get(f"/field?operator={people['op'].id}").text
        assert people["op"].full_name not in html and people["op2"].full_name not in html

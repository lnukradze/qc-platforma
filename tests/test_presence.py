# -*- coding: utf-8 -*-
"""
Presence (`/api/presence/{id}`, `/leave`) — ერთდროული ping / leave 500-ს არ იძლევა.

ადრე: ORM-ის read-modify-write. საკუთარი ძველი (>10 წთ) ჩანაწერი იმავე მოთხოვნის წმენდამ წაშალა,
ან პარალელურმა leave-მა → UPDATE 0 მწკრივი → StaleDataError; ორი ჩანართის პირველი ping → ორი INSERT →
IntegrityError. ახლა — ერთი ატომური upsert. ორი thread, ორი HTTP სესია, ფაილური SQLite; მონაცემი გამოგონილია.
"""
import datetime as dt
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import domain as D
from app.db import SessionLocal
from app.main import app
from app.models import Presence
from conftest import make_item

ORIGIN = {"origin": "http://testserver"}
ROUNDS = 20
TIMEOUT = 30


def client(user, role):
    c = TestClient(app, raise_server_exceptions=False)          # 500 — შედეგად, არა exception-ად
    r = c.post("/login/demo", data={"user_id": str(user.id), "role": role}, headers=ORIGIN,
               follow_redirects=False)
    assert r.status_code == 303 and "err=" not in r.headers["location"]
    return c


def rows(item_id):
    s = SessionLocal()
    try:
        return [(p.user_id, p.role, p.last_seen) for p in s.query(Presence).filter_by(item_id=item_id)]
    finally:
        s.close()


def put(item_id, user, role, minutes_ago):
    s = SessionLocal()
    try:
        s.query(Presence).filter_by(item_id=item_id, user_id=user.id).delete()
        s.add(Presence(item_id=item_id, user_id=user.id, role=role,
                       last_seen=dt.datetime.now() - dt.timedelta(minutes=minutes_ago)))
        s.commit()
    finally:
        s.close()


def clear():
    s = SessionLocal()
    try:
        s.query(Presence).delete()
        s.commit()
    finally:
        s.close()


def together(*calls):
    """ერთდროულად — barrier HTTP-მდე; ჩაწერას არაფერი ასერიალებს, გარდა ბაზისა."""
    b = threading.Barrier(len(calls), timeout=TIMEOUT)

    def run(f):
        b.wait()
        return f()
    with ThreadPoolExecutor(len(calls)) as ex:
        return [x.result(timeout=TIMEOUT) for x in [ex.submit(run, f) for f in calls]]


@pytest.fixture()
def it(db, people):
    return make_item(db, people)


def ping(c, item_id):
    return c.post(f"/api/presence/{item_id}", headers=ORIGIN)


def leave(c, item_id):
    return c.post(f"/api/presence/{item_id}/leave", headers=ORIGIN)


# ── 1. საკუთარი ძველი ჩანაწერი — კონკურენციის გარეშეც ─────────────────
def test_own_stale_row_ping_ok_and_not_sticky(db, people, it):
    c = client(people["qcm"], D.QC_MANAGER)
    put(it.id, people["qcm"], D.QC_MANAGER, 11)                  # ჩანართი >10 წთ ეძინა
    before = dt.datetime.now()
    codes = [ping(c, it.id).status_code for _ in range(6)]
    assert codes == [200] * 6
    (uid, role, seen), = rows(it.id)
    assert uid == people["qcm"].id and role == D.QC_MANAGER and seen >= before


def test_other_users_stale_rows_cleaned(db, people, it):
    put(it.id, people["op"], D.QC_OPERATOR, 11)
    assert ping(client(people["qcm"], D.QC_MANAGER), it.id).status_code == 200
    assert [u for u, _, _ in rows(it.id)] == [people["qcm"].id]   # ძველი სხვისი — წაიშალა


# ── 2. ორი ჩანართი — ერთდროული პირველი ping ───────────────────────────
def test_parallel_first_pings_one_row(db, people, it):
    c1, c2 = client(people["qcm"], D.QC_MANAGER), client(people["qcm"], D.QC_MANAGER)
    for _ in range(ROUNDS):
        clear()
        codes = [r.status_code for r in together(lambda: ping(c1, it.id), lambda: ping(c2, it.id))]
        assert codes == [200, 200], codes
        assert len(rows(it.id)) == 1


# ── 3. ping ‖ leave — ერთდროულად, ერთი მომხმარებელი ─────────────────────
@pytest.mark.parametrize("minutes_ago", [0, 11])
def test_parallel_ping_and_leave(db, people, it, minutes_ago):
    c1, c2 = client(people["qcm"], D.QC_MANAGER), client(people["qcm"], D.QC_MANAGER)
    for _ in range(ROUNDS):
        put(it.id, people["qcm"], D.QC_MANAGER, minutes_ago)
        codes = [r.status_code for r in together(lambda: ping(c1, it.id), lambda: leave(c2, it.id))]
        assert codes == [200, 200], codes
        left = rows(it.id)
        assert len(left) <= 1                                      # ან წაშლილია, ან ერთი, ახალი
        if left:
            assert left[0][2] >= dt.datetime.now() - dt.timedelta(minutes=1)


def test_parallel_ping_and_other_users_cleanup(db, people, it):
    """ჩემი ჩანაწერი ძველია; სხვა მომხმარებლის ping-ის წმენდა მას ერთდროულად შლის."""
    me, other = client(people["qcm"], D.QC_MANAGER), client(people["op"], D.QC_OPERATOR)
    for _ in range(ROUNDS):
        clear()
        put(it.id, people["qcm"], D.QC_MANAGER, 11)
        codes = [r.status_code for r in together(lambda: ping(me, it.id), lambda: ping(other, it.id))]
        assert codes == [200, 200], codes
        assert sorted(u for u, _, _ in rows(it.id)) == sorted([people["qcm"].id, people["op"].id])


# ── 4. დაკარგული განახლება არა: ძველი დრო ახალს არ გადაწერს ─────────────
def test_upsert_never_moves_last_seen_back(db, people, it):
    future = dt.datetime.now() + dt.timedelta(seconds=30)
    s = SessionLocal()
    s.add(Presence(item_id=it.id, user_id=people["qcm"].id, role=D.QC_MANAGER, last_seen=future))
    s.commit()
    s.close()
    assert ping(client(people["qcm"], D.QC_MANAGER), it.id).status_code == 200
    (_, _, seen), = rows(it.id)
    assert seen == future


# ── 5. კონტრაქტი უცვლელია: პასუხი, ანონიმურობა (T-015), leave ──────────
def test_contract_and_anonymity(db, people, it):
    from app.workflow import apply
    apply(db, it, people["op"], D.QC_OPERATOR, "send",
          {"version": it.version, "verdict": D.NEGATIVE, "qc_comment": "ფოტო აკლია (ტესტი)"})
    db.commit()
    qcm, sv = client(people["qcm"], D.QC_MANAGER), client(people["sv"], D.SURVEYOR)
    assert ping(qcm, it.id).json() == {"others": []}
    d = ping(sv, it.id).json()
    assert d == {"others": [{"name": D.QC_ANON_LABEL}]}            # როლის გარეშე
    d = ping(qcm, it.id).json()
    assert d["others"][0]["name"] == people["sv"].full_name and d["others"][0]["role"]
    assert leave(sv, it.id).json() == {"ok": True}
    assert [u for u, _, _ in rows(it.id)] == [people["qcm"].id]


def test_ping_scope_and_origin_unchanged(db, people, it):
    r = client(people["other"], D.SURVEYOR).post(f"/api/presence/{it.id}", headers=ORIGIN)
    assert r.status_code == 404                                    # გაუგზავნელი / სხვისი ოქმი
    r = client(people["qcm"], D.QC_MANAGER).post(f"/api/presence/{it.id}",
                                                 headers={"origin": "http://evil.example.com"})
    assert r.status_code == 403 and rows(it.id) == []

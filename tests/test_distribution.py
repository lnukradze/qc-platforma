# -*- coding: utf-8 -*-
"""განაწილება — ძველი პრინციპები + პროცენტული დაფარვა + მენეჯერის დადგენა (2026-10-20)."""
import datetime as dt
import random

from app.models import ManagerOverride, Team, TeamMember
from app.services.directory import NOT_FIELD, OK, UNSORTED, FieldDirectory
from app.services.distribution import algo
from app.services.people import name_key


def recs(n_blocks, per_block, zone="51", manager=1, start=1, backlog=False):
    out = []
    for b in range(start, start + n_blocks):
        for p in range(1, per_block + 1):
            out.append({"cadcode": f"202.{zone}.12.40.{b:03d}.{p:03d}", "manager_id": manager,
                        "manager_ids": [manager], "disp_dt": f"2026-10-{1 + b % 20:02d}",
                        "backlog": backlog})
    return out


def test_block_key_and_zone():
    assert algo.block_key("202.69.11.60.030.017") == "202.69.11.60.030"
    assert algo.zone_of("202.43.12.42.095.042") == "43"
    assert algo.sector_of("202.43.12.42.095.042") == "43.12"


def test_block_is_never_split():
    blocks = algo.group_blocks(recs(30, 4) + recs(10, 7, start=100))
    assign, loads = algo.assign_to_operators(blocks, list(blocks), {1: 100, 2: 100, 3: 100},
                                             random.Random(7))
    assert set(assign) == set(blocks)
    assert sum(loads.values()) == sum(g["n"] for g in blocks.values())


def test_operator_numbers_are_proportional():
    blocks = algo.group_blocks(recs(200, 3))
    _, loads = algo.assign_to_operators(blocks, list(blocks), {1: 300, 2: 150, 3: 150},
                                        random.Random(1))
    assert abs(loads[1] - 2 * loads[2]) <= 6
    assert abs(loads[2] - loads[3]) <= 3


def test_coverage_default_and_override_max_wins():
    """ნაგულისხმევი 70%; ზონა 53 — 70%, მენეჯერი 2 — 100% → მენეჯერი 2 თელავშიც 100%."""
    r = recs(100, 2, zone="53", manager=1) + recs(50, 2, zone="53", manager=2, start=500) + \
        recs(40, 2, zone="71", manager=3, start=900)
    blocks = algo.group_blocks(r)
    rules = algo.normalize_rules(70, [{"type": "zone", "key": "53", "pct": 70},
                                      {"type": "manager", "key": "2", "pct": 100}])
    chosen, _ = algo.select_by_coverage(blocks, rules, random.Random(3))
    by_mgr = {}
    for k in chosen:
        by_mgr[blocks[k]["manager_id"]] = by_mgr.get(blocks[k]["manager_id"], 0) + blocks[k]["n"]
    assert by_mgr[2] == 100                      # 100% — ყველა
    assert abs(by_mgr[1] - 140) <= 2             # ~70% 200-დან
    assert abs(by_mgr[3] - 56) <= 2              # ~70% 80-დან


def test_sector_rule_bazaleti():
    r = recs(10, 3, zone="71") + [{"cadcode": f"202.71.56.11.{b:03d}.001", "manager_id": 1,
                                   "manager_ids": [1], "disp_dt": "2026-10-01"} for b in range(20)]
    blocks = algo.group_blocks(r)
    rules = algo.normalize_rules(0, [{"type": "sector", "key": "71.56", "pct": 100}])
    chosen, _ = algo.select_by_coverage(blocks, rules, random.Random(1))
    assert {blocks[k]["sector"] for k in chosen} == {"71.56"} and len(chosen) == 20


def test_capacity_overflow_goes_to_backlog_and_backlog_first():
    blocks = algo.group_blocks(recs(10, 5) + recs(2, 5, start=50, backlog=True))
    for g in blocks.values():
        g["pct"] = 70
    take, rest = algo.fit_capacity(blocks, list(blocks), 30)
    assert sum(blocks[k]["n"] for k in take) == 30 and len(rest) == 6
    assert all(blocks[k]["backlog"] for k in take[:2])     # ნაშთი პირველი შედის


def test_exclude_open_status():
    r = [{"first_status": "აღწერის პროცესი-საველე განცხადება"}, {"first_status": "დასრულებულია საველე წარმოება"}]
    kept, removed = algo.exclude_status(r, ["აღწერის პროცესი-საველე  განცხადება"])
    assert len(kept) == 1 and sum(removed.values()) == 1


# ── ვინ ვისი მენეჯერია ──────────────────────────────────────────────────
def _teams(db, people):
    """mgr: sv (მიმდინარე); mgr2: sv2 (მიმდინარე); other — წასული (ძველი გუნდი, mgr2)."""
    t1 = Team(name="t1", kind="field", manager_id=people["mgr"].id, active=True)
    t2 = Team(name="t2", kind="field", manager_id=people["mgr2"].id, active=True)
    db.add_all([t1, t2])
    db.flush()
    db.add_all([TeamMember(team_id=t1.id, user_id=people["sv"].id),
                TeamMember(team_id=t2.id, user_id=people["sv2"].id),
                TeamMember(team_id=t2.id, user_id=people["other"].id, valid_to=dt.date(2026, 10, 19))])
    db.commit()


def test_directory_rules(db, people):
    _teams(db, people)
    d = FieldDirectory(db)
    res = d.resolve(["ამზომველი F", "ამზომველი G"])            # ორი გუნდი → ორივე მენეჯერი
    assert res.status == OK and [m.id for m in res.managers] == [people["mgr"].id, people["mgr2"].id]
    res = d.resolve(["სხვა ამზომველი", "ამზომველი G"])          # შემდგენი წასულია → მეორის მენეჯერი
    assert res.primary.id == people["mgr2"].id and res.departed == ["სხვა ამზომველი"]
    res = d.resolve(["სხვა ამზომველი"])                         # არავინ 272-ში → დაუჯგუფებელი
    assert res.status == UNSORTED
    res = d.resolve(["რეგისტრატორი ვინმე"])                     # Field Group-ში არ არის
    assert res.status == NOT_FIELD
    res = d.resolve(["ამზომველი F", "რეგისტრატორი ვინმე"])      # რეგისტრატორი ოქმში არ შედის
    assert [n for n, _ in res.surveyors] == ["ამზომველი F"] and res.excluded == ["რეგისტრატორი ვინმე"]


def test_manual_manager_override(db, people):
    _teams(db, people)
    db.add(ManagerOverride(person_key=name_key("სხვა ამზომველი"), person_name="სხვა ამზომველი",
                           manager_id=people["mgr"].id))
    db.commit()
    res = FieldDirectory(db).resolve(["სხვა ამზომველი"])
    assert res.status == OK and res.primary.id == people["mgr"].id and res.via_override


def test_manager_is_current_team_only(db, people):
    """OQMI_CREATOR → მისი **მიმდინარე** გუნდის მენეჯერი; ძველი გუნდი არ ითვლება."""
    from app.models import PersonAlias
    from app.services.seed import manager_map

    cur = Team(name="მიმდინარე", kind="field", manager_id=people["mgr"].id, active=True)
    old = Team(name="ძველი", kind="field", manager_id=people["mgr2"].id, active=False)
    db.add_all([cur, old])
    db.flush()
    db.add_all([TeamMember(team_id=cur.id, user_id=people["sv"].id),
                TeamMember(team_id=old.id, user_id=people["sv2"].id,
                           valid_to=dt.date(2026, 10, 19)),
                PersonAlias(alias_key=name_key("ამზ. F (ძველი ჩანაწერი)"),
                            user_id=people["sv"].id)])
    db.commit()
    m = manager_map(db)
    assert m[people["sv"].name_key].id == people["mgr"].id
    assert m[name_key("ამზ. F (ძველი ჩანაწერი)")].id == people["mgr"].id   # ალიასით
    assert people["sv2"].name_key not in m                                  # წასული — მენეჯერი არ ჰყავს
    assert m[people["mgr"].name_key].id == people["mgr"].id                 # მენეჯერი თავად ზომავს
    assert people["mgr2"].name_key not in m

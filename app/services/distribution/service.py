# -*- coding: utf-8 -*-
"""
განაწილება: გადახედვა (preview) → დადასტურება (confirm).

გადახედვა ბაზაში **არაფერს** წერს. დადასტურება ერთ ტრანზაქციაში ქმნის
დანიშვნებს; `uq_item_protocol_cad` ერთსა და იმავე ოქმს ორჯერ განაწილებას
ფიზიკურად კრძალავს (ორი ადამიანი ერთდროულად რომც დააჭიროს).

ნაბიჯები:
  1. დიაპაზონის კოდები (პირველი ოქმის წესი) + წინა განაწილების ნაშთი;
  2. გამორიცხვა: ღია საველე სტატუსი, უკვე კონტროლშია, Field Group-ში არავინაა,
     „დაუჯგუფებელი" (ამზომველი წასულია, მენეჯერი ჯერ არ მიუწერიათ);
  3. პროცენტული დაფარვა ზონა × მენეჯერის მიხედვით;
  4. ოპერატორების მაქსიმუმში ჩატევა — ნაშთი შემდეგ განაწილებაზე;
  5. ბლოკები ოპერატორებზე.
"""
import datetime as dt
import random
import threading
import time
import uuid
from collections import Counter, defaultdict

from sqlalchemy import select

from ... import domain as D
from ...models import DistributionBacklog, DistributionRun, ItemPerson, QcEvent, QcItem, Setting, User
from ..directory import NOT_FIELD, UNSORTED, FieldDirectory
from ..people import clean_name, name_key
from . import algo, source

_PREVIEWS: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()
PREVIEW_TTL = 30 * 60


def defaults(db) -> dict:
    s = db.get(Setting, "distribution_defaults")
    return dict(s.value) if s else {}


def resolve_records(records, directory):
    """REGFIELDALL ჩანაწერები → ამზომველები და მენეჯერები. აბრუნებს (ok, not_field, unsorted)."""
    ok, not_field, unsorted = [], [], []
    for r in records:
        res = directory.resolve([r.get("first_oqmi"), r.get("first_moxaz")])
        r["creator"] = clean_name(r.get("first_oqmi"))
        r["moxaz"] = clean_name(r.get("first_moxaz"))
        r["surveyors"] = [[name, u.id if u else None] for name, u in res.surveyors]
        r["creator_id"] = next((uid for name, uid in r["surveyors"] if name == r["creator"]), None)
        r["manager_ids"] = [m.id for m in res.managers]
        r["manager_id"] = res.primary.id if res.primary else None
        r["manager"] = res.primary.full_name if res.primary else ""
        r["via_override"] = res.via_override
        r["departed"] = res.departed
        r["zone"] = algo.zone_of(r["cadcode"])
        (not_field if res.status == NOT_FIELD else unsorted if res.status == UNSORTED else ok).append(r)
    return ok, not_field, unsorted


def _backlog_records(db):
    out = []
    for b in db.scalars(select(DistributionBacklog).where(DistributionBacklog.status == "open")):
        r = dict(b.record)
        r["backlog"] = True
        r["backlog_id"] = b.id
        out.append(r)
    return out


def prepare(db, params: dict) -> dict:
    seed = int(params.get("seed") or random.randrange(1, 2_000_000_000))
    rnd = random.Random(seed)
    quotas = {int(k): int(v) for k, v in (params.get("operators") or {}).items() if int(v) > 0}
    if not quotas:
        raise ValueError("მონიშნეთ მინიმუმ ერთი ოპერატორი და მიუთითეთ რაოდენობა.")
    ops = {u.id: u for u in db.scalars(select(User).where(User.id.in_(quotas)))}
    excl_zones = {z.zfill(2) for z in params.get("exclude_zones") or [] if z}
    rules = algo.normalize_rules(params.get("default_pct", 70), params.get("rules"))

    t0 = time.time()
    fresh = source.query_candidates(params["date_from"], params["date_to"])
    n_pool = len(fresh)
    backlog = _backlog_records(db)
    seen = {(r["first_paper_id"], r["cadcode"]) for r in backlog}
    records = backlog + [r for r in fresh if (r["first_paper_id"], r["cadcode"]) not in seen]
    records, open_status = algo.exclude_status(records, params.get("exclude_statuses"))

    existing = {p for (p,) in db.execute(select(QcItem.protocol_number))}
    kept, removed_existing = [], 0
    for r in records:
        if r["first_paper_id"] and r["first_paper_id"] in existing:
            removed_existing += 1
        else:
            kept.append(r)
    records = [r for r in kept if algo.zone_of(r["cadcode"]) not in excl_zones]
    n_excl_zone = len(kept) - len(records)

    directory = FieldDirectory(db)
    ok, not_field, unsorted = resolve_records(records, directory)

    blocks = algo.group_blocks(ok)
    backlog_keys = [k for k, g in blocks.items() if g["backlog"]]
    chosen, strata = algo.select_by_coverage({k: g for k, g in blocks.items() if not g["backlog"]},
                                             rules, rnd)
    for k in backlog_keys:
        blocks[k]["pct"] = algo.effective_pct(blocks[k], rules)
    capacity = sum(quotas.values())
    take, overflow = algo.fit_capacity(blocks, backlog_keys + chosen, capacity)
    assign, op_loads = algo.assign_to_operators(blocks, take, quotas, rnd) if take else ({}, {})

    names = dict(db.execute(select(User.id, User.full_name)).all())
    rows, over_rows = [], []
    for keys, out in ((take, rows), (overflow, over_rows)):
        for k in keys:
            for r in blocks[k]["recs"]:
                op = assign.get(k)
                out.append({"cadcode": r["cadcode"], "block": k, "protocol": r["first_paper_id"],
                            "protocol_count": r.get("protocol_count"), "disp_dt": r.get("disp_dt"),
                            "first_status": r.get("first_status"), "creator": r["creator"],
                            "moxaz": r["moxaz"], "first_oqmi": r.get("first_oqmi"),
                            "first_moxaz": r.get("first_moxaz"), "first_paper_id": r["first_paper_id"],
                            "surveyors": r["surveyors"], "creator_id": r["creator_id"],
                            "manager_ids": r["manager_ids"],
                            "manager_id": r["manager_id"], "manager": r["manager"],
                            "zone": r["zone"], "pct": blocks[k]["pct"],
                            "backlog": bool(r.get("backlog")), "backlog_id": r.get("backlog_id"),
                            "operator_id": op, "operator": ops[op].full_name if op else ""})
    rows.sort(key=lambda x: (x["operator"], x["block"], x["cadcode"]))

    op_rows = []
    for oid, q in quotas.items():
        n = op_loads.get(oid, 0)
        op_rows.append({"operator_id": oid, "operator": ops[oid].full_name, "quota": q,
                        "protocols": n, "blocks": sum(1 for k in take if assign.get(k) == oid),
                        "fill": round(100.0 * n / q) if q else 0})

    # დაფარვა ზონებითა და მენეჯერებით: ვარგისი → შერჩეული (%-ით) → განაწილდა
    chosen_set, take_set = set(chosen) | set(backlog_keys), set(take)
    cov_z, cov_m = defaultdict(lambda: [0, 0, 0, 0.0]), defaultdict(lambda: [0, 0, 0, 0.0])
    for k, g in blocks.items():
        for table, key in ((cov_z, g["zone"] or "—"), (cov_m, g["manager_id"])):
            row = table[key]
            row[0] += g["n"]
            row[1] += g["n"] if k in chosen_set else 0
            row[2] += g["n"] if k in take_set else 0
            row[3] = max(row[3], g.get("pct", rules["default"]))

    def cov(table, label, rule):
        return sorted(({"key": key, "name": label(key), "eligible": a, "selected": b, "assigned": c,
                        "pct": p, "rule": rule(key), "actual": round(100.0 * b / a) if a else 0}
                       for key, (a, b, c, p) in table.items()), key=lambda x: -x["eligible"])

    unsorted_people = Counter()
    for r in unsorted:
        for n in r["departed"]:
            unsorted_people[n] += 1
    preview = {
        "token": uuid.uuid4().hex, "seed": seed, "params": params, "rules": rules,
        "source": source.source_info(),
        "counts": {"pool": n_pool, "backlog": len(backlog), "open_status": open_status,
                   "open_status_total": sum(open_status.values()),
                   "existing": removed_existing, "excluded_zone": n_excl_zone,
                   "not_field": len(not_field), "unsorted": len(unsorted),
                   "candidates": len(ok), "blocks": len(blocks),
                   "selected": sum(blocks[k]["n"] for k in chosen_set),
                   "capacity": capacity, "assigned": len(rows), "overflow": len(over_rows),
                   "assigned_blocks": len(take)},
        "not_field_top": Counter(r["creator"] or "(ცარიელი)" for r in not_field).most_common(12),
        "unsorted_top": unsorted_people.most_common(12),
        "operators": op_rows,
        "zones": cov(cov_z, lambda z: z, lambda z: rules["zone"].get(z)),
        "managers": cov(cov_m, lambda m: names.get(m, "—"), lambda m: rules["manager"].get(str(m))),
        "strata": len(strata),
        "rows": rows, "overflow_rows": over_rows, "seconds": round(time.time() - t0, 1),
    }
    with _LOCK:
        now = time.time()
        for k in [k for k, (t, _) in _PREVIEWS.items() if now - t > PREVIEW_TTL]:
            _PREVIEWS.pop(k, None)
        _PREVIEWS[preview["token"]] = (now, preview)
    return preview


def get_preview(token):
    with _LOCK:
        hit = _PREVIEWS.get(token)
    return hit[1] if hit else None


def build_people(r, user_ids):
    """ოქმის ამზომველები (შემდგენი პირველი) და მიკუთვნებული მენეჯერები (პასუხისმგებელი პირველი)."""
    people = []
    for pos, (name, uid) in enumerate(r.get("surveyors") or []):
        people.append(ItemPerson(kind=D.P_SURVEYOR, user_id=uid if uid in user_ids else None,
                                 name=None if uid in user_ids else name, position=pos,
                                 is_primary=pos == 0, source="auto"))
    for pos, mid in enumerate(r.get("manager_ids") or []):
        people.append(ItemPerson(kind=D.P_MANAGER, user_id=mid, position=pos,
                                 is_primary=mid == r.get("manager_id"), source="auto"))
    return people


def confirm(db, token: str, user, role: str = D.QC_MANAGER) -> DistributionRun:
    preview = get_preview(token)
    if preview is None:
        raise ValueError("გადახედვის ვადა ამოიწურა — გაუშვით ხელახლა.")
    with _LOCK:                                       # ერთდროული დადასტურებისგან დაცვა (პროცესის შიგნით)
        if preview.get("confirmed_run"):
            return db.get(DistributionRun, preview["confirmed_run"])
        user_ids = {uid for (uid,) in db.execute(select(User.id))}
        existing = {(p, c) for p, c in db.execute(select(QcItem.protocol_number, QcItem.cadcode))}
        run = DistributionRun(created_by_id=user.id, params=preview["params"], seed=preview["seed"],
                              source_info=preview["source"],
                              summary={"counts": preview["counts"], "operators": preview["operators"],
                                       "rules": preview["rules"], "zones": preview["zones"][:60],
                                       "managers": preview["managers"]})
        db.add(run)
        db.flush()
        now = dt.datetime.now()
        n = skipped = 0
        for r in preview["rows"]:
            if (r["protocol"], r["cadcode"]) in existing:
                skipped += 1
                continue
            item = QcItem(
                protocol_number=r["protocol"], cadcode=r["cadcode"], kind=D.SYSTEMATIC,
                block_key=r["block"], zone=r["zone"], sector=algo.sector_of(r["cadcode"]),
                drawing_date=_parse(r["disp_dt"]), field_status=r["first_status"],
                protocol_creator_name=r["creator"] or None,
                protocol_creator_id=r["creator_id"] if r["creator_id"] in user_ids else None,
                operator_id=r["operator_id"], assigned_at=now, field_manager_id=r["manager_id"],
                distribution_run_id=run.id, state=D.PENDING)
            item.people = build_people(r, user_ids)
            db.add(item)
            db.flush()
            db.add(QcEvent(item_id=item.id, at=now, actor_id=user.id, actor_role=role,
                           action="assigned", to_state=D.PENDING,
                           data={"run": run.id, "operator": r["operator"], "pct": r["pct"],
                                 "backlog": r["backlog"]}))
            if r.get("backlog_id"):
                b = db.get(DistributionBacklog, r["backlog_id"])
                if b is not None:
                    b.status = "assigned"
            existing.add((r["protocol"], r["cadcode"]))
            n += 1
        carried = 0
        open_keys = {(b.protocol_number, b.cadcode) for b in db.scalars(select(DistributionBacklog))}
        for r in preview["overflow_rows"]:
            key = (r["protocol"], r["cadcode"])
            if key in existing or key in open_keys:
                continue
            rec = {k: r[k] for k in ("cadcode", "first_paper_id", "first_oqmi", "first_moxaz",
                                     "first_status", "disp_dt", "protocol_count")}
            db.add(DistributionBacklog(protocol_number=r["protocol"], cadcode=r["cadcode"],
                                       block_key=r["block"], record=rec, run_id=run.id))
            open_keys.add(key)
            carried += 1
        run.item_count = n
        run.summary = dict(run.summary, skipped=skipped, carried_over=carried)
        db.commit()
        preview["confirmed_run"] = run.id
        return run


def unsorted_report(db, date_from, date_to, exclude_statuses=None):
    """„დაუჯგუფებელი": Field Group-ის ამზომველები, რომლებიც დღეს არცერთ გუნდში არ არიან."""
    records = source.query_candidates(date_from, date_to)
    records, _ = algo.exclude_status(records, exclude_statuses)
    existing = {p for (p,) in db.execute(select(QcItem.protocol_number))}
    records = [r for r in records if r["first_paper_id"] not in existing]
    directory = FieldDirectory(db)
    _ok, _nf, unsorted = resolve_records(records, directory)
    people = {}
    for r in unsorted:
        for name in r["departed"][:1]:                 # პასუხისმგებლობის რიგით პირველი
            key = clean_name(name)
            p = people.setdefault(key, {"name": key, "count": 0, "samples": [], "zones": Counter()})
            p["count"] += 1
            p["zones"][r["zone"]] += 1
            if len(p["samples"]) < 5:
                p["samples"].append({"protocol": r["first_paper_id"], "cadcode": r["cadcode"],
                                     "date": (r.get("disp_dt") or "")[:10]})
    for p in people.values():
        last = directory.last_manager.get(name_key(p["name"]))
        p["last_manager"] = last.full_name if last else None
        p["last_manager_id"] = last.id if last else None
        p["zones"] = [z for z, _ in p["zones"].most_common(3)]
    return sorted(people.values(), key=lambda x: -x["count"]), len(unsorted)


def _parse(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "")[:19])
    except ValueError:
        return None

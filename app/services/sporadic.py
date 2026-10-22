# -*- coding: utf-8 -*-
"""
სპორადული: IT-ის ყოველდღიური სია (xlsx) → ფილტრი → განაწილება ოპერატორებზე.

ფაილი (sporaduli_datvaliereba.xlsx, შემოწმდა 2026-10-20): FLD_PAPER_ID = ოქმის ნომერი
(ძველი სპორადულის 2 908-დან 2 907 ემთხვევა), CADCODE, SURVEY_DAY — დათვალიერების დღე,
CALL_STATUS, ST_NAME (საველე სტატუსი), TR_NAME (სამუშაოს ტიპი), USER_REAL_NAME (დამგეგმავი).
ოქმის ნამდვილი ამზომველი REGFIELDALL-ის MOXAZ_CREATOR-ია (OQMI = „სისტემური სერვისი").

🔐 განმცხადებლების პირადი ნომრები, ტელეფონები და მისამართი (APPLICS, APP_PERSONS, REG_EMP,
   ADDRESS) **არ იკითხება** — პლატფორმას არ სჭირდება. ატვირთული ფაილი დამუშავებისთანავე იშლება.

⚠️ ფილტრები დასაზუსტებელია (მომხმარებელი შემდეგ ეტაპზე უპასუხებს) — ამიტომ პარამეტრებია:
   SURVEY_DAY (მხოლოდ გუშინ / გუშინ და ადრე), CALL_STATUS, ღია სტატუსი, TR_NAME, ოპერატორები.
"""
import datetime as dt
import random
import threading
import time
import uuid
from collections import Counter

import openpyxl
from sqlalchemy import select

from .. import domain as D
from ..models import QcEvent, QcItem, SporadicImport, User
from .directory import NOT_FIELD, UNSORTED, FieldDirectory
from .distribution import algo, source
from .distribution.service import build_people
from .people import clean_name

NEEDED = ("FLD_PAPER_ID", "CADCODE", "SURVEY_DAY", "SURVEY_TIME", "CALL_STATUS", "ST_NAME",
          "TR_NAME", "USER_REAL_NAME", "REGNUMBER", "CREATE_DATE")
COMPLETED = "ადგილზე დათვალიერება დასრულებულია"
OPEN_STATUSES = ("შედგენილია -საველე განცხადება მიღებულია", "აღწერის პროცესი-საველე განცხადება")
SYSTEM = "სისტემური სერვისი"

_PREVIEWS: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()
PREVIEW_TTL = 30 * 60


def _norm(s):
    return " ".join(str(s or "").split())


def _day(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    return None


def read_file(path) -> list[dict]:
    """xlsx → მხოლოდ საჭირო სვეტები (პირადი მონაცემის გარეშე)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        header = [str(h or "").strip().upper() for h in next(rows, [])]
        missing = [c for c in ("FLD_PAPER_ID", "CADCODE", "SURVEY_DAY") if c not in header]
        if missing:
            raise ValueError("ფაილში არ არის სვეტები: " + ", ".join(missing))
        idx = {c: header.index(c) for c in NEEDED if c in header}
        out = []
        for r in rows:
            rec = {c: (r[i] if i < len(r) else None) for c, i in idx.items()}
            pid = str(rec.get("FLD_PAPER_ID") or "").strip()
            if not pid:
                continue
            try:
                pid = str(int(float(pid)))
            except ValueError:
                pass
            out.append({"protocol": pid, "cadcode": _norm(rec.get("CADCODE")),
                        "survey_day": _day(rec.get("SURVEY_DAY")),
                        "survey_time": _norm(rec.get("SURVEY_TIME")),
                        "call_status": _norm(rec.get("CALL_STATUS")),
                        "st_name": _norm(rec.get("ST_NAME")), "tr_name": _norm(rec.get("TR_NAME")),
                        "scheduler": clean_name(rec.get("USER_REAL_NAME")),
                        "regnumber": _norm(rec.get("REGNUMBER"))})
        return out
    finally:
        wb.close()


def prepare(db, rows, params, today=None) -> dict:
    t0 = time.time()
    today = today or dt.date.today()
    yesterday = today - dt.timedelta(days=1)
    mode = params.get("survey_day_mode") or "upto_yesterday"
    lookback = int(params.get("lookback_days") or 7)
    seed = int(params.get("seed") or random.randrange(1, 2_000_000_000))
    rnd = random.Random(seed)

    funnel = Counter()
    sel = []
    for r in rows:
        d = r["survey_day"]
        if d is None:
            continue
        funnel["with_day"] += 1
        if mode == "yesterday" and d != yesterday:
            continue
        if mode != "yesterday" and not (yesterday - dt.timedelta(days=lookback) <= d <= yesterday):
            continue
        funnel["day_ok"] += 1
        if params.get("call_status_completed_only", True) and r["call_status"] != COMPLETED:
            funnel["call_status"] += 1
            continue
        if params.get("exclude_open_status", True) and r["st_name"] in OPEN_STATUSES:
            funnel["open_status"] += 1
            continue
        if params.get("tr_names") and r["tr_name"] not in params["tr_names"]:
            funnel["tr_name"] += 1
            continue
        sel.append(r)

    existing = {(i.protocol_number, i.cadcode): i for i in db.scalars(
        select(QcItem).where(QcItem.protocol_number.in_([r["protocol"] for r in sel] or ["-"])))}
    convert, ready = [], []
    for r in sel:
        it = existing.get((r["protocol"], r["cadcode"]))
        if it is None:
            ready.append(r)
        elif it.kind == D.SYSTEMATIC and it.state == D.PENDING:
            r["convert_item_id"] = it.id                  # სისტემურში გაუვლელია → სპორადულში
            convert.append(r)
            ready.append(r)
        else:
            funnel["already"] += 1

    found = source.lookup_protocols([r["protocol"] for r in ready])
    directory = FieldDirectory(db)
    ok, not_field, unsorted, missing = [], [], [], []
    for r in ready:
        hits = found.get(r["protocol"]) or []
        hit = next((h for h in hits if h["cadcode"] == r["cadcode"]), hits[0] if hits else None)
        if hit is None:
            missing.append(r)
            continue
        names = [hit["moxaz"]] + ([hit["oqmi"]] if _norm(hit["oqmi"]) != SYSTEM else [])
        res = directory.resolve(names)
        r["creator"] = clean_name(hit["moxaz"])
        r["surveyors"] = [[n, u.id if u else None] for n, u in res.surveyors]
        r["creator_id"] = next((uid for n, uid in r["surveyors"] if n == r["creator"]), None)
        r["manager_ids"] = [m.id for m in res.managers]
        r["manager_id"] = res.primary.id if res.primary else None
        r["manager"] = res.primary.full_name if res.primary else ""
        r["departed"] = res.departed
        r["field_status"] = hit["status"]
        r["created"] = hit["created"]
        r["zone"] = algo.zone_of(r["cadcode"])
        (not_field if res.status == NOT_FIELD else unsorted if res.status == UNSORTED else ok).append(r)

    ops_in = {int(k): (int(v) if str(v).strip().isdigit() else 0)
              for k, v in (params.get("operators") or {}).items()}
    picked = [o for o in ops_in]
    if not picked:
        raise ValueError("მონიშნეთ მინიმუმ ერთი ოპერატორი.")
    quotas = {o: q for o, q in ops_in.items() if q > 0} or algo.split_even(len(ok), picked)
    ops = {u.id: u for u in db.scalars(select(User).where(User.id.in_(quotas)))}
    blocks = {f"{r['protocol']}|{r['cadcode']}": {"n": 1, "recs": [r], "backlog": False,
                                                  "pct": 100, "first_dt": str(r["survey_day"])}
              for r in ok}
    take, overflow = algo.fit_capacity(blocks, list(blocks), sum(quotas.values()))
    assign, loads = algo.assign_to_operators(blocks, take, quotas, rnd) if take else ({}, {})
    out_rows = []
    for k in take:
        r = dict(blocks[k]["recs"][0])
        r["operator_id"] = assign[k]
        r["operator"] = ops[assign[k]].full_name
        r["survey_day"] = r["survey_day"].isoformat()
        out_rows.append(r)
    out_rows.sort(key=lambda x: (x["operator"], x["survey_day"], x["cadcode"]))
    preview = {
        "token": uuid.uuid4().hex, "seed": seed, "params": {k: v for k, v in params.items()},
        "today": today.isoformat(), "yesterday": yesterday.isoformat(),
        "counts": {"rows": len(rows), "with_day": funnel["with_day"], "day_ok": funnel["day_ok"],
                   "call_status": funnel["call_status"], "open_status": funnel["open_status"],
                   "tr_name": funnel["tr_name"], "already": funnel["already"],
                   "convert": len(convert), "missing": len(missing), "not_field": len(not_field),
                   "unsorted": len(unsorted), "ready": len(ok), "assigned": len(out_rows),
                   "overflow": len(overflow)},
        "days": sorted(Counter(r["survey_day"].isoformat() for r in sel).items()),
        "tr_names": Counter(r["tr_name"] for r in sel).most_common(),
        "unsorted_top": Counter(n for r in unsorted for n in r["departed"][:1]).most_common(10),
        "missing_sample": [(r["protocol"], r["cadcode"]) for r in missing[:10]],
        "operators": [{"operator_id": o, "operator": ops[o].full_name, "quota": q,
                       "protocols": loads.get(o, 0)} for o, q in quotas.items()],
        "rows": out_rows, "seconds": round(time.time() - t0, 1),
    }
    with _LOCK:
        now = time.time()
        for k in [k for k, (t_, _) in _PREVIEWS.items() if now - t_ > PREVIEW_TTL]:
            _PREVIEWS.pop(k, None)
        _PREVIEWS[preview["token"]] = (now, preview)
    return preview


def get_preview(token):
    with _LOCK:
        hit = _PREVIEWS.get(token)
    return hit[1] if hit else None


def confirm(db, token, user, role, filename=None) -> SporadicImport:
    preview = get_preview(token)
    if preview is None:
        raise ValueError("გადახედვის ვადა ამოიწურა — ატვირთეთ ფაილი ხელახლა.")
    with _LOCK:
        if preview.get("confirmed"):
            return db.get(SporadicImport, preview["confirmed"])
        user_ids = {uid for (uid,) in db.execute(select(User.id))}
        imp = SporadicImport(created_by_id=user.id, filename=filename, params=preview["params"],
                             summary={"counts": preview["counts"], "operators": preview["operators"],
                                      "days": preview["days"]})
        db.add(imp)
        db.flush()
        now = dt.datetime.now()
        n = 0
        for r in preview["rows"]:
            meta = {"survey_day": r["survey_day"], "survey_time": r["survey_time"],
                    "call_status": r["call_status"], "tr_name": r["tr_name"],
                    "scheduler": r["scheduler"], "regnumber": r["regnumber"], "import": imp.id}
            if r.get("convert_item_id"):
                item = db.get(QcItem, r["convert_item_id"])
                if item is None or item.state != D.PENDING:
                    continue
                item.kind = D.SPORADIC
                item.operator_id = r["operator_id"]
                item.sporadic_meta = meta
                db.add(QcEvent(item_id=item.id, at=now, actor_id=user.id, actor_role=role,
                               action="converted_to_sporadic", from_state=D.PENDING,
                               to_state=D.PENDING, data={"import": imp.id, "operator": r["operator"]}))
            else:
                item = QcItem(protocol_number=r["protocol"], cadcode=r["cadcode"], kind=D.SPORADIC,
                              block_key=algo.block_key(r["cadcode"]), zone=r["zone"],
                              sector=algo.sector_of(r["cadcode"]), field_status=r["field_status"],
                              drawing_date=_parse(r.get("created")),
                              protocol_creator_name=r["creator"] or None,
                              protocol_creator_id=r["creator_id"] if r["creator_id"] in user_ids else None,
                              operator_id=r["operator_id"], assigned_at=now,
                              field_manager_id=r["manager_id"], state=D.PENDING, sporadic_meta=meta)
                item.people = build_people(r, user_ids)
                db.add(item)
                db.flush()
                db.add(QcEvent(item_id=item.id, at=now, actor_id=user.id, actor_role=role,
                               action="assigned", to_state=D.PENDING,
                               data={"sporadic_import": imp.id, "operator": r["operator"]}))
            n += 1
        imp.item_count = n
        db.commit()
        preview["confirmed"] = imp.id
        return imp


def _parse(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "")[:19])
    except ValueError:
        return None

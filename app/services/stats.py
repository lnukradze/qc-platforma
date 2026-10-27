# -*- coding: utf-8 -*-
"""
სტატისტიკა — **ერთი წყარო, ერთი განმარტება ყველა როლისთვის**.

ყოველი რიცხვი ერთსა და იმავე ფუნქციებით ითვლება; როლი მხოლოდ იმას ცვლის,
**რომელი ჩანაწერები** შედის (`scope.item_filter`). ამიტომ ოპერატორის,
მენეჯერისა და კოორდინატორის ციფრები ერთმანეთს ვერ დაშორდება.

მეტრიკების ლექსიკონი (docs/ARCHITECTURE.md-შიც):
  შემოწმებული   — სტატუსი გაგზავნილია (D = `checked_at` — პირველი გაგზავნა, ფილტრის თარიღი)
  დადებითი      — დადებითი (დაზუსტება **არ** ითვლება — ის კითხვაა, სტატუსი პასუხის შემდეგ ენიჭება)
  დაზუსტებაში   — კითხვა გაგზავნილია, საბოლოო სტატუსი ჯერ არ არის
  ხარვეზი %     — უარყოფითი ÷ შემოწმებული
  კრიტიკული %   — უარყოფითი, რომელსაც ≥1 კრიტიკული კოდი აქვს ÷ შემოწმებული
  გასწორდა      — დახურული „გასწორდა"-თი (M) ÷ უარყოფითი
  ველზე ღია     — ველის, მენეჯერის ან QC მენეჯერის მხარეს მყოფი
  პასუხის დრო   — გაგზავნიდან ველის პასუხამდე (ძველ მონაცემზე — მიახლოებით)
  ამზომველი     — ოქმის ყველა ამზომველი იღებს შემთხვევას; მენეჯერები ამ სიაში არ შედიან
  მენეჯერი      — ოქმი ყველა მიკუთვნებულ მენეჯერს ეთვლება (სხვადასხვა გუნდის ამზომველები)
  გავლილი       — ოპერატორის სამუშაო: პირველი გაგზავნა (დაზუსტების კითხვაც) — `first_sent_at`
  ოპერატორის შეცდომა / QC მენეჯერის შეფასება / ცრუ გასწორება — მხოლოდ შეზღუდულ ნაწილში
"""
import datetime as dt
import statistics
from collections import defaultdict

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import aliased

from .. import domain as D
from .. import scope
from ..models import DefectCode, ItemPerson, QcItem, QcItemCode, QcReview, Team, User, UserRole

FIELD_OPEN = (D.AWAITING_FIELD, D.AWAITING_MANAGER, D.RETURNED_TO_MANAGER, D.AWAITING_QCM)


def parse_filters(q) -> dict:
    g = lambda k: (q.get(k) or "").strip()
    f = {k: g(k) for k in ("date_from", "date_to", "kind", "operator", "manager", "surveyor",
                           "zone", "verdict", "code", "cad", "protocol", "group", "severity")}
    return f


def _date(s, end=False):
    try:
        d = dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return dt.datetime.combine(d, dt.time.max if end else dt.time.min)


def _has_person(kind, user_id):
    ip = aliased(ItemPerson)
    return exists().where(ip.item_id == QcItem.id, ip.kind == kind,
                          ip.user_id == user_id).correlate(QcItem)


def conditions(ctx, f, checked_only=True):
    c = [scope.item_filter(ctx)]
    if checked_only:
        c.append(QcItem.checked_at.is_not(None))
    if f.get("date_from") and _date(f["date_from"]):
        c.append(QcItem.checked_at >= _date(f["date_from"]))
    if f.get("date_to") and _date(f["date_to"], True):
        c.append(QcItem.checked_at <= _date(f["date_to"], True))
    if f.get("kind") in (D.SYSTEMATIC, D.SPORADIC):
        c.append(QcItem.kind == f["kind"])
    if f.get("operator", "").isdigit() and scope.can_see_operator_stats(ctx):
        c.append(QcItem.operator_id == int(f["operator"]))
    if f.get("manager", "").isdigit():
        mid = int(f["manager"])
        c.append(or_(QcItem.field_manager_id == mid, _has_person(D.P_MANAGER, mid)))
    if f.get("surveyor", "").isdigit():
        sid = int(f["surveyor"])
        c.append(or_(QcItem.protocol_creator_id == sid, _has_person(D.P_SURVEYOR, sid)))
    if f.get("zone"):
        c.append(QcItem.zone == f["zone"].zfill(2))
    if f.get("verdict") in D.VERDICTS:
        c.append(QcItem.verdict == f["verdict"])
    if f.get("cad"):
        c.append(QcItem.cadcode.like(f["cad"].strip() + "%"))
    if f.get("protocol"):
        c.append(QcItem.protocol_number == f["protocol"].strip())
    if f.get("code") or f.get("group") or f.get("severity"):
        sub = select(QcItemCode.item_id).join(DefectCode, DefectCode.code == QcItemCode.code)
        if f.get("code"):
            sub = sub.where(QcItemCode.code == f["code"])
        if f.get("group"):
            sub = sub.where(DefectCode.group == f["group"])
        if f.get("severity"):
            sub = sub.where(DefectCode.severity == f["severity"])
        c.append(QcItem.id.in_(sub))
    return and_(*c)


def _cat_exprs(db):
    """კატეგორიები SQL-ში. ველი მართალი/ორივე მართალი → QC მენეჯერმა „დადებითი" მონიშნა."""
    return (QcItem.verdict == D.POSITIVE, QcItem.verdict == D.NEGATIVE,
            QcItem.verdict == D.RECOMMENDATION)


def _crit_item_ids():
    return (select(QcItemCode.item_id).join(DefectCode, DefectCode.code == QcItemCode.code)
            .where(DefectCode.severity == "Critical"))


def _agg_cols(db):
    is_pos, is_neg, is_rec = _cat_exprs(db)
    s = lambda cond: func.sum(case((cond, 1), else_=0))
    return [
        func.count(QcItem.id).label("checked"),
        s(is_pos).label("positive"),
        s(is_neg).label("negative"),
        s(is_rec).label("recommendation"),
        s(and_(is_neg, QcItem.id.in_(_crit_item_ids()))).label("critical"),
        s(QcItem.state.in_(FIELD_OPEN)).label("in_field"),
        s(QcItem.state == D.AWAITING_QC).label("awaiting_qc"),
        s(QcItem.state == D.AWAITING_QCM).label("awaiting_qcm"),
        s(QcItem.close_reason == D.CR_CORRECTED).label("corrected"),
        s(QcItem.close_reason == D.CR_ACKNOWLEDGED).label("acknowledged"),
        s(QcItem.dispute_count > 0).label("disputed"),
        s(QcItem.kind == D.SPORADIC).label("sporadic"),
    ]


def _row_dict(row):
    d = dict(row._mapping)
    chk = d.get("checked") or 0
    neg = d.get("negative") or 0
    d["defect_rate"] = round(100.0 * neg / chk, 1) if chk else 0.0
    d["critical_rate"] = round(100.0 * (d.get("critical") or 0) / chk, 1) if chk else 0.0
    d["corrected_rate"] = round(100.0 * (d.get("corrected") or 0) / neg, 1) if neg else 0.0
    return d


def _pending(db, ctx, f):
    """შეუმოწმებელი (გასავლელი) — ვერდიქტი ჯერ არ გაგზავნილა."""
    cond = conditions(ctx, {**f, "date_from": "", "date_to": "", "verdict": ""}, checked_only=False)
    return db.scalar(select(func.count(QcItem.id)).where(cond, QcItem.state == D.PENDING)) or 0


def _in_clarification(db, ctx, f):
    cond = conditions(ctx, {**f, "date_from": "", "date_to": "", "verdict": ""}, checked_only=False)
    return db.scalar(select(func.count(QcItem.id)).where(cond, QcItem.verdict == D.CLARIFICATION,
                                                         QcItem.state != D.CLOSED)) or 0


def kpi(db, ctx, f):
    row = db.execute(select(*_agg_cols(db)).where(conditions(ctx, f))).one()
    d = _row_dict(row)
    if ctx.role not in D.FIELD_ROLES:          # გაუგზავნელის რაოდენობა ველს არ უჩანს (B-14)
        d["pending"] = _pending(db, ctx, f)
    d["in_clarification"] = _in_clarification(db, ctx, f)
    d.update(response_times(db, ctx, f))
    return d


def operator_daily(db, operator_id, today=None):
    """ოპერატორის დღის რაოდენობა — რამდენი გაგზავნა (პირველი გაგზავნა, დაზუსტების კითხვაც)."""
    today = today or dt.date.today()
    start = dt.datetime.combine(today, dt.time.min)
    week0 = dt.datetime.combine(today - dt.timedelta(days=today.weekday()), dt.time.min)
    base = select(func.count(QcItem.id)).where(QcItem.operator_id == operator_id)
    count = lambda a, b: db.scalar(base.where(QcItem.first_sent_at >= a, QcItem.first_sent_at < b)) or 0
    day = dt.timedelta(days=1)
    return {"today": count(start, start + day), "yesterday": count(start - day, start),
            "week": count(week0, start + day),
            "pending": db.scalar(select(func.count(QcItem.id)).where(
                QcItem.operator_id == operator_id, QcItem.state == D.PENDING)) or 0}


def _week(db, col):
    """კვირის გასაღები — SQLite-ზეც და PostgreSQL-ზეც."""
    if db.get_bind().dialect.name == "sqlite":
        return func.strftime("%Y-%W", col)
    return func.to_char(func.date_trunc("week", col), "IYYY-IW")


def trend(db, ctx, f):
    is_pos, is_neg, is_rec = _cat_exprs(db)
    wk = _week(db, QcItem.checked_at)
    s = lambda cond: func.sum(case((cond, 1), else_=0))
    rows = db.execute(select(wk.label("week"), func.min(QcItem.checked_at).label("start"),
                             func.count(QcItem.id).label("checked"), s(is_pos).label("positive"),
                             s(is_neg).label("negative"), s(is_rec).label("recommendation"))
                      .where(conditions(ctx, f), QcItem.checked_at.is_not(None))
                      .group_by(wk).order_by(wk)).all()
    out = []
    this_year = dt.date.today().year
    for r in rows:
        d = _row_dict(r)
        if r.start:
            d["label"] = r.start.strftime("%d.%m") if r.start.year == this_year else r.start.strftime("%d.%m.%y")
        else:
            d["label"] = r.week
        # სანდოობის დამცავი (qc-dashboard-ის MIN_N): 30-ზე ნაკლებ შემოწმებაზე % არ ისახება
        d["reliable"] = (d.get("checked") or 0) >= MIN_N
        out.append(d)
    return out


MIN_N = 30


def by_operator(db, ctx, f):
    """„კონტროლის სტატისტიკა" — მხოლოდ QC მხარეს (scope.can_see_operator_stats)."""
    if not scope.can_see_operator_stats(ctx):
        return []
    days =func.count(func.distinct(func.date(QcItem.checked_at)))
    rows = db.execute(select(User.id, User.full_name.label("name"), *_agg_cols(db),
                             days.label("active_days"),
                             func.sum(case((QcItem.return_count > 0, 1), else_=0)).label("returned"))
                      .join(User, User.id == QcItem.operator_id)
                      .where(conditions(ctx, f)).group_by(User.id, User.full_name)).all()
    pend = dict(db.execute(select(QcItem.operator_id, func.count(QcItem.id))
                           .where(conditions(ctx, {**f, "date_from": "", "date_to": ""},
                                             checked_only=False), QcItem.state == D.PENDING)
                           .group_by(QcItem.operator_id)).all())
    pc = [conditions(ctx, {**f, "date_from": "", "date_to": "", "verdict": ""}, checked_only=False),
          QcItem.first_sent_at.is_not(None)]
    if f.get("date_from") and _date(f["date_from"]):
        pc.append(QcItem.first_sent_at >= _date(f["date_from"]))
    if f.get("date_to") and _date(f["date_to"], True):
        pc.append(QcItem.first_sent_at <= _date(f["date_to"], True))
    passed = dict(db.execute(select(QcItem.operator_id, func.count(QcItem.id)).where(*pc)
                             .group_by(QcItem.operator_id)).all())
    out = []
    for r in rows:
        d = _row_dict(r)
        d["pending"] = pend.get(r.id, 0)
        d["passed"] = passed.get(r.id, 0)
        d["daily_avg"] = round(d["checked"] / d["active_days"], 1) if d["active_days"] else 0
        out.append(d)
    return sorted(out, key=lambda x: -x["checked"])


def by_manager(db, ctx, f):
    """ოქმი ყველა მიკუთვნებულ მენეჯერს ეთვლება (სხვადასხვა გუნდის ამზომველები)."""
    rows = db.execute(select(User.id, User.full_name.label("name"), *_agg_cols(db))
                      .select_from(QcItem)
                      .join(ItemPerson, and_(ItemPerson.item_id == QcItem.id,
                                             ItemPerson.kind == D.P_MANAGER))
                      .join(User, User.id == ItemPerson.user_id)
                      .where(conditions(ctx, f)).group_by(User.id, User.full_name)).all()
    rt = response_times(db, ctx, f, group="manager")
    out = []
    for r in rows:
        d = _row_dict(r)
        d["median_response_days"] = rt.get(r.id)
        out.append(d)
    return sorted(out, key=lambda x: -x["checked"])


def _manager_ids(db):
    return {uid for (uid,) in db.execute(select(UserRole.user_id)
                                          .where(UserRole.role == D.FIELD_MANAGER))}


def by_surveyor(db, ctx, f, limit=400):
    """ოქმის ყველა ამზომველი იღებს შემთხვევას. მენეჯერები ამ სიიდან გამოირიცხება."""
    is_pos, is_neg, is_rec = _cat_exprs(db)
    cond = conditions(ctx, f)
    u = (select(ItemPerson.user_id.label("uid"), QcItem.id.label("iid"))
         .join(QcItem, QcItem.id == ItemPerson.item_id)
         .where(cond, ItemPerson.kind == D.P_SURVEYOR, ItemPerson.user_id.is_not(None))
         .distinct().subquery())
    s = lambda c: func.sum(case((c, 1), else_=0))
    rows = db.execute(
        select(User.id, User.full_name.label("name"), func.count(u.c.iid).label("checked"),
               s(is_pos).label("positive"), s(is_neg).label("negative"),
               s(is_rec).label("recommendation"),
               s(QcItem.close_reason == D.CR_CORRECTED).label("corrected"),
               s(QcItem.state.in_(FIELD_OPEN)).label("in_field"),
               s(QcItem.dispute_count > 0).label("disputed"),
               s(and_(is_neg, QcItem.id.in_(_crit_item_ids()))).label("critical"))
        .select_from(u).join(QcItem, QcItem.id == u.c.iid).join(User, User.id == u.c.uid)
        .group_by(User.id, User.full_name)).all()
    mgr = _manager_ids(db)
    out = [_row_dict(r) for r in rows if r.id not in mgr]
    return sorted(out, key=lambda x: -x["checked"])[:limit]


def codes(db, ctx, f):
    is_pos, is_neg, is_rec = _cat_exprs(db)
    rows = db.execute(select(QcItemCode.code, DefectCode.name, DefectCode.group, DefectCode.severity,
                             func.sum(case((is_neg, 1), else_=0)).label("negative"),
                             func.sum(case((is_rec, 1), else_=0)).label("recommendation"))
                      .join(QcItem, QcItem.id == QcItemCode.item_id)
                      .join(DefectCode, DefectCode.code == QcItemCode.code, isouter=True)
                      .where(conditions(ctx, f))
                      .group_by(QcItemCode.code, DefectCode.name, DefectCode.group,
                                DefectCode.severity)).all()
    out = [dict(r._mapping) for r in rows if r.code != "QC-00"]
    return sorted(out, key=lambda x: -(x["negative"] or 0))


def zones(db, ctx, f, names=None):
    rows = db.execute(select(QcItem.zone, *_agg_cols(db)).where(conditions(ctx, f),
                                                               QcItem.zone.is_not(None))
                      .group_by(QcItem.zone)).all()
    out = []
    for r in rows:
        d = _row_dict(r)
        d["name"] = (names or {}).get(r.zone, r.zone)
        out.append(d)
    return sorted(out, key=lambda x: -x["checked"])


def response_times(db, ctx, f, group=None):
    """პასუხის დრო (დღე) — გაგზავნიდან ველის პასუხამდე. მედიანა + 75-ე პროცენტილი."""
    rows = db.execute(select(QcItem.sent_at, QcItem.field_responded_at, QcItem.is_legacy,
                             QcItem.field_manager_id)
                      .where(conditions(ctx, f), QcItem.sent_at.is_not(None),
                             QcItem.field_responded_at.is_not(None))).all()
    if group == "manager":
        per = defaultdict(list)
        for s_, r_, _l, m in rows:
            d = (r_ - s_).total_seconds() / 86400
            if d >= 0:
                per[m].append(d)
        return {m: round(statistics.median(v), 1) for m, v in per.items() if v}
    vals = [(r_ - s_).total_seconds() / 86400 for s_, r_, _l, _m in rows]
    vals = [v for v in vals if v >= 0]
    legacy = sum(1 for _s, _r, l, _m in rows if l)
    if not vals:
        return {"response_median": None, "response_p75": None, "response_n": 0,
                "response_legacy_share": 0}
    vals.sort()
    return {"response_median": round(statistics.median(vals), 1),
            "response_p75": round(vals[int(0.75 * (len(vals) - 1))], 1),
            "response_n": len(vals),
            "response_legacy_share": round(100.0 * legacy / len(rows)) if rows else 0}


def restricted(db, ctx, f):
    """
    შეზღუდული (QC მენეჯერი + ადმინი): ოპერატორის შეცდომები — „ველი მართალია",
    QC მენეჯერის შეფასებები (სწორია / არასწორი / გამორჩენილი / არასრულყოფილი, ძველი TYPE-ის
    ჩათვლით) და „ორივე მართალია". „ცრუ გასწორება" — ასევე საველე მენეჯერს.
    """
    out = {}
    cond = conditions(ctx, f)
    if scope.can_see_restricted_stats(ctx):
        s_ = lambda c: func.sum(case((c, 1), else_=0))
        rows = db.execute(select(User.id, User.full_name.label("name"),
                                 func.count(QcItem.id).label("checked"),
                                 s_(QcItem.qc_error.is_(True)).label("qc_errors"),
                                 s_(QcItem.both_right.is_(True)).label("both_right"),
                                 s_(QcItem.dispute_count > 0).label("disputed"),
                                 s_(QcItem.verdict == D.NEGATIVE).label("negative"))
                          .join(User, User.id == QcItem.operator_id).where(cond)
                          .group_by(User.id, User.full_name)).all()
        per = {r.id: {**dict(r._mapping), **{m: 0 for m in D.REVIEW_MARKS}, "reviewed": 0}
               for r in rows}
        rev_src = {"manual": 0, "legacy": 0}
        for op_id, marks, src in db.execute(select(QcItem.operator_id, QcReview.marks, QcReview.source)
                                            .join(QcReview, QcReview.item_id == QcItem.id)
                                            .where(cond)):
            d = per.get(op_id)
            if d is None:
                continue
            d["reviewed"] += 1
            rev_src[src if src in rev_src else "manual"] += 1
            for m in marks or []:
                if m in d:
                    d[m] += 1
        for d in per.values():
            d["errors_total"] = d["qc_errors"] + sum(d[m] for m in D.ERROR_MARKS)
        out["qc_errors"] = sorted(per.values(), key=lambda x: -x["errors_total"])
        out["review_sources"] = rev_src
    if scope.can_see_false_fix(ctx):
        rows = db.execute(select(User.full_name.label("name"),
                                 func.sum(QcItem.false_fix_count).label("false_fix"),
                                 func.sum(case((QcItem.return_count > 0, 1), else_=0)).label("returned_items"),
                                 func.sum(QcItem.return_count).label("returns"))
                          .join(User, User.id == QcItem.field_manager_id).where(cond)
                          .group_by(User.full_name)).all()
        out["false_fix_by_manager"] = sorted((dict(r._mapping) for r in rows),
                                             key=lambda x: -(x["returns"] or 0))
    return out


def filter_options(db, ctx):
    cond = scope.item_filter(ctx)
    ops = db.execute(select(User.id, User.full_name).join(QcItem, QcItem.operator_id == User.id)
                     .where(cond).group_by(User.id, User.full_name).order_by(User.full_name)).all() \
        if scope.can_see_operator_stats(ctx) else []
    mgrs = db.execute(select(User.id, User.full_name)
                      .join(ItemPerson, and_(ItemPerson.user_id == User.id,
                                             ItemPerson.kind == D.P_MANAGER))
                      .join(QcItem, QcItem.id == ItemPerson.item_id)
                      .where(cond).group_by(User.id, User.full_name).order_by(User.full_name)).all()
    zs = [z for (z,) in db.execute(select(QcItem.zone).where(cond, QcItem.zone.is_not(None))
                                   .group_by(QcItem.zone).order_by(QcItem.zone))]
    return {"operators": [{"id": i, "name": n} for i, n in ops],
            "managers": [{"id": i, "name": n} for i, n in mgrs], "zones": zs}


def team_surveyors(db, manager_id):
    t = db.scalar(select(Team).where(Team.manager_id == manager_id))
    if not t:
        return []
    return sorted((m.user for m in t.members if m.valid_to is None), key=lambda u: u.full_name)

# -*- coding: utf-8 -*-
"""
საწყისი მონაცემი: ცნობარები, მომხმარებლები, გუნდები.

  • ხარვეზის კოდები — `seed/code_catalog.json`
  • მივლინებები     — `seed/missions.json`
  • ამზომველები და მენეჯერები — Field Group (მიმდინარე + სრული ფურცელი)
  • QC ოპერატორები  — კონტროლის ცხრილის ჩანართებიდან
  • QC მენეჯერები — გიორგი ჩიგოგიძე (სისტემური), ბექა სალუქვაძე (სპორადული)
  • დემო ანგარიშები — კოორდინატორი, სამსახურის უფროსი (ადამიანები ჯერ განსაზღვრული არ არის)
"""
import datetime as dt
import json

from sqlalchemy import select

from .. import domain as D
from ..config import RAW_DIR, SEED_DIR
from ..models import DefectCode, Mission, PersonAlias, Setting, Team, TeamMember, User, UserRole
from .people import clean_manager, clean_name, name_key

# ამ ეტაპზე ორი ადამიანი — QC ოპერატორი + ადმინისტრატორი (მომხმარებლის პასუხი, 2026-10-19)
DEVELOPER_ADMINS = ("ლუკა ნუკრაძე", "სალომე დავითაშვილი")
# QC მენეჯერები და მათი ნაგულისხმევი მიმართულება (პასუხი, 2026-10-20) — ადმინები არ არიან
QC_MANAGERS = (("გიორგი ჩიგოგიძე", "systematic"), ("ბექა სალუქვაძე", "sporadic"))

DEFAULT_SETTINGS = {
    "allowed_responses": D.DEFAULT_ALLOWED_RESPONSES,
    "distribution_defaults": {
        # ოპერატორის რაოდენობა = მაქსიმუმი; რაც არ ჩაეტია, შემდეგ განაწილებაზე გადადის
        "per_operator": 450,
        # ყველა არეალიდან ~70%; ზონას/სექტორს/მენეჯერს საკუთარი პროცენტი შეიძლება ჰქონდეს
        "default_pct": 70,
        "exclude_statuses": ["შედგენილია -საველე განცხადება მიღებულია",
                             "აღწერის პროცესი-საველე განცხადება"],
    },
    # სპორადულის ფილტრები — ⚠️ დასაზუსტებელია (მომხმარებელი შემდეგ ეტაპზე უპასუხებს)
    "sporadic_defaults": {
        "survey_day_mode": "upto_yesterday",          # yesterday | upto_yesterday
        "call_status_completed_only": True,
        "exclude_open_status": True,
    },
    # Pre-QC: მივლინების მესამე დღიდან — „დღე N ამოწმებს დღე N-2-ის ოქმებს"
    "preqc_lag_days": 2,
}


class People:
    """name_key → User, ხელახალი ძებნის გარეშე."""

    def __init__(self, db):
        self.db = db
        self.by_key = {u.name_key: u for u in db.scalars(select(User))}
        for a in db.scalars(select(PersonAlias)):
            u = db.get(User, a.user_id)
            if u:
                self.by_key.setdefault(a.alias_key, u)

    def get(self, name):
        k = name_key(name)
        return self.by_key.get(k) if k else None

    def ensure(self, name, role=None, source="manual", active=True, is_demo=False):
        k = name_key(name)
        if not k:
            return None
        u = self.by_key.get(k)
        if u is None:
            u = User(full_name=clean_name(name), name_key=k, source=source, active=active,
                     is_demo=is_demo)
            self.db.add(u)
            self.db.flush()
            self.by_key[k] = u
        if role and role not in u.role_set:
            u.roles.append(UserRole(role=role))
        return u


def seed_reference(db):
    with open(SEED_DIR / "code_catalog.json", encoding="utf-8") as f:
        cat = json.load(f)
    for i, (code, c) in enumerate(cat["codes"].items()):
        db.merge(DefectCode(code=code, name=c["name"], group=c["group"], severity=c["sev"],
                            page=c.get("page"), description=c.get("desc"), active=True, sort=i))
    p = cat.get("pending") or {}
    if p:
        db.merge(DefectCode(code=p["code"], name=p["name"], group="დროებითი", severity="pending",
                            description=p.get("desc"), active=True, sort=99))
    with open(SEED_DIR / "missions.json", encoding="utf-8") as f:
        ms = json.load(f)
    for m in ms["missions"]:
        db.merge(Mission(n=m["n"], start=dt.date.fromisoformat(m["start"]),
                         end=dt.date.fromisoformat(m["end"])))
    for k, v in DEFAULT_SETTINGS.items():
        if db.get(Setting, k) is None:
            db.add(Setting(key=k, value=v))
    db.flush()


def seed_people(db):
    """Field Group → ამზომველები, მენეჯერები, გუნდები; ოპერატორები ცხრილიდან."""
    ppl = People(db)
    fg = json.loads((RAW_DIR / "field_group.json").read_text(encoding="utf-8"))
    teams = {t.manager_id: t for t in db.scalars(select(Team))}

    def team_of(mgr_user, active=True):
        t = teams.get(mgr_user.id)
        if t is None:
            t = Team(name=mgr_user.full_name, kind="field", manager_id=mgr_user.id, active=active)
            db.add(t)
            db.flush()
            teams[mgr_user.id] = t
        return t

    current = {}
    for r in fg["current"]["rows"]:
        nm, mg = clean_name(r.get("name")), clean_manager(r.get("manager"))
        if nm:
            current[name_key(nm)] = (nm, mg)
    manager_keys = {name_key(m) for _, m in current.values() if m}

    # მენეჯერები (ისინიც შეიძლება ზომავდნენ — ამზომველთა სიაში არ ითვლებიან)
    for _, mg in current.values():
        if mg:
            ppl.ensure(mg, D.FIELD_MANAGER, source="field_group")
    # მიმდინარე ამზომველები
    for k, (nm, mg) in current.items():
        if k in manager_keys:
            continue
        u = ppl.ensure(nm, D.SURVEYOR, source="field_group")
        if mg:
            t = team_of(ppl.get(mg))
            db.add(TeamMember(team_id=t.id, user_id=u.id, source="field_group"))
    # სრული ფურცელი — წასული თანამშრომლები (ისტორიული მიკუთვნებისთვის, არააქტიური)
    for r in fg["full"]["rows"]:
        nm, mg = clean_name(r.get("name")), clean_manager(r.get("manager"))
        k = name_key(nm)
        if not k or k in current or k in manager_keys:
            continue
        u = ppl.ensure(nm, D.SURVEYOR, source="field_group_full", active=False)
        if mg:
            mu = ppl.get(mg) or ppl.ensure(mg, D.FIELD_MANAGER, source="field_group_full",
                                          active=False)
            # ძველი გუნდი — მხოლოდ ისტორიისთვის; მიმდინარე მენეჯერის გუნდი უცვლელი რჩება
            t = team_of(mu, active=False)
            db.add(TeamMember(team_id=t.id, user_id=u.id, source="field_group_full",
                              valid_to=dt.date(2026, 10, 19)))

    # QC ოპერატორები — კონტროლის ცხრილის ჩანართებიდან
    man = json.loads((RAW_DIR / "control" / "manifest.json").read_text(encoding="utf-8"))
    qc_team = db.scalar(select(Team).where(Team.kind == "qc"))
    if qc_team is None:
        qc_team = Team(name="ხარისხის კონტროლი", kind="qc")
        db.add(qc_team)
        db.flush()
    def to_control(u):
        """კონტროლში გადმოსული — ველის როლები აღარ აქვს (მაგ. სალომე: „ოფისი" Field Group-ში)."""
        u.active = True
        u.roles[:] = [r for r in u.roles if r.role not in D.FIELD_ROLES]

    for t in man["tabs"]:
        if t["name"] == "სპორადული":
            continue
        u = ppl.ensure(t["name"], D.QC_OPERATOR, source="control_sheet")
        to_control(u)
        db.add(TeamMember(team_id=qc_team.id, user_id=u.id, source="control_sheet"))
    for nm in DEVELOPER_ADMINS:
        u = ppl.ensure(nm, D.QC_OPERATOR, source="control_sheet")
        to_control(u)
        ppl.ensure(nm, D.ADMIN)
    for i, (nm, kind) in enumerate(QC_MANAGERS):
        u = ppl.ensure(nm, D.QC_MANAGER, source="control_team")
        to_control(u)
        u.prefs = {"kind": kind}
        if i == 0:
            qc_team.manager_id = u.id

    # დემო ანგარიშები — როლები, რომლებზეც ადამიანი ჯერ არ არის განსაზღვრული
    ppl.ensure("კოორდინატორი (დემო)", D.COORDINATOR, source="demo", is_demo=True)
    ppl.ensure("სამსახურის უფროსი (დემო)", D.HEAD_OF_SERVICE, source="demo", is_demo=True)
    db.flush()
    return ppl


def manager_map(db) -> dict:
    """ამზომველის name_key (და მისი ალიასები) → მენეჯერის User.

    წესი (2026-10-19): ოქმი ეწერება იმ მენეჯერს, ვის გუნდშიც OQMI_CREATOR არის
    **განაწილების დროს** — ამიტომ მხოლოდ მიმდინარე წევრობა და აქტიური გუნდი.
    წასული თანამშრომლის ოქმს მენეჯერი არ ჰყავს („მენეჯერი ვერ მოიძებნა").
    """
    out = {}
    teams = [t for t in db.scalars(select(Team).where(Team.kind == "field",
                                                      Team.active.is_(True)))
             if t.manager is not None and t.manager.active]
    for t in teams:
        for tm in t.members:
            if tm.valid_to is None:
                out[tm.user.name_key] = t.manager
    for t in teams:                       # მენეჯერი თავად ზომავს — საკუთარი გუნდი
        out.setdefault(t.manager.name_key, t.manager)
    ids = dict(db.execute(select(User.name_key, User.id)).all())
    by_id = {ids[k]: m for k, m in out.items() if k in ids}
    for a in db.scalars(select(PersonAlias)):  # Reference/TblPlannerMap — სხვა ჩაწერის ფორმები
        if a.user_id in by_id:
            out.setdefault(a.alias_key, by_id[a.user_id])
    return out

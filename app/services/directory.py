# -*- coding: utf-8 -*-
"""
ვინ ვისი გუნდიდანაა — Field Group-ის მიხედვით (განაწილება, სპორადული, ხელით მინიჭება).

წესები (მომხმარებლის პასუხები, 2026-10-19 / 2026-10-20):
  • ოქმის შემსრულებლები შედარდება FIELD_GROUP_ALL-ს (წასულების ჩათვლით). ვინც იქ არ
    არის (მაგ. რეგისტრატორი), ოქმში ამზომველად არ შედის;
  • მენეჯერი — FIELD_GROUP_272-ის (დღევანდელი) მიხედვით. თუ ამზომველები სხვადასხვა
    მენეჯერთან არიან, ოქმი **ყველა** მენეჯერს ეკუთვნის (ხედავს, სტატისტიკაში ეთვლება);
    მოქმედებს მხოლოდ **ოქმის შემდგენის** მენეჯერი;
  • შემდგენი წასულია → პასუხისმგებელია მეორე ამზომველის მენეჯერი;
  • არცერთი ამზომველი 272-ში არ არის → „დაუჯგუფებელი": QC მენეჯერი ხელით მიუწერს
    მენეჯერს (`ManagerOverride`), შემდეგ ოქმი ჩვეულებრივ ნაწილდება.
"""
from dataclasses import dataclass, field

from sqlalchemy import select

from ..models import ManagerOverride, PersonAlias, Team, TeamMember, User
from .people import clean_name, name_key
from .seed import manager_map

OK = "ok"
UNSORTED = "unsorted"        # ამზომველი Field Group-შია, მაგრამ დღეს არცერთ გუნდში
NOT_FIELD = "not_field"      # არცერთი შემსრულებელი Field Group-ში არ არის


@dataclass
class Resolution:
    status: str
    surveyors: list = field(default_factory=list)      # [(სახელი, User|None)] — მხოლოდ საველე
    excluded: list = field(default_factory=list)       # სახელები, რომლებიც Field Group-ში არ არიან
    managers: list = field(default_factory=list)       # [User] — პასუხისმგებელი პირველია
    departed: list = field(default_factory=list)       # წასული ამზომველები (272-ში აღარ არიან)
    via_override: bool = False

    @property
    def primary(self):
        return self.managers[0] if self.managers else None


class FieldDirectory:
    """ერთხელ იტვირთება ოპერაციაზე (განაწილების გადახედვა, სპორადულის იმპორტი)."""

    def __init__(self, db):
        self.current = manager_map(db)                 # name_key → მენეჯერი (272 + ალიასები)
        self.users = {}
        for u in db.scalars(select(User)):
            self.users.setdefault(u.name_key, u)
        self.field_keys = set()
        self.last_manager = {}                         # წასულისთვის — ბოლო ცნობილი მენეჯერი (მინიშნება)
        for tm in db.scalars(select(TeamMember).join(Team).where(Team.kind == "field")):
            self.field_keys.add(tm.user.name_key)
            if tm.team.manager is not None:
                self.last_manager.setdefault(tm.user.name_key, tm.team.manager)
        for t in db.scalars(select(Team).where(Team.kind == "field")):
            if t.manager is not None:
                self.field_keys.add(t.manager.name_key)
        ids = {u.id: u for u in self.users.values()}
        for a in db.scalars(select(PersonAlias)):
            u = ids.get(a.user_id)
            if u is not None and u.name_key in self.field_keys:
                self.field_keys.add(a.alias_key)
                self.users.setdefault(a.alias_key, u)
        self.overrides = {o.person_key: o.manager for o in db.scalars(select(ManagerOverride))}

    # ── ერთეული პირი ──
    def user(self, name):
        return self.users.get(name_key(name))

    def is_field(self, name) -> bool:
        return name_key(name) in self.field_keys

    def manager_of(self, name):
        """(მენეჯერი, ხელით_მინიჭებულია) — 272-ით, სხვაგვარად QC მენეჯერის მინიჭებით."""
        k = name_key(name)
        m = self.current.get(k)
        if m is not None:
            return m, False
        o = self.overrides.get(k)
        return (o, True) if o is not None else (None, False)

    # ── ოქმი ──
    def resolve(self, names) -> Resolution:
        """`names` — ოქმის შემსრულებლები, **შემდგენი პირველი** (OQMI_CREATOR, MOXAZ_CREATOR, …)."""
        seen, ordered = set(), []
        for n in names:
            n = clean_name(n)
            k = name_key(n)
            if k and k not in seen:
                seen.add(k)
                ordered.append(n)
        res = Resolution(status=OK)
        for n in ordered:
            if self.is_field(n):
                res.surveyors.append((n, self.user(n)))
            else:
                res.excluded.append(n)
        if not res.surveyors:
            res.status = NOT_FIELD
            return res
        for n, _u in res.surveyors:                    # თანმიმდევრობა = პასუხისმგებლობის რიგი
            m, via = self.manager_of(n)
            if m is None:
                res.departed.append(n)
                continue
            res.via_override = res.via_override or via
            if all(m.id != x.id for x in res.managers):
                res.managers.append(m)
        if not res.managers:
            res.status = UNSORTED
        return res

# -*- coding: utf-8 -*-
"""
სიების ერთიანი ფილტრი (T-011): `/qc`, `/field`, `/qc/disagreements`, `/checked`.

ლუკას გადაწყვეტილება (`docs/OPEN_QUESTIONS.md`, „სიების ფილტრები“, 2026-10-26) — ერთი წესი ყველა სიაში:

  • თარიღი — ნახაზის შეტანა (`drawing_date`); „დან“ ჩათვლით, „მდე“ — არა (01.01–02.01 → მხოლოდ 01.01).
    from ≥ to → შედეგი ცარიელია (`empty_range`).
  • ზონა — რამდენიმე, მძიმით ან ჰარით (`50, 73`); სექტორი — მხოლოდ ზონასთან ერთად (`39` ან `43.39`).
  • მენეჯერი / ამზომველი — id ან სახელის ნაწილი; მენეჯერის არჩევისას ამზომველები — მისი გუნდი.
  • ოპერატორი — id; ველის როლებზე იგნორდება და სია ცარიელია (კონტროლი ანონიმურია, T-015).
  • გვერდზე `D.PAGE_SIZE_MIN`..`D.PAGE_SIZE_MAX` ჩანაწერი.

ფილტრი ყოველთვის უკვე scope-ით შეზღუდულ მოთხოვნას ემატება — სხვისი ოქმი ფილტრით არ ჩანს.
"""
import datetime as dt
import re

from sqlalchemy import exists, false, or_, select, true
from sqlalchemy.orm import aliased

from .. import domain as D
from ..models import ItemPerson, QcItem, User
from .stats import team_surveyors

KEYS = ("protocol", "cad", "date_from", "date_to", "zone", "sector", "manager", "surveyor",
        "operator", "verdict", "response", "kind")
LIMITED_KEYS = ("protocol", "cad", "kind")      # ოპერატორის „გასავლელი“ (kind — ჩანართის ჩიპი)
SEARCH_KEYS = ("protocol", "cad", "verdict", "date_from", "date_to")
_SPLIT = re.compile(r"[,\s]+")


def page_size(raw) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return D.PAGE_SIZE_DEFAULT
    return min(max(n, D.PAGE_SIZE_MIN), D.PAGE_SIZE_MAX)


def _date(s):
    try:
        return dt.date.fromisoformat((s or "").strip())
    except ValueError:
        return None


def _tokens(s):
    return [t for t in _SPLIT.split((s or "").strip()) if t]


def _sector(token, zones):
    """`43.39` → [`43.39`]; `39` → ყოველ მითითებულ ზონაზე (`50.39`, `73.39`)."""
    if "." in token:
        z, s = token.split(".", 1)
        return [f"{z.zfill(2)}.{s.zfill(2)}"]
    return [f"{z}.{token.zfill(2)}" for z in zones]


def _person(kind, cond):
    """EXISTS ოქმის ადამიანებში — ერთი ოქმი რამდენჯერმე არ ბრუნდება (ალიასი — scope-ის მსგავსად)."""
    ip = aliased(ItemPerson)
    return exists().where(ip.item_id == QcItem.id, ip.kind == kind, cond(ip)).correlate(QcItem)


def _users_like(like):
    return select(User.id).where(User.full_name.like(like))


class ListFilter:
    """
    `ListFilter(ctx, request.query_params, limited=…, show_status=…)`:
    `apply(stmt)` — WHERE პირობები; `context(db, base)` — შაბლონის `flt` (კონტრაქტი — T-011, ბრიფი).
    """

    def __init__(self, ctx, params, limited=False, show_status=True):
        self.field = ctx.role in D.FIELD_ROLES
        self.limited = limited
        self.show_status = show_status and not limited
        self.per = page_size(params.get("per"))
        v = {k: (params.get(k) or "").strip() for k in KEYS}

        d_from, d_to = _date(v["date_from"]), _date(v["date_to"])
        v["date_from"] = d_from.isoformat() if d_from else ""
        v["date_to"] = d_to.isoformat() if d_to else ""
        self.zones = [t.zfill(2) for t in _tokens(v["zone"])]
        v["zone"] = ", ".join(self.zones)
        self.sectors = sorted({s for t in _tokens(v["sector"]) for s in _sector(t, self.zones)}) \
            if self.zones else []
        v["sector"] = ", ".join(_tokens(v["sector"])) if self.zones else ""
        if not v["operator"].isdigit() or self.field:
            v["operator"] = ""
        if v["verdict"] not in D.VERDICTS or not self.show_status:
            v["verdict"] = ""
        if v["response"] not in D.RESPONSE_LABELS:
            v["response"] = ""
        if v["kind"] not in (D.SYSTEMATIC, D.SPORADIC):
            v["kind"] = ""
        if limited:
            v = {k: (v[k] if k in LIMITED_KEYS else "") for k in KEYS}
            d_from = d_to = None
            self.zones = self.sectors = []
        self.values = v
        self.d_from, self.d_to = d_from, d_to
        self.empty_range = bool(d_from and d_to and d_from >= d_to)

    @property
    def searching(self) -> bool:
        """ძებნა ან სტატუსის / თარიღის ფილტრი — ველის სიაში დახურულიც ჩანს (T-007 Q-02)."""
        return self.empty_range or any(self.values[k] for k in SEARCH_KEYS)

    def apply(self, stmt):
        v = self.values
        if self.empty_range:
            return stmt.where(false())
        if v["protocol"]:
            stmt = stmt.where(QcItem.protocol_number.like(v["protocol"] + "%"))
        if v["cad"]:
            stmt = stmt.where(QcItem.cadcode.like(v["cad"] + "%"))
        if v["kind"]:
            stmt = stmt.where(QcItem.kind == v["kind"])
        if self.zones:
            stmt = stmt.where(QcItem.zone.in_(self.zones))
        if self.sectors:
            stmt = stmt.where(QcItem.sector.in_(self.sectors))
        if v["manager"].isdigit():
            mid = int(v["manager"])
            stmt = stmt.where(or_(QcItem.field_manager_id == mid,
                                  _person(D.P_MANAGER, lambda ip: ip.user_id == mid)))
        elif v["manager"]:
            like = f"%{v['manager']}%"
            stmt = stmt.where(or_(QcItem.field_manager_id.in_(_users_like(like)), _person(
                D.P_MANAGER, lambda ip: or_(ip.name.like(like), ip.user_id.in_(_users_like(like))))))
        if v["surveyor"].isdigit():
            sid = int(v["surveyor"])
            stmt = stmt.where(or_(QcItem.protocol_creator_id == sid,
                                  _person(D.P_SURVEYOR, lambda ip: ip.user_id == sid)))
        elif v["surveyor"]:
            like = f"%{v['surveyor']}%"
            stmt = stmt.where(or_(
                QcItem.protocol_creator_name.like(like), QcItem.protocol_creator_id.in_(_users_like(like)),
                _person(D.P_SURVEYOR, lambda ip: or_(ip.name.like(like), ip.user_id.in_(_users_like(like))))))
        if v["operator"]:
            stmt = stmt.where(QcItem.operator_id == int(v["operator"]))
        if v["verdict"]:
            stmt = stmt.where(QcItem.verdict == v["verdict"])
        if v["response"]:
            stmt = stmt.where(QcItem.field_response == v["response"])
        if self.d_from:
            stmt = stmt.where(QcItem.drawing_date >= dt.datetime.combine(self.d_from, dt.time.min))
        if self.d_to:
            stmt = stmt.where(QcItem.drawing_date < dt.datetime.combine(self.d_to, dt.time.min))
        return stmt

    def context(self, db, base):
        """
        `flt` შაბლონისთვის. `base` — სიის საწყისი `select(QcItem)` (scope + სიის პირობა, მომხმარებლის
        ფილტრის გარეშე): არჩევანის სიებში მხოლოდ ის ხალხია, ვისი ოქმებიც ამ სიაში ჩანს.
        """
        managers, surveyors, operators = [], [], []
        if not self.limited:
            where = base.whereclause if base.whereclause is not None else true()
            managers = self._names(db, select(QcItem.field_manager_id).where(where))
            surveyors = self._names(db, select(ItemPerson.user_id).join(QcItem, QcItem.id == ItemPerson.item_id)
                                    .where(where, ItemPerson.kind == D.P_SURVEYOR,
                                           ItemPerson.user_id.is_not(None)),
                                    self._team(db))
            if not self.field:
                operators = self._names(db, select(QcItem.operator_id).where(where))
        return {"values": dict(self.values), "managers": managers, "surveyors": surveyors,
                "operators": operators, "show_operator": not self.field,
                "show_status": self.show_status, "limited": self.limited, "per": self.per,
                "empty_range": self.empty_range}

    def _team(self, db):
        """არჩეული მენეჯერის (id) გუნდი — `stats.team_surveyors`-ის წესით; სხვა შემთხვევაში None."""
        m = self.values["manager"]
        return [u.id for u in team_surveyors(db, int(m))] if m.isdigit() else None

    @staticmethod
    def _names(db, ids, only=None):
        q = select(User.id, User.full_name).where(User.id.in_(ids))
        if only is not None:
            q = q.where(User.id.in_(only))
        return [tuple(r) for r in db.execute(q.order_by(User.full_name)).all()]


def api_surveyors(db, ctx, manager):
    """
    `GET /api/filters/surveyors?manager=<id>` — მენეჯერის გუნდის ამზომველები.
    QC როლები, ადმინი, კოორდინატორი — ნებისმიერი მენეჯერი; საველე მენეჯერი — მხოლოდ საკუთარი; სხვა — [].
    """
    if not (manager or "").isdigit():
        return []
    mid = int(manager)
    if ctx.role == D.FIELD_MANAGER:
        allowed = mid == ctx.user.id
    else:
        allowed = ctx.role in (*D.QC_ROLES, D.COORDINATOR)
    return [{"id": u.id, "name": u.full_name} for u in team_surveyors(db, mid)] if allowed else []

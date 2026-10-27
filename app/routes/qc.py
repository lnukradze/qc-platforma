# -*- coding: utf-8 -*-
"""
QC სამუშაო სივრცე: გასავლელი / უკან მობრუნებული / გაგზავნილი / დასრულებული.

⚠️ ოპერატორს „გასავლელში" მენეჯერის, ამზომველის, ზონისა და თარიღის ფილტრი **არ აქვს**
   (მომხმარებლის წესი, 2026-10-20): რიგს სისტემა განსაზღვრავს და „შემდეგი ოქმი" ღილაკით
   მიდის — რომ მხოლოდ ერთი მენეჯერის ოქმები არ გაიაროს. გაგზავნილ/დასრულებულ ოქმებში
   ფილტრი რჩება (ძებნისთვის). QC მენეჯერს/ადმინს ყველგან ყველა ფილტრი აქვს.
"""
import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy import case, exists, func, or_, select, true
from sqlalchemy.orm import selectinload

from .. import domain as D
from .. import scope
from ..db import get_db
from ..models import ItemPerson, QcItem, User, VerdictRequest
from ..security import require
from ..services import stats as S
from .common import paginate, qs, redirect, render

router = APIRouter()

QC_ROLES = (D.QC_OPERATOR, D.QC_MANAGER, D.ADMIN)
SENT_STATES = (D.AWAITING_FIELD, D.AWAITING_MANAGER, D.AWAITING_QCM, D.RETURNED_TO_MANAGER)
TABS = {
    "todo": ("გასავლელი", lambda: QcItem.state == D.PENDING),
    "returned": ("უკან მობრუნებული", lambda: QcItem.state == D.AWAITING_QC),
    "sent": ("გაგზავნილი", lambda: QcItem.state.in_(SENT_STATES)),
    "closed": ("დასრულებული", lambda: QcItem.state == D.CLOSED),
}
# რიგი: განაწილების თანმიმდევრობით, ბლოკი ერთად
QUEUE_ORDER = (QcItem.assigned_at.asc().nulls_last(), QcItem.block_key, QcItem.cadcode, QcItem.id)


def restricted_filters(ctx, tab) -> bool:
    """ოპერატორს გასავლელში მხოლოდ ოქმის ნომრით/კოდით ძებნა აქვს."""
    return ctx.role == D.QC_OPERATOR and tab == "todo"


def _filters(stmt, p, limited=False):
    if p.get("protocol"):
        stmt = stmt.where(QcItem.protocol_number.like(p["protocol"].strip() + "%"))
    if p.get("cad"):
        stmt = stmt.where(QcItem.cadcode.like(p["cad"].strip() + "%"))
    if p.get("kind") in (D.SYSTEMATIC, D.SPORADIC):
        stmt = stmt.where(QcItem.kind == p["kind"])
    if limited:
        return stmt
    if p.get("zone"):
        stmt = stmt.where(QcItem.zone == p["zone"].zfill(2))
    if p.get("surveyor"):
        like = f"%{p['surveyor'].strip()}%"
        stmt = stmt.where(or_(QcItem.protocol_creator_name.like(like), exists().where(
            ItemPerson.item_id == QcItem.id, ItemPerson.kind == D.P_SURVEYOR,
            or_(ItemPerson.name.like(like),
                ItemPerson.user_id.in_(select(User.id).where(User.full_name.like(like)))))))
    if p.get("manager", "").isdigit():
        mid = int(p["manager"])
        stmt = stmt.where(or_(QcItem.field_manager_id == mid, exists().where(
            ItemPerson.item_id == QcItem.id, ItemPerson.kind == D.P_MANAGER, ItemPerson.user_id == mid)))
    if p.get("operator", "").isdigit():
        stmt = stmt.where(QcItem.operator_id == int(p["operator"]))
    if p.get("verdict") in D.VERDICTS:
        stmt = stmt.where(QcItem.verdict == p["verdict"])
    if p.get("response") in D.RESPONSE_LABELS:
        stmt = stmt.where(QcItem.field_response == p["response"])
    if p.get("date_from") and _d(p["date_from"]):
        stmt = stmt.where(QcItem.drawing_date >= _d(p["date_from"]))
    if p.get("date_to") and _d(p["date_to"], True):
        stmt = stmt.where(QcItem.drawing_date <= _d(p["date_to"], True))
    return stmt


def _d(s, end=False):
    try:
        d = dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return dt.datetime.combine(d, dt.time.max if end else dt.time.min)


def default_kind(ctx):
    """QC მენეჯერის ნაგულისხმევი მიმართულება (ბექა სალუქვაძე — სპორადული)."""
    prefs = ctx.user.prefs or {}
    return prefs.get("kind") if ctx.role == D.QC_MANAGER else None


def next_pending(db, ctx, after_id=None):
    """ოპერატორის რიგის შემდეგი ოქმი (გასავლელი)."""
    stmt = select(QcItem.id).where(scope.item_filter(ctx), QcItem.state == D.PENDING)
    if after_id:
        stmt = stmt.where(QcItem.id != after_id)
    return db.scalar(stmt.order_by(*QUEUE_ORDER).limit(1))


@router.get("/qc")
def qc_list(request: Request, tab: str = "todo", page: int = 1,
            ctx=Depends(require(*QC_ROLES)), db=Depends(get_db)):
    p = dict(request.query_params)
    if "kind" not in p and default_kind(ctx):
        p["kind"] = default_kind(ctx)
    tab = tab if tab in TABS else "todo"
    limited = restricted_filters(ctx, tab)
    own = scope.item_filter(ctx)
    stmt = _filters(select(QcItem).where(own, TABS[tab][1]()), p, limited)
    stmt = stmt.options(selectinload(QcItem.codes), selectinload(QcItem.field_manager),
                        selectinload(QcItem.operator),
                        selectinload(QcItem.people).selectinload(ItemPerson.user))
    if tab == "todo":
        stmt = stmt.order_by(*QUEUE_ORDER)
    elif tab == "returned":
        stmt = stmt.order_by(QcItem.field_responded_at.asc().nulls_last(), QcItem.id)
    else:
        stmt = stmt.order_by(QcItem.updated_at.desc(), QcItem.id.desc())
    rows, total, page, pages = paginate(db, stmt, page)

    kind_cond = QcItem.kind == p["kind"] if p.get("kind") in (D.SYSTEMATIC, D.SPORADIC) else true()
    vals = db.execute(select(*[func.sum(case((TABS[t][1](), 1), else_=0)) for t in TABS])
                      .where(own, kind_cond)).one()
    counts = {t: (v or 0) for t, v in zip(TABS, vals)}
    operators = []
    if ctx.role in (D.QC_MANAGER, D.ADMIN):
        operators = db.execute(select(User.id, User.full_name).join(QcItem, QcItem.operator_id == User.id)
                               .group_by(User.id, User.full_name).order_by(User.full_name)).all()
    managers = [] if limited else db.execute(
        select(User.id, User.full_name).join(QcItem, QcItem.field_manager_id == User.id)
        .where(own).group_by(User.id, User.full_name).order_by(User.full_name)).all()
    daily = S.operator_daily(db, ctx.user.id) if ctx.role == D.QC_OPERATOR else None
    tpl = "qc/_table.html" if request.headers.get("hx-request") else "qc/list.html"
    return render(request, ctx, tpl, active="qc", rows=rows, total=total, page=page, pages=pages,
                  tab=tab, tabs=TABS, p=p, counts=counts, operators=operators, managers=managers,
                  limited=limited, daily=daily, qs=lambda **o: qs(p, **o))


@router.get("/qc/next")
def qc_next(request: Request, after: int = 0, ctx=Depends(require(*QC_ROLES)), db=Depends(get_db)):
    nid = next_pending(db, ctx, after or None)
    if nid is None:
        return redirect("/qc?tab=todo", ok="გასავლელი ოქმი აღარ დარჩა.")
    return redirect(f"/items/{nid}?back=/qc%3Ftab%3Dtodo&queue=1")


@router.get("/qc/disputes")
def disputes_old():
    return redirect("/qc/disagreements")


@router.get("/qc/disagreements")
def disagreements(request: Request, page: int = 1, ctx=Depends(require(D.QC_MANAGER, D.ADMIN)),
                  db=Depends(get_db)):
    """არ დათანხმებულები: ველმა „არ ვეთანხმები" გასცა და საველე მენეჯერმა დაადასტურა."""
    p = dict(request.query_params)
    if "kind" not in p and default_kind(ctx):
        p["kind"] = default_kind(ctx)
    stmt = select(QcItem).where(QcItem.state == D.AWAITING_QCM)
    stmt = _filters(stmt, p).options(selectinload(QcItem.codes), selectinload(QcItem.operator),
                                     selectinload(QcItem.field_manager),
                                     selectinload(QcItem.people).selectinload(ItemPerson.user))
    stmt = stmt.order_by(QcItem.field_responded_at.asc().nulls_last(), QcItem.id)
    rows, total, page, pages = paginate(db, stmt, page, 25)
    by_kind = dict(db.execute(select(QcItem.kind, func.count()).where(QcItem.state == D.AWAITING_QCM)
                              .group_by(QcItem.kind)).all())
    operators = db.execute(select(User.id, User.full_name).join(QcItem, QcItem.operator_id == User.id)
                           .where(QcItem.state == D.AWAITING_QCM).group_by(User.id, User.full_name)
                           .order_by(User.full_name)).all()
    return render(request, ctx, "qc/disputes.html", active="disputes", rows=rows, total=total,
                  page=page, pages=pages, p=p, operators=operators, by_kind=by_kind,
                  qs=lambda **o: qs(p, **o))


@router.get("/qc/requests")
def verdict_requests(request: Request, ctx=Depends(require(D.QC_MANAGER, D.ADMIN)),
                     db=Depends(get_db)):
    """ოპერატორების მოთხოვნები გაგზავნილი სტატუსის შეცვლაზე."""
    pending = db.scalars(select(VerdictRequest).where(VerdictRequest.status == "pending")
                         .options(selectinload(VerdictRequest.item), selectinload(VerdictRequest.requested_by))
                         .order_by(VerdictRequest.requested_at)).all()
    recent = db.scalars(select(VerdictRequest).where(VerdictRequest.status != "pending")
                        .options(selectinload(VerdictRequest.item), selectinload(VerdictRequest.requested_by),
                                 selectinload(VerdictRequest.decided_by))
                        .order_by(VerdictRequest.decided_at.desc()).limit(30)).all()
    return render(request, ctx, "qc/requests.html", active="requests", pending=pending, recent=recent)


@router.get("/checked")
def checked(request: Request, page: int = 1,
            ctx=Depends(require(D.COORDINATOR, D.QC_MANAGER, D.ADMIN)), db=Depends(get_db)):
    """კოორდინატორი: კონტროლის გავლილი ოქმები — მხოლოდ ნახვით (რედაქტირების უფლება არ აქვს)."""
    p = dict(request.query_params)
    stmt = _filters(scope.items_query(ctx).where(QcItem.first_sent_at.is_not(None)), p)
    stmt = stmt.options(selectinload(QcItem.codes), selectinload(QcItem.field_manager),
                        selectinload(QcItem.operator),
                        selectinload(QcItem.people).selectinload(ItemPerson.user))
    stmt = stmt.order_by(QcItem.first_sent_at.desc(), QcItem.id.desc())
    rows, total, page, pages = paginate(db, stmt, page)
    operators = db.execute(select(User.id, User.full_name).join(QcItem, QcItem.operator_id == User.id)
                           .group_by(User.id, User.full_name).order_by(User.full_name)).all()
    managers = db.execute(select(User.id, User.full_name).join(QcItem, QcItem.field_manager_id == User.id)
                          .group_by(User.id, User.full_name).order_by(User.full_name)).all()
    return render(request, ctx, "qc/checked.html", active="checked", rows=rows, total=total,
                  page=page, pages=pages, tab="checked", p=p, operators=operators,
                  managers=managers, list_url="/checked", qs=lambda **o: qs(p, **o))

# -*- coding: utf-8 -*-
"""ველის მხარე: ამზომველი და საველე მენეჯერი.

ჩანართები: სისტემური / სპორადული / მენეჯერზე მიწერილი-დაბრუნებული.
ველზე მხოლოდ უარყოფითი, რეკომენდაცია და დაზუსტება მოდის — დადებითი არა.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import case, func, select, true
from sqlalchemy.orm import selectinload

from .. import domain as D
from .. import scope
from ..db import get_db
from ..models import ItemPerson, QcItem
from ..security import require
from ..services.listfilter import ListFilter
from .common import paginate, qs, render

router = APIRouter()

FIELD_ROLES = (D.SURVEYOR, D.FIELD_MANAGER, D.ADMIN)
MANAGER_STATES = (D.AWAITING_MANAGER, D.RETURNED_TO_MANAGER)
ORDER = case((QcItem.state == D.AWAITING_FIELD, 0), (QcItem.state == D.AWAITING_MANAGER, 1),
             (QcItem.state == D.RETURNED_TO_MANAGER, 1), (QcItem.state == D.CLOSED, 3), else_=2)


@router.get("/field")
def field_list(request: Request, tab: str = "systematic", page: int = 1,
               ctx=Depends(require(*FIELD_ROLES)), db=Depends(get_db)):
    p = dict(request.query_params)
    own = scope.item_filter(ctx) & scope.field_visible()
    base = stmt = select(QcItem).where(own)
    if tab not in ("manager", "cc", D.SYSTEMATIC, D.SPORADIC):
        tab = D.SYSTEMATIC
    if tab == "cc" and ctx.role != D.FIELD_MANAGER:
        tab = D.SYSTEMATIC
    if tab == "manager":
        stmt = stmt.where(QcItem.state.in_(MANAGER_STATES))
        if ctx.role == D.FIELD_MANAGER:                 # მოქმედება — მხოლოდ პასუხისმგებელს
            stmt = stmt.where(QcItem.field_manager_id == ctx.user.id)
    elif tab == "cc":                                   # სხვა გუნდის ოქმი, სადაც ჩემი ამზომველიცაა
        stmt = stmt.where(QcItem.field_manager_id != ctx.user.id)
    else:
        stmt = stmt.where(QcItem.kind == tab)
    f = ListFilter(ctx, p)
    stmt = f.apply(stmt)
    if p.get("state") in D.STATES:
        stmt = stmt.where(QcItem.state == p["state"])
    elif p.get("state") == "open" or not f.searching:
        # საბოლოოდ დადასტურებული — მხოლოდ ფილტრით / ძებნით (ლუკა, 2026-10-27, T-007 Q-02)
        stmt = stmt.where(QcItem.state != D.CLOSED)
    stmt = stmt.options(selectinload(QcItem.codes), selectinload(QcItem.operator),
                        selectinload(QcItem.field_manager),
                        selectinload(QcItem.people).selectinload(ItemPerson.user))
    stmt = stmt.order_by(ORDER, QcItem.sent_at.desc().nulls_last(), QcItem.id.desc())
    rows, total, page, pages = paginate(db, stmt, page, f.per)

    primary = QcItem.field_manager_id == ctx.user.id if ctx.role == D.FIELD_MANAGER else true()
    c = db.execute(select(
        func.sum(case(((QcItem.kind == D.SYSTEMATIC) & (QcItem.state == D.AWAITING_FIELD), 1), else_=0)),
        func.sum(case(((QcItem.kind == D.SPORADIC) & (QcItem.state == D.AWAITING_FIELD), 1), else_=0)),
        func.sum(case((QcItem.state.in_(MANAGER_STATES) & primary, 1), else_=0)),
        func.sum(case(((QcItem.state == D.AWAITING_MANAGER) & primary, 1), else_=0)),
        func.sum(case(((QcItem.state == D.RETURNED_TO_MANAGER) & primary, 1), else_=0)),
        func.sum(case((QcItem.field_manager_id != ctx.user.id, 1), else_=0)),
    ).where(own)).one()
    counts = {"systematic": c[0] or 0, "sporadic": c[1] or 0, "manager": c[2] or 0,
              "awaiting_manager": c[3] or 0, "returned": c[4] or 0,
              "cc": (c[5] or 0) if ctx.role == D.FIELD_MANAGER else 0}
    flt = f.context(db, base)
    # ძველი context — მიმდინარე შაბლონისთვის, T-012 ბ-მდე
    surveyors = flt["surveyors"] if ctx.role in (D.FIELD_MANAGER, D.ADMIN) else []
    tpl = "field/_table.html" if request.headers.get("hx-request") else "field/list.html"
    return render(request, ctx, tpl, active="field", rows=rows, total=total, page=page,
                  pages=pages, tab=tab, p=p, counts=counts, surveyors=surveyors, flt=flt,
                  qs=lambda **o: qs(p, **o))

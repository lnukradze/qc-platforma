# -*- coding: utf-8 -*-
"""მთავარი გვერდი (როლის მიხედვით) და „სისტემის შესახებ"."""
import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy import case, func, select

from .. import domain as D
from .. import scope
from ..db import get_db
from ..models import (DistributionRun, ImportRun, PreqcCheck, QcEvent, QcItem, User, UserRole,
                      VerdictRequest)
from ..security import current
from ..services import stats as S
from ..services.distribution import source
from .common import render

router = APIRouter()


def _color_counts(db, cond):
    draft = QcItem.draft_saved_at.is_not(None)
    rows = db.execute(select(QcItem.state, QcItem.kind, draft, func.count()).where(cond)
                      .group_by(QcItem.state, QcItem.kind, draft)).all()
    out = {"gray": 0, "draft": 0, "lightgreen": 0, "green": 0, "yellow": 0}
    kinds = {D.SYSTEMATIC: dict(out), D.SPORADIC: dict(out)}
    for st, kind, is_draft, n in rows:
        c = D.operator_color(st, bool(is_draft))
        out[c] += n
        kinds[kind][c] += n
    return out, kinds


@router.get("/")
def home(request: Request, ctx=Depends(current), db=Depends(get_db)):
    r = ctx.role
    data = {}
    if r == D.QC_OPERATOR:
        data["colors"], data["kinds"] = _color_counts(db, QcItem.operator_id == ctx.user.id)
        data["daily"] = S.operator_daily(db, ctx.user.id)
    if r in (D.QC_MANAGER, D.ADMIN):
        rows = db.execute(
            select(User.id, User.full_name,
                   func.sum(case((QcItem.state == D.PENDING, 1), else_=0)),
                   func.sum(case((QcItem.state == D.AWAITING_QC, 1), else_=0)),
                   func.sum(case((QcItem.state.in_([D.AWAITING_FIELD, D.AWAITING_MANAGER,
                                                    D.AWAITING_QCM, D.RETURNED_TO_MANAGER]), 1), else_=0)),
                   func.sum(case((QcItem.state == D.CLOSED, 1), else_=0)))
            .join(User, User.id == QcItem.operator_id).group_by(User.id, User.full_name)
            .order_by(User.full_name)).all()
        data["operators"] = [{"id": i, "name": n, "gray": a or 0, "yellow": b or 0,
                              "lightgreen": c or 0, "green": d or 0} for i, n, a, b, c, d in rows]
        data["disputes"] = db.scalar(select(func.count()).where(QcItem.state == D.AWAITING_QCM))
        data["requests"] = db.scalar(select(func.count()).where(VerdictRequest.status == "pending"))
        data["last_run"] = db.scalar(select(DistributionRun).order_by(DistributionRun.id.desc()))
        data["colors"], data["kinds"] = _color_counts(db, scope.item_filter(ctx))
    if r in (D.FIELD_MANAGER, D.SURVEYOR):
        cond = scope.item_filter(ctx) & scope.field_visible()
        rows = dict(db.execute(select(QcItem.state, func.count()).where(cond)
                               .group_by(QcItem.state)).all())
        data["field"] = rows
        pq = select(func.count(PreqcCheck.id), func.sum(case((PreqcCheck.status == "fail", 1), else_=0)))
        pq = pq.where(PreqcCheck.surveyor_id == ctx.user.id) if r == D.SURVEYOR else \
            pq.where(PreqcCheck.field_manager_id == ctx.user.id)
        data["preqc"] = db.execute(pq).one()
    data["kpi"] = S.kpi(db, ctx, S.parse_filters({}))
    if r == D.ADMIN:
        data["users"] = db.scalar(select(func.count(User.id)).where(User.active.is_(True)))
        data["no_email"] = db.scalar(select(func.count(User.id)).where(User.active.is_(True),
                                                                      User.email.is_(None)))
        data["import"] = db.scalar(select(ImportRun).order_by(ImportRun.id.desc()))
        data["source"] = source.source_info()
    recent = db.execute(select(QcEvent).join(QcItem).where(scope.item_filter(ctx),
                                                          scope.event_filter(ctx),
                                                          QcEvent.action != "legacy_import")
                        .order_by(QcEvent.id.desc()).limit(8)).scalars().all() \
        if r not in (D.COORDINATOR, D.HEAD_OF_SERVICE) else []
    return render(request, ctx, "home.html", active="home", data=data, recent=recent)


@router.get("/about")
def about(request: Request, ctx=Depends(current), db=Depends(get_db)):
    imp = db.scalar(select(ImportRun).order_by(ImportRun.id.desc()))
    counts = {
        "items": db.scalar(select(func.count(QcItem.id))),
        "legacy": db.scalar(select(func.count(QcItem.id)).where(QcItem.is_legacy.is_(True))),
        "users": db.scalar(select(func.count(User.id))),
        "events": db.scalar(select(func.count(QcEvent.id))),
        "preqc": db.scalar(select(func.count(PreqcCheck.id))),
    }
    return render(request, ctx, "about.html", active="about", imp=imp, counts=counts,
                  source=source.source_info())

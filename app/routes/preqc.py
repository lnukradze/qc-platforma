# -*- coding: utf-8 -*-
"""Pre-QC ხარვეზები — ამ ეტაპზე ფიქსირებული სადემონსტრაციო მონაცემით.

Pre-QC მხოლოდ საველე მენეჯერს და ამზომველს უჩანს — სხვას არავის (მომხმარებლის წესი,
2026-10-20); კონტროლის შეფასება დამოუკიდებელი რჩება.
"""
import datetime as dt
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from .. import domain as D
from .. import scope
from ..db import get_db
from ..models import Mission, PreqcCheck, PreqcFinding, Setting, User
from ..security import current
from ..services.preqc_demo import mission_day, schedule_for
from .common import paginate, qs, render

router = APIRouter()
STATUS_LABELS = {"pass": "მზადაა", "warn": "გასასწორებელია (რეკომენდაცია)",
                 "review": "ხელით გადასამოწმებელი", "fail": "გასასწორებელია"}


def _guard(ctx):
    if not scope.can_see_preqc(ctx):
        raise HTTPException(403, "Pre-QC ხარვეზები მხოლოდ საველე მენეჯერს და ამზომველს უჩანს "
                                 "(კონტროლის შეფასება დამოუკიდებელი რჩება).")


def _scope(stmt, ctx):
    if ctx.role == D.SURVEYOR:
        return stmt.where(PreqcCheck.surveyor_id == ctx.user.id)
    if ctx.role == D.FIELD_MANAGER:
        return stmt.where(PreqcCheck.field_manager_id == ctx.user.id)
    return stmt


@router.get("/preqc")
def preqc(request: Request, page: int = 1, ctx=Depends(current), db=Depends(get_db)):
    _guard(ctx)
    p = dict(request.query_params)
    missions = db.scalars(select(Mission).order_by(Mission.n)).all()
    lag_s = db.get(Setting, "preqc_lag_days")
    lag = int(lag_s.value) if lag_s else 2
    today = dt.date.today()
    cur, cur_day = mission_day(missions, today)
    demo_mission = db.get(Mission, 14)
    stmt = _scope(select(PreqcCheck), ctx)
    if p.get("surveyor", "").isdigit():
        stmt = stmt.where(PreqcCheck.surveyor_id == int(p["surveyor"]))
    if p.get("status") in STATUS_LABELS:
        stmt = stmt.where(PreqcCheck.status == p["status"])
    if p.get("day"):
        try:
            stmt = stmt.where(PreqcCheck.protocol_date == dt.date.fromisoformat(p["day"]))
        except ValueError:
            pass
    if p.get("code"):
        stmt = stmt.where(PreqcCheck.id.in_(select(PreqcFinding.check_id)
                                            .where(PreqcFinding.official_code == p["code"])))
    all_checks = db.scalars(_scope(select(PreqcCheck), ctx)
                           .options(selectinload(PreqcCheck.findings))).all()
    st = Counter(c.status for c in all_checks)
    codes = Counter(f.official_code for c in all_checks for f in c.findings if f.official_code)
    per_surv = defaultdict(Counter)
    for c in all_checks:
        per_surv[c.surveyor_id][c.status] += 1
    names = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(per_surv)))}
    by_day = Counter(c.protocol_date for c in all_checks)
    stmt = stmt.options(selectinload(PreqcCheck.findings), selectinload(PreqcCheck.surveyor)) \
        .order_by(PreqcCheck.checked_on.desc(), PreqcCheck.id.desc())
    rows, total, page, pages = paginate(db, stmt, page, 30)
    avg = round(sum(c.score for c in all_checks) / len(all_checks)) if all_checks else None
    return render(request, ctx, "preqc/index.html", active="preqc", rows=rows, total=total,
                  page=page, pages=pages, p=p, qs=lambda **o: qs(p, **o), status=st,
                  codes=codes.most_common(10), per_surv=per_surv, names=names, avg=avg,
                  n=len(all_checks), labels=STATUS_LABELS, current=cur, cur_day=cur_day, lag=lag,
                  sched_cur=schedule_for(cur, lag, today) if cur else [],
                  sched_demo=schedule_for(demo_mission, lag, today) if demo_mission else [],
                  demo_mission=demo_mission, by_day=by_day)


@router.get("/preqc/{check_id}")
def preqc_detail(check_id: int, request: Request, ctx=Depends(current), db=Depends(get_db)):
    _guard(ctx)
    c = db.scalar(_scope(select(PreqcCheck).where(PreqcCheck.id == check_id), ctx)
                  .options(selectinload(PreqcCheck.findings), selectinload(PreqcCheck.surveyor)))
    if c is None:
        raise HTTPException(404, "შემოწმება ვერ მოიძებნა.")
    return render(request, ctx, "preqc/detail.html", active="preqc", c=c, labels=STATUS_LABELS)

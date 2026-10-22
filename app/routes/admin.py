# -*- coding: utf-8 -*-
"""ადმინისტრირება: მომხმარებლები და როლები, გუნდები, კოდები, პარამეტრები, იმპორტი, აუდიტი."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from .. import domain as D
from ..db import get_db
from fastapi.responses import HTMLResponse

from ..config import SMTP_HOST
from ..models import (AuditLog, DefectCode, EmailMessage, ImportRun, Setting, Team, TeamMember, User,
                      UserRole)
from ..security import audit, require, same_origin
from ..services.people import name_key
from .common import paginate, qs, redirect, render

router = APIRouter()
ADMIN = require(D.ADMIN)


@router.get("/admin")
def users(request: Request, page: int = 1, ctx=Depends(ADMIN), db=Depends(get_db)):
    p = dict(request.query_params)
    stmt = select(User).options(selectinload(User.roles))
    if p.get("q"):
        stmt = stmt.where(or_(User.full_name.like(f"%{p['q'].strip()}%"),
                              User.email.like(f"%{p['q'].strip()}%")))
    if p.get("role") in D.ROLES:
        stmt = stmt.where(User.id.in_(select(UserRole.user_id).where(UserRole.role == p["role"])))
    if p.get("status") == "active":
        stmt = stmt.where(User.active.is_(True))
    elif p.get("status") == "inactive":
        stmt = stmt.where(User.active.is_(False))
    if p.get("email") == "missing":
        stmt = stmt.where(User.email.is_(None), User.active.is_(True))
    stmt = stmt.order_by(User.active.desc(), User.full_name)
    rows, total, page, pages = paginate(db, stmt, page, 40)
    team_of = {}
    for tm in db.scalars(select(TeamMember).where(TeamMember.valid_to.is_(None))
                         .options(selectinload(TeamMember.team))):
        team_of.setdefault(tm.user_id, tm.team.name)
    stats = {
        "active": db.scalar(select(func.count(User.id)).where(User.active.is_(True))),
        "no_email": db.scalar(select(func.count(User.id)).where(User.active.is_(True), User.email.is_(None))),
        "by_role": dict(db.execute(select(UserRole.role, func.count()).join(User)
                                   .where(User.active.is_(True)).group_by(UserRole.role)).all()),
    }
    return render(request, ctx, "admin/users.html", active="admin", rows=rows, total=total,
                  page=page, pages=pages, p=p, qs=lambda **o: qs(p, **o), team_of=team_of, stats=stats)


@router.get("/admin/users/{user_id}")
def user_edit(user_id: int, request: Request, ctx=Depends(ADMIN), db=Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "მომხმარებელი ვერ მოიძებნა.")
    teams = db.scalars(select(Team).where(Team.kind == "field", Team.active.is_(True))
                       .order_by(Team.name)).all()
    current_team = db.scalar(select(TeamMember).where(TeamMember.user_id == u.id,
                                                      TeamMember.valid_to.is_(None)))
    return render(request, ctx, "admin/user_edit.html", active="admin", u=u, teams=teams,
                  current_team=current_team)


@router.post("/admin/users/{user_id}")
async def user_save(user_id: int, request: Request, ctx=Depends(ADMIN), db=Depends(get_db)):
    same_origin(request)
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "მომხმარებელი ვერ მოიძებნა.")
    form = await request.form()
    email = (form.get("email") or "").strip().lower() or None
    if email and db.scalar(select(User).where(User.email == email, User.id != u.id)):
        return redirect(f"/admin/users/{u.id}", err="ეს ელფოსტა სხვა მომხმარებელს უკვე აქვს.")
    roles = {r for r in form.getlist("roles") if r in D.ROLES}
    if u.id == ctx.user.id and D.ADMIN not in roles:
        return redirect(f"/admin/users/{u.id}", err="საკუთარ თავს ადმინის როლს ვერ მოხსნით.")
    before = {"email": u.email, "roles": sorted(u.role_set), "active": u.active}
    u.email = email
    u.full_name = (form.get("full_name") or u.full_name).strip()
    u.active = form.get("active") == "on"
    for r in list(u.roles):
        if r.role not in roles:
            db.delete(r)
    for r in roles - u.role_set:
        u.roles.append(UserRole(role=r))
    team_id = form.get("team_id")
    cur = db.scalar(select(TeamMember).where(TeamMember.user_id == u.id, TeamMember.valid_to.is_(None)))
    if team_id and (cur is None or str(cur.team_id) != team_id):
        import datetime as dt
        if cur:
            cur.valid_to = dt.date.today()
        db.add(TeamMember(team_id=int(team_id), user_id=u.id, valid_from=dt.date.today(),
                          source="admin"))
    audit(db, ctx.user, "user_updated", "user", u.id,
          {"before": before, "after": {"email": email, "roles": sorted(roles), "active": u.active}},
          request)
    db.commit()
    return redirect(f"/admin/users/{u.id}", ok="შენახულია.")


@router.post("/admin/users")
async def user_create(request: Request, ctx=Depends(ADMIN), db=Depends(get_db)):
    same_origin(request)
    form = await request.form()
    name = (form.get("full_name") or "").strip()
    if not name:
        return redirect("/admin", err="მიუთითეთ სახელი და გვარი.")
    if db.scalar(select(User).where(User.name_key == name_key(name))):
        return redirect("/admin", err="ასეთი სახელით მომხმარებელი უკვე არსებობს.")
    u = User(full_name=name, name_key=name_key(name), email=(form.get("email") or "").strip().lower() or None,
             source="admin")
    role = form.get("role")
    if role in D.ROLES:
        u.roles.append(UserRole(role=role))
    db.add(u)
    db.flush()
    audit(db, ctx.user, "user_created", "user", u.id, {"role": role}, request)
    db.commit()
    return redirect(f"/admin/users/{u.id}", ok="მომხმარებელი შეიქმნა.")


@router.get("/admin/teams")
def teams(request: Request, ctx=Depends(ADMIN), db=Depends(get_db)):
    ts = db.scalars(select(Team).options(selectinload(Team.members).selectinload(TeamMember.user),
                                         selectinload(Team.manager))
                    .order_by(Team.kind.desc(), Team.active.desc(), Team.name)).all()
    return render(request, ctx, "admin/teams.html", active="admin", teams=ts)


@router.get("/admin/codes")
def codes(request: Request, ctx=Depends(ADMIN), db=Depends(get_db)):
    cs = db.scalars(select(DefectCode).order_by(DefectCode.sort)).all()
    return render(request, ctx, "admin/codes.html", active="admin", codes=cs)


@router.post("/admin/codes/{code}")
async def code_save(code: str, request: Request, ctx=Depends(ADMIN), db=Depends(get_db)):
    same_origin(request)
    c = db.get(DefectCode, code)
    if c is None:
        raise HTTPException(404, "კოდი ვერ მოიძებნა.")
    form = await request.form()
    before = {"name": c.name, "severity": c.severity, "active": c.active}
    c.name = (form.get("name") or c.name).strip()
    if form.get("severity") in ("Critical", "Major", "pending"):
        c.severity = form.get("severity")
    c.active = form.get("active") == "on"
    audit(db, ctx.user, "code_updated", "defect_code", None,
          {"code": code, "before": before, "after": {"name": c.name, "severity": c.severity,
                                                     "active": c.active}}, request)
    db.commit()
    return redirect("/admin/codes", ok=f"{code} შენახულია.")


@router.get("/admin/settings")
def settings(request: Request, ctx=Depends(ADMIN), db=Depends(get_db)):
    s = {x.key: x.value for x in db.scalars(select(Setting))}
    return render(request, ctx, "admin/settings.html", active="admin", s=s)


@router.post("/admin/settings")
async def settings_save(request: Request, ctx=Depends(ADMIN), db=Depends(get_db)):
    same_origin(request)
    form = await request.form()
    allowed = {}
    for v in (D.NEGATIVE, D.RECOMMENDATION, D.CLARIFICATION):
        allowed[v] = [r for r in form.getlist(f"resp_{v}") if r in D.RESPONSE_LABELS]
        if not allowed[v]:
            return redirect("/admin/settings", err="თითო ვერდიქტზე მინიმუმ ერთი პასუხი უნდა იყოს დაშვებული.")
    dist = dict((db.get(Setting, "distribution_defaults").value or {}) if db.get(Setting, "distribution_defaults") else {})
    try:
        dist["default_pct"] = max(0, min(100, int(form.get("default_pct") or 70)))
        dist["per_operator"] = max(1, int(form.get("per_operator") or 450))
    except ValueError:
        return redirect("/admin/settings", err="პროცენტი და რაოდენობა რიცხვი უნდა იყოს.")
    vals = {
        "allowed_responses": allowed,
        "distribution_defaults": dist,
        "preqc_lag_days": int(form.get("preqc_lag_days") or 2),
    }
    for k, v in vals.items():
        row = db.get(Setting, k)
        if row is None:
            db.add(Setting(key=k, value=v))
        else:
            row.value = v
    audit(db, ctx.user, "settings_updated", "settings", None, vals, request)
    db.commit()
    return redirect("/admin/settings", ok="პარამეტრები შენახულია.")


@router.get("/admin/import")
def import_page(request: Request, ctx=Depends(ADMIN), db=Depends(get_db)):
    runs = db.scalars(select(ImportRun).order_by(ImportRun.id.desc()).limit(5)).all()
    return render(request, ctx, "admin/import.html", active="admin", runs=runs)


@router.get("/admin/audit")
def audit_page(request: Request, page: int = 1, ctx=Depends(ADMIN), db=Depends(get_db)):
    stmt = select(AuditLog).options(selectinload(AuditLog.actor)).order_by(AuditLog.id.desc())
    rows, total, page, pages = paginate(db, stmt, page, 50)
    return render(request, ctx, "admin/audit.html", active="admin", rows=rows, total=total,
                  page=page, pages=pages, qs=lambda **o: qs({}, **o))


@router.get("/admin/emails")
def emails(request: Request, page: int = 1, ctx=Depends(ADMIN), db=Depends(get_db)):
    """მეილების ჟურნალი — SMTP-ის გარეშე აქ ჩანს, რა წავიდოდა და ვის."""
    stmt = (select(EmailMessage).options(selectinload(EmailMessage.to_user),
                                         selectinload(EmailMessage.created_by))
            .order_by(EmailMessage.id.desc()))
    rows, total, page, pages = paginate(db, stmt, page, 40)
    return render(request, ctx, "admin/emails.html", active="admin", rows=rows, total=total,
                  page=page, pages=pages, smtp=bool(SMTP_HOST), qs=lambda **o: qs({}, **o))


@router.get("/admin/emails/{eid}")
def email_view(eid: int, ctx=Depends(require(D.ADMIN, D.QC_MANAGER, D.QC_OPERATOR)),
               db=Depends(get_db)):
    m = db.get(EmailMessage, eid)
    if m is None or (ctx.role == D.QC_OPERATOR and m.created_by_id != ctx.user.id):
        raise HTTPException(404, "მეილი ვერ მოიძებნა.")
    return HTMLResponse(m.html, headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:"})

# -*- coding: utf-8 -*-
"""შესვლა/გასვლა. პროტოტიპში — მომხმარებლის არჩევით (დემო); საწარმოოში — Google OIDC."""
import hmac
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import domain as D
from ..config import (DEMO_LOGIN, DEMO_PIN, GOOGLE_CLIENT_ID, SESSION_COOKIE, SESSION_HOURS,
                      SESSION_SECRET)
from ..db import get_db
from ..models import User, UserRole
from ..security import create_session, read_session, revoke, same_origin, switch_role
from ..templating import templates
from .google_auth import enabled as google_enabled

router = APIRouter()

# შესვლის გვერდზე — თითო როლში რამდენი ადამიანი ჩანს ძებნის გარეშე
SHOW_PER_ROLE = 14

# LAN-ზე ჩვენება: სანამ PIN არ შეიყვანება, მომხმარებლების სია არ ჩანს
PIN_COOKIE = "qcp_demo_pin"
_pin_signer = URLSafeTimedSerializer(SESSION_SECRET, salt="qcp-demo-pin")


def _pin_ok(request: Request) -> bool:
    if not DEMO_PIN:
        return True
    raw = request.cookies.get(PIN_COOKIE)
    if not raw:
        return False
    try:
        return _pin_signer.loads(raw, max_age=SESSION_HOURS * 3600) == "ok"
    except BadSignature:
        return False


@router.get("/login")
def login_page(request: Request, next: str = "/", db=Depends(get_db)):
    s, u = read_session(request)
    if u is not None:
        return RedirectResponse(next or "/", status_code=303)
    if DEMO_LOGIN and not _pin_ok(request):
        return templates.TemplateResponse(request, "login.html", {
            "groups": {}, "next": next, "demo": DEMO_LOGIN, "google": google_enabled(),
            "show": SHOW_PER_ROLE, "pin_required": True, "err": request.query_params.get("err")})
    users = db.scalars(select(User).where(User.active.is_(True))
                       .options(selectinload(User.roles)).order_by(User.full_name)).all()
    groups = {r: [] for r in (D.ADMIN, D.QC_MANAGER, D.QC_OPERATOR, D.COORDINATOR,
                              D.FIELD_MANAGER, D.SURVEYOR)}
    for u in users:
        for r in u.role_set:
            if r in groups:
                groups[r].append(u)
    # სადემონსტრაციო ამზომველები სიის თავში (Pre-QC-ის საჩვენებლად)
    groups[D.SURVEYOR].sort(key=lambda u: (not u.is_demo, u.full_name))
    groups[D.FIELD_MANAGER].sort(key=lambda u: (not u.is_demo, u.full_name))
    return templates.TemplateResponse(request, "login.html", {
        "groups": groups, "next": next, "demo": DEMO_LOGIN, "google": google_enabled(),
        "show": SHOW_PER_ROLE, "err": request.query_params.get("err")})


@router.post("/login/demo")
def login_demo(request: Request, user_id: int = Form(...), role: str = Form(""),
               next: str = Form("/"), db=Depends(get_db)):
    same_origin(request)
    if not DEMO_LOGIN:
        return RedirectResponse("/login?err=demo_off", status_code=303)
    if not _pin_ok(request):
        return RedirectResponse("/login?err=pin", status_code=303)
    u = db.get(User, user_id)
    if u is None or not u.active:
        return RedirectResponse("/login?err=user", status_code=303)
    token = create_session(db, u, request, role or None)
    resp = RedirectResponse(next if next.startswith("/") else "/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax",
                    max_age=SESSION_HOURS * 3600)
    return resp


@router.post("/login/pin")
def login_pin(request: Request, pin: str = Form(""), next: str = Form("/")):
    same_origin(request)
    if not DEMO_PIN or not hmac.compare_digest(pin.strip(), DEMO_PIN):
        time.sleep(1)                                   # შერჩევით გამოცნობის შენელება
        return RedirectResponse("/login?err=pin", status_code=303)
    resp = RedirectResponse("/login?next=" + (next if next.startswith("/") else "/"),
                            status_code=303)
    resp.set_cookie(PIN_COOKIE, _pin_signer.dumps("ok"), httponly=True, samesite="lax",
                    max_age=SESSION_HOURS * 3600)
    return resp


@router.post("/logout")
def logout(request: Request, db=Depends(get_db)):
    same_origin(request)
    revoke(db, request)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@router.post("/role")
def change_role(request: Request, role: str = Form(...), db=Depends(get_db)):
    same_origin(request)
    switch_role(db, request, role)
    return RedirectResponse("/", status_code=303)

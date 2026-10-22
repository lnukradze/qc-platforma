# -*- coding: utf-8 -*-
"""
შესვლა, სესია და უფლებები.

  • სესია სერვერის მხარეს ინახება (`sessions` ცხრილი); cookie-ში მხოლოდ
    ხელმოწერილი sid დევს — გასვლა ან მომხმარებლის გათიშვა მაშინვე მოქმედებს.
  • ყოველი გვერდი/API აქტიურ როლს სერვერზე ამოწმებს; ინტერფეისში დამალვა
    უსაფრთხოება არ არის.
  • მდგომარეობის შემცვლელ მოთხოვნებზე — იგივე წყაროს შემოწმება (CSRF).

🔒 პროტოტიპში შესვლა მომხმარებლის არჩევით ხდება (დემო რეჟიმი). საწარმოოში
   იგივე სესიის მექანიზმი Google OIDC-ის შემდეგ ირთვება — მხოლოდ იმ
   ელფოსტებისთვის, რომლებიც ადმინმა დაარეგისტრირა.
"""
import datetime as dt
import secrets
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeSerializer

from . import domain as D
from .config import SESSION_COOKIE, SESSION_HOURS, SESSION_SECRET
from .db import SessionLocal
from .models import AuditLog, Session, User

_signer = URLSafeSerializer(SESSION_SECRET, salt="qcp-session")


class LoginRequired(Exception):
    pass


def create_session(db, user: User, request: Request, role: str | None = None) -> str:
    sid = secrets.token_urlsafe(32)
    role = role if role in user.role_set else _default_role(user)
    db.add(Session(sid=sid, user_id=user.id, active_role=role,
                   expires_at=dt.datetime.now() + dt.timedelta(hours=SESSION_HOURS),
                   ip=request.client.host if request.client else None,
                   user_agent=(request.headers.get("user-agent") or "")[:300]))
    audit(db, user, "login", "user", user.id, {"role": role}, request)
    db.commit()
    return _signer.dumps(sid)


def _default_role(user: User):
    order = (D.ADMIN, D.QC_MANAGER, D.QC_OPERATOR, D.COORDINATOR, D.FIELD_MANAGER, D.SURVEYOR)
    for r in order:
        if r in user.role_set:
            return r
    return None


def read_session(request: Request):
    """(session, user) ან (None, None). DB სესია მოთხოვნის ბოლოს იხურება."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None, None
    try:
        sid = _signer.loads(raw)
    except BadSignature:
        return None, None
    db = SessionLocal()
    try:
        s = db.get(Session, sid)
        if s is None or s.revoked_at or s.expires_at < dt.datetime.now():
            return None, None
        u = db.get(User, s.user_id)
        if u is None or not u.active:
            return None, None
        _ = u.role_set
        db.expunge_all()
        return s, u
    finally:
        db.close()


def revoke(db, request: Request):
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return
    try:
        sid = _signer.loads(raw)
    except BadSignature:
        return
    s = db.get(Session, sid)
    if s and not s.revoked_at:
        s.revoked_at = dt.datetime.now()
        db.commit()


def switch_role(db, request: Request, role: str):
    raw = request.cookies.get(SESSION_COOKIE)
    sid = _signer.loads(raw)
    s = db.get(Session, sid)
    u = db.get(User, s.user_id)
    if role not in u.role_set:
        raise HTTPException(403, "ეს როლი თქვენ არ გაქვთ.")
    s.active_role = role
    audit(db, u, "role_switch", "user", u.id, {"role": role}, request)
    db.commit()


class Ctx:
    """მიმდინარე მომხმარებელი + აქტიური როლი (ყოველ მოთხოვნაზე ბაზიდან)."""

    def __init__(self, user: User, role: str):
        self.user = user
        self.role = role

    @property
    def is_admin(self):
        return self.role == D.ADMIN

    def can(self, *roles):
        return self.role in roles


def current(request: Request) -> Ctx:
    s, u = read_session(request)
    if u is None:
        raise LoginRequired()
    role = s.active_role if s.active_role in u.role_set else _default_role(u)
    return Ctx(u, role)


def require(*roles):
    """FastAPI dependency: აქტიური როლი უნდა იყოს ჩამოთვლილთაგან."""
    def dep(request: Request) -> Ctx:
        ctx = current(request)
        if roles and ctx.role not in roles:
            raise HTTPException(403, "ამ გვერდზე წვდომა თქვენს როლს არ აქვს.")
        return ctx
    return dep


def same_origin(request: Request):
    """CSRF: მდგომარეობის შემცვლელი მოთხოვნა მხოლოდ იმავე საიტიდან."""
    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin:
        return
    host = request.headers.get("host", "")
    if urlparse(origin).netloc != host:
        raise HTTPException(403, "მოთხოვნა სხვა საიტიდან მოვიდა.")


def audit(db, user, action, entity=None, entity_id=None, detail=None, request=None):
    db.add(AuditLog(actor_id=user.id if user else None, action=action, entity=entity,
                    entity_id=entity_id, detail=detail,
                    ip=request.client.host if request is not None and request.client else None))

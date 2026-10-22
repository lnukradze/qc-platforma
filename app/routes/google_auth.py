# -*- coding: utf-8 -*-
"""
Google-ით შესვლა (OpenID Connect, Authorization Code + PKCE).

  • ჩაირთვება, როცა გარემოში მითითებულია QCP_GOOGLE_CLIENT_ID / QCP_GOOGLE_CLIENT_SECRET
    (IT ქმნის Google Cloud-ში, redirect URI: <QCP_BASE_URL>/auth/google/callback);
  • შედის **მხოლოდ** ის, ვისი ელფოსტაც ადმინმა დაარეგისტრირა (ადმინისტრირება → მომხმარებლები);
    როლებს ჩვენი ადმინები მართავენ (ლუკა ნუკრაძე, სალომე დავითაშვილი);
  • ID token-ი პირდაპირ Google-ის token endpoint-იდან მოდის TLS-ით, ამიტომ ხელმოწერის ცალკე
    შემოწმება საჭირო არ არის (OpenID Connect Core 3.1.3.7) — მოწმდება iss, aud, exp, nonce,
    email_verified და (სურვილისამებრ) დომენი.
"""
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import func, select

from ..config import (BASE_URL, GOOGLE_ALLOWED_DOMAIN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
                      SESSION_COOKIE, SESSION_HOURS, SESSION_SECRET)
from ..db import get_db
from ..models import User
from ..security import audit, create_session

router = APIRouter()

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
OIDC_COOKIE = "qcp_oidc"
_signer = URLSafeTimedSerializer(SESSION_SECRET, salt="qcp-oidc")


def enabled() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def _redirect_uri(request: Request) -> str:
    return (BASE_URL + "/auth/google/callback") if BASE_URL else str(request.url_for("google_callback"))


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _claims(id_token: str) -> dict:
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return {}


def _fail(reason: str):
    resp = RedirectResponse(f"/login?err={reason}", status_code=303)
    resp.delete_cookie(OIDC_COOKIE)
    return resp


@router.get("/auth/google")
def google_start(request: Request, next: str = "/"):
    if not enabled():
        return RedirectResponse("/login?err=google_off", status_code=303)
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    params = {"client_id": GOOGLE_CLIENT_ID, "redirect_uri": _redirect_uri(request),
              "response_type": "code", "scope": "openid email profile", "state": state,
              "nonce": nonce, "prompt": "select_account",
              "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
              "code_challenge_method": "S256"}
    if GOOGLE_ALLOWED_DOMAIN:
        params["hd"] = GOOGLE_ALLOWED_DOMAIN
    resp = RedirectResponse(AUTH_URL + "?" + urlencode(params), status_code=303)
    resp.set_cookie(OIDC_COOKIE, _signer.dumps({"s": state, "n": nonce, "v": verifier,
                                                 "next": next if next.startswith("/") else "/"}),
                    httponly=True, samesite="lax", max_age=600)
    return resp


@router.get("/auth/google/callback", name="google_callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = "",
                    db=Depends(get_db)):
    if error or not code:
        return _fail("google_cancel")
    try:
        saved = _signer.loads(request.cookies.get(OIDC_COOKIE, ""), max_age=600)
    except BadSignature:
        return _fail("google_state")
    if not secrets.compare_digest(state, saved.get("s", "")):
        return _fail("google_state")
    try:
        r = requests.post(TOKEN_URL, timeout=15, data={
            "code": code, "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": _redirect_uri(request), "grant_type": "authorization_code",
            "code_verifier": saved["v"]})
        r.raise_for_status()
        claims = _claims(r.json().get("id_token", ""))
    except (requests.RequestException, ValueError):
        return _fail("google_token")
    email = str(claims.get("email") or "").strip().lower()
    if (claims.get("iss") not in ISSUERS or claims.get("aud") != GOOGLE_CLIENT_ID
            or float(claims.get("exp") or 0) < time.time() or claims.get("nonce") != saved.get("n")
            or not claims.get("email_verified") or not email):
        return _fail("google_claims")
    if GOOGLE_ALLOWED_DOMAIN and str(claims.get("hd") or "").lower() != GOOGLE_ALLOWED_DOMAIN:
        return _fail("google_domain")
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.active.is_(True)))
    if user is None:
        audit(db, None, "login_denied", "user", None, {"email": email}, request)
        db.commit()
        return _fail("not_registered")
    token = create_session(db, user, request)
    resp = RedirectResponse(saved.get("next") or "/", status_code=303)
    resp.delete_cookie(OIDC_COOKIE)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax",
                    secure=request.url.scheme == "https", max_age=SESSION_HOURS * 3600)
    return resp

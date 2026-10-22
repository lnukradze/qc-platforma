# -*- coding: utf-8 -*-
"""
აპლიკაციის ქარხანა.

გაშვება:  .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8200
API დოკუმენტაცია (IT-სთვის): http://127.0.0.1:8200/docs
"""
try:                                    # კორპორატიული სერტიფიკატი (Google OAuth, SMTP TLS)
    import truststore
    truststore.inject_into_ssl()
except ImportError:                     # pragma: no cover
    pass

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import APP_DIR
from .db import Base, engine
from .routes import admin, api, auth, distribution, field, google_auth, items, pages, preqc, qc, stats
from .security import LoginRequired
from .templating import templates

app = FastAPI(
    title="NAPR — ხარისხის კონტროლის ერთიანი პლატფორმა (პროტოტიპი)",
    version=__version__,
    description="განაწილება · QC შემოწმება · ველის პასუხები · Pre-QC · სტატისტიკა. "
                "ყველა მოთხოვნა როლითა და საკუთრებით იფილტრება სერვერზე.",
)
Base.metadata.create_all(engine)

app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
for r in (auth, google_auth, pages, qc, field, items, distribution, stats, preqc, admin, api):
    app.include_router(r.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/") or request.url.path.startswith("/items/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, exc: LoginRequired):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "login_required"}, status_code=401)
    nxt = request.url.path if request.method == "GET" else "/"
    return RedirectResponse(f"/login?next={nxt}", status_code=303)


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    titles = {403: "წვდომა შეზღუდულია", 404: "ვერ მოიძებნა"}
    return templates.TemplateResponse(
        request, "error.html",
        {"code": exc.status_code, "title": titles.get(exc.status_code, "შეცდომა"),
         "detail": exc.detail}, status_code=exc.status_code)

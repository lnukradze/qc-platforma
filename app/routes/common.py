# -*- coding: utf-8 -*-
"""გვერდებისთვის საერთო დამხმარეები."""
import json
from urllib.parse import quote, urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from ..config import RAW_DIR
from ..services import anon
from ..templating import templates

PER_PAGE = 50


def render(request: Request, ctx, name: str, status_code=200, **kw):
    viewer_role = getattr(ctx, "role", None)

    def actor_name(user, actor_role=None):
        """შაბლონისთვის: სახელი ან „ხარისხის კონტროლი" — ამ მოთხოვნის მნახველის როლით."""
        return anon.actor_name(viewer_role, user, actor_role)

    context = {"ctx": ctx, "ok": request.query_params.get("ok"),
               "err": request.query_params.get("err"), "data_info": data_info(),
               "actor_name": actor_name}
    context.update(kw)
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def redirect(url: str, ok: str | None = None, err: str | None = None):
    sep = "&" if "?" in url else "?"
    if ok:
        url += f"{sep}ok={quote(ok)}"
    elif err:
        url += f"{sep}err={quote(err)}"
    return RedirectResponse(url, status_code=303)


def paginate(db, stmt, page: int, per_page: int = PER_PAGE):
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    page = max(1, page)
    rows = db.scalars(stmt.limit(per_page).offset((page - 1) * per_page)).all()
    pages = max(1, (total + per_page - 1) // per_page)
    return rows, total, page, pages


def qs(params: dict, **override) -> str:
    p = {k: v for k, v in params.items() if v not in (None, "")}
    p.update({k: v for k, v in override.items()})
    p = {k: v for k, v in p.items() if v not in (None, "")}
    return urlencode(p)


_INFO = {}


def data_info():
    """ქვედა ზოლისთვის — როდის წამოვიდა ცხრილის მონაცემი."""
    if "v" not in _INFO:
        try:
            m = json.loads((RAW_DIR / "control" / "manifest.json").read_text(encoding="utf-8"))
            _INFO["v"] = m.get("fetched_at")
        except (OSError, ValueError):
            _INFO["v"] = None
    return _INFO["v"]

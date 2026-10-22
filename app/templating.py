# -*- coding: utf-8 -*-
"""Jinja2 შაბლონები და ქართული ფორმატირების დამხმარეები."""
import datetime as dt
import json

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from . import __version__
from . import domain as D
from .config import APP_DIR

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
env = templates.env

MONTHS = ["იანვ.", "თებ.", "მარტი", "აპრ.", "მაისი", "ივნ.", "ივლ.", "აგვ.", "სექტ.", "ოქტ.", "ნოემ.", "დეკ."]


def fmt_dt(v, with_time=True):
    if not v:
        return ""
    if isinstance(v, str):
        try:
            v = dt.datetime.fromisoformat(v.replace("Z", "")[:19])
        except ValueError:
            return v
    if isinstance(v, dt.datetime):
        return v.strftime("%d.%m.%Y %H:%M") if with_time else v.strftime("%d.%m.%Y")
    if isinstance(v, dt.date):
        return v.strftime("%d.%m.%Y")
    return str(v)


def fmt_date(v):
    return fmt_dt(v, with_time=False)


def num(v):
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return v
    if n.is_integer():
        return f"{int(n):,}".replace(",", " ")
    return f"{n:,.1f}".replace(",", " ")


def mask_pid(v):
    s = str(v or "")
    return ("•" * max(0, len(s) - 4) + s[-4:]) if s else ""


def ago(v):
    if not v:
        return ""
    d = dt.datetime.now() - v
    if d.days > 0:
        return f"{d.days} დღის წინ"
    h = d.seconds // 3600
    if h:
        return f"{h} სთ-ის წინ"
    m = max(1, d.seconds // 60)
    return f"{m} წთ-ის წინ"


def tojson_attr(v):
    return Markup(json.dumps(v, ensure_ascii=False).replace("<", "\\u003c"))


env.filters.update(dt=fmt_dt, date=fmt_date, num=num, mask_pid=mask_pid, ago=ago,
                   tojson_attr=tojson_attr)
env.globals.update(
    D=D, VERSION=__version__,
    ROLE_LABELS=D.ROLE_LABELS, ROLE_SHORT=D.ROLE_SHORT,
    VERDICT_LABELS=D.VERDICT_LABELS, STATE_LABELS=D.STATE_LABELS,
    RESPONSE_LABELS=D.RESPONSE_LABELS, CLOSE_REASON_LABELS=D.CLOSE_REASON_LABELS,
    KIND_LABELS=D.KIND_LABELS, EVENT_LABELS=D.EVENT_LABELS, COLOR_LABELS=D.COLOR_LABELS,
    operator_color=D.operator_color, field_color=D.field_color,
    SEVERITY_LABELS=D.SEVERITY_LABELS, now=dt.datetime.now,
    QCM_DECISION_LABELS=D.QCM_DECISION_LABELS, MARK_LABELS=D.MARK_LABELS,
    RESPONSE_STYLE=D.RESPONSE_STYLE, RESPONSE_ICONS=D.RESPONSE_ICONS,
    EMAIL_STATUS={"preview": "მომზადებული (SMTP არ არის)", "sent": "გაგზავნილი",
                  "failed": "ვერ გაიგზავნა", "no_address": "ელფოსტა არ აქვს"},
)


def nav_items(role):
    """მთავარი მენიუ — როლის მიხედვით (სერვერი მაინც ამოწმებს ყოველ გვერდზე)."""
    items = [("/", "მთავარი", "home")]
    if role in (D.SURVEYOR, D.FIELD_MANAGER):              # Pre-QC — მხოლოდ ველს
        items.append(("/preqc", "Pre-QC ხარვეზები", "preqc"))
    if role in (D.QC_OPERATOR, D.QC_MANAGER, D.ADMIN):
        items.append(("/qc", "ხარისხის კონტროლი", "qc"))
    if role in (D.SURVEYOR, D.FIELD_MANAGER, D.ADMIN):
        items.append(("/field", "ველის შემთხვევები", "field"))
    if role == D.COORDINATOR:
        items.append(("/checked", "გავლილი ოქმები", "checked"))
    if role in (D.QC_MANAGER, D.ADMIN):
        items.append(("/qc/disagreements", "არ დათანხმებულები", "disputes"))
        items.append(("/qc/requests", "სტატუსის მოთხოვნები", "requests"))
        items.append(("/distribution", "განაწილება", "distribution"))
    items.append(("/stats", "სტატისტიკა", "stats"))
    if role == D.ADMIN:
        items.append(("/admin", "ადმინისტრირება", "admin"))
    items.append(("/about", "სისტემის შესახებ", "about"))
    return items


env.globals["nav_items"] = nav_items

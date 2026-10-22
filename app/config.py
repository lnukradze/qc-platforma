# -*- coding: utf-8 -*-
"""
პარამეტრები — გარემოს ცვლადებიდან, ნაგულისხმევი მნიშვნელობებით.

პროტოტიპი ლოკალურად მუშაობს (SQLite). საწარმოო ვერსიაში იგივე კოდი
PostgreSQL-ზე გადავა — საკმარისია `QCP_DATABASE_URL`-ის შეცვლა.
"""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
DATA_DIR = Path(os.environ.get("QCP_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
UPLOAD_DIR = DATA_DIR / "uploads"
SEED_DIR = APP_DIR / "seed"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("QCP_DATABASE_URL", f"sqlite:///{(DATA_DIR / 'platform.db').as_posix()}")

# განაწილების წყარო — არსებული პროგრამის ლოკალური ბაზა (მხოლოდ კითხვა).
# საწარმოოში ეს იქნება ღამის იმპორტი GDB-დან ან სააგენტოს ბაზიდან.
DISTRIBUTOR_DB = Path(os.environ.get(
    "QCP_DISTRIBUTOR_DB",
    ROOT.parent / "dzveli masalebi da saitebi" / "NAPR_Distributor" / "napr_data.sqlite"))

# QC სამუშაო.xlsx — ძველი პერიოდი + სახელების რუკა (Reference)
QC_WORKBOOK = Path(os.environ.get(
    "QCP_QC_WORKBOOK", ROOT.parents[1] / "კონტროლ;ის სტატისტიკა" / "QC სამუშაო.xlsx"))


def _secret():
    """სესიის გასაღები — ერთხელ იქმნება და data/-ში ინახება."""
    env = os.environ.get("QCP_SESSION_SECRET")
    if env:
        return env
    f = DATA_DIR / ".session_secret"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    s = secrets.token_hex(32)
    f.write_text(s, encoding="utf-8")
    return s


SESSION_SECRET = _secret()
SESSION_COOKIE = "qcp_session"
SESSION_HOURS = 12

# 🔒 დემო რეჟიმი: შესვლა მომხმარებლის არჩევით (Google-ის გარეშე).
# საწარმოოში — Google OIDC, მხოლოდ რეგისტრირებული ელფოსტებით.
DEMO_LOGIN = os.environ.get("QCP_DEMO_LOGIN", "1") == "1"
# ქსელში (LAN) ჩვენებისას — დემო შესვლა მხოლოდ ამ კოდით (run_lan.bat ყოველ გაშვებაზე ქმნის)
DEMO_PIN = os.environ.get("QCP_DEMO_PIN", "").strip()
GOOGLE_CLIENT_ID = os.environ.get("QCP_GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("QCP_GOOGLE_CLIENT_SECRET", "")
# სურვილისამებრ: მხოლოდ ერთი Google Workspace დომენი (მაგ. napr.gov.ge); ცარიელი — პირადი Gmail-იც
GOOGLE_ALLOWED_DOMAIN = os.environ.get("QCP_GOOGLE_ALLOWED_DOMAIN", "").strip().lower()

# საიტის საჯარო მისამართი (მეილის ბმულები, Google-ის redirect). ცარიელი — მოთხოვნიდან.
BASE_URL = os.environ.get("QCP_BASE_URL", "").rstrip("/")

# 📧 მეილი — SMTP (IT-ის საფოსტო სერვერი). ცარიელი → მეილი მხოლოდ ინახება („preview")
SMTP_HOST = os.environ.get("QCP_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("QCP_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("QCP_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("QCP_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("QCP_SMTP_FROM", "NAPR QC <noreply@localhost>")
SMTP_STARTTLS = os.environ.get("QCP_SMTP_STARTTLS", "1") == "1"

MAX_UPLOAD_MB = 10
ALLOWED_UPLOAD_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}

TIMEZONE_LABEL = "Asia/Tbilisi"

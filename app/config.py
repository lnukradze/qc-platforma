# -*- coding: utf-8 -*-
"""
პარამეტრები — გარემოს ცვლადებიდან, ნაგულისხმევი მნიშვნელობებით.

პროტოტიპი ლოკალურად მუშაობს (SQLite). საწარმოო ვერსიაში იგივე კოდი
PostgreSQL-ზე გადავა — საკმარისია `QCP_DATABASE_URL`-ის შეცვლა.
"""
import os
import secrets
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"

# 🔐 AI აგენტი რეალურ მონაცემს არ ხსნის (AGENTS.md; ლუკა, 2026-10-26). Claude Code თავის ბრძანებებს
#    CLAUDECODE=1-ით უშვებს, agent.ps1 — QCP_AGENT=1-ით. მაშინ ყველა ადგილი, რომელიც დემო ან დროებით
#    საქაღალდეში არ არის, დემოთი იცვლება — როგორც არ უნდა გაეშვას აგენტი (Task, პანელი, ტერმინალი).
AGENT = os.environ.get("CLAUDECODE") == "1" or os.environ.get("QCP_AGENT") == "1"
DEMO_DIR = ROOT.parent / "qc-demo-data"


def _inside(p: Path, base: Path) -> bool:
    a, b = (os.path.normcase(os.path.realpath(x)) for x in (p, base))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def _agent_safe(p: Path, demo: Path) -> Path:
    if AGENT and not any(_inside(p, b) for b in (DEMO_DIR, Path(tempfile.gettempdir()))):
        return demo
    return p


DATA_DIR = _agent_safe(Path(os.environ.get("QCP_DATA_DIR", ROOT / "data")), DEMO_DIR)
RAW_DIR = DATA_DIR / "raw"
UPLOAD_DIR = DATA_DIR / "uploads"
SEED_DIR = APP_DIR / "seed"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_default_db = f"sqlite:///{(DATA_DIR / 'platform.db').as_posix()}"
DATABASE_URL = os.environ.get("QCP_DATABASE_URL", _default_db)
if AGENT and DATABASE_URL.startswith("sqlite:///") and \
        _agent_safe(Path(DATABASE_URL[len("sqlite:///"):]), DEMO_DIR) == DEMO_DIR:
    DATABASE_URL = _default_db

# განაწილების წყარო — არსებული პროგრამის ლოკალური ბაზა (მხოლოდ კითხვა).
# საწარმოოში ეს იქნება ღამის იმპორტი GDB-დან ან სააგენტოს ბაზიდან.
DISTRIBUTOR_DB = _agent_safe(Path(os.environ.get(
    "QCP_DISTRIBUTOR_DB",
    ROOT.parent / "dzveli masalebi da saitebi" / "NAPR_Distributor" / "napr_data.sqlite")),
    DEMO_DIR / "distributor.sqlite")

# QC სამუშაო.xlsx — ძველი პერიოდი + სახელების რუკა (Reference)
QC_WORKBOOK = _agent_safe(Path(os.environ.get(
    "QCP_QC_WORKBOOK", ROOT.parents[1] / "კონტროლ;ის სტატისტიკა" / "QC სამუშაო.xlsx")),
    DEMO_DIR / "no-workbook.xlsx")


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

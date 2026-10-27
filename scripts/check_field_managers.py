# -*- coding: utf-8 -*-
"""
ძველი არასწორი მიკუთვნებები (T-030) — **მხოლოდ კითხვა**.

ჩამოთვლის ოქმებს, სადაც პასუხისმგებელი მენეჯერი (`field_manager_id`) ან მიკუთვნებული მენეჯერი
(`ItemPerson`, kind=manager) დასაშვები საველე მენეჯერი არ არის (აქტიური + საველე მენეჯერის როლი).
იბეჭდება მხოლოდ ოქმის ნომერი და რაოდენობა — სახელები არა. ბაზაში არაფერი იწერება:
SQLite იხსნება `mode=ro`-ით, PostgreSQL — `READ ONLY` ტრანზაქციით.

გასწორება — ბარათზე „მენეჯერის მიწერა“ (QC მენეჯერი / ადმინი). რეალურ ბაზაზე უშვებს მხოლოდ ლუკა;
აგენტი — მხოლოდ დემოზე.

  python scripts/check_field_managers.py [--limit 200]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import domain as D  # noqa: E402
from app.config import DATABASE_URL  # noqa: E402
from app.models import ItemPerson, QcItem, User, UserRole  # noqa: E402


def read_only_engine(url):
    if url.startswith("sqlite"):
        path = Path(url.split(":///", 1)[1]).resolve()
        if not path.exists():
            raise SystemExit(f"ბაზა ვერ მოიძებნა: {path.name}")
        uri = path.as_uri() + "?mode=ro"
        return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
    eng = create_engine(url)

    @event.listens_for(eng, "begin")
    def _read_only(conn):
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    return eng


def find(s):
    """(ოქმები არასწორი პასუხისმგებლით, ოქმები არასწორი მიკუთვნებული მენეჯერით) — წესი, როგორც is_field_manager()."""
    valid = select(User.id).join(UserRole).where(User.active.is_(True), UserRole.role == D.FIELD_MANAGER)
    primary = s.scalars(select(QcItem.protocol_number).where(
        QcItem.field_manager_id.is_not(None), QcItem.field_manager_id.not_in(valid))
        .order_by(QcItem.protocol_number)).all()
    people = s.scalars(select(QcItem.protocol_number).join(ItemPerson, ItemPerson.item_id == QcItem.id)
                       .where(ItemPerson.kind == D.P_MANAGER, ItemPerson.user_id.not_in(valid))
                       .distinct().order_by(QcItem.protocol_number)).all()
    return primary, people


def show(title, protocols, limit):
    print(f"{title}: {len(protocols)}")
    for p in protocols[:limit]:
        print(f"  {p}")
    if len(protocols) > limit:
        print(f"  … და კიდევ {len(protocols) - limit}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="არასწორი საველე მენეჯერის მიკუთვნებები (მხოლოდ კითხვა)")
    ap.add_argument("--limit", type=int, default=200, help="რამდენი ოქმის ნომერი დაიბეჭდოს")
    args = ap.parse_args(argv)
    eng = read_only_engine(DATABASE_URL)
    try:
        with Session(eng) as s:
            primary, people = find(s)
    finally:
        eng.dispose()
    show("პასუხისმგებელი მენეჯერი დასაშვები არ არის (ოქმი)", primary, args.limit)
    show("მიკუთვნებული მენეჯერი დასაშვები არ არის (ოქმი)", people, args.limit)
    print("გასწორება — ბარათზე „მენეჯერის მიწერა“. ბაზაში არაფერი ჩაწერილა.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

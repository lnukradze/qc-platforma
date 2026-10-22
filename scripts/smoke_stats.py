# -*- coding: utf-8 -*-
"""სტატისტიკის სწრაფი შემოწმება ბაზაზე (დიაგნოსტიკა)."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select  # noqa: E402

from app import domain as D  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import User, UserRole  # noqa: E402
from app.security import Ctx  # noqa: E402
from app.services import stats  # noqa: E402

db = SessionLocal()
admin = db.scalar(select(User).join(UserRole).where(UserRole.role == D.ADMIN))
for role, user in [(D.ADMIN, admin),
                   (D.FIELD_MANAGER, db.scalar(select(User).join(UserRole).where(UserRole.role == D.FIELD_MANAGER, User.active.is_(True)))),
                   (D.QC_OPERATOR, admin)]:
    ctx = Ctx(user, role)
    t0 = time.time()
    f = stats.parse_filters({})
    k = stats.kpi(db, ctx, f)
    tr = stats.trend(db, ctx, f)
    bo = stats.by_operator(db, ctx, f)
    bm = stats.by_manager(db, ctx, f)
    bs = stats.by_surveyor(db, ctx, f)
    cd = stats.codes(db, ctx, f)
    zn = stats.zones(db, ctx, f)
    rs = stats.restricted(db, ctx, f)
    print(f"== {role} ({user.full_name}) {time.time() - t0:.2f}s")
    print("  kpi:", json.dumps(k, ensure_ascii=False))
    print("  trend weeks:", len(tr), "| ops:", len(bo), "| mgrs:", len(bm), "| surveyors:", len(bs),
          "| codes:", len(cd), "| zones:", len(zn))
    if bo:
        print("  top op:", bo[0])
    if cd:
        print("  top codes:", [(c["code"], c["negative"]) for c in cd[:6]])
    print("  restricted keys:", list(rs.keys()), rs.get("legacy_type_flags"))
db.close()

# -*- coding: utf-8 -*-
"""განაწილების გადახედვა რეალურ წყაროზე (ბაზაში არაფერს წერს)."""
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
from app.services.distribution import service  # noqa: E402

db = SessionLocal()
ops = db.scalars(select(User).join(UserRole).where(UserRole.role == D.QC_OPERATOR,
                                                   User.active.is_(True))).all()
d_from, d_to = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("2026-10-12", "2026-10-18")
for creator in ("oqmi_creator", "moxaz_creator"):
    t0 = time.time()
    pv = service.prepare(db, {"date_from": d_from, "date_to": d_to,
                              "operators": {str(o.id): 450 for o in ops},
                              "full_zones": [], "balance": True, "min_share": 0.2,
                              "exclude_statuses": ["შედგენილია -საველე განცხადება მიღებულია",
                                                   "აღწერის პროცესი-საველე განცხადება"],
                              "drop_without_manager": True, "manager_by": creator, "seed": 42})
    print(f"== {creator}: {time.time() - t0:.1f}s")
    print("  counts:", json.dumps(pv["counts"], ensure_ascii=False))
    print("  no manager top:", pv["no_manager_top"][:6])
    print("  operators:", [(o["operator"], o["protocols"]) for o in pv["operators"]][:5])
    if pv["balance"]:
        print("  spread:", pv["balance"]["spread_before"], "→", pv["balance"]["spread_after"])
db.close()

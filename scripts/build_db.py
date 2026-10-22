# -*- coding: utf-8 -*-
"""
პროტოტიპის ბაზის აწყობა ნულიდან:

  1. სქემა (ცხრილები)
  2. ცნობარები — ხარვეზის კოდები, მივლინებები, პარამეტრები
  3. ადამიანები და გუნდები — Field Group + კონტროლის ცხრილის ოპერატორები
  4. ძველი კონტროლის ცხრილის გადმოტანა (data/raw/control — fetch_sheets.py)
  5. Pre-QC — სადემონსტრაციო გუნდი და ფიქსირებული შედეგები

გაშვება:  .venv\\Scripts\\python.exe scripts\\build_db.py
⚠️ data/platform.db თავიდან იქმნება — პროტოტიპში შეტანილი ცვლილებები იკარგება.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app.config import DATA_DIR  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402,F401
from app.services import legacy_import, preqc_demo, seed  # noqa: E402


def main():
    t0 = time.time()
    db_file = DATA_DIR / "platform.db"
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_file) + suffix)
        if p.exists():
            p.unlink()
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed.seed_reference(db)
        print("✓ ცნობარები")
        seed.seed_people(db)
        db.commit()
        print("✓ ადამიანები და გუნდები:", db.query(models.User).count(), "მომხმარებელი,",
              db.query(models.Team).count(), "გუნდი")
        rep = legacy_import.import_control(db)
        db.commit()
        print("✓ ძველი ცხრილი:", json.dumps({k: rep[k] for k in (
            "source_rows", "records", "unique_items", "duplicates", "states", "verdicts",
            "planner_links", "unmatched_planner_names", "aliases_loaded", "surveyors_from_regfieldall",
            "duplicates_sporadic_kept", "legacy_review_marks")}, ensure_ascii=False))
        demo = preqc_demo.build_demo(db)
        db.commit()
        print("✓ Pre-QC (დემო):", demo)
    finally:
        db.close()
    print(f"მზადაა — {time.time() - t0:.1f} წმ → {db_file}")


if __name__ == "__main__":
    main()

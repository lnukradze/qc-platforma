# -*- coding: utf-8 -*-
"""
ხარვეზის კოდები: კანონიკური კატალოგი + ავტომატური მინიჭება კომენტარიდან.

  • კატალოგი — `seed/code_catalog.json` (27 კოდი + QC-00, სახელმძღვანელოს მიხედვით)
  • ავტომატური წესები — `taxonomy.py` (იგივე, რაც `rules.gs`; ბრაუზერში იგივე
    წესები მუშაობს `static/js/qc-rules.js`-ით, ასე ოპერატორი კოდს წერისთანავე ხედავს)
"""
import json
import re

from ..config import SEED_DIR
from . import taxonomy

CODE_RE = re.compile(r"[A-Z]{2,4}-\d{2,3}")
PENDING_CODE = "QC-00"


def load_catalog() -> dict:
    with open(SEED_DIR / "code_catalog.json", encoding="utf-8") as f:
        return json.load(f)


def classify(comment: str | None) -> list[str]:
    """თავისუფალი ტექსტი → დალაგებული კოდების სია (ცარიელზე — ცარიელი)."""
    t = taxonomy.N(comment or "")
    if not t.strip():
        return []
    return sorted(taxonomy.rules(t))


def parse_codes(cell) -> list[str]:
    """ძველი ცხრილის H სვეტი („GEO-01, SLR-03") → კოდების სია (გამეორების გარეშე)."""
    seen, out = set(), []
    for c in CODE_RE.findall(str(cell or "").upper()):
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out

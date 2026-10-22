# -*- coding: utf-8 -*-
"""წამოღებული ნედლი მონაცემის მოკლე პროფილი (დიაგნოსტიკა, არაფერს წერს)."""
import json
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
PID = re.compile(r"(?<!\d)\d{9,11}(?!\d)")


def load(folder, name):
    return json.loads((RAW / folder / (urllib.parse.quote(name, safe="") + ".json")).read_text(encoding="utf-8"))


m = json.loads((RAW / "control" / "manifest.json").read_text(encoding="utf-8"))
headers = Counter()
allkeys = Counter()
status = Counter()
jstat = Counter()
by_tab = {}
for t in m["tabs"]:
    d = load("control", t["name"])
    h = tuple(d["header"])
    headers[h] += 1
    rows = d["rows"]
    e = Counter((r[4] if len(r) > 4 else "") for r in rows)
    by_tab[t["name"]] = (len(rows), dict(e))
    for r in rows:
        a, b = (r[0] if r else ""), (r[1] if len(r) > 1 else "")
        if a or b:
            allkeys[(a.strip(), b.strip())] += 1
        status[r[4] if len(r) > 4 else ""] += 1
        jstat[r[9] if len(r) > 9 else ""] += 1

print("== header variants:")
for h, n in headers.items():
    print(n, "×", list(h))
print("\n== per tab (rows, E statuses):")
for k, v in by_tab.items():
    print(" ", k, v)
print("\n== E overall:", status.most_common())
print("== J overall:", jstat.most_common())
dups = {k: n for k, n in allkeys.items() if n > 1}
print("\n== unique (A,B):", len(allkeys), "| duplicate keys:", len(dups), "| extra rows:", sum(n - 1 for n in dups.values()))
print("   sample dup keys:", list(dups.items())[:5])
empty_a = sum(1 for (a, b) in allkeys if not a)
print("   keys with empty A:", empty_a)

for ref in ("არდათანხმებულები", "შემაჯამებელი", "_კოდების ცნობარი", "QC ფილტრები", "ამზომველები"):
    try:
        d = load("control_ref", ref)
    except FileNotFoundError:
        print("missing", ref)
        continue
    print(f"\n== {ref}: header={d['header']}")
    for r in d["rows"][:4]:
        print("   ", [PID.sub("[PID]", str(x))[:60] for x in r])
fg = json.loads((RAW / "field_group.json").read_text(encoding="utf-8"))
cur = fg["current"]["rows"]
print("\n== Field Group current:", len(cur), "tab:", fg["current"].get("tab"), "| managers:",
      Counter(r["manager"] for r in cur).most_common(20))
print("== Field Group full:", len(fg["full"]["rows"]), "tab:", fg["full"].get("tab"))

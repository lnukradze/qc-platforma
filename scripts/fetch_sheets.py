# -*- coding: utf-8 -*-
"""
Google ცხრილებიდან მონაცემის წამოღება — **მხოლოდ კითხვა**.
=============================================================

გამოიყენება არსებული read-only კავშირები:

  • QCStatRead (სტატისტიკის პანელის Apps Script, მხოლოდ კითხვა)
      კონტროლის ცხრილის ჩანართები — ოპერატორები + „სპორადული"
      კონფიგი: ..\\კონტროლ;ის სტატისტიკა\\dashboard\\sheet_config.json
  • Field Group (განაწილების პროგრამის Apps Script, მხოლოდ კითხვა)
      ამზომველი → მენეჯერი (მიმდინარე და სრული ფურცელი)
      კონფიგი: ..\\dzveli masalebi da saitebi\\NAPR_Distributor\\config.json

⚠️ ჩაწერის (POST) მოქმედებებს ეს სკრიპტი **არ იძახებს** — არც შეუძლია:
   მხოლოდ GET მოთხოვნები იგზავნება.
🔐 token-ები არსად იბეჭდება და data/raw-ში არ ინახება.

გაშვება:
    .venv\\Scripts\\python.exe scripts\\fetch_sheets.py tabs
    .venv\\Scripts\\python.exe scripts\\fetch_sheets.py fetch
"""
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests
import truststore

truststore.inject_into_ssl()          # კორპორატიული სერტიფიკატი Windows-ის საცავიდან
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DESKTOP = ROOT.parents[1]
QCSTAT_CFG = Path(os.environ.get(
    "QCSTAT_CONFIG", DESKTOP / "კონტროლ;ის სტატისტიკა" / "dashboard" / "sheet_config.json"))
DISTRIBUTOR_CFG = Path(os.environ.get(
    "DISTRIBUTOR_CONFIG",
    ROOT.parent / "dzveli masalebi da saitebi" / "NAPR_Distributor" / "config.json"))

# ოპერატორის ჩანართი არ არის: სარკეები (ფორმულით აგებული ასლები) — არ ვკითხულობთ,
# თორემ ყველაფერი გაორმაგდებოდა. „პირადი ნომრები" ამ ეტაპზე არ გვჭირდება.
SKIP_TABS = {"ყველა-მონაცემი", "SQL", "reingebi", "პირადი ნომრები"}
# მცირე დამხმარე ჩანართები — ცალკე საქაღალდეში, ცნობისთვის და შესადარებლად.
REF_TABS = {"არდათანხმებულები", "შემაჯამებელი", "_კოდების ცნობარი", "ამზომველები",
            "QC ფილტრები"}
PAGE = 8000
TIMEOUT = 330


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get(url, params, what):
    """ერთი GET მოთხოვნა ხელახალი ცდებით. ცხრილში არაფერი იწერება."""
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
            text = r.text
            try:
                data = json.loads(text)
            except ValueError:
                raise RuntimeError("JSON-ის ნაცვლად სხვა პასუხი: " + text[:120].replace("\n", " "))
            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError("Apps Script: %s" % data["error"])
            return data
        except Exception as e:                      # noqa: BLE001
            last = e
            wait = 5 * (attempt + 1)
            print(f"   ⚠ {what}: {e} — ხელახლა {wait} წმ-ში")
            time.sleep(wait)
    raise RuntimeError(f"{what}: {last}")


def qcstat():
    cfg = _load_json(QCSTAT_CFG)
    return cfg["url"], cfg["token"]


def list_tabs(ss="control"):
    url, token = qcstat()
    data = _get(url, {"token": token, "action": "tabs", "ss": ss}, f"tabs({ss})")
    return data.get("tabs", [])


def fetch_tab(name, total, ss="control"):
    """ერთი ჩანართი გვერდებად. აბრუნებს {header, rows}."""
    url, token = qcstat()
    header, rows = [], []
    offset = 0
    while offset < max(total, 1):
        part = _get(url, {"token": token, "action": "rows", "ss": ss, "tab": name,
                          "limit": PAGE, "offset": offset}, f"{name}@{offset}")
        header = part.get("header") or header
        got = part.get("rows") or []
        rows.extend(got)
        print(f"   {name}: {offset}+{len(got)} / {part.get('total')}")
        if not got:
            break
        offset += len(got)
        total = part.get("total") or total
        time.sleep(1.0)                              # ცხრილს ზედმეტად არ ვტვირთავთ
    return {"tab": name, "header": header, "rows": rows}


def is_data_header(header):
    h = [str(x).strip() for x in (header or [])]
    return len(h) >= 2 and h[0] == "ოქმის N" and h[1] == "CADCODE"


def fetch_field_group():
    cfg = _load_json(DISTRIBUTOR_CFG)
    url, token = cfg["manager_sheet_url"], cfg["manager_sheet_token"]
    out = {}
    out["current"] = _get(url, {"token": token}, "FieldGroup(current)")
    full_gid = cfg.get("full_sheet_gid") or "884624702"
    out["full"] = _get(url, {"token": token, "gid": full_gid}, "FieldGroup(full)")
    return out


def cmd_tabs():
    for ss in ("control",):
        tabs = list_tabs(ss)
        print(f"== {ss}: {len(tabs)} ჩანართი")
        for t in tabs:
            print(f"   {t['name']:<32} gid={t['gid']:<12} rows={t['rows']:<6} cols={t['cols']}")


def cmd_fetch():
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target = RAW / "control"
    target.mkdir(parents=True, exist_ok=True)
    tabs = list_tabs("control")
    manifest = {"fetched_at": stamp, "source": "QCStatRead (read-only)", "tabs": []}
    ref_dir = RAW / "control_ref"
    ref_dir.mkdir(parents=True, exist_ok=True)
    for t in tabs:
        name = t["name"]
        if name in SKIP_TABS:
            print(f"-- გამოტოვებულია: {name}")
            continue
        is_ref = name in REF_TABS or name.startswith("_")
        print(f"== {name} ({t['rows']} მწკრივი){' [ცნობარი]' if is_ref else ''}")
        data = fetch_tab(name, t["rows"])
        data["fetched_at"] = stamp
        fn_name = urllib.parse.quote(name, safe="") + ".json"
        if is_ref:
            (ref_dir / fn_name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            continue
        if not is_data_header(data["header"]):
            print(f"-- სათაური არ ემთხვევა, გამოტოვებულია: {name}")
            continue
        (target / fn_name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        manifest["tabs"].append({"name": name, "file": fn_name, "rows": len(data["rows"]),
                                 "cols": len(data["header"])})
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("== Field Group")
    fg = fetch_field_group()
    fg["fetched_at"] = stamp
    (RAW / "field_group.json").write_text(json.dumps(fg, ensure_ascii=False), encoding="utf-8")
    print("   მიმდინარე:", fg["current"].get("count"), "| სრული:", fg["full"].get("count"))
    print("✓ დასრულდა:", stamp)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tabs"
    {"tabs": cmd_tabs, "fetch": cmd_fetch}[cmd]()

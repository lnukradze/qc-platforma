# -*- coding: utf-8 -*-
"""
setup.bat-ის მეორე ნაწილი: მონაცემის წამოღება (მხოლოდ კითხვით) და ლოკალური ბაზის აწყობა.

  • Google ცხრილებში არაფერი იწერება — fetch_sheets.py მხოლოდ GET მოთხოვნებს აგზავნის;
  • უკვე წამოღებულ მონაცემს და აწყობილ ბაზას თავიდან არ ეხება
    (განახლება: `fetch_sheets.py fetch` → `build_db.py`).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)


def run(script, *args):
    subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], check=True, cwd=ROOT)


def main():
    from app.config import DATA_DIR, RAW_DIR
    print("  ✓ ბიბლიოთეკები დაყენებულია")
    if not (RAW_DIR / "control" / "manifest.json").exists():
        print("\n  მონაცემის წამოღება Google ცხრილებიდან (მხოლოდ კითხვა, რამდენიმე წუთი) ...")
        run("fetch_sheets.py", "fetch")
    else:
        print("  ✓ მონაცემი უკვე წამოღებულია (data/raw)")
    if not (DATA_DIR / "platform.db").exists():
        print("\n  ლოკალური ბაზის აწყობა ...")
        run("build_db.py")
    else:
        print("  ✓ ბაზა უკვე არსებობს (data/platform.db)")
    print("\n  ✓ მზადაა. გასაშვებად: run.bat   (ქსელში ჩვენებისთვის: run_lan.bat)\n")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        print("\n  [!] დაყენება შეწყდა — იხილეთ შეცდომა ზემოთ.")
        sys.exit(1)

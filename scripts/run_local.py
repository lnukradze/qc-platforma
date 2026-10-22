# -*- coding: utf-8 -*-
"""
ლოკალური გაშვება (run.bat იძახებს): ბაზის შემოწმება → ბრაუზერი → სერვერი.

.bat ფაილები მხოლოდ ლათინურ სიმბოლოებს შეიცავს (cmd.exe UTF-8-ს არასწორად
კითხულობს) — ქართული შეტყობინებები აქედან იბეჭდება.
"""
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
PORT = int(os.environ.get("QCP_PORT", "8200"))


def main():
    from app.config import DATA_DIR
    os.chdir(ROOT)
    print()
    print("  NAPR — ხარისხის კონტროლის ერთიანი პლატფორმა (პროტოტიპი)")
    print("  ─────────────────────────────────────────────")
    print(f"  ბრაუზერში:        http://127.0.0.1:{PORT}")
    print(f"  API (IT-სთვის):   http://127.0.0.1:{PORT}/docs")
    print("  გასაჩერებლად:     Ctrl+C ან ფანჯრის დახურვა")
    print()
    if not (DATA_DIR / "platform.db").exists():
        print("  ბაზა არ არის — ვაწყობ (≈1 წუთი) ...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_db.py")], check=True)
    if "--no-browser" not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
პორტატული ვერსიის გაშვება (START.bat იძახებს): ჩაშენებული Python → ბრაუზერი → სერვერი.

  • მუშაობს მხოლოდ ამ კომპიუტერზე (127.0.0.1) — სხვა კომპიუტერიდან არ იხსნება;
  • შესვლა — დემო არჩევით; მეილი არ იგზავნება, Google-ით შესვლა გამორთულია;
  • ბაზას არ აწყობს: თუ data\\platform.db არ არის, ჩერდება.
"""
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

os.environ.setdefault("QCP_DEMO_LOGIN", "1")
for key in ("QCP_SMTP_HOST", "QCP_GOOGLE_CLIENT_ID", "QCP_GOOGLE_CLIENT_SECRET", "QCP_BASE_URL"):
    os.environ[key] = ""


def free_port(start=8200, tries=20):
    """პირველი თავისუფალი პორტი 8200-დან (თუ ეს კომპიუტერი სხვა რამეს უკვე უშვებს)."""
    for port in range(start, start + tries):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return None


def main():
    from app.config import DATA_DIR
    print()
    print("  NAPR — ხარისხის კონტროლის ერთიანი პლატფორმა (პროტოტიპი, პორტატული ვერსია)")
    print("  ─────────────────────────────────────────────")
    if not (DATA_DIR / "platform.db").exists():
        print(f"  ✗ ბაზა ვერ მოიძებნა: {DATA_DIR / 'platform.db'}")
        print("    პაკეტი არასრულია — ZIP მთლიანად ამოაარქივეთ ან გამომგზავნს მიმართეთ.")
        return 1
    port = free_port(int(os.environ.get("QCP_PORT", "8200")))
    if port is None:
        print("  ✗ თავისუფალი პორტი ვერ მოიძებნა (8200–8219).")
        return 1
    url = f"http://127.0.0.1:{port}"
    print(f"  ბრაუზერში:      {url}")
    print("  შესვლა:         აირჩიეთ მომხმარებელი სიიდან (დემო რეჟიმი)")
    print("  გასაჩერებლად:   დახურეთ ეს ფანჯარა")
    print()
    if "--no-browser" not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())

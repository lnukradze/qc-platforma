# -*- coding: utf-8 -*-
"""
ქსელში ჩვენება — ტელეფონი/პლანშეტი იმავე Wi-Fi-ში (run_lan.bat იძახებს).

  • ყოველ გაშვებაზე იქმნება ახალი დემო კოდი (PIN); მის გარეშე შესვლის
    გვერდზე მომხმარებლების სიაც არ ჩანს;
  • სერვერი ყველა ქსელურ მისამართზე უსმენს (0.0.0.0), პორტი 8200.

⚠️ მხოლოდ მოკლე, დახურულ ჩვენებაზე: ბაზაში რეალური სახელები და QC კომენტარებია.
"""
import os
import secrets
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
PORT = int(os.environ.get("QCP_PORT", "8200"))


def addresses():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:                                    # ძირითადი ინტერფეისი (პაკეტი არ იგზავნება)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith(("127.", "169.254.")))


def main():
    pin = os.environ.get("QCP_DEMO_PIN") or f"{secrets.randbelow(900000) + 100000}"
    os.environ["QCP_DEMO_PIN"] = pin
    os.environ.setdefault("QCP_DEMO_LOGIN", "1")
    print()
    print("  NAPR QC — ქსელში ჩვენება")
    print("  ─────────────────────────────────────────────")
    print("  ტელეფონზე/პლანშეტზე გახსენით (იმავე ქსელში):")
    for ip in addresses() or ["<ამ კომპიუტერის IP>"]:
        print(f"     http://{ip}:{PORT}")
    print()
    print(f"  დემო კოდი (PIN):  {pin}")
    print()
    print("  ⚠  მხოლოდ მოკლე ჩვენებისთვის. დასრულებისას დახურეთ ეს ფანჯარა (Ctrl+C).")
    print("  ⚠  Windows-მა შეიძლება იკითხოს Firewall-ის ნებართვა — აირჩიეთ მხოლოდ")
    print("     Private network (სახლის/სამსახურის), არა Public.")
    print()
    import uvicorn
    os.chdir(ROOT)
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()

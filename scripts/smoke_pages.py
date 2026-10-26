# -*- coding: utf-8 -*-
"""გვერდების სწრაფი შემოწმება ყველა როლით (გაშვებულ სერვერზე, :8200 ან $QCP_PORT)."""
import os
import sys
from pathlib import Path

import requests
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app import domain as D  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import ItemPerson, PreqcCheck, QcItem, User, UserRole  # noqa: E402

BASE = f"http://127.0.0.1:{os.environ.get('QCP_PORT', '8200')}"
db = SessionLocal()


def by_role(role):
    user = db.scalar(select(User).join(UserRole).where(
        UserRole.role == role, User.active.is_(True)).order_by(User.id))
    if user is None:
        raise SystemExit(f"Missing active user for role: {role}")
    return user


admin = by_role(D.ADMIN)
operator = by_role(D.QC_OPERATOR)
qcm = by_role(D.QC_MANAGER)
coord = by_role(D.COORDINATOR)
head = by_role(D.HEAD_OF_SERVICE)
fm_id = db.scalar(select(QcItem.field_manager_id).where(QcItem.state == D.AWAITING_FIELD))
fm = db.get(User, fm_id)
sv_id = db.scalar(select(ItemPerson.user_id).join(QcItem, QcItem.id == ItemPerson.item_id)
                  .where(QcItem.state == D.AWAITING_FIELD, ItemPerson.kind == D.P_SURVEYOR,
                         ItemPerson.user_id.is_not(None)))
sv = db.get(User, sv_id)
item_op = db.scalar(select(QcItem.id).where(QcItem.operator_id == operator.id, QcItem.state == D.AWAITING_QC))
item_fm = db.scalar(select(QcItem.id).where(QcItem.field_manager_id == fm.id, QcItem.state == D.AWAITING_FIELD))
item_qcm = db.scalar(select(QcItem.id).where(QcItem.state == D.AWAITING_QCM))
item_ret = db.scalar(select(QcItem.id).where(QcItem.state == D.RETURNED_TO_MANAGER))
preqc_surveyor = db.scalar(select(User).join(PreqcCheck, PreqcCheck.surveyor_id == User.id)
                          .where(User.active.is_(True)).order_by(User.id))
if any(x is None for x in (fm, sv, preqc_surveyor, item_op, item_fm, item_qcm, item_ret)):
    raise SystemExit("Missing users/items for smoke scenarios")
db.close()

PAGES = {
    D.ADMIN: ["/", "/qc", "/qc?tab=returned", "/qc?tab=sent", "/qc?tab=closed", "/qc/disagreements",
              "/qc/requests", "/field", "/field?tab=manager", "/stats", "/api/stats", "/preqc",
              "/distribution", "/distribution/sporadic", "/distribution/unsorted", "/admin",
              f"/admin/users/{admin.id}", "/admin/teams", "/admin/codes", "/admin/settings",
              "/admin/import", "/admin/emails", "/admin/audit", "/about", f"/items/{item_op}",
              f"/items/{item_qcm}", f"/items/{item_ret}", "/api/me", "/api/items", "/docs"],
    D.QC_OPERATOR: ["/", "/qc", "/qc?tab=returned", "/qc/next", "/stats", "/api/stats",
                    f"/items/{item_op}", "/preqc", "/field", "/admin"],
    D.QC_MANAGER: ["/", "/qc", "/qc/disagreements", "/qc/requests", f"/items/{item_qcm}",
                   "/distribution", "/distribution/unsorted", "/stats", "/api/stats", "/preqc"],
    D.COORDINATOR: ["/", "/checked", "/stats", "/api/stats", "/preqc", "/qc", f"/items/{item_op}"],
    D.HEAD_OF_SERVICE: ["/", "/stats", "/api/stats", "/checked", f"/items/{item_op}", "/preqc"],
    D.FIELD_MANAGER: ["/", "/field", "/field?tab=manager", "/field?tab=cc", f"/items/{item_fm}",
                      "/stats", "/api/stats", "/preqc", "/qc"],
    D.SURVEYOR: ["/", "/field", "/stats", "/api/stats", "/preqc", f"/items/{item_op}"],
}
WHO = {D.ADMIN: admin, D.QC_OPERATOR: operator, D.QC_MANAGER: qcm, D.COORDINATOR: coord,
       D.HEAD_OF_SERVICE: head, D.FIELD_MANAGER: fm, D.SURVEYOR: sv}

DENIED = {
    D.ADMIN: {"/preqc": 403},
    D.QC_OPERATOR: {"/preqc": 403, "/field": 403, "/admin": 403},
    D.QC_MANAGER: {"/preqc": 403},
    D.COORDINATOR: {"/preqc": 403, "/qc": 403},
    D.HEAD_OF_SERVICE: {"/checked": 403, "/preqc": 403, f"/items/{item_op}": 404},
    D.FIELD_MANAGER: {"/qc": 403},
    D.SURVEYOR: {f"/items/{item_op}": 404},
}

bad = 0
for role, pages in PAGES.items():
    u = WHO[role]
    s = requests.Session()
    r = s.post(BASE + "/login/demo", data={"user_id": u.id, "role": role, "next": "/"}, timeout=30,
               allow_redirects=False)
    if r.status_code != 303 or not s.cookies:
        raise SystemExit(f"Login failed for {role}: {r.status_code}")
    print(f"== {role} — {u.full_name} (login {r.status_code})")
    for p in pages:
        r = s.get(BASE + p, allow_redirects=False, timeout=30)
        expected = DENIED.get(role, {}).get(p, 303 if p == "/qc/next" else 200)
        flag = "" if r.status_code == expected else f"  unexpected (expected {expected})"
        if r.status_code != expected:
            bad += 1
        print(f"   {r.status_code} {p}{flag}")
# Pre-QC — მომხმარებელი, რომელსაც სატესტო ჩანაწერები აქვს
s = requests.Session()
r = s.post(BASE + "/login/demo", data={"user_id": preqc_surveyor.id, "role": D.SURVEYOR, "next": "/"}, timeout=30, allow_redirects=False)
if r.status_code != 303 or not s.cookies:
    raise SystemExit("Pre-QC login failed")
for p in ["/preqc", "/"]:
    r = s.get(BASE + p, timeout=30)
    print(f"   preqc-surveyor {r.status_code} {p}")
    bad += r.status_code != 200
print("ERRORS:", bad)
sys.exit(1 if bad else 0)

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
from app.models import ItemPerson, QcItem, User  # noqa: E402

BASE = f"http://127.0.0.1:{os.environ.get('QCP_PORT', '8200')}"
db = SessionLocal()


def by_name(n):
    return db.scalar(select(User).where(User.full_name == n))


admin = by_name("ლუკა ნუკრაძე")
qcm = by_name("გიორგი ჩიგოგიძე")
coord = by_name("კოორდინატორი (დემო)")
head = by_name("სამსახურის უფროსი (დემო)")
demo_mgr = by_name("საველე მენეჯერი (დემო)")
fm_id = db.scalar(select(QcItem.field_manager_id).where(QcItem.state == D.AWAITING_FIELD))
fm = db.get(User, fm_id)
sv_id = db.scalar(select(ItemPerson.user_id).join(QcItem, QcItem.id == ItemPerson.item_id)
                  .where(QcItem.state == D.AWAITING_FIELD, ItemPerson.kind == D.P_SURVEYOR,
                         ItemPerson.user_id.is_not(None)))
sv = db.get(User, sv_id)
item_op = db.scalar(select(QcItem.id).where(QcItem.operator_id == admin.id, QcItem.state == D.AWAITING_QC))
item_fm = db.scalar(select(QcItem.id).where(QcItem.field_manager_id == fm.id, QcItem.state == D.AWAITING_FIELD))
item_qcm = db.scalar(select(QcItem.id).where(QcItem.state == D.AWAITING_QCM))
item_ret = db.scalar(select(QcItem.id).where(QcItem.state == D.RETURNED_TO_MANAGER))
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
WHO = {D.ADMIN: admin, D.QC_OPERATOR: admin, D.QC_MANAGER: qcm, D.COORDINATOR: coord,
       D.HEAD_OF_SERVICE: head, D.FIELD_MANAGER: fm, D.SURVEYOR: sv}

bad = 0
for role, pages in PAGES.items():
    u = WHO[role]
    s = requests.Session()
    r = s.post(BASE + "/login/demo", data={"user_id": u.id, "role": role, "next": "/"},
               allow_redirects=False)
    print(f"== {role} — {u.full_name} (login {r.status_code})")
    for p in pages:
        r = s.get(BASE + p, allow_redirects=False)
        flag = "" if r.status_code in (200, 303, 403, 404) else "  ⚠"
        if r.status_code >= 500:
            bad += 1
        print(f"   {r.status_code} {p}{flag}")
# Pre-QC — დემო გუნდის მენეჯერი
s = requests.Session()
s.post(BASE + "/login/demo", data={"user_id": demo_mgr.id, "role": D.FIELD_MANAGER, "next": "/"})
for p in ["/preqc", "/"]:
    r = s.get(BASE + p)
    print(f"   demo-manager {r.status_code} {p}")
    bad += r.status_code >= 500
print("ERRORS:", bad)

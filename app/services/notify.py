# -*- coding: utf-8 -*-
"""
მეილით შეტყობინება — ძირითადად საველე მენეჯერებს (მომხმარებლის მოთხოვნა, 2026-10-20).

  • მოქმედებაზე მონიშვნით „მეილით შეტყობინება" (დაბრუნება, QC მენეჯერის გადაწყვეტილება)
    ან ერთი კლიკით ბარათის „კომუნიკაციიდან";
  • ადრესატი — პასუხისმგებელი მენეჯერი, დანარჩენი მიკუთვნებული მენეჯერები — ასლში (CC);
  • SMTP — გარემოს ცვლადებით (QCP_SMTP_*). თუ არ არის, მეილი ინახება „preview" სტატუსით
    და ჩანს: ადმინისტრირება → მეილები (პროტოტიპში ასეა).
"""
import datetime as dt
import smtplib
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, parseaddr

from .. import domain as D
from ..config import (BASE_URL, SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_STARTTLS,
                      SMTP_USER)
from ..models import EmailMessage, User
from ..templating import env
from . import anon

SUBJECTS = {
    "qc_returned": "ოქმი დაბრუნდა — არ არის გასწორებული",
    "qcm_stand": "არ დათანხმებული — ხარვეზი რჩება",
    "qcm_field_right": "არ დათანხმებული — ველი მართალია",
    "qcm_both_right": "არ დათანხმებული — ორივე მართალია",
    "sent": "ახალი შენიშვნა ოქმზე",
    "comment": "შეტყობინება ოქმზე",
}


def recipients(db, item):
    """(მთავარი ადრესატი, CC სია) — პასუხისმგებელი მენეჯერი და სხვა მიკუთვნებული მენეჯერები."""
    primary = db.get(User, item.field_manager_id) if item.field_manager_id else None
    cc = [p.user for p in item.managers if p.user and (primary is None or p.user_id != primary.id)]
    if primary is None and cc:
        primary, cc = cc[0], cc[1:]
    return primary, cc


def sender_name(event, sender, recipients):
    """
    გამომგზავნის სახელი წერილში. HTML/ტექსტი ყველა ადრესატს (CC-ის ჩათვლით) ერთი და იგივე
    მიდის — თუ ერთი მაინც ველის როლშია (ან როლი არ აქვს — ადრესატი ველის მენეჯერად აირჩა),
    QC გამომგზავნი ანონიმურია (T-015).
    """
    actor_role = event.actor_role if event is not None else None
    field = any(not u.role_set or set(u.role_set) & set(D.FIELD_ROLES)
                for u in recipients if u is not None)
    return anon.actor_name(D.FIELD_ROLES[0] if field else None, sender, actor_role)


def queue(db, item, event, sender, kind, base_url=""):
    """
    ქმნის მეილის ჩანაწერს (იმავე ტრანზაქციაში, რაც მოქმედება). **არ აგზავნის** — გაგზავნა
    `deliver()`-ით, მხოლოდ წარმატებული commit-ის შემდეგ (T-019: rollback-ი წერილს ვერ დააბრუნებს).
    აბრუნებს EmailMessage-ს ან None-ს.
    """
    to, cc = recipients(db, item)
    if to is None:
        return None
    link = f"{(BASE_URL or base_url).rstrip('/')}/items/{item.id}"
    subject = f"NAPR QC · ოქმი {item.protocol_number} — {SUBJECTS.get(kind, 'შეტყობინება')}"
    ctx = {"item": item, "event": event, "sender": sender,
           "sender_name": sender_name(event, sender, [to, *cc]), "kind": kind, "link": link,
           "title": SUBJECTS.get(kind, "შეტყობინება ოქმზე"), "to": to, "D": D}
    html = env.get_template("email/notice.html").render(**ctx)
    text = env.get_template("email/notice.txt").render(**ctx)
    msg = EmailMessage(created_by_id=sender.id, to_user_id=to.id, to_email=to.email,
                       cc=[u.email for u in cc if u.email], subject=subject, html=html, text=text,
                       item_id=item.id, kind=kind,
                       status="no_address" if not to.email else "preview")
    db.add(msg)
    db.flush()
    return msg


def deliver(db, msg):
    """commit-ის შემდეგ: SMTP მითითებულია → აგზავნის და სტატუსს ინახავს. SMTP არ არის → preview რჩება."""
    if msg is None or msg.status != "preview" or not msg.to_email or not SMTP_HOST:
        return msg
    _send(msg)
    db.commit()
    return msg


def _send(msg):
    m = MimeMessage()
    m["Subject"] = msg.subject
    name, addr = parseaddr(SMTP_FROM)
    m["From"] = formataddr((name or "NAPR QC", addr))
    m["To"] = msg.to_email
    if msg.cc:
        m["Cc"] = ", ".join(msg.cc)
    m.set_content(msg.text)
    m.add_alternative(msg.html, subtype="html")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            if SMTP_STARTTLS:
                s.starttls()
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(m)
        msg.status = "sent"
        msg.sent_at = dt.datetime.now()
    except (OSError, smtplib.SMTPException) as e:          # ქსელი/ავტორიზაცია — ჩანაწერი რჩება
        msg.status = "failed"
        msg.error = str(e)[:500]

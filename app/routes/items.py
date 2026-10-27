# -*- coding: utf-8 -*-
"""ერთი შემთხვევის ბარათი (ოქმი + საკადასტრო კოდი): ინფორმაცია, მოქმედებები, ისტორია."""
import json
import secrets
from collections import defaultdict
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import domain as D
from .. import scope
from ..config import APP_DIR, UPLOAD_DIR
from ..db import get_db
from ..models import (Attachment, DefectCode, EmailMessage, ItemPerson, QcEvent, QcItem, QcReview,
                      User, UserRole)
from ..security import current, same_origin
from ..services import anon, notify
from ..workflow import (ConflictError, DuplicateError, WorkflowError, allowed_responses, apply,
                        available_actions, discard_new_files, is_item_manager, is_primary_manager,
                        keep_new_files, pending_request)
from .common import redirect, render
from .qc import next_pending

router = APIRouter()

_ZONES = {}
NOTIFY_ACTIONS = ("qc_returned", "qcm_stand", "qcm_field_right", "qcm_both_right", "comment")


def zone_names():
    if not _ZONES:
        d = json.loads((APP_DIR / "static" / "geo" / "names.json").read_text(encoding="utf-8"))
        _ZONES.update(d.get("zones", {}))
    return _ZONES


def _load(db, item_id, ctx):
    item = db.scalar(select(QcItem).where(QcItem.id == item_id).options(
        selectinload(QcItem.codes), selectinload(QcItem.operator), selectinload(QcItem.field_manager),
        selectinload(QcItem.people).selectinload(ItemPerson.user),
        selectinload(QcItem.protocol_creator)))
    if item is None or not scope.can_view(ctx, item):
        raise HTTPException(404, "ჩანაწერი ვერ მოიძებნა ან თქვენთვის ხელმისაწვდომი არ არის.")
    return item


@router.get("/items/{item_id}")
def detail(item_id: int, request: Request, ctx=Depends(current), db=Depends(get_db)):
    item = _load(db, item_id, ctx)
    events = db.scalars(select(QcEvent).where(QcEvent.item_id == item.id)
                        .options(selectinload(QcEvent.actor)).order_by(QcEvent.id)).all()
    atts = defaultdict(list)
    for a in db.scalars(select(Attachment).where(Attachment.item_id == item.id)):
        atts[a.event_id].append(a)
    if ctx.role in D.FIELD_ROLES:
        hidden = [e for e in events if e.action in scope.QC_INTERNAL_EVENTS]
        events = [e for e in events if e.action not in scope.QC_INTERNAL_EVENTS]
        sent = next((e for e in events if e.action == "sent"), None)
        for e in hidden:                      # გაგზავნამდე ატვირთული ფოტო გაგზავნასთან ჩანს
            moved = atts.pop(e.id, [])
            if moved and sent is not None:
                atts[sent.id].extend(moved)
    acts = available_actions(db, item, ctx.user, ctx.role)
    catalog = db.scalars(select(DefectCode).where(DefectCode.active.is_(True))
                         .order_by(DefectCode.sort)).all()
    # კონტროლი ველისთვის ანონიმურია (T-015) — ოპერატორი და გადანაწილება ველს არ გადაეცემა
    show_operator = ctx.role not in D.FIELD_ROLES
    surveyor_options, operators, manager_options = [], [], []
    if "save_review" in acts or "edit" in acts:
        have = {p.user_id for p in item.surveyors}
        surveyor_options = [(i, n) for i, n in db.execute(
            select(User.id, User.full_name).join(UserRole)
            .where(UserRole.role.in_([D.SURVEYOR, D.FIELD_MANAGER]), User.active.is_(True))
            .order_by(User.full_name)).all() if i not in have]
    if "reassign" in acts and show_operator:
        operators = db.execute(select(User.id, User.full_name).join(UserRole)
                               .where(UserRole.role == D.QC_OPERATOR, User.active.is_(True))
                               .order_by(User.full_name)).all()
    if "assign_manager" in acts:
        manager_options = db.execute(select(User.id, User.full_name).join(UserRole)
                                     .where(UserRole.role == D.FIELD_MANAGER, User.active.is_(True))
                                     .order_by(User.full_name)).all()
    emails = defaultdict(list)
    if ctx.role in D.QC_ROLES:
        ev_by_time = {e.id: e for e in events}
        for m in db.scalars(select(EmailMessage).where(EmailMessage.item_id == item.id)
                            .options(selectinload(EmailMessage.to_user))):
            # მეილი იმ მოვლენასთან ჩანს, რომლის შემდეგაც შეიქმნა
            ev = max((e for e in ev_by_time.values() if e.at <= m.created_at), key=lambda e: e.id,
                     default=None)
            if ev is not None:
                emails[ev.id].append(m)
    qc_role = ctx.role in (D.QC_OPERATOR, D.QC_MANAGER)
    back = request.query_params.get("back") or ""
    if not back.startswith("/"):
        back = "/qc" if qc_role else "/field"
    # ხედი (ფერები, მენიუ) — საიდანაც მოვიდა: QC სიიდან თუ ველის სიიდან
    view = "qc" if (qc_role or back.startswith("/qc")) else "field"
    if ctx.role in D.FIELD_ROLES:
        view = "field"
    queue = request.query_params.get("queue") == "1" and item.state == D.PENDING
    next_id = next_pending(db, ctx, item.id) if ctx.role == D.QC_OPERATOR and queue else None
    review = db.get(QcReview, item.id) if (ctx.role in (D.QC_MANAGER, D.ADMIN) or
                                           (ctx.role == D.QC_OPERATOR)) else None
    if review is not None:
        db.refresh(review, ["reviewer"])
    cc_only = (ctx.role == D.FIELD_MANAGER and is_item_manager(item, ctx.user)
               and not is_primary_manager(item, ctx.user))
    active = "disputes" if back.startswith("/qc/disagreements") else \
        "requests" if back.startswith("/qc/requests") else view
    return render(request, ctx, "items/detail.html", active=active, view=view,
        item=item, events=events, atts=atts, acts=acts, emails=emails,
        responses=allowed_responses(db, item.verdict) if item.verdict else [],
        manager_responses=allowed_responses(db, item.verdict) if item.verdict else [],
        responder=db.get(User, item.field_responder_id) if item.field_responder_id else None,
        pending_req=pending_request(db, item), review=review, cc_only=cc_only,
        catalog=catalog, catalog_map={c.code: c for c in catalog}, surveyor_options=surveyor_options,
        operators=operators, manager_options=manager_options, queue=queue, next_id=next_id,
        show_operator=show_operator,
        once=secrets.token_urlsafe(24),       # კომენტარის ფორმის ერთჯერადი token (T-019)
        zone_name=zone_names().get(item.zone or "", ""),
        show_false_fix=scope.can_see_false_fix(ctx),
        show_qc_error=scope.can_see_restricted_stats(ctx), back=back)


MESSAGES = {
    "save_review": "შენახულია (ჯერ არ გაგზავნილა).", "send": "გაიგზავნა.",
    "edit": "ცვლილება შენახულია.", "change_verdict": "სტატუსი შეიცვალა.",
    "request_verdict_change": "მოთხოვნა გაეგზავნა QC მენეჯერს.",
    "approve_verdict_change": "სტატუსის შეცვლა დადასტურდა.",
    "reject_verdict_change": "მოთხოვნა უარყოფილია.",
    "field_respond": "პასუხი გაიგზავნა.",
    "manager_approve": "„არ ვეთანხმები“ დადასტურდა — გადაეგზავნა QC მენეჯერს.",
    "manager_reject": "დაუბრუნდა ამზომველს.", "manager_respond": "პასუხი გაიგზავნა.",
    "qcm_stand": "ახსნა გაიგზავნა ველზე.",
    "qcm_field_right": "ველი მართალია — ოქმი დადებითით დაიხურა, აღირიცხა ოპერატორის შეცდომა.",
    "qcm_both_right": "ორივე მართალია — ოქმი დადებითით დაიხურა.",
    "qc_confirm": "დადასტურებულია — შემთხვევა დაიხურა.",
    "qc_return": "დაბრუნებულია.", "resolve_clarification": "სტატუსი მიენიჭა.",
    "clarify_again": "კითხვა გაიგზავნა.", "reassign": "გადანაწილდა.",
    "assign_manager": "მენეჯერი მიეწერა.", "review": "შეფასება შენახულია.",
    "comment": "კომენტარი დაემატა.",
}


@router.post("/items/{item_id}/action")
async def action(item_id: int, request: Request, ctx=Depends(current), db=Depends(get_db)):
    same_origin(request)
    item = _load(db, item_id, ctx)
    form = await request.form()
    data = {k: form.get(k) for k in form.keys() if k not in ("files", "surveyors", "marks")}
    if "surveyors_present" in form:
        data["surveyors"] = [x for x in form.getlist("surveyors") if str(x).strip()]
    data["marks"] = form.getlist("marks")
    files = [f for f in form.getlist("files") if getattr(f, "filename", "")]
    act = data.get("action", "")
    back = data.get("back") or f"/items/{item_id}"
    msg = None
    try:
        ev = apply(db, item, ctx.user, ctx.role, act, data, files)
        if (str(data.get("notify")) == "on" and ctx.role in D.QC_ROLES
                and ev.action in NOTIFY_ACTIONS):
            msg = notify.queue(db, item, ev, ctx.user, ev.action, base_url=str(request.base_url))
        db.commit()
    except DuplicateError as e:                 # იგივე ფორმა მეორედ — ახალი მოვლენა/მეილი არ არის
        db.rollback()
        discard_new_files(db)
        return redirect(f"/items/{item_id}", ok=str(e))
    except ConflictError as e:
        db.rollback()
        discard_new_files(db)
        db.refresh(item)
        if act == "field_respond" and item.field_response and item.field_responded_at:
            who = db.get(User, item.field_responder_id) if item.field_responder_id else None
            name = anon.actor_name(ctx.role, who, None) if who else "სხვამ"
            return redirect(f"/items/{item_id}", err=(
                f"ამ ოქმზე პასუხი უკვე გაგზავნა {name}"
                f" ({item.field_responded_at:%d.%m %H:%M}) — ერთ კოდზე ერთი პასუხი იგზავნება. "
                "შეგიძლიათ კომენტარი დაამატოთ."))
        return redirect(f"/items/{item_id}", err=str(e))
    except WorkflowError as e:
        db.rollback()
        discard_new_files(db)
        return redirect(f"/items/{item_id}?back={quote(back)}", err=str(e))
    except Exception:
        db.rollback()
        discard_new_files(db)
        raise
    keep_new_files(db)
    notice = ""
    if msg is not None:                         # გაგზავნა — მხოლოდ წარმატებული commit-ის შემდეგ
        notify.deliver(db, msg)
        notice = (" ✉ მეილი გაიგზავნა." if msg.status == "sent" else
                  " ✉ მეილი მომზადდა (SMTP ჯერ არ არის — ჩანს ადმინისტრირება → მეილები)."
                  if msg.status == "preview" else
                  " ✉ მეილი ვერ გაიგზავნა (ჩანს ადმინისტრირება → მეილები)." if msg.status == "failed"
                  else " ✉ მენეჯერს ელფოსტა არ აქვს რეგისტრირებული.")
    ok = MESSAGES.get(act, "შესრულდა.") + notice
    if act in ("send", "save_review") and data.get("go_next") and ctx.role == D.QC_OPERATOR:
        nid = next_pending(db, ctx, item.id)
        if nid:
            return redirect(f"/items/{nid}?back=/qc%3Ftab%3Dtodo&queue=1", ok=ok + " გაიხსნა შემდეგი ოქმი.")
    if act in ("send", "qc_confirm", "qcm_field_right", "qcm_both_right", "qcm_stand") and data.get("back"):
        return redirect(back, ok=ok)
    return redirect(f"/items/{item_id}", ok=ok)


@router.get("/attachments/{att_id}")
def attachment(att_id: int, ctx=Depends(current), db=Depends(get_db)):
    a = db.get(Attachment, att_id)
    if a is None:
        raise HTTPException(404, "ფაილი ვერ მოიძებნა.")
    _load(db, a.item_id, ctx)                       # ხილვადობის შემოწმება
    path = UPLOAD_DIR / str(a.item_id) / a.stored_name
    if not path.exists():
        raise HTTPException(404, "ფაილი ვერ მოიძებნა.")
    return FileResponse(path, media_type=a.content_type, filename=a.filename,
                        content_disposition_type="inline")

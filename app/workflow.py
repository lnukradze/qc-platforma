# -*- coding: utf-8 -*-
"""
სამუშაო პროცესი — სტატუსების სქემა (state machine).

ყოველი მოქმედება:
  1. ამოწმებს უფლებას (როლი + საკუთრება) და მიმდინარე მდგომარეობას;
  2. ამოწმებს ვერსიას — თუ ამასობაში სხვამ შეცვალა, ცვლილება არ შედის;
  3. ცვლის მდგომარეობას და **ყოველთვის** წერს ისტორიის ჩანაწერს (`QcEvent`).

სცენარები (მომხმარებლის აღწერა, 2026-10-19 / 2026-10-20):
  A  უარყოფითი/რეკომენდაცია → ველი „შესწორდა" / „გავითვალისწინებთ" → QC ადასტურებს (M)
  B  „არ ვეთანხმები" → **მხოლოდ** პასუხისმგებელი საველე მენეჯერის დადასტურებით → QC მენეჯერი:
       • ხარვეზი რჩება — დეტალური ახსნა; მონიშვნით წყდება, საჭიროა თუ არა მენეჯერის ჩართვა
       • ველი მართალია — სავალდებულოდ „დადებითი"; ოპერატორის შეცდომა (შეზღუდული სტატისტიკა)
       • ორივე მართალია — სავალდებულოდ „დადებითი"; არავის ეთვლება
  C  „შესწორდა", მაგრამ არ გასწორდა → QC აბრუნებს (მენეჯერის ჩართვა — მონიშვნით);
     აღირიცხება „ცრუ გასწორება"
  დაზუსტება — კითხვა და არა სტატუსი; პასუხის შემდეგ ოპერატორი საბოლოო სტატუსს ანიჭებს.
  გაგზავნის შემდეგ სტატუსს ცვლის QC მენეჯერი; ოპერატორი — მხოლოდ მოთხოვნით (დადასტურებით).
  კომენტარის, კოდებისა და ფოტოს შეცვლა თავისუფალია. ფოტოს ატვირთავს მხოლოდ კონტროლი.
"""
import datetime as dt
import mimetypes
import uuid

from sqlalchemy import select

from . import domain as D
from .config import ALLOWED_UPLOAD_TYPES, MAX_UPLOAD_MB, UPLOAD_DIR
from .models import (Attachment, ItemPerson, QcEvent, QcItemCode, QcReview, Setting, User,
                     VerdictRequest)
from .services.codes import classify


class WorkflowError(Exception):
    pass


class ConflictError(WorkflowError):
    pass


def allowed_responses(db, verdict):
    s = db.get(Setting, "allowed_responses")
    table = s.value if s else D.DEFAULT_ALLOWED_RESPONSES
    return list(table.get(verdict, []))


# ── ვინ ვისი ─────────────────────────────────────────────────────────
def is_item_operator(item, user):
    return item.operator_id == user.id


def is_item_surveyor(item, user):
    return item.protocol_creator_id == user.id or any(p.user_id == user.id for p in item.surveyors)


def is_primary_manager(item, user):
    """მოქმედებს მხოლოდ პასუხისმგებელი (ოქმის შემდგენის) მენეჯერი."""
    return item.field_manager_id == user.id


def is_item_manager(item, user):
    """მიკუთვნებული მენეჯერი (CC) — ხედავს, მაგრამ მოქმედება პასუხისმგებელისაა."""
    return is_primary_manager(item, user) or any(p.user_id == user.id for p in item.managers)


def pending_request(db, item):
    return db.scalar(select(VerdictRequest).where(VerdictRequest.item_id == item.id,
                                                  VerdictRequest.status == "pending"))


def _qc_side(item, user, role):
    return role in (D.QC_MANAGER, D.ADMIN) or (role == D.QC_OPERATOR and is_item_operator(item, user))


def _field_responder(item, user, role):
    return role == D.ADMIN or (role == D.SURVEYOR and is_item_surveyor(item, user)) or \
        (role == D.FIELD_MANAGER and is_primary_manager(item, user))


def _primary_manager_side(item, user, role):
    return role == D.ADMIN or (role == D.FIELD_MANAGER and is_primary_manager(item, user))


def available_actions(db, item, user, role) -> list[str]:
    """რა ღილაკები უნდა გამოჩნდეს ამ მომხმარებლისთვის ამ მდგომარეობაში."""
    s = item.state
    acts = []
    qcm = role in (D.QC_MANAGER, D.ADMIN)
    if _qc_side(item, user, role):
        if s == D.PENDING:
            acts += ["save_review", "send"]
        else:
            acts.append("edit")                         # კომენტარი, კოდები, ამზომველები, ფოტო
            if qcm:
                acts.append("change_verdict")
            elif pending_request(db, item) is None:
                acts.append("request_verdict_change")
        if s == D.AWAITING_QC:
            if item.verdict == D.CLARIFICATION:
                acts += ["resolve_clarification", "clarify_again"]
            else:
                acts += ["qc_confirm", "qc_return"]
    if qcm:
        if s == D.AWAITING_QCM:
            acts += ["qcm_stand", "qcm_field_right", "qcm_both_right"]
        if pending_request(db, item) is not None:
            acts += ["approve_verdict_change", "reject_verdict_change"]
        if s != D.CLOSED:
            acts += ["reassign", "assign_manager"]
        if item.checked_at is not None:
            acts.append("review")
    if s == D.AWAITING_FIELD and _field_responder(item, user, role):
        acts.append("field_respond")
    if _primary_manager_side(item, user, role):
        if s == D.AWAITING_MANAGER:
            acts += ["manager_approve", "manager_reject"]
        if s == D.RETURNED_TO_MANAGER:
            acts.append("manager_respond")
    if role not in (D.COORDINATOR, D.HEAD_OF_SERVICE):
        acts.append("comment")
    return acts


# ── დამხმარეები ──────────────────────────────────────────────────────
def _event(db, item, user, role, action, frm, to, comment=None, data=None):
    ev = QcEvent(item_id=item.id, at=dt.datetime.now(), actor_id=user.id, actor_role=role,
                 action=action, from_state=frm, to_state=to, comment=(comment or None), data=data)
    db.add(ev)
    db.flush()
    return ev


def _set_codes(db, item, codes, source):
    for c in list(item.codes):
        db.delete(c)
    db.flush()
    for code in dict.fromkeys(codes):
        db.add(QcItemCode(item_id=item.id, code=code, source=source))


def _codes_from_form(db, item, form, verdict, qc_comment):
    manual = [c.strip() for c in (form.get("codes") or "").split(",") if c.strip()]
    if verdict == D.POSITIVE:
        _set_codes(db, item, [], "manual")
    elif manual:
        src = form.get("codes_source") if form.get("codes_source") in ("auto", "manual", "legacy") \
            else "manual"
        _set_codes(db, item, manual, src)
    elif qc_comment:
        _set_codes(db, item, list(classify(qc_comment)), "auto")


def _set_surveyors(db, item, ids):
    """ოპერატორი ასწორებს ოქმის ამზომველებს (ყველა ხედავს შემთხვევას)."""
    ids = [int(x) for x in ids if str(x).strip().isdigit()]
    ids = list(dict.fromkeys(ids))
    if not ids and item.surveyors:
        raise WorkflowError("ოქმს მინიმუმ ერთი ამზომველი უნდა ჰყავდეს.")
    keep = {p.user_id: p for p in item.surveyors if p.user_id in ids}
    for p in list(item.surveyors):
        if p.user_id not in keep:
            item.people.remove(p)
    for pos, uid in enumerate(ids):
        p = keep.get(uid)
        if p is None:
            item.people.append(ItemPerson(kind=D.P_SURVEYOR, user_id=uid, position=pos,
                                          is_primary=pos == 0, source="manual"))
        else:
            p.position, p.is_primary = pos, pos == 0


def _close(item, reason):
    item.state = D.CLOSED
    item.close_reason = reason
    item.closed_at = dt.datetime.now()


def _reopen_to_field(item):
    item.state = D.AWAITING_FIELD
    item.close_reason = None
    item.closed_at = None
    item.field_response = None


def _apply_verdict(item, verdict, now):
    """ახალი სტატუსი გაგზავნის შემდეგ. D (checked_at) არ იცვლება — პირველი მინიჭებაა."""
    if verdict in D.FINAL_VERDICTS:
        item.checked_at = item.checked_at or now
        item.original_verdict = item.original_verdict or verdict
    item.verdict = verdict
    if verdict == D.POSITIVE:
        _close(item, D.CR_POSITIVE)
    else:
        _reopen_to_field(item)


def _flag(form, key):
    return str(form.get(key) or "").lower() in ("on", "1", "true", "yes")


def save_files(db, item, event, user, files):
    """ფოტოს/ფაილის ატვირთვა — ტიპისა და ზომის შემოწმებით."""
    saved = []
    for f in files or []:
        if not f or not getattr(f, "filename", ""):
            continue
        content = f.file.read()
        if not content:
            continue
        if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
            raise WorkflowError(f"ფაილი „{f.filename}“ {MAX_UPLOAD_MB} MB-ზე დიდია.")
        ctype = f.content_type or mimetypes.guess_type(f.filename)[0] or ""
        if ctype not in ALLOWED_UPLOAD_TYPES:
            raise WorkflowError(f"ფაილის ტიპი დაუშვებელია: {f.filename}")
        ext = mimetypes.guess_extension(ctype) or ""
        folder = UPLOAD_DIR / str(item.id)
        folder.mkdir(parents=True, exist_ok=True)
        stored = uuid.uuid4().hex + ext
        (folder / stored).write_bytes(content)
        a = Attachment(item_id=item.id, event_id=event.id if event else None,
                       uploaded_by_id=user.id, filename=f.filename[:255], stored_name=stored,
                       content_type=ctype, size=len(content))
        db.add(a)
        saved.append(a)
    db.flush()
    return saved


# ── მოქმედებები ──────────────────────────────────────────────────────
def apply(db, item, user, role, action, form: dict, files=None) -> QcEvent:
    if action not in available_actions(db, item, user, role):
        raise WorkflowError("ეს მოქმედება ამ მდგომარეობაში ან ამ როლით დაშვებული არ არის.")
    v = form.get("version")
    if v is not None and str(v) != str(item.version):
        raise ConflictError("ჩანაწერი ამასობაში სხვამ შეცვალა — გადახედეთ განახლებულ ვერსიას.")
    if files and role not in D.QC_ROLES:
        raise WorkflowError("ფოტოს ატვირთვა მხოლოდ კონტროლს შეუძლია.")

    frm = item.state
    comment = (form.get("comment") or "").strip()
    now = dt.datetime.now()
    data = {}

    if action in ("save_review", "send"):
        verdict = form.get("verdict") or None
        if verdict and verdict not in D.VERDICTS:
            raise WorkflowError("უცნობი ვერდიქტი.")
        qc_comment = (form.get("qc_comment") or "").strip()
        if action == "send":
            if not verdict:
                raise WorkflowError("აირჩიეთ ვერდიქტი.")
            if verdict != D.POSITIVE and not qc_comment:
                raise WorkflowError("უარყოფით, რეკომენდაციასა და დაზუსტებაზე კომენტარი სავალდებულოა.")
        item.verdict = verdict
        item.qc_comment = qc_comment or None
        _codes_from_form(db, item, form, verdict, qc_comment)
        if form.get("surveyors") is not None:
            _set_surveyors(db, item, form.get("surveyors") or [])
        db.flush()
        db.refresh(item)
        data = {"verdict": verdict, "codes": item.code_list}
        comment = comment or qc_comment
        if action == "save_review":
            item.draft_saved_at = now
            ev_action, to = "review_saved", frm
        else:
            item.first_sent_at = item.first_sent_at or now     # დღის რაოდენობა (დაზუსტებაც)
            item.sent_at = now
            item.draft_saved_at = None
            if verdict in D.FINAL_VERDICTS:                    # D — პირველი გაგზავნა
                item.checked_at = item.checked_at or now
                item.original_verdict = item.original_verdict or verdict
            if verdict == D.POSITIVE:
                _close(item, D.CR_POSITIVE)
            else:
                item.state = D.AWAITING_FIELD
            ev_action, to = "sent", item.state

    elif action == "edit":                                     # სტატუსის გარეშე
        qc_comment = (form.get("qc_comment") or "").strip()
        if item.verdict != D.POSITIVE and not qc_comment:
            raise WorkflowError("კომენტარი სავალდებულოა.")
        old = {"comment": item.qc_comment, "codes": item.code_list}
        item.qc_comment = qc_comment or None
        _codes_from_form(db, item, form, item.verdict, qc_comment)
        if form.get("surveyors") is not None:
            _set_surveyors(db, item, form.get("surveyors") or [])
        db.flush()
        db.refresh(item)
        data = {"before": old, "codes": item.code_list}
        ev_action, to = "edited", item.state

    elif action == "change_verdict":                           # QC მენეჯერი — პირდაპირ
        new = form.get("new_verdict")
        if new not in D.VERDICTS or new == item.verdict:
            raise WorkflowError("აირჩიეთ ახალი სტატუსი.")
        if not comment:
            raise WorkflowError("მიუთითეთ შეცვლის მიზეზი.")
        data = {"before": item.verdict, "verdict": new}
        _apply_verdict(item, new, now)
        ev_action, to = "verdict_changed", item.state

    elif action == "request_verdict_change":                   # ოპერატორი — დადასტურებით
        new = form.get("new_verdict")
        if new not in D.VERDICTS or new == item.verdict:
            raise WorkflowError("აირჩიეთ ახალი სტატუსი.")
        if not comment:
            raise WorkflowError("მიუთითეთ, რატომ უნდა შეიცვალოს სტატუსი.")
        db.add(VerdictRequest(item_id=item.id, requested_by_id=user.id, from_verdict=item.verdict,
                              to_verdict=new, comment=comment))
        data = {"from": item.verdict, "to": new}
        ev_action, to = "verdict_change_requested", frm

    elif action in ("approve_verdict_change", "reject_verdict_change"):
        req = pending_request(db, item)
        req.decided_by_id, req.decided_at, req.decision_comment = user.id, now, comment or None
        data = {"from": req.from_verdict, "to": req.to_verdict}
        if action == "approve_verdict_change":
            req.status = "approved"
            _apply_verdict(item, req.to_verdict, now)
            ev_action, to = "verdict_change_approved", item.state
        else:
            if not comment:
                raise WorkflowError("მიუთითეთ უარის მიზეზი.")
            req.status = "rejected"
            ev_action, to = "verdict_change_rejected", frm

    elif action == "field_respond":
        resp = form.get("response")
        if resp not in allowed_responses(db, item.verdict):
            raise WorkflowError("ეს პასუხი ამ ვერდიქტზე დაშვებული არ არის.")
        if resp in (D.R_DISAGREE, D.R_ANSWER) and not comment:
            raise WorkflowError("ამ პასუხს კომენტარი სჭირდება.")
        item.field_response = resp
        item.field_comment = comment or None
        item.field_responded_at = now
        item.field_responder_id = user.id
        item.state = D.AWAITING_MANAGER if resp == D.R_DISAGREE else D.AWAITING_QC
        ev_action, to, data = "field_responded", item.state, {"response": resp}

    elif action == "manager_approve":                          # „არ ვეთანხმები" დადასტურდა
        item.manager_visa_comment = comment or None
        item.dispute_count += 1
        item.state = D.AWAITING_QCM
        ev_action, to = "manager_approved", item.state

    elif action == "manager_reject":
        if not comment:
            raise WorkflowError("მიუთითეთ, რატომ უბრუნებთ ამზომველს.")
        item.state = D.AWAITING_FIELD
        item.field_response = None
        ev_action, to = "manager_rejected", item.state

    elif action == "manager_respond":
        resp = form.get("response")
        if resp not in allowed_responses(db, item.verdict):
            raise WorkflowError("აირჩიეთ პასუხი.")
        if resp in (D.R_DISAGREE, D.R_ANSWER) and not comment:
            raise WorkflowError("ამ პასუხს კომენტარი სჭირდება.")
        item.field_response = resp
        item.field_comment = comment or None
        item.field_responded_at = now
        item.field_responder_id = user.id
        if resp == D.R_DISAGREE:                                # იშვიათად — ისევ არ ეთანხმება
            item.dispute_count += 1
            item.state = D.AWAITING_QCM
        else:
            item.state = D.AWAITING_QC
        ev_action, to, data = "manager_responded", item.state, {"response": resp}

    elif action == "qcm_stand":                                # ხარვეზი რჩება
        if not comment:
            raise WorkflowError("დეტალური ახსნა სავალდებულოა — რატომ არის ხარვეზი გასასწორებელი.")
        item.qcm_explanation = comment
        item.qcm_decision = D.QCM_STAND
        item.manager_required = _flag(form, "manager_required")
        item.field_response = None
        item.state = D.RETURNED_TO_MANAGER if item.manager_required else D.AWAITING_FIELD
        ev_action, to = "qcm_stand", item.state
        data = {"manager_required": item.manager_required}

    elif action in ("qcm_field_right", "qcm_both_right"):
        key = "confirm_field_right" if action == "qcm_field_right" else "confirm_both_right"
        if not (_flag(form, "confirm_positive") or _flag(form, key)):
            raise WorkflowError("მონიშნეთ „დადებითი“ — ამის გარეშე გადაწყვეტილება ვერ შეინახება.")
        data = {"before": item.verdict}
        item.verdict = D.POSITIVE
        item.checked_at = item.checked_at or now
        item.qcm_explanation = comment or item.qcm_explanation
        if action == "qcm_field_right":
            item.qc_error = True
            item.qcm_decision = D.QCM_FIELD_RIGHT
            _close(item, D.CR_QC_ERROR)
        else:
            item.both_right = True
            item.qcm_decision = D.QCM_BOTH_RIGHT
            _close(item, D.CR_BOTH_RIGHT)
        ev_action, to = action, item.state

    elif action == "qc_confirm":
        item.corrected_confirmed = True
        item.confirmed_at = now
        _close(item, D.CR_CORRECTED if item.verdict == D.NEGATIVE else D.CR_ACKNOWLEDGED)
        ev_action, to = "qc_confirmed", item.state

    elif action == "qc_return":
        if not comment:
            raise WorkflowError("დაწერეთ, რა დარჩა გასასწორებელი.")
        item.returned_comment = comment
        item.return_count += 1
        if item.field_response == D.R_CORRECTED:
            item.false_fix_count += 1                          # „შესწორდა" — მაგრამ არ გასწორდა
        item.manager_required = _flag(form, "manager_required")
        item.field_response = None
        item.state = D.RETURNED_TO_MANAGER if item.manager_required else D.AWAITING_FIELD
        ev_action, to = "qc_returned", item.state
        data = {"manager_required": item.manager_required}

    elif action == "resolve_clarification":                    # დაზუსტდა → საბოლოო სტატუსი
        new = form.get("new_verdict")
        if new not in D.FINAL_VERDICTS:
            raise WorkflowError("აირჩიეთ საბოლოო სტატუსი.")
        qc_comment = (form.get("qc_comment") or "").strip() or item.qc_comment or ""
        if new != D.POSITIVE and not qc_comment:
            raise WorkflowError("უარყოფითსა და რეკომენდაციაზე კომენტარი სავალდებულოა.")
        item.qc_comment = qc_comment or None
        item.clarified = True
        _codes_from_form(db, item, form, new, qc_comment)
        _apply_verdict(item, new, now)
        item.sent_at = now
        db.flush()
        db.refresh(item)
        data = {"verdict": new, "codes": item.code_list}
        ev_action, to = "clarification_resolved", item.state

    elif action == "clarify_again":                            # დამატებითი კითხვა
        if not comment:
            raise WorkflowError("დაწერეთ კითხვა.")
        item.returned_comment = comment
        item.field_response = None
        item.state = D.AWAITING_FIELD
        ev_action, to = "clarify_again", item.state

    elif action == "reassign":
        new_op = form.get("operator_id")
        if not new_op:
            raise WorkflowError("აირჩიეთ ოპერატორი.")
        data = {"from": item.operator_id, "to": int(new_op)}
        item.operator_id = int(new_op)
        ev_action, to = "reassigned", frm

    elif action == "assign_manager":                           # QC მენეჯერი — ხელით
        mid = form.get("manager_id")
        if not str(mid or "").isdigit():
            raise WorkflowError("აირჩიეთ მენეჯერი.")
        mid = int(mid)
        if db.get(User, mid) is None:
            raise WorkflowError("მენეჯერი ვერ მოიძებნა.")
        data = {"from": item.field_manager_id, "to": mid}
        item.field_manager_id = mid
        for p in item.managers:
            p.is_primary = p.user_id == mid
        if all(p.user_id != mid for p in item.managers):
            item.people.append(ItemPerson(kind=D.P_MANAGER, user_id=mid, is_primary=True,
                                          position=0, source="manual"))
        ev_action, to = "manager_assigned", frm

    elif action == "review":                                   # QC მენეჯერის შეფასება
        marks = [m for m in (form.get("marks") or []) if m in D.REVIEW_MARKS]
        if not marks:
            raise WorkflowError("მონიშნეთ შეფასება.")
        if D.MARK_CORRECT in marks and len(marks) > 1:
            raise WorkflowError("„სწორია“ სხვა შენიშვნასთან ერთად ვერ მოინიშნება.")
        r = db.get(QcReview, item.id)
        if r is None:
            r = QcReview(item_id=item.id, marks=marks)
            db.add(r)
        r.marks, r.comment, r.reviewer_id, r.at, r.source = marks, comment or None, user.id, now, "manual"
        data = {"marks": marks}
        ev_action, to = "qc_reviewed", frm

    elif action == "comment":
        if not comment and not any(getattr(f, "filename", "") for f in (files or [])):
            raise WorkflowError("დაწერეთ კომენტარი ან მიამაგრეთ ფაილი.")
        ev_action, to = "comment", frm
    else:
        raise WorkflowError("უცნობი მოქმედება.")

    ev = _event(db, item, user, role, ev_action, frm, to, comment, data or None)
    if files:
        save_files(db, item, ev, user, files)
    item.version += 1
    item.updated_at = now
    db.flush()
    return ev

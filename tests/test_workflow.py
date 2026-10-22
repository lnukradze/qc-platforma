# -*- coding: utf-8 -*-
"""სამუშაო პროცესი — მომხმარებლის მიერ აღწერილი სცენარები (2026-10-19 / 2026-10-20)."""
import pytest

from app import domain as D
from app.models import QcEvent, QcReview, VerdictRequest
from app.services import stats as S
from app.workflow import ConflictError, WorkflowError, apply, available_actions


def act(db, item, user, role, action, files=None, **form):
    form.setdefault("version", item.version)
    ev = apply(db, item, user, role, action, form, files)
    db.commit()
    return ev


def send_negative(db, item, op, comment="ხელმოწერა აკლია მიმთითებელს"):
    return act(db, item, op, D.QC_OPERATOR, "send", verdict=D.NEGATIVE, qc_comment=comment)


def test_positive_is_closed_and_not_forwarded(db, people, item):
    act(db, item, people["op"], D.QC_OPERATOR, "send", verdict=D.POSITIVE)
    assert item.state == D.CLOSED and item.close_reason == D.CR_POSITIVE
    assert item.code_list == []
    assert "field_respond" not in available_actions(db, item, people["sv"], D.SURVEYOR)


def test_negative_requires_comment_and_gets_auto_codes(db, people, item):
    with pytest.raises(WorkflowError):
        act(db, item, people["op"], D.QC_OPERATOR, "send", verdict=D.NEGATIVE, qc_comment="")
    db.rollback()
    send_negative(db, item, people["op"])
    assert item.state == D.AWAITING_FIELD
    assert "DOC-04" in item.code_list          # „ხელმოწერა" → DOC-04 (rules.gs / taxonomy.py)
    assert item.checked_at is not None and item.first_sent_at is not None


def test_draft_is_not_counted_until_sent(db, people, item):
    """შენახვა (გაგზავნის გარეშე) D-ს და დღის რაოდენობას არ ცვლის — მხოლოდ გაგზავნა."""
    act(db, item, people["op"], D.QC_OPERATOR, "save_review", verdict=D.NEGATIVE, qc_comment="ფოტო")
    assert item.is_draft and item.checked_at is None and item.first_sent_at is None
    assert D.operator_color(item.state, item.is_draft) == "draft"
    assert S.operator_daily(db, people["op"].id)["today"] == 0
    send_negative(db, item, people["op"])
    assert not item.is_draft and item.checked_at is not None
    assert S.operator_daily(db, people["op"].id)["today"] == 1


def test_scenario_a_corrected_then_confirmed(db, people, item):
    send_negative(db, item, people["op"])
    act(db, item, people["sv2"], D.SURVEYOR, "field_respond", response=D.R_CORRECTED)   # G-ც პასუხობს
    assert item.state == D.AWAITING_QC
    assert D.operator_color(item.state) == "yellow"
    act(db, item, people["op"], D.QC_OPERATOR, "qc_confirm")
    assert item.state == D.CLOSED and item.close_reason == D.CR_CORRECTED
    assert item.corrected_confirmed is True
    assert item.verdict == D.NEGATIVE          # თავდაპირველი ვერდიქტი რჩება (მომხმარებლის წესი)


def test_disagreement_needs_manager_then_qcm_stands(db, people, item):
    send_negative(db, item, people["op"])
    with pytest.raises(WorkflowError):        # დასაბუთების გარეშე „არ ვეთანხმები" არ მიიღება
        act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_DISAGREE)
    db.rollback()
    act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_DISAGREE,
        comment="ზედდება არ არის — მეზობლის ნახაზია მოძველებული")
    assert item.state == D.AWAITING_MANAGER
    # QC მენეჯერს მენეჯერის დადასტურებამდე ვერაფერი შეუძლია
    assert "qcm_stand" not in available_actions(db, item, people["qcm"], D.QC_MANAGER)
    act(db, item, people["mgr"], D.FIELD_MANAGER, "manager_approve", comment="ვადასტურებ")
    assert item.state == D.AWAITING_QCM and item.dispute_count == 1
    with pytest.raises(WorkflowError):        # ახსნა სავალდებულოა
        act(db, item, people["qcm"], D.QC_MANAGER, "qcm_stand")
    db.rollback()
    act(db, item, people["qcm"], D.QC_MANAGER, "qcm_stand", comment="ორთოფოტოზე ზედდება ჩანს — 12 მ²",
        manager_required="on")
    assert item.state == D.RETURNED_TO_MANAGER and item.manager_required
    # დაბრუნებულზე ამზომველი ვეღარ პასუხობს — მხოლოდ მენეჯერი
    assert "field_respond" not in available_actions(db, item, people["sv"], D.SURVEYOR)
    act(db, item, people["mgr"], D.FIELD_MANAGER, "manager_respond", response=D.R_DISAGREE,
        comment="მაინც არ ვეთანხმებით")      # იშვიათად, მაგრამ დასაშვებია
    assert item.state == D.AWAITING_QCM and item.dispute_count == 2


def test_cc_principle_return_without_manager(db, people, item):
    """„საჭიროა საველე მენეჯერის ჩართვა" მოუნიშნავი → ამზომველებს უბრუნდებათ."""
    send_negative(db, item, people["op"])
    act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_CORRECTED)
    act(db, item, people["op"], D.QC_OPERATOR, "qc_return", comment="GAP ისევ არის")
    assert item.state == D.AWAITING_FIELD and not item.manager_required
    assert item.false_fix_count == 1 and item.return_count == 1
    assert "field_respond" in available_actions(db, item, people["sv2"], D.SURVEYOR)


def test_field_right_requires_positive_mark_and_counts_as_qc_error(db, people, item):
    send_negative(db, item, people["op"])
    act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_DISAGREE, comment="x")
    act(db, item, people["mgr"], D.FIELD_MANAGER, "manager_approve")
    with pytest.raises(WorkflowError):        # „დადებითი" მონიშვნის გარეშე ვერ შეინახება
        act(db, item, people["qcm"], D.QC_MANAGER, "qcm_field_right")
    db.rollback()
    act(db, item, people["qcm"], D.QC_MANAGER, "qcm_field_right", confirm_field_right="on")
    assert item.state == D.CLOSED and item.close_reason == D.CR_QC_ERROR
    assert item.verdict == D.POSITIVE and item.original_verdict == D.NEGATIVE and item.qc_error


def test_both_right_closes_positive_without_error(db, people, item):
    send_negative(db, item, people["op"])
    act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_DISAGREE, comment="x")
    act(db, item, people["mgr"], D.FIELD_MANAGER, "manager_approve")
    act(db, item, people["qcm"], D.QC_MANAGER, "qcm_both_right", confirm_both_right="on")
    assert item.close_reason == D.CR_BOTH_RIGHT and item.verdict == D.POSITIVE
    assert item.both_right and not item.qc_error


def test_recommendation_allows_acknowledge_or_disagree(db, people, item):
    act(db, item, people["op"], D.QC_OPERATOR, "send", verdict=D.RECOMMENDATION,
        qc_comment="სასურველია ფოტოები სხვადასხვა რაკურსიდან")
    with pytest.raises(WorkflowError):
        act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_CORRECTED)
    db.rollback()
    act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_DISAGREE, comment="ფოტო საკმარისია")
    assert item.state == D.AWAITING_MANAGER               # რეკომენდაციაზეც — მენეჯერის დადასტურებით


def test_clarification_is_not_a_status_until_resolved(db, people, item):
    act(db, item, people["op"], D.QC_OPERATOR, "send", verdict=D.CLARIFICATION,
        qc_comment="რა საფუძვლით ფლობს მეორე მოსარგებლე?")
    assert item.checked_at is None and item.first_sent_at is not None   # დღეში ითვლება, D — არა
    assert S.operator_daily(db, people["op"].id)["today"] == 1
    act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_ANSWER,
        comment="ნასყიდობის ხელშეკრულება 2004 წლის")
    assert "resolve_clarification" in available_actions(db, item, people["op"], D.QC_OPERATOR)
    act(db, item, people["op"], D.QC_OPERATOR, "resolve_clarification", new_verdict=D.NEGATIVE,
        qc_comment="ხელშეკრულება ოქმს არ ერთვის — ატვირთეთ")
    assert item.verdict == D.NEGATIVE and item.state == D.AWAITING_FIELD
    assert item.clarified and item.checked_at is not None


def test_operator_cannot_change_status_after_send_without_approval(db, people, item):
    send_negative(db, item, people["op"])
    acts = available_actions(db, item, people["op"], D.QC_OPERATOR)
    assert "change_verdict" not in acts and "request_verdict_change" in acts
    d_time = item.checked_at
    # კომენტარის შეცვლა თავისუფალია, სტატუსი — არა
    act(db, item, people["op"], D.QC_OPERATOR, "edit", qc_comment="ხელმოწერა აკლია (გვ. 2)",
        verdict=D.POSITIVE)
    assert item.verdict == D.NEGATIVE
    act(db, item, people["op"], D.QC_OPERATOR, "request_verdict_change", new_verdict=D.RECOMMENDATION,
        comment="შეცდომით მივანიჭე")
    assert db.query(VerdictRequest).filter_by(status="pending").count() == 1
    act(db, item, people["qcm"], D.QC_MANAGER, "approve_verdict_change")
    assert item.verdict == D.RECOMMENDATION and item.checked_at == d_time   # D არ იცვლება
    assert item.original_verdict == D.NEGATIVE


def test_qc_manager_changes_status_directly(db, people, item):
    send_negative(db, item, people["op"])
    act(db, item, people["qcm"], D.QC_MANAGER, "change_verdict", new_verdict=D.POSITIVE,
        comment="ხარვეზი არ არის")
    assert item.state == D.CLOSED and item.verdict == D.POSITIVE


def test_review_marks_are_saved(db, people, item):
    send_negative(db, item, people["op"])
    act(db, item, people["qcm"], D.QC_MANAGER, "review", marks=[D.MARK_MISSED, D.MARK_INCOMPLETE],
        comment="EVD-01 გამორჩა")
    r = db.get(QcReview, item.id)
    assert set(r.marks) == {D.MARK_MISSED, D.MARK_INCOMPLETE}
    with pytest.raises(WorkflowError):        # „სწორია" სხვა შენიშვნასთან ერთად — არა
        act(db, item, people["qcm"], D.QC_MANAGER, "review", marks=[D.MARK_CORRECT, D.MARK_WRONG])


def test_field_cannot_upload_files(db, people, item):
    send_negative(db, item, people["op"])

    class F:
        filename = "a.png"
        content_type = "image/png"
    with pytest.raises(WorkflowError):
        act(db, item, people["sv"], D.SURVEYOR, "field_respond", files=[F()], response=D.R_CORRECTED)


def test_only_primary_manager_acts(db, people):
    """სხვადასხვა გუნდის ამზომველები: ორივე მენეჯერი ხედავს, მოქმედებს შემდგენის მენეჯერი."""
    from conftest import make_item
    it = make_item(db, people, managers=("mgr", "mgr2"))
    send_negative(db, it, people["op"])
    act(db, it, people["sv"], D.SURVEYOR, "field_respond", response=D.R_DISAGREE, comment="x")
    assert "manager_approve" in available_actions(db, it, people["mgr"], D.FIELD_MANAGER)
    assert "manager_approve" not in available_actions(db, it, people["mgr2"], D.FIELD_MANAGER)


def test_only_own_operator_and_right_roles(db, people, item):
    assert available_actions(db, item, people["op2"], D.QC_OPERATOR) == ["comment"]
    with pytest.raises(WorkflowError):
        act(db, item, people["op2"], D.QC_OPERATOR, "send", verdict=D.POSITIVE)
    db.rollback()
    send_negative(db, item, people["op"])
    with pytest.raises(WorkflowError):        # სხვა გუნდის მენეჯერი ვერ პასუხობს
        act(db, item, people["mgr2"], D.FIELD_MANAGER, "field_respond", response=D.R_CORRECTED)
    db.rollback()
    with pytest.raises(WorkflowError):        # სხვა ამზომველი ვერ პასუხობს
        act(db, item, people["other"], D.SURVEYOR, "field_respond", response=D.R_CORRECTED)


def test_second_surveyor_gets_conflict(db, people, item):
    """ორი ამზომველი ერთდროულად: ვინც პირველი გაგზავნის, იმის პასუხი ითვლება."""
    send_negative(db, item, people["op"])
    stale = item.version
    act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_CORRECTED)
    with pytest.raises((ConflictError, WorkflowError)):
        apply(db, item, people["sv2"], D.SURVEYOR, "field_respond",
              {"version": stale, "response": D.R_DISAGREE, "comment": "x"})


def test_every_action_is_in_history(db, people, item):
    send_negative(db, item, people["op"])
    act(db, item, people["sv"], D.SURVEYOR, "field_respond", response=D.R_CORRECTED)
    act(db, item, people["op"], D.QC_OPERATOR, "qc_confirm")
    actions = [e.action for e in db.query(QcEvent).filter_by(item_id=item.id).order_by(QcEvent.id)]
    assert actions == ["sent", "field_responded", "qc_confirmed"]
    roles = [e.actor_role for e in db.query(QcEvent).filter_by(item_id=item.id).order_by(QcEvent.id)]
    assert roles == [D.QC_OPERATOR, D.SURVEYOR, D.QC_OPERATOR]

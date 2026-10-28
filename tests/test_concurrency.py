# -*- coding: utf-8 -*-
"""
T-019 — ერთდროული ჩაწერა: ერთ ვერსიაზე პირველი ითვლება (ატომური CAS), კომენტარი ერთჯერადი
token-ით (FormToken), კომენტარი და შეფასება ვერსიას არ ზრდის, /qc/bulk-send აღარ არსებობს.

პარალელი ნამდვილია: ორი thread, ორი HTTP სესია, ორი დამოუკიდებელი DB კავშირი (ფაილური SQLite,
WAL). ტესტის barrier მხოლოდ იმას უზრუნველყოფს, რომ ორივე CAS-მდე ერთსა და იმავე ვერსიით მივიდეს —
თავად ჩაწერას არაფერი არ ასერიალებს, გარდა ბაზისა. მონაცემი გამოგონილია.
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import domain as D
from app import workflow
from app.db import SessionLocal
from app.main import app
from app.models import Attachment, EmailMessage, FormToken, QcEvent, QcItem, QcReview
from app.services import notify
from app.workflow import ConflictError, DuplicateError, WorkflowError, apply
from conftest import make_item

ORIGIN = {"origin": "http://testserver"}
ROUNDS = 20
TIMEOUT = 30


def client(user, role):
    c = TestClient(app)
    r = c.post("/login/demo", data={"user_id": str(user.id), "role": role}, headers=ORIGIN,
               follow_redirects=False)
    assert r.status_code == 303 and "err=" not in r.headers["location"]
    return c


def outcome(r):
    """route წარმატებასაც და შეცდომასაც 303-ით აბრუნებს — ვარჩევთ ok / err-ს."""
    assert r.status_code == 303, r.status_code
    q = parse_qs(urlparse(r.headers["location"]).query)
    if "err" in q:
        return "err", q["err"][0]
    return "ok", q.get("ok", [""])[0]


def post(c, item_id, **data):
    return c.post(f"/items/{item_id}/action", data=data, headers=ORIGIN, follow_redirects=False)


def fresh():
    """მესამე, ახალი სესია — მხოლოდ commit-ებული მდგომარეობა."""
    return SessionLocal()


def count(s, model, **where):
    q = s.query(model)
    for k, v in where.items():
        q = q.filter(getattr(model, k) == v)
    return q.count()


@pytest.fixture(autouse=True)
def uploads(monkeypatch, tmp_path):
    """ყოველ ტესტს — საკუთარი, ახალი uploads (ოქმის id ბაზის ხელახლა შექმნისას მეორდება)."""
    from app.routes import items as items_route
    monkeypatch.setattr(workflow, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(items_route, "UPLOAD_DIR", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def sends(monkeypatch):
    """რეალური SMTP არა: _send — დამჭერი, რომელიც მცდელობებს ითვლის (ქსელი არ გამოიყენება)."""
    calls = []
    monkeypatch.setattr(notify, "SMTP_HOST", "")

    def fake(msg):
        s = fresh()                                    # გაგზავნამდე ჩანაწერი უკვე commit-ებულია
        try:
            calls.append(s.get(EmailMessage, msg.id) is not None)
        finally:
            s.close()
        msg.status = "sent"
    monkeypatch.setattr(notify, "_send", fake)
    return calls


def sent_item(db, people, protocol, verdict=D.NEGATIVE, qc_comment="ფოტო აკლია (ტესტი)"):
    it = make_item(db, people, protocol=protocol, cad=f"202.51.12.40.{protocol[-3:]}.001")
    apply(db, it, people["op"], D.QC_OPERATOR, "send",
          {"version": it.version, "verdict": verdict, "qc_comment": qc_comment})
    db.commit()
    return it


class Gate:
    """ორივე მონაწილე ჩერდება მითითებულ ფუნქციამდე და ერთად გრძელდება."""

    def __init__(self, monkeypatch, name, parties=2):
        self.barrier = threading.Barrier(parties, timeout=TIMEOUT)
        self.seen, self.errors = [], []
        orig = getattr(workflow, name)

        def wrapper(*a, **k):
            if threading.current_thread() is threading.main_thread():     # მოსამზადებელი ნაბიჯი
                return orig(*a, **k)
            self.seen.append(a[2] if name == "_bump_version" else None)
            self.barrier.wait()
            try:
                return orig(*a, **k)
            except Exception as e:                    # სერვისის დონის შეცდომის ტიპი
                self.errors.append(type(e))
                raise
        monkeypatch.setattr(workflow, name, wrapper)

    def reset(self):
        self.barrier.reset()
        self.seen.clear()
        self.errors.clear()


def race(*calls):
    with ThreadPoolExecutor(len(calls)) as ex:
        futs = [ex.submit(f) for f in calls]
        return [f.result(timeout=TIMEOUT) for f in futs]


# ── 1. ორი ერთდროული პასუხი — 20 რაუნდი ─────────────────────────────────
def test_parallel_field_respond_first_wins(db, people, monkeypatch):
    c1, c2 = client(people["sv"], D.SURVEYOR), client(people["sv2"], D.SURVEYOR)
    gate = Gate(monkeypatch, "_bump_version")
    ids = {c1: people["sv"].id, c2: people["sv2"].id}
    for n in range(ROUNDS):
        it = sent_item(db, people, f"63{n:05d}")
        v = it.version
        gate.reset()
        res = race(*[lambda c=c: (c, outcome(post(c, it.id, action="field_respond", version=v,
                                                   response=D.R_CORRECTED, comment=f"from {ids[c]}")))
                     for c in (c1, c2)])
        assert gate.seen == [v, v]                                   # ორივემ ერთი ვერსია ნახა
        assert gate.errors == [ConflictError]                        # სერვისი: ზუსტად ერთი კონფლიქტი
        wins = [c for c, (k, _) in res if k == "ok"]
        loss = [(c, m) for c, (k, m) in res if k == "err"]
        assert len(wins) == 1 and len(loss) == 1, res
        assert "პასუხი უკვე გაგზავნა" in loss[0][1]
        s = fresh()
        try:
            row = s.get(QcItem, it.id)
            evs = s.query(QcEvent).filter_by(item_id=it.id, action="field_responded").all()
            assert len(evs) == 1 and row.version == v + 1
            assert evs[0].actor_id == row.field_responder_id == ids[wins[0]]
            assert row.field_comment == f"from {ids[wins[0]]}" and evs[0].comment == row.field_comment
            assert row.state == D.AWAITING_QC
        finally:
            s.close()


def test_parallel_service_level_two_sessions(db, people, monkeypatch):
    """იგივე სერვისის დონეზე: ორი დამოუკიდებელი Session, ორი thread."""
    it = sent_item(db, people, "6400001")
    gate = Gate(monkeypatch, "_bump_version")

    def run(who):
        s = fresh()
        try:
            item = s.get(QcItem, it.id)
            user = s.get(type(people[who]), people[who].id)
            try:
                apply(s, item, user, D.SURVEYOR, "field_respond",
                      {"version": it.version, "response": D.R_CORRECTED})
                s.commit()
                return "ok"
            except ConflictError:
                s.rollback()
                return "conflict"
        finally:
            s.close()
    assert sorted(race(lambda: run("sv"), lambda: run("sv2"))) == ["conflict", "ok"]
    s = fresh()
    try:
        assert count(s, QcEvent, item_id=it.id, action="field_responded") == 1
        assert s.get(QcItem, it.id).version == it.version + 1
    finally:
        s.close()


# ── 2. version სავალდებულოა ყველა მოქმედებაზე, გარდა comment / review ─────
def _v(db, it):
    db.refresh(it)
    return it.version


def _go(db, it, people, who, role, action, **form):
    apply(db, it, people[who], role, action, {"version": _v(db, it), **form})
    db.commit()


def _st_sent(db, it, p):
    pass


def _st_disagree(db, it, p):
    _go(db, it, p, "sv", D.SURVEYOR, "field_respond", response=D.R_DISAGREE, comment="არა")


def _st_awaiting_qcm(db, it, p):
    _st_disagree(db, it, p)
    _go(db, it, p, "mgr", D.FIELD_MANAGER, "manager_approve")


def _st_corrected(db, it, p):
    _go(db, it, p, "sv", D.SURVEYOR, "field_respond", response=D.R_CORRECTED)


def _st_returned_mgr(db, it, p):
    _st_corrected(db, it, p)
    _go(db, it, p, "op", D.QC_OPERATOR, "qc_return", comment="ისევ", manager_required="on")


def _st_request(db, it, p):
    _go(db, it, p, "op", D.QC_OPERATOR, "request_verdict_change",
        new_verdict=D.RECOMMENDATION, comment="უკეთესია")


def _st_clarification_answered(db, it, p):
    _go(db, it, p, "sv", D.SURVEYOR, "field_respond", response=D.R_ANSWER, comment="პასუხი")


# (მოქმედება, საწყისი მდგომარეობა, ვინ, როლი, ფორმა, ვერდიქტი გაგზავნისას; None — გაუგზავნელი)
CASES = [
    ("save_review", None, "op", D.QC_OPERATOR, {"verdict": D.NEGATIVE, "qc_comment": "x"}, None),
    ("send", None, "op", D.QC_OPERATOR, {"verdict": D.NEGATIVE, "qc_comment": "x"}, None),
    ("edit", _st_sent, "op", D.QC_OPERATOR, {"qc_comment": "ახალი"}, D.NEGATIVE),
    ("change_verdict", _st_sent, "qcm", D.QC_MANAGER,
     {"new_verdict": D.RECOMMENDATION, "comment": "მიზეზი"}, D.NEGATIVE),
    ("request_verdict_change", _st_sent, "op", D.QC_OPERATOR,
     {"new_verdict": D.RECOMMENDATION, "comment": "მიზეზი"}, D.NEGATIVE),
    ("approve_verdict_change", _st_request, "qcm", D.QC_MANAGER, {"comment": "კი"}, D.NEGATIVE),
    ("reject_verdict_change", _st_request, "qcm", D.QC_MANAGER, {"comment": "არა"}, D.NEGATIVE),
    ("field_respond", _st_sent, "sv", D.SURVEYOR, {"response": D.R_CORRECTED}, D.NEGATIVE),
    ("manager_approve", _st_disagree, "mgr", D.FIELD_MANAGER, {}, D.NEGATIVE),
    ("manager_reject", _st_disagree, "mgr", D.FIELD_MANAGER, {"comment": "გაასწორე"}, D.NEGATIVE),
    ("manager_respond", _st_returned_mgr, "mgr", D.FIELD_MANAGER, {"response": D.R_CORRECTED},
     D.NEGATIVE),
    ("qcm_stand", _st_awaiting_qcm, "qcm", D.QC_MANAGER, {"comment": "რჩება"}, D.NEGATIVE),
    ("qcm_field_right", _st_awaiting_qcm, "qcm", D.QC_MANAGER, {"confirm_positive": "on"},
     D.NEGATIVE),
    ("qcm_both_right", _st_awaiting_qcm, "qcm", D.QC_MANAGER, {"confirm_positive": "on"},
     D.NEGATIVE),
    ("qc_confirm", _st_corrected, "op", D.QC_OPERATOR, {}, D.NEGATIVE),
    ("qc_return", _st_corrected, "op", D.QC_OPERATOR, {"comment": "ისევ"}, D.NEGATIVE),
    ("resolve_clarification", _st_clarification_answered, "op", D.QC_OPERATOR,
     {"new_verdict": D.NEGATIVE, "qc_comment": "x"}, D.CLARIFICATION),
    ("clarify_again", _st_clarification_answered, "op", D.QC_OPERATOR, {"comment": "კიდევ?"},
     D.CLARIFICATION),
    ("reassign", _st_sent, "qcm", D.QC_MANAGER, {"operator_id": "OP2"}, D.NEGATIVE),
    ("assign_manager", _st_sent, "qcm", D.QC_MANAGER, {"manager_id": "MGR2"}, D.NEGATIVE),
]


def _prepare(db, people, setup, verdict):
    it = make_item(db, people)
    if setup is not None:
        apply(db, it, people["op"], D.QC_OPERATOR, "send",
              {"version": it.version, "verdict": verdict, "qc_comment": "შენიშვნა"})
        db.commit()
        setup(db, it, people)
    db.refresh(it)
    return it


def _snapshot(s, item_id):
    row = s.get(QcItem, item_id)
    return (row.version, row.state, row.verdict, row.operator_id, row.field_manager_id,
            count(s, QcEvent, item_id=item_id))


@pytest.mark.parametrize("action,setup,who,role,form,verdict", CASES, ids=[c[0] for c in CASES])
def test_version_required_and_atomic(db, people, action, setup, who, role, form, verdict):
    it = _prepare(db, people, setup, verdict)
    form = {k: (str(people["op2"].id) if v == "OP2" else str(people["mgr2"].id) if v == "MGR2" else v)
            for k, v in form.items()}
    assert action in workflow.available_actions(db, it, people[who], role)
    v = it.version
    s = fresh()
    before = _snapshot(s, it.id)
    s.close()
    bad = {"missing": None, "empty": "", "text": "abc", "float": "1.5", "negative": "-1", "zero": "0"}
    for name, val in bad.items():
        f = dict(form) if val is None else {**form, "version": val}
        with pytest.raises(WorkflowError) as e:
            apply(db, it, people[who], role, action, f)
        assert not isinstance(e.value, ConflictError), name
        db.rollback()
    with pytest.raises(ConflictError):
        apply(db, it, people[who], role, action, {**form, "version": v + 7})
    db.rollback()
    s = fresh()
    assert _snapshot(s, it.id) == before                      # უარზე გვერდითი ეფექტი ნულია
    s.close()
    apply(db, it, people[who], role, action, {**form, "version": v})
    db.commit()
    s = fresh()
    try:
        assert s.get(QcItem, it.id).version == v + 1         # ზუსტად ერთხელ, არა v+2
        assert count(s, QcEvent, item_id=it.id) == before[-1] + 1
    finally:
        s.close()


def test_http_without_version_rejected(db, people):
    it = sent_item(db, people, "6500001")
    c = client(people["sv"], D.SURVEYOR)
    kind, msg = outcome(post(c, it.id, action="field_respond", response=D.R_CORRECTED))
    assert kind == "err" and "განაახლეთ გვერდი" in msg
    s = fresh()
    try:
        assert s.get(QcItem, it.id).state == D.AWAITING_FIELD
        assert count(s, QcEvent, item_id=it.id, action="field_responded") == 0
    finally:
        s.close()


def test_stale_form_after_state_change_gets_conflict_message(db, people):
    """წაგებულმა უკვე შეცვლილი მდგომარეობა ნახა — მაინც კონფლიქტის განმარტება, არა „დაუშვებელია“."""
    it = sent_item(db, people, "6500002")
    v = it.version
    assert outcome(post(client(people["sv"], D.SURVEYOR), it.id, action="field_respond",
                        version=v, response=D.R_CORRECTED))[0] == "ok"
    kind, msg = outcome(post(client(people["sv2"], D.SURVEYOR), it.id, action="field_respond",
                             version=v, response=D.R_CORRECTED))
    assert kind == "err" and "პასუხი უკვე გაგზავნა" in msg


def test_role_origin_and_scope_still_enforced(db, people):
    it = sent_item(db, people, "6500003")
    kind, _ = outcome(post(client(people["coord"], D.COORDINATOR), it.id, action="field_respond",
                           version=it.version, response=D.R_CORRECTED))
    assert kind == "err"
    r = client(people["other"], D.SURVEYOR).post(
        f"/items/{it.id}/action", headers=ORIGIN, follow_redirects=False,
        data={"action": "field_respond", "version": it.version, "response": D.R_CORRECTED})
    assert r.status_code == 404                                    # სხვისი ოქმი
    r = client(people["sv"], D.SURVEYOR).post(
        f"/items/{it.id}/action", headers={"origin": "http://evil.example.com"},
        follow_redirects=False,
        data={"action": "field_respond", "version": it.version, "response": D.R_CORRECTED})
    assert r.status_code == 403
    s = fresh()
    try:
        assert s.get(QcItem, it.id).version == it.version
    finally:
        s.close()


# ── 3. კომენტარი: ერთჯერადი token (B-11, შებრუნებული) ──────────────────
def _once(c, item_id):
    r = c.get(f"/items/{item_id}")
    assert r.status_code == 200
    return r.context["once"]


def test_detail_context_has_fresh_once(db, people):
    it = sent_item(db, people, "6600001")
    c = client(people["op"], D.QC_OPERATOR)
    a, b = _once(c, it.id), _once(c, it.id)
    assert a != b and len(a) >= 32 and len(a) <= 64


def test_same_token_twice_one_comment_one_email(db, people, monkeypatch, sends):
    monkeypatch.setattr(notify, "SMTP_HOST", "smtp.invalid")        # დამჭერი — ქსელი არა
    it = sent_item(db, people, "6600002")
    c = client(people["op"], D.QC_OPERATOR)
    once = _once(c, it.id)
    v = it.version
    k1, m1 = outcome(post(c, it.id, action="comment", comment="გთხოვთ", notify="on", once=once))
    k2, m2 = outcome(post(c, it.id, action="comment", comment="სხვა ტექსტი", notify="on", once=once))
    assert (k1, k2) == ("ok", "ok") and "კომენტარი დაემატა" in m1
    assert "კომენტარი უკვე დამატებულია" in m2 and "✉" not in m2
    s = fresh()
    try:
        assert count(s, QcEvent, item_id=it.id, action="comment") == 1
        assert count(s, EmailMessage, item_id=it.id) == 1
        assert count(s, FormToken, token=once) == 1
        assert s.get(QcItem, it.id).version == v                    # კომენტარი ვერსიას არ ზრდის
    finally:
        s.close()
    assert sends == [True]                                          # ერთი გაგზავნა, commit-ის შემდეგ


def test_same_token_preview_mode_one_record(db, people, sends):
    it = sent_item(db, people, "6600003")
    c = client(people["op"], D.QC_OPERATOR)
    once = _once(c, it.id)
    for _ in range(2):
        post(c, it.id, action="comment", comment="x", notify="on", once=once)
    s = fresh()
    try:
        assert count(s, EmailMessage, item_id=it.id) == 1
        assert s.query(EmailMessage).filter_by(item_id=it.id).one().status == "preview"
    finally:
        s.close()
    assert sends == []


def test_same_token_parallel(db, people, monkeypatch):
    it = sent_item(db, people, "6600004")
    c1, c2 = client(people["op"], D.QC_OPERATOR), client(people["op"], D.QC_OPERATOR)
    once = _once(c1, it.id)
    Gate(monkeypatch, "_use_token")
    res = race(*[lambda c=c: outcome(post(c, it.id, action="comment", comment="ერთად", notify="on",
                                          once=once)) for c in (c1, c2)])
    msgs = sorted(m for _, m in res)
    assert all(k == "ok" for k, _ in res)
    assert any("კომენტარი დაემატა" in m for m in msgs)
    assert any("კომენტარი უკვე დამატებულია" in m for m in msgs)
    s = fresh()
    try:
        assert count(s, QcEvent, item_id=it.id, action="comment") == 1
        assert count(s, EmailMessage, item_id=it.id) == 1
        assert count(s, FormToken, token=once) == 1
    finally:
        s.close()


def test_comment_without_token_refused(db, people):
    it = sent_item(db, people, "6600005")
    c = client(people["op"], D.QC_OPERATOR)
    kind, msg = outcome(post(c, it.id, action="comment", comment="x", notify="on"))
    assert kind == "err" and "განაახლეთ გვერდი" in msg
    s = fresh()
    try:
        assert count(s, QcEvent, item_id=it.id, action="comment") == 0
        assert count(s, EmailMessage, item_id=it.id) == 0 and count(s, FormToken) == 0
    finally:
        s.close()


def test_different_tokens_same_text_both_saved(db, people):
    """60-წამიანი ტექსტის წესი არ გამოიყენება — განსხვავებული token → ორი კომენტარი."""
    it = sent_item(db, people, "6600006")
    c = client(people["op"], D.QC_OPERATOR)
    for _ in range(2):
        assert outcome(post(c, it.id, action="comment", comment="იგივე", once=_once(c, it.id)))[0] == "ok"
    s = fresh()
    try:
        assert count(s, QcEvent, item_id=it.id, action="comment") == 2
    finally:
        s.close()


def test_service_duplicate_error(db, people):
    it = sent_item(db, people, "6600007")
    apply(db, it, people["op"], D.QC_OPERATOR, "comment", {"comment": "a", "once": "tok-1"})
    db.commit()
    with pytest.raises(DuplicateError):
        apply(db, it, people["op"], D.QC_OPERATOR, "comment", {"comment": "b", "once": "tok-1"})
    db.rollback()
    assert count(db, QcEvent, item_id=it.id, action="comment") == 1


# ── 4. კომენტარი / შეფასება ვერსიას არ ზრდის (B-12, შებრუნებული) ────────
def test_comment_does_not_break_open_edit_form(db, people):
    it = sent_item(db, people, "6700001")
    op = client(people["op"], D.QC_OPERATOR)
    v = op.get(f"/items/{it.id}").context["item"].version            # ოპერატორის ღია ფორმა
    sv = client(people["sv"], D.SURVEYOR)
    assert outcome(post(sv, it.id, action="comment", comment="ხვალ", once=_once(sv, it.id)))[0] == "ok"
    s = fresh()
    assert s.get(QcItem, it.id).version == v
    s.close()
    kind, msg = outcome(post(op, it.id, action="edit", version=v, qc_comment="დაზუსტებული"))
    assert kind == "ok", msg
    s = fresh()
    try:
        assert s.get(QcItem, it.id).version == v + 1
    finally:
        s.close()


def test_comment_and_review_ignore_stale_version(db, people):
    it = sent_item(db, people, "6700002", verdict=D.POSITIVE, qc_comment="")
    v = it.version
    apply(db, it, people["qcm"], D.QC_MANAGER, "comment",
          {"comment": "a", "once": "tok-stale", "version": v - 1})
    apply(db, it, people["qcm"], D.QC_MANAGER, "review", {"marks": [D.MARK_CORRECT], "version": "abc"})
    db.commit()
    db.refresh(it)
    assert it.version == v


def test_parallel_first_reviews_no_500_last_wins(db, people, monkeypatch):
    it = sent_item(db, people, "6700003", verdict=D.POSITIVE, qc_comment="")
    v = it.version
    qcm, adm = client(people["qcm"], D.QC_MANAGER), client(people["admin"], D.ADMIN)
    gate = Gate(monkeypatch, "_save_review")
    payload = {qcm: ([D.MARK_MISSED], "first"), adm: ([D.MARK_INCOMPLETE], "second")}
    res = race(*[lambda c=c: outcome(post(c, it.id, action="review", marks=payload[c][0],
                                          comment=payload[c][1])) for c in (qcm, adm)])
    assert all(k == "ok" for k, _ in res) and gate.errors == []
    s = fresh()
    try:
        evs = s.query(QcEvent).filter_by(item_id=it.id, action="qc_reviewed").order_by(QcEvent.id).all()
        assert len(evs) == 2
        r = s.get(QcReview, it.id)
        last = evs[-1]                                  # ბოლოს commit-ებული — ბოლო მოვლენაც მისია
        assert r.reviewer_id == last.actor_id and r.comment == last.comment
        assert r.marks == last.data["marks"]            # ერთი payload, არა ნარევი
        assert s.get(QcItem, it.id).version == v
    finally:
        s.close()


def test_review_then_state_change_keeps_both(db, people):
    it = sent_item(db, people, "6700004")
    v = it.version
    apply(db, it, people["qcm"], D.QC_MANAGER, "review", {"marks": [D.MARK_CORRECT]})
    db.commit()
    apply(db, it, people["sv"], D.SURVEYOR, "field_respond", {"version": v, "response": D.R_CORRECTED})
    db.commit()
    s = fresh()
    try:
        row = s.get(QcItem, it.id)
        assert row.version == v + 1 and row.field_response == D.R_CORRECTED
        assert s.get(QcReview, it.id).marks == [D.MARK_CORRECT]
    finally:
        s.close()


# ── 5. ფაილები და rollback ───────────────────────────────────────────────
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _files(item_id):
    folder = workflow.UPLOAD_DIR / str(item_id)
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_photo_only_comment_once(db, people):
    it = sent_item(db, people, "6800001")
    c = client(people["op"], D.QC_OPERATOR)
    once = _once(c, it.id)
    send = lambda: c.post(f"/items/{it.id}/action", headers=ORIGIN, follow_redirects=False,  # noqa: E731
                          data={"action": "comment", "once": once},
                          files=[("files", ("a.png", PNG, "image/png"))])
    assert outcome(send())[0] == "ok"
    first = _files(it.id)
    assert len(first) == 1
    kind, msg = outcome(send())
    assert kind == "ok" and "უკვე დამატებულია" in msg
    assert _files(it.id) == first                                 # ახალი ფაილი არ დარჩა
    r = c.post(f"/items/{it.id}/action", headers=ORIGIN, follow_redirects=False,
               data={"action": "comment", "once": _once(c, it.id)},
               files=[("files", ("b.png", PNG, "image/png"))])
    assert outcome(r)[0] == "ok"                                  # ახალი token — ახალი ფოტო
    s = fresh()
    try:
        assert count(s, Attachment, item_id=it.id) == 2
        assert count(s, QcEvent, item_id=it.id, action="comment") == 2
    finally:
        s.close()


def test_field_cannot_upload(db, people):
    it = sent_item(db, people, "6800002")
    c = client(people["sv"], D.SURVEYOR)
    r = c.post(f"/items/{it.id}/action", headers=ORIGIN, follow_redirects=False,
               data={"action": "comment", "comment": "x", "once": _once(c, it.id)},
               files=[("files", ("a.png", PNG, "image/png"))])
    assert outcome(r)[0] == "err" and _files(it.id) == []


def test_failure_after_upload_rolls_back_token_and_file(db, people, monkeypatch):
    it = sent_item(db, people, "6800003")
    c = client(people["op"], D.QC_OPERATOR)
    once = _once(c, it.id)

    def broken(*a, **k):
        raise WorkflowError("ტესტის მარცხი")
    real_queue = notify.queue
    monkeypatch.setattr(notify, "queue", broken)
    data = {"action": "comment", "comment": "x", "notify": "on", "once": once}
    r = c.post(f"/items/{it.id}/action", headers=ORIGIN, follow_redirects=False, data=data,
               files=[("files", ("a.png", PNG, "image/png"))])
    assert outcome(r)[0] == "err"
    assert _files(it.id) == []
    s = fresh()
    try:
        assert count(s, FormToken, token=once) == 0 and count(s, Attachment, item_id=it.id) == 0
        assert count(s, QcEvent, item_id=it.id, action="comment") == 0
    finally:
        s.close()
    monkeypatch.setattr(notify, "queue", real_queue)
    r = c.post(f"/items/{it.id}/action", headers=ORIGIN, follow_redirects=False, data=data,
               files=[("files", ("a.png", PNG, "image/png"))])
    assert outcome(r)[0] == "ok" and len(_files(it.id)) == 1        # გამართული retry იმავე token-ით


# ── 6. /qc/bulk-send აღარ არსებობს ───────────────────────────────────────
def test_bulk_send_removed(db, people):
    it = make_item(db, people, protocol="6900001")
    apply(db, it, people["op"], D.QC_OPERATOR, "save_review",
          {"version": it.version, "verdict": D.NEGATIVE, "qc_comment": "x"})
    db.commit()
    s = fresh()
    before = _snapshot(s, it.id)
    s.close()
    c = client(people["op"], D.QC_OPERATOR)
    r = c.post("/qc/bulk-send", data={"ids": str(it.id)}, headers=ORIGIN, follow_redirects=False)
    assert r.status_code == 404
    assert "/qc/bulk-send" not in app.openapi()["paths"]
    s = fresh()
    try:
        assert _snapshot(s, it.id) == before
    finally:
        s.close()
    kind, _ = outcome(post(c, it.id, action="send", version=before[0], verdict=D.NEGATIVE,
                           qc_comment="x"))
    assert kind == "ok"                                             # ერთეული send მუშაობს

# -*- coding: utf-8 -*-
"""ხილვადობა — სერვერზე, როლითა და საკუთრებით."""
from sqlalchemy import select

from app import domain as D
from app import scope
from app.models import QcEvent, QcItem
from app.workflow import apply
from conftest import ctx, make_item


def _ids(db, c):
    return {i.id for i in db.scalars(scope.items_query(c))}


def test_operator_sees_only_own(db, people, item):
    assert item.id in _ids(db, ctx(people["op"], D.QC_OPERATOR))
    assert item.id not in _ids(db, ctx(people["op2"], D.QC_OPERATOR))
    assert scope.can_view(ctx(people["qcm"], D.QC_MANAGER), item)


def test_field_sees_nothing_before_send_and_nothing_positive(db, people, item):
    sv = ctx(people["sv"], D.SURVEYOR)
    assert not scope.can_view(sv, item)                       # ჯერ არ გაგზავნილა
    apply(db, item, people["op"], D.QC_OPERATOR, "send", {"version": item.version, "verdict": D.POSITIVE})
    db.commit()
    assert not scope.can_view(sv, item)                       # დადებითი ველზე არ მიდის
    assert item.id not in _ids(db, sv)


def test_all_surveyors_and_all_managers_see_negative(db, people):
    it = make_item(db, people, managers=("mgr", "mgr2"))
    apply(db, it, people["op"], D.QC_OPERATOR, "send", {"version": it.version, "verdict": D.NEGATIVE, "qc_comment": "ფოტო აკლია"})
    db.commit()
    assert scope.can_view(ctx(people["sv"], D.SURVEYOR), it)
    assert scope.can_view(ctx(people["sv2"], D.SURVEYOR), it)
    assert scope.can_view(ctx(people["mgr"], D.FIELD_MANAGER), it)
    assert scope.can_view(ctx(people["mgr2"], D.FIELD_MANAGER), it)   # CC — ხედავს
    assert not scope.can_view(ctx(people["other"], D.SURVEYOR), it)


def test_coordinator_reads_checked_items_head_sees_stats_only(db, people, item):
    c = ctx(people["coord"], D.COORDINATOR)
    h = ctx(people["head"], D.HEAD_OF_SERVICE)
    assert not scope.can_view(c, item)                         # ჯერ არ გავლილა
    apply(db, item, people["op"], D.QC_OPERATOR, "send", {"version": item.version, "verdict": D.NEGATIVE, "qc_comment": "x"})
    db.commit()
    assert scope.can_view(c, item) and item.id in _ids(db, c)
    assert not scope.can_view(h, item) and _ids(db, h) == set()
    # სტატისტიკისთვის ყველა ჩანაწერი შედის ორივესთვის
    assert db.scalar(select(QcItem.id).where(scope.item_filter(h))) == item.id
    assert not scope.can_see_operator_stats(h)
    assert not scope.can_see_operator_stats(c)                 # T-015: კოორდინატორს — ველის ჭრილი
    for role in D.ROLES:
        assert scope.can_see_operator_stats(ctx(people["admin"], role)) == (role in D.QC_ROLES)


def test_preqc_only_for_field_roles(db, people):
    assert scope.can_see_preqc(ctx(people["sv"], D.SURVEYOR))
    assert scope.can_see_preqc(ctx(people["mgr"], D.FIELD_MANAGER))
    for who, role in (("op", D.QC_OPERATOR), ("qcm", D.QC_MANAGER), ("admin", D.ADMIN),
                      ("coord", D.COORDINATOR), ("head", D.HEAD_OF_SERVICE)):
        assert not scope.can_see_preqc(ctx(people[who], role))


def test_restricted_stats(db, people):
    assert scope.can_see_restricted_stats(ctx(people["qcm"], D.QC_MANAGER))
    assert not scope.can_see_restricted_stats(ctx(people["mgr"], D.FIELD_MANAGER))
    assert not scope.can_see_restricted_stats(ctx(people["coord"], D.COORDINATOR))


def test_field_does_not_see_qc_internal_history(db, people, item):
    """დანიშვნა, გაუგზავნელი სამუშაო ვერსია, მოთხოვნები, შეფასება — QC-ს შიდა საქმეა."""
    apply(db, item, people["op"], D.QC_OPERATOR, "save_review",
          {"version": item.version, "verdict": D.POSITIVE, "qc_comment": ""})
    apply(db, item, people["op"], D.QC_OPERATOR, "send",
          {"version": item.version, "verdict": D.NEGATIVE, "qc_comment": "ფოტო აკლია"})
    apply(db, item, people["qcm"], D.QC_MANAGER, "review", {"marks": [D.MARK_CORRECT]})
    db.commit()
    q = select(QcEvent.action).join(QcItem).where(QcEvent.item_id == item.id)
    sv = ctx(people["sv"], D.SURVEYOR)
    assert set(db.scalars(q.where(scope.event_filter(sv)))) == {"sent"}
    assert set(db.scalars(q.where(scope.event_filter(ctx(people["op"], D.QC_OPERATOR))))) == \
        {"review_saved", "sent", "qc_reviewed"}

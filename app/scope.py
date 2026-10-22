# -*- coding: utf-8 -*-
"""
ხილვადობა — **ვინ რომელ ჩანაწერს ხედავს**. ყველა სია, დეტალი, სტატისტიკა და
API ამ ფუნქციებს გადის; სხვისი ჩანაწერი 404-ს იძლევა (და არა 403-ს — რომ
ჩანაწერის არსებობაც არ გამჟღავნდეს).

  QC ოპერატორი      — მხოლოდ მასზე დანიშნული ოქმები
  QC მენეჯერი/ადმინი — ყველაფერი
  საველე მენეჯერი   — მისთვის მიკუთვნებული ოქმები (მოქმედებს მხოლოდ პასუხისმგებელი)
  ამზომველი         — სადაც ის ოქმის ამზომველია ან შემდგენია
  კოორდინატორი      — კონტროლის გავლილი ოქმები, მხოლოდ ნახვით + სტატისტიკა
  სამსახურის უფროსი — მხოლოდ ხარვეზების სტატისტიკა (ოქმის ბარათი — არა)
  Pre-QC            — მხოლოდ საველე მენეჯერი და ამზომველი (მომხმარებლის წესი, 2026-10-20)
"""
from sqlalchemy import and_, exists, false, or_, true
from sqlalchemy.orm import aliased

from . import domain as D
from .models import ItemPerson, QcEvent, QcItem


def _person(kind, user_id):
    """EXISTS ოქმის ადამიანებში — ალიასით, რომ სხვა ItemPerson მოთხოვნაში არ „შეიწოვოს"."""
    ip = aliased(ItemPerson)
    return exists().where(ip.item_id == QcItem.id, ip.kind == kind,
                          ip.user_id == user_id).correlate(QcItem)


def item_filter(ctx):
    """WHERE პირობა აქტიური როლისთვის (სტატისტიკისთვისაც)."""
    u, r = ctx.user, ctx.role
    if r in (D.ADMIN, D.QC_MANAGER, D.COORDINATOR, D.HEAD_OF_SERVICE):
        return true()
    if r == D.QC_OPERATOR:
        return QcItem.operator_id == u.id
    if r == D.FIELD_MANAGER:
        return or_(QcItem.field_manager_id == u.id, _person(D.P_MANAGER, u.id))
    if r == D.SURVEYOR:
        return or_(QcItem.protocol_creator_id == u.id, _person(D.P_SURVEYOR, u.id))
    return false()


def field_visible():
    """ველზე გაგზავნილი შემთხვევები: დადებითი ველზე არ მიდის (მომხმარებლის წესი)."""
    return and_(QcItem.first_sent_at.is_not(None),
                or_(QcItem.close_reason.is_(None), QcItem.close_reason != D.CR_POSITIVE))


# QC-ს შიდა ჩანაწერები — ველს არ უჩანს (დანიშვნა, სამუშაო ვერსია, გადანაწილება,
# სტატუსის შეცვლის მოთხოვნა, QC მენეჯერის შეფასება)
QC_INTERNAL_EVENTS = ("assigned", "review_saved", "reassigned", "verdict_change_requested",
                      "verdict_change_rejected", "qc_reviewed")


def event_filter(ctx):
    """ისტორიის ჩანაწერები, რომლებიც აქტიურ როლს უჩანს (item_filter-თან ერთად)."""
    if ctx.role in D.FIELD_ROLES:
        return and_(field_visible(), QcEvent.action.not_in(QC_INTERNAL_EVENTS))
    return true()


def items_query(ctx):
    from sqlalchemy import select
    q = select(QcItem).where(item_filter(ctx))
    if ctx.role in D.FIELD_ROLES:
        q = q.where(field_visible())
    elif ctx.role == D.COORDINATOR:
        q = q.where(QcItem.first_sent_at.is_not(None))
    elif ctx.role == D.HEAD_OF_SERVICE:
        q = q.where(false())
    return q


def can_view(ctx, item) -> bool:
    r, u = ctx.role, ctx.user
    if r == D.HEAD_OF_SERVICE:
        return False
    if r == D.COORDINATOR:
        return item.first_sent_at is not None          # გავლილი — მხოლოდ ნახვით
    if r in (D.ADMIN, D.QC_MANAGER):
        return True
    if r == D.QC_OPERATOR:
        return item.operator_id == u.id
    if r in D.FIELD_ROLES:
        if item.first_sent_at is None or item.close_reason == D.CR_POSITIVE:
            return False
        if r == D.FIELD_MANAGER:
            return item.field_manager_id == u.id or any(p.user_id == u.id for p in item.managers)
        return item.protocol_creator_id == u.id or any(p.user_id == u.id for p in item.surveyors)
    return False


def can_open_items(ctx) -> bool:
    """ოქმის ბარათები/სიები საერთოდ უჩანს თუ არა როლს."""
    return ctx.role != D.HEAD_OF_SERVICE


def can_see_preqc(ctx) -> bool:
    """Pre-QC მხოლოდ საველე მენეჯერს და ამზომველს — სხვას არავის."""
    return ctx.role in D.FIELD_ROLES


def can_see_restricted_stats(ctx) -> bool:
    """ოპერატორის შეცდომები და QC მენეჯერის შეფასებები — მხოლოდ QC მენეჯერი და ადმინი."""
    return ctx.role in (D.QC_MANAGER, D.ADMIN)


def can_see_false_fix(ctx) -> bool:
    """„ცრუ გასწორების" აღრიცხვა — მენეჯერები და ადმინი (არა საერთო სტატისტიკაში)."""
    return ctx.role in (D.QC_MANAGER, D.FIELD_MANAGER, D.ADMIN)


def can_see_operator_stats(ctx) -> bool:
    """„კონტროლის სტატისტიკა" (ოპერატორების ჭრილი) — სამსახურის უფროსს არ უჩანს."""
    return ctx.role != D.HEAD_OF_SERVICE

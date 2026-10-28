# -*- coding: utf-8 -*-
"""
JSON API — სამომავლო ინტეგრაციებისთვის (სააგენტოს სხვა სისტემები, მობილური, Pre-QC).

ყველა endpoint იგივე ხილვადობის ფილტრს გადის, რასაც გვერდები.
სრული აღწერა: /docs (OpenAPI).
"""
import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import selectinload

from .. import domain as D
from .. import scope
from ..db import get_db
from ..models import ItemPerson, Presence, QcEvent, QcItem
from ..security import current, same_origin
from ..services import anon
from ..services.listfilter import api_surveyors
from ..workflow import _insert              # INSERT … ON CONFLICT — SQLite / PostgreSQL (T-019)

PRESENCE_SECONDS = 60          # რამდენ ხანს ითვლება „ახლა ხსნის" ბოლო სიგნალის შემდეგ
log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["API"])


@router.get("/health")
def health(db=Depends(get_db)):
    ok = db.scalar(select(QcItem.id).limit(1)) is not None
    return {"status": "ok" if ok else "empty"}


@router.get("/me")
def me(ctx=Depends(current)):
    return {"id": ctx.user.id, "name": ctx.user.full_name, "role": ctx.role,
            "roles": sorted(ctx.user.role_set)}


def _item_json(i: QcItem, viewer_role, detail=False):
    d = {"id": i.id, "protocol": i.protocol_number, "cadcode": i.cadcode, "kind": i.kind,
         "zone": i.zone, "state": i.state,
         "state_label": D.labels(viewer_role)["STATE_LABELS"].get(i.state),     # ველს — ნეიტრალური (T-031)
         "verdict": i.verdict, "codes": i.code_list,
         "checked_at": i.checked_at.isoformat() if i.checked_at else None,
         "field_manager": i.field_manager.full_name if i.field_manager else None,
         "surveyors": i.surveyor_names,
         "managers": [p.display_name for p in i.managers]}
    if viewer_role not in D.FIELD_ROLES:           # კონტროლი ველისთვის ანონიმურია (T-015)
        d["operator"] = i.operator.full_name if i.operator else None
    if detail:
        d.update({"qc_comment": i.qc_comment, "field_response": i.field_response,
                  "field_comment": i.field_comment, "close_reason": i.close_reason,
                  "version": i.version})
    return d


@router.get("/items")
def items(request: Request, state: str | None = None, limit: int = 50, offset: int = 0,
          ctx=Depends(current), db=Depends(get_db)):
    q = scope.items_query(ctx).options(selectinload(QcItem.codes), selectinload(QcItem.operator),
                                       selectinload(QcItem.field_manager),
                                       selectinload(QcItem.people).selectinload(ItemPerson.user))
    if state in D.STATES:
        q = q.where(QcItem.state == state)
    rows = db.scalars(q.order_by(QcItem.id.desc()).limit(min(limit, 200)).offset(offset)).all()
    return {"items": [_item_json(i, ctx.role) for i in rows], "limit": limit, "offset": offset}


@router.get("/items/{item_id}")
def item(item_id: int, ctx=Depends(current), db=Depends(get_db)):
    i = db.get(QcItem, item_id)
    if i is None or not scope.can_view(ctx, i):
        raise HTTPException(404, "ვერ მოიძებნა")
    events = db.scalars(select(QcEvent).join(QcItem).where(QcEvent.item_id == i.id,
                                                            scope.event_filter(ctx))
                        .options(selectinload(QcEvent.actor)).order_by(QcEvent.id)).all()
    d = _item_json(i, ctx.role, detail=True)
    d["history"] = [_event_json(e, ctx.role) for e in events]
    return d


def _event_json(e, viewer_role):
    h = {"at": e.at.isoformat(), "action": e.action, "from": e.from_state, "to": e.to_state,
         "comment": e.comment, "approx": e.approx}
    # ველს QC-ის როლი არ უჩანს (T-031) — როგორც presence-ში (_others)
    if not anon.hidden(viewer_role, e.actor, e.actor_role):
        h["role"] = e.actor_role
    return h


@router.get("/filters/surveyors")
def filter_surveyors(manager: str = "", ctx=Depends(current), db=Depends(get_db)):
    """ფილტრის ჩამოშლისთვის: მენეჯერის გუნდის ამზომველები (T-011). საველე მენეჯერს — მხოლოდ საკუთარი."""
    return api_surveyors(db, ctx, manager)


# ── ვინ ხსნის ოქმს ახლა (ყვითელი მოციმციმე ნიშანი) ─────────────────────
def _others(db, ids, me_id, viewer_role):
    since = dt.datetime.now() - dt.timedelta(seconds=PRESENCE_SECONDS)
    out = {}
    for pr in db.scalars(select(Presence).where(Presence.item_id.in_(ids), Presence.last_seen >= since,
                                                Presence.user_id != me_id)
                         .options(selectinload(Presence.user))):
        # ველის მნახველს QC-ის მონაწილე — მხოლოდ „ხარისხის კონტროლი", როლის გარეშე
        p = {"name": anon.actor_name(viewer_role, pr.user, pr.role)}
        if not anon.hidden(viewer_role, pr.user, pr.role):
            p["role"] = D.ROLE_SHORT.get(pr.role, "")
        out.setdefault(pr.item_id, []).append(p)
    return out


@router.post("/presence/{item_id}")
def presence_ping(item_id: int, request: Request, ctx=Depends(current), db=Depends(get_db)):
    """ოქმის გვერდი ყოველ ~20 წამში აგზავნის — „ამ ოქმს ვხსნი"."""
    same_origin(request)
    item = db.get(QcItem, item_id)
    if item is None or not scope.can_view(ctx, item):
        raise HTTPException(404, "ვერ მოიძებნა")
    now = dt.datetime.now()
    # ერთი ატომური upsert (არა ORM read-modify-write): ორი ჩანართის პირველი ping, პარალელური leave
    # ან წმენდა 500-ს აღარ იძლევა. ძველი დრო ახალს არ გადაწერს (WHERE) — განახლება არ იკარგება.
    ins = _insert(db, Presence).values(item_id=item_id, user_id=ctx.user.id, role=ctx.role,
                                       last_seen=now)
    db.execute(ins.on_conflict_do_update(
        index_elements=["item_id", "user_id"],
        set_={"last_seen": ins.excluded.last_seen, "role": ins.excluded.role},
        where=Presence.last_seen <= ins.excluded.last_seen))
    db.commit()
    _cleanup(db, now)
    return {"others": _others(db, [item_id], ctx.user.id, ctx.role).get(item_id, [])}


def _cleanup(db, now):
    """
    ძველი (>10 წთ) ჩანაწერები — ping-ის commit-ის შემდეგ, ცალკე ტრანზაქციაში: საკუთარი ჩანაწერი უკვე
    ახალია და არ წაიშლება. ჩაწერის ლოკი / deadlock → გამოტოვება (შემდეგი ping წმენდს), არა 500.
    """
    try:
        db.execute(delete(Presence).where(Presence.last_seen < now - dt.timedelta(minutes=10)))
        db.commit()
    except OperationalError:
        db.rollback()
        log.warning("presence: ძველი ჩანაწერების წმენდა გამოტოვდა (ბაზა დაკავებულია)")


@router.post("/presence/{item_id}/leave")
def presence_leave(item_id: int, request: Request, ctx=Depends(current), db=Depends(get_db)):
    same_origin(request)
    db.execute(delete(Presence).where(Presence.item_id == item_id, Presence.user_id == ctx.user.id))
    db.commit()
    return {"ok": True}


@router.get("/presence")
def presence(ids: str = "", ctx=Depends(current), db=Depends(get_db)):
    """სიისთვის: რომელ ოქმებს ხსნის ახლა სხვა (მხოლოდ ჩემთვის ხილული ოქმები)."""
    wanted = [int(x) for x in ids.split(",") if x.strip().isdigit()][:300]
    if not wanted:
        return {}
    visible = [i for (i,) in db.execute(scope.items_query(ctx).with_only_columns(QcItem.id)
                                        .where(QcItem.id.in_(wanted)))]
    return _others(db, visible, ctx.user.id, ctx.role)

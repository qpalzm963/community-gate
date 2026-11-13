"""訪客預約／現場登記。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..db import get_db
from ..models import Alert, AlertType, Household, User, VehicleSession, Visitor, VisitorStatus, now
from ..schemas import VisitorIn
from ..services.events import bus
from ..vision.plate import clean, format_plate

router = APIRouter(prefix="/api/visitors", tags=["visitors"])


def visitor_dict(v: Visitor) -> dict:
    return {
        "id": v.id,
        "household_id": v.household_id,
        "household_unit": v.household.unit_no if v.household else "",
        "name": v.name,
        "phone": v.phone,
        "plate": v.plate,
        "plate_display": format_plate(v.plate),
        "vehicle_type": v.vehicle_type,
        "purpose": v.purpose,
        "authorized_from": v.authorized_from,
        "authorized_until": v.authorized_until,
        "status": v.status,
        "source": v.source,
        "entered_at": v.entered_at,
        "exited_at": v.exited_at,
        "created_at": v.created_at,
    }


@router.get("")
def list_visitors(
    scope: str = "today",
    q: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Visitor).options(selectinload(Visitor.household))
    n = now()
    if scope == "today":
        start = datetime.combine(n.date(), datetime.min.time())
        end = start + timedelta(days=1)
        stmt = stmt.where(Visitor.authorized_from < end, Visitor.authorized_until >= start)
    elif scope == "onsite":
        stmt = stmt.where(Visitor.status.in_([VisitorStatus.ENTERED.value, VisitorStatus.OVERSTAY.value]))
    elif scope == "overstay":
        stmt = stmt.where(Visitor.status == VisitorStatus.OVERSTAY.value)
    elif scope == "upcoming":
        stmt = stmt.where(Visitor.status == VisitorStatus.RESERVED.value, Visitor.authorized_until >= n)
    if date_from:
        stmt = stmt.where(Visitor.authorized_until >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Visitor.authorized_from < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    if q:
        like = f"%{q.strip()}%"
        sub = select(Household.id).where(Household.unit_no.like(like))
        stmt = stmt.where(
            or_(Visitor.name.like(like), Visitor.phone.like(like), Visitor.plate.like(f"%{clean(q)}%"), Visitor.household_id.in_(sub))
        )
    stmt = stmt.order_by(Visitor.authorized_from.desc()).limit(1000)
    return [visitor_dict(v) for v in db.scalars(stmt).all()]


@router.get("/{vid}")
def get_visitor(vid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    v = db.get(Visitor, vid)
    if v is None:
        raise HTTPException(404, "訪客不存在")
    return visitor_dict(v)


@router.post("")
def create_visitor(body: VisitorIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.get(Household, body.household_id) is None:
        raise HTTPException(404, "戶別不存在")
    v = Visitor(**body.model_dump(), created_by=user.id, status=VisitorStatus.RESERVED.value)
    db.add(v)
    db.commit()
    db.refresh(v)
    bus.publish("visitors_changed", {"ids": [v.id]})
    return visitor_dict(v)


@router.put("/{vid}")
def update_visitor(vid: int, body: VisitorIn, _: User = Depends(current_user), db: Session = Depends(get_db)):
    v = db.get(Visitor, vid)
    if v is None:
        raise HTTPException(404, "訪客不存在")
    if db.get(Household, body.household_id) is None:
        raise HTTPException(404, "戶別不存在")
    for k, val in body.model_dump().items():
        setattr(v, k, val)
    # 延長授權後，逾時狀態恢復為在場
    if v.status == VisitorStatus.OVERSTAY.value and v.authorized_until > now():
        v.status = VisitorStatus.ENTERED.value
    db.commit()
    db.refresh(v)
    bus.publish("visitors_changed", {"ids": [v.id]})
    return visitor_dict(v)


@router.post("/{vid}/cancel")
def cancel_visitor(vid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    v = db.get(Visitor, vid)
    if v is None:
        raise HTTPException(404, "訪客不存在")
    if v.status in (VisitorStatus.ENTERED.value, VisitorStatus.OVERSTAY.value):
        raise HTTPException(400, "訪客在場中，請先標記離場")
    v.status = VisitorStatus.CANCELLED.value
    db.commit()
    bus.publish("visitors_changed", {"ids": [v.id]})
    return visitor_dict(v)


@router.post("/{vid}/checkout")
def checkout_visitor(vid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """手動標記離場（例如步行訪客或未經辨識離場）。"""
    v = db.get(Visitor, vid)
    if v is None:
        raise HTTPException(404, "訪客不存在")
    at = now()
    v.status = VisitorStatus.EXITED.value
    v.exited_at = at
    if v.plate:
        for s in db.scalars(select(VehicleSession).where(VehicleSession.plate == v.plate, VehicleSession.exited_at.is_(None))):
            s.exited_at = at
    for a in db.scalars(
        select(Alert).where(Alert.visitor_id == v.id, Alert.type == AlertType.OVERSTAY.value, Alert.acknowledged.is_(False))
    ):
        a.acknowledged = True
        a.acknowledged_by = user.id
        a.acknowledged_at = at
    db.commit()
    bus.publish("visitors_changed", {"ids": [v.id]})
    return visitor_dict(v)


@router.post("/{vid}/checkin")
def checkin_visitor(vid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    """手動標記入場（步行訪客）。"""
    v = db.get(Visitor, vid)
    if v is None:
        raise HTTPException(404, "訪客不存在")
    if v.status == VisitorStatus.CANCELLED.value:
        raise HTTPException(400, "訪客已取消")
    v.status = VisitorStatus.ENTERED.value
    v.entered_at = now()
    v.exited_at = None
    db.commit()
    bus.publish("visitors_changed", {"ids": [v.id]})
    return visitor_dict(v)


@router.delete("/{vid}")
def delete_visitor(vid: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    v = db.get(Visitor, vid)
    if v is None:
        raise HTTPException(404, "訪客不存在")
    db.delete(v)
    db.commit()
    bus.publish("visitors_changed", {"ids": [vid]})
    return {"ok": True}

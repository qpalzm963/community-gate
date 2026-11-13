"""進出紀錄、警示、儀表板、在場車輛、截圖。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..access.service import AccessError, alert_dict, event_dict, manual_decision
from ..auth import current_user
from ..db import get_db
from ..models import (
    AccessEvent,
    Alert,
    EventDecision,
    LaneDirection,
    ResidentVehicle,
    User,
    VehicleSession,
    Visitor,
    VisitorStatus,
    now,
)
from ..schemas import DecisionIn
from ..services import export, snapshots
from ..services.events import bus
from ..vision.plate import clean, format_plate

router = APIRouter(prefix="/api", tags=["records"])

MAX_EXPORT = 50000


def _event_query(
    start: date | None,
    end: date | None,
    plate: str,
    category: str,
    decision: str,
    lane_id: int | None,
    vehicle_type: str,
    direction: str,
):
    stmt = select(AccessEvent).options(selectinload(AccessEvent.lane), selectinload(AccessEvent.operator))
    if start:
        stmt = stmt.where(AccessEvent.occurred_at >= datetime.combine(start, datetime.min.time()))
    if end:
        stmt = stmt.where(AccessEvent.occurred_at < datetime.combine(end + timedelta(days=1), datetime.min.time()))
    if plate:
        stmt = stmt.where(AccessEvent.plate.like(f"%{clean(plate)}%"))
    if category:
        stmt = stmt.where(AccessEvent.category.in_(category.split(",")))
    if decision:
        stmt = stmt.where(AccessEvent.decision.in_(decision.split(",")))
    if lane_id:
        stmt = stmt.where(AccessEvent.lane_id == lane_id)
    if vehicle_type:
        stmt = stmt.where(AccessEvent.vehicle_type.in_(vehicle_type.split(",")))
    if direction:
        stmt = stmt.where(AccessEvent.direction == direction)
    return stmt


@router.get("/events")
def list_events(
    start: date | None = None,
    end: date | None = None,
    plate: str = "",
    category: str = "",
    decision: str = "",
    lane_id: int | None = None,
    vehicle_type: str = "",
    direction: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = _event_query(start, end, plate, category, decision, lane_id, vehicle_type, direction)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(
        stmt.order_by(AccessEvent.occurred_at.desc(), AccessEvent.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [event_dict(e) for e in rows]}


@router.get("/events/export")
def export_events(
    format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
    start: date | None = None,
    end: date | None = None,
    plate: str = "",
    category: str = "",
    decision: str = "",
    lane_id: int | None = None,
    vehicle_type: str = "",
    direction: str = "",
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = _event_query(start, end, plate, category, decision, lane_id, vehicle_type, direction)
    rows = db.scalars(stmt.order_by(AccessEvent.occurred_at.desc()).limit(MAX_EXPORT)).all()
    events = [event_dict(e) for e in rows]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if format == "csv":
        return Response(
            export.to_csv(events),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="access_events_{stamp}.csv"'},
        )
    return Response(
        export.to_xlsx(events),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="access_events_{stamp}.xlsx"'},
    )


@router.get("/events/pending")
def pending_events(_: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(AccessEvent)
        .options(selectinload(AccessEvent.lane))
        .where(AccessEvent.decision == EventDecision.PENDING.value)
        .order_by(AccessEvent.occurred_at.desc())
        .limit(50)
    ).all()
    return [event_dict(e) for e in rows]


@router.get("/events/{event_id}")
def get_event(event_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    ev = db.get(AccessEvent, event_id)
    if ev is None:
        raise HTTPException(404, "事件不存在")
    return event_dict(ev)


@router.post("/events/{event_id}/decision")
async def decide_event(event_id: int, body: DecisionIn, user: User = Depends(current_user)):
    try:
        return await run_in_threadpool(manual_decision, event_id, body.action, user.id, body.visitor_id, body.note)
    except AccessError as e:
        raise HTTPException(400, str(e)) from e


# ------------------------------------------------------------------ 警示


@router.get("/alerts")
def list_alerts(
    acknowledged: bool | None = None,
    type: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Alert)
    if acknowledged is not None:
        stmt = stmt.where(Alert.acknowledged.is_(acknowledged))
    if type:
        stmt = stmt.where(Alert.type.in_(type.split(",")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Alert.created_at.desc(), Alert.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "items": [alert_dict(a) for a in rows]}


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "警示不存在")
    if not a.acknowledged:
        a.acknowledged = True
        a.acknowledged_by = user.id
        a.acknowledged_at = now()
        db.commit()
    bus.publish("alerts_changed", {})
    return alert_dict(a)


@router.post("/alerts/ack-all")
def ack_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    at = now()
    n = 0
    for a in db.scalars(select(Alert).where(Alert.acknowledged.is_(False))):
        a.acknowledged = True
        a.acknowledged_by = user.id
        a.acknowledged_at = at
        n += 1
    db.commit()
    bus.publish("alerts_changed", {})
    return {"acknowledged": n}


# ------------------------------------------------------------------ 儀表板 / 在場


@router.get("/dashboard")
def dashboard(_: User = Depends(current_user), db: Session = Depends(get_db)):
    start = datetime.combine(date.today(), datetime.min.time())
    allowed = [EventDecision.AUTO_ALLOW.value, EventDecision.MANUAL_ALLOW.value]

    def count(*conds):
        return db.scalar(select(func.count(AccessEvent.id)).where(AccessEvent.occurred_at >= start, *conds)) or 0

    return {
        "today_in": count(AccessEvent.direction == LaneDirection.IN.value, AccessEvent.decision.in_(allowed)),
        "today_out": count(AccessEvent.direction == LaneDirection.OUT.value, AccessEvent.decision.in_(allowed)),
        "today_denied": count(AccessEvent.decision == EventDecision.DENY.value),
        "pending": db.scalar(select(func.count(AccessEvent.id)).where(AccessEvent.decision == EventDecision.PENDING.value)) or 0,
        "onsite_vehicles": db.scalar(select(func.count(VehicleSession.id)).where(VehicleSession.exited_at.is_(None))) or 0,
        "onsite_visitors": db.scalar(
            select(func.count(Visitor.id)).where(Visitor.status.in_([VisitorStatus.ENTERED.value, VisitorStatus.OVERSTAY.value]))
        )
        or 0,
        "overstay_visitors": db.scalar(select(func.count(Visitor.id)).where(Visitor.status == VisitorStatus.OVERSTAY.value)) or 0,
        "unack_alerts": db.scalar(select(func.count(Alert.id)).where(Alert.acknowledged.is_(False))) or 0,
    }


@router.get("/presence")
def presence(_: User = Depends(current_user), db: Session = Depends(get_db)):
    """目前在場車輛（有進場、尚未離場）。"""
    sessions = db.scalars(
        select(VehicleSession).where(VehicleSession.exited_at.is_(None)).order_by(VehicleSession.entered_at.desc())
    ).all()
    out = []
    for s in sessions:
        ev = db.get(AccessEvent, s.entry_event_id) if s.entry_event_id else None
        out.append(
            {
                "id": s.id,
                "plate": s.plate,
                "plate_display": format_plate(s.plate),
                "entered_at": s.entered_at,
                "category": ev.category if ev else "",
                "household_unit": ev.household_unit if ev else "",
                "vehicle_type": ev.vehicle_type if ev else "",
                "is_resident": bool(
                    db.scalar(select(func.count(ResidentVehicle.id)).where(ResidentVehicle.plate == s.plate))
                ),
            }
        )
    return out


@router.post("/presence/{session_id}/close")
def close_presence(session_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(VehicleSession, session_id)
    if s is None:
        raise HTTPException(404, "紀錄不存在")
    s.exited_at = now()
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ 截圖


@router.get("/snapshots/{rel:path}")
def get_snapshot(rel: str, _: User = Depends(current_user)):
    p = snapshots.resolve(rel)
    if p is None:
        raise HTTPException(404, "截圖不存在或已過保存期限")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

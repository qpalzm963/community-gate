"""出入事件處理：寫入紀錄、存截圖、開閘、更新在場/訪客狀態、產生警示、推播。"""
from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..gate import build_gate
from ..models import (
    AccessEvent,
    Alert,
    AlertType,
    EventCategory,
    EventDecision,
    Lane,
    LaneDirection,
    VehicleSession,
    Visitor,
    VisitorStatus,
    now,
)
from ..services.events import bus
from ..services import snapshots
from ..services.snapshots import save_jpeg
from ..vision.plate import format_plate
from .engine import Decision, decide, lane_vehicle_type

log = logging.getLogger(__name__)


class AccessError(ValueError):
    pass


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def snapshot_url(rel: str) -> str:
    return f"/api/snapshots/{rel}" if rel else ""


def event_dict(ev: AccessEvent) -> dict:
    return {
        "id": ev.id,
        "lane_id": ev.lane_id,
        "lane_name": ev.lane.name if ev.lane else "",
        "direction": ev.direction,
        "plate": ev.plate,
        "plate_display": format_plate(ev.plate),
        "vehicle_type": ev.vehicle_type,
        "confidence": ev.confidence,
        "category": ev.category,
        "decision": ev.decision,
        "household_unit": ev.household_unit,
        "ref_vehicle_id": ev.ref_vehicle_id,
        "ref_visitor_id": ev.ref_visitor_id,
        "operator_name": (ev.operator.display_name or ev.operator.username) if ev.operator else "",
        "note": ev.note,
        "snapshot_url": snapshot_url(ev.snapshot_path),
        "plate_crop_url": snapshot_url(ev.plate_crop_path),
        "occurred_at": ev.occurred_at,
        "decided_at": ev.decided_at,
    }


def alert_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "type": a.type,
        "plate": a.plate,
        "plate_display": format_plate(a.plate),
        "event_id": a.event_id,
        "visitor_id": a.visitor_id,
        "lane_id": a.lane_id,
        "message": a.message,
        "acknowledged": a.acknowledged,
        "acknowledged_by": a.acknowledged_by,
        "acknowledged_at": a.acknowledged_at,
        "created_at": a.created_at,
    }


# ---------------------------------------------------------------------------
# 內部工具
# ---------------------------------------------------------------------------


def create_alert(
    db: Session,
    type_: AlertType,
    message: str,
    plate: str = "",
    event_id: int | None = None,
    visitor_id: int | None = None,
    lane_id: int | None = None,
) -> Alert:
    a = Alert(type=type_.value, message=message, plate=plate, event_id=event_id, visitor_id=visitor_id, lane_id=lane_id)
    db.add(a)
    db.flush()
    return a


def _apply_allow_effects(db: Session, ev: AccessEvent, visitor: Visitor | None) -> None:
    """放行後：更新在場車輛（vehicle_sessions）與訪客狀態。"""
    at = ev.occurred_at
    if ev.plate:
        open_sessions = db.scalars(
            select(VehicleSession)
            .where(VehicleSession.plate == ev.plate, VehicleSession.exited_at.is_(None))
            .order_by(VehicleSession.entered_at.desc())
        ).all()
        if ev.direction == LaneDirection.IN.value:
            # 先前遺漏離場紀錄的 session 視為已離場
            for s in open_sessions:
                s.exited_at = at
            db.add(VehicleSession(plate=ev.plate, entry_event_id=ev.id, entered_at=at))
        else:
            if open_sessions:
                s = open_sessions[0]
                s.exit_event_id = ev.id
                s.exited_at = at
                for older in open_sessions[1:]:
                    older.exited_at = at
    if visitor is not None:
        if ev.direction == LaneDirection.IN.value:
            visitor.status = VisitorStatus.ENTERED.value
            visitor.entered_at = at
            visitor.exited_at = None
        else:
            visitor.status = VisitorStatus.EXITED.value
            visitor.exited_at = at


def _open_gate(lane: Lane | None, reason: str, event_id: int | None) -> tuple[bool, str]:
    if lane is None:
        return False, "找不到車道"
    gate = build_gate(lane.gate_driver, lane.id, lane.gate_config)
    try:
        res = gate.open(reason)
    except Exception as e:  # noqa: BLE001
        log.exception("開閘失敗")
        res_ok, res_msg = False, f"開閘例外：{e}"
    else:
        res_ok, res_msg = res.ok, res.message
    bus.publish("gate", {"lane_id": lane.id, "lane_name": lane.name, "ok": res_ok, "message": res_msg, "event_id": event_id})
    if not res_ok:
        db = SessionLocal()
        try:
            a = create_alert(db, AlertType.GATE_ERROR, f"{lane.name} 開閘失敗：{res_msg}", event_id=event_id, lane_id=lane.id)
            db.commit()
            bus.publish("alert", alert_dict(a))
        finally:
            db.close()
    return res_ok, res_msg


# ---------------------------------------------------------------------------
# 對外 API
# ---------------------------------------------------------------------------


def handle_detection(
    plate: str,
    confidence: float,
    lane_id: int,
    frame: np.ndarray | None = None,
    crop: np.ndarray | None = None,
    at: datetime | None = None,
) -> dict:
    """處理一筆已確認的車牌辨識結果，回傳事件資料。"""
    at = at or now()
    db = SessionLocal()
    saved: tuple[str, ...] = ()
    committed = False
    try:
        lane = db.get(Lane, lane_id)
        if lane is None:
            raise AccessError(f"車道 {lane_id} 不存在")
        d: Decision = decide(db, plate, lane, at)
        saved = (save_jpeg(frame, f"L{lane.id}_full", at), save_jpeg(crop, f"L{lane.id}_plate", at))
        ev = AccessEvent(
            lane_id=lane.id,
            direction=lane.direction,
            plate=plate,
            vehicle_type=d.vehicle_type,
            confidence=round(float(confidence), 4),
            category=d.category.value,
            decision=d.decision.value,
            ref_vehicle_id=d.vehicle.id if d.vehicle else None,
            ref_visitor_id=d.visitor.id if d.visitor else None,
            household_unit=d.household_unit,
            note=d.message,
            occurred_at=at,
            decided_at=at if d.decision != EventDecision.PENDING else None,
            snapshot_path=saved[0],
            plate_crop_path=saved[1],
        )
        db.add(ev)
        db.flush()

        alerts: list[Alert] = []
        if d.category == EventCategory.BLACKLIST:
            alerts.append(
                create_alert(db, AlertType.BLACKLIST, f"{lane.name}：{format_plate(plate)} {d.message}", plate, ev.id, lane_id=lane.id)
            )
        elif d.decision == EventDecision.PENDING:
            alerts.append(
                create_alert(
                    db, AlertType.UNKNOWN_VEHICLE, f"{lane.name}：未登記車輛 {format_plate(plate)}", plate, ev.id, lane_id=lane.id
                )
            )
        if d.allowed:
            _apply_allow_effects(db, ev, d.visitor)
        db.commit()
        committed = True
        db.refresh(ev)
        data = event_dict(ev)
        alert_data = [alert_dict(a) for a in alerts]
    except Exception:
        # 事件沒寫進資料庫就不該留下截圖，否則會變成找不到對應紀錄的孤兒檔；
        # 已 commit 的事件則仍指向這些截圖，不能刪
        if not committed:
            db.rollback()
            snapshots.remove(*saved)
        raise
    finally:
        db.close()

    bus.publish("access_event", data)
    for a in alert_data:
        bus.publish("alert", a)
    if data["decision"] == EventDecision.AUTO_ALLOW.value:
        _open_gate(lane, f"{data['category']} {data['plate_display']}", data["id"])
    return data


def manual_decision(
    event_id: int,
    action: str,
    operator_id: int | None,
    visitor_id: int | None = None,
    note: str = "",
) -> dict:
    """警衛對待處理事件做決定：allow（放行一次 / 已登記訪客）或 deny。"""
    if action not in ("allow", "deny"):
        raise AccessError("action 必須為 allow 或 deny")
    db = SessionLocal()
    try:
        if db.get(AccessEvent, event_id) is None:
            raise AccessError("事件不存在")
        visitor = None
        if action == "allow" and visitor_id is not None:
            visitor = db.get(Visitor, visitor_id)
            if visitor is None:
                raise AccessError("訪客不存在")
        at = now()
        new_decision = EventDecision.DENY if action == "deny" else EventDecision.MANUAL_ALLOW
        # 條件式更新搶單：兩位警衛同時處理時只有一個 UPDATE 會命中，避免重複開閘與重複在場紀錄
        claimed = db.execute(
            update(AccessEvent)
            .where(AccessEvent.id == event_id, AccessEvent.decision == EventDecision.PENDING.value)
            .values(decision=new_decision.value, operator_id=operator_id, decided_at=at)
            .execution_options(synchronize_session=False)
        ).rowcount
        if claimed != 1:
            db.rollback()
            raise AccessError("此事件已處理")
        ev = db.get(AccessEvent, event_id, populate_existing=True)
        if action == "deny":
            ev.note = note or "警衛拒絕"
        else:
            ev.note = note or "警衛放行一次"
            if visitor is not None:
                ev.category = EventCategory.VISITOR.value
                ev.ref_visitor_id = visitor.id
                ev.household_unit = visitor.household.unit_no if visitor.household else ""
                ev.vehicle_type = visitor.vehicle_type
                ev.note = note or f"現場登記訪客 {visitor.name}"
            _apply_allow_effects(db, ev, visitor)
        for a in db.scalars(select(Alert).where(Alert.event_id == ev.id, Alert.acknowledged.is_(False))):
            a.acknowledged = True
            a.acknowledged_by = operator_id
            a.acknowledged_at = at
        db.commit()
        db.refresh(ev)
        lane = ev.lane
        data = event_dict(ev)
    finally:
        db.close()
    bus.publish("access_event_updated", data)
    if action == "allow":
        _open_gate(lane, f"人工放行 {data['plate_display']}", data["id"])
    return data


def manual_open(
    lane_id: int,
    operator_id: int | None,
    note: str = "",
    plate: str = "",
    frame: np.ndarray | None = None,
) -> dict:
    """手動開閘（無辨識事件）。可選填車牌，會一併更新在場紀錄。"""
    at = now()
    db = SessionLocal()
    try:
        lane = db.get(Lane, lane_id)
        if lane is None:
            raise AccessError("車道不存在")
        ev = AccessEvent(
            lane_id=lane.id,
            direction=lane.direction,
            plate=plate,
            vehicle_type=lane_vehicle_type(lane),
            category=EventCategory.MANUAL.value,
            decision=EventDecision.MANUAL_ALLOW.value,
            operator_id=operator_id,
            note=note or "手動開閘",
            occurred_at=at,
            decided_at=at,
            snapshot_path=save_jpeg(frame, f"L{lane.id}_manual", at),
        )
        db.add(ev)
        db.flush()
        _apply_allow_effects(db, ev, None)
        db.commit()
        db.refresh(ev)
        data = event_dict(ev)
    finally:
        db.close()
    bus.publish("access_event", data)
    _open_gate(lane, "手動開閘", data["id"])
    return data

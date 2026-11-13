"""出入判斷引擎：黑名單 → 住戶 → 訪客 → 未登記。純判斷，不寫資料庫。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import (
    BlacklistEntry,
    EventCategory,
    EventDecision,
    Lane,
    LaneDirection,
    LaneVehicleTypes,
    ResidentVehicle,
    VehicleType,
    Visitor,
    VisitorStatus,
)


@dataclass
class Decision:
    category: EventCategory
    decision: EventDecision
    vehicle_type: str = VehicleType.UNKNOWN.value
    vehicle: ResidentVehicle | None = None
    visitor: Visitor | None = None
    blacklist: BlacklistEntry | None = None
    household_unit: str = ""
    message: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision in (EventDecision.AUTO_ALLOW, EventDecision.MANUAL_ALLOW)


def lane_vehicle_type(lane: Lane | None) -> str:
    if lane is not None and lane.vehicle_types in (LaneVehicleTypes.CAR.value, LaneVehicleTypes.MOTO.value):
        return lane.vehicle_types
    return VehicleType.UNKNOWN.value


def find_blacklist(db: Session, plate: str) -> BlacklistEntry | None:
    return db.scalars(
        select(BlacklistEntry).where(BlacklistEntry.plate == plate, BlacklistEntry.is_active.is_(True))
    ).first()


def find_resident_vehicle(db: Session, plate: str, at: datetime) -> ResidentVehicle | None:
    d = at.date()
    return db.scalars(
        select(ResidentVehicle).where(
            ResidentVehicle.plate == plate,
            ResidentVehicle.is_active.is_(True),
            or_(ResidentVehicle.valid_from.is_(None), ResidentVehicle.valid_from <= d),
            or_(ResidentVehicle.valid_until.is_(None), ResidentVehicle.valid_until >= d),
        )
    ).first()


def find_visitor(db: Session, plate: str, at: datetime, direction: str) -> Visitor | None:
    base = select(Visitor).where(Visitor.plate == plate, Visitor.status != VisitorStatus.CANCELLED.value)
    in_window = (Visitor.authorized_from <= at) & (Visitor.authorized_until >= at)
    if direction == LaneDirection.OUT.value:
        # 離場：在場中的訪客即使已逾時也要能出去
        cond = or_(Visitor.status.in_([VisitorStatus.ENTERED.value, VisitorStatus.OVERSTAY.value]), in_window)
        order = (Visitor.entered_at.desc().nulls_last(), Visitor.authorized_from.desc())
    else:
        cond = in_window
        order = (Visitor.authorized_from.desc(),)
    return db.scalars(base.where(cond).order_by(*order)).first()


def decide(db: Session, plate: str, lane: Lane | None, at: datetime | None = None) -> Decision:
    at = at or datetime.now()
    direction = lane.direction if lane else LaneDirection.IN.value

    bl = find_blacklist(db, plate)
    if bl is not None:
        return Decision(
            EventCategory.BLACKLIST,
            EventDecision.DENY,
            vehicle_type=bl.vehicle_type if bl.vehicle_type != VehicleType.UNKNOWN.value else lane_vehicle_type(lane),
            blacklist=bl,
            message=f"黑名單車輛：{bl.reason}" if bl.reason else "黑名單車輛",
        )

    rv = find_resident_vehicle(db, plate, at)
    if rv is not None:
        return Decision(
            EventCategory.RESIDENT,
            EventDecision.AUTO_ALLOW,
            vehicle_type=rv.vehicle_type,
            vehicle=rv,
            household_unit=rv.household.unit_no if rv.household else "",
            message="住戶車輛",
        )

    v = find_visitor(db, plate, at, direction)
    if v is not None:
        return Decision(
            EventCategory.VISITOR,
            EventDecision.AUTO_ALLOW,
            vehicle_type=v.vehicle_type,
            visitor=v,
            household_unit=v.household.unit_no if v.household else "",
            message=f"訪客 {v.name}",
        )

    if lane is not None and lane.auto_allow_unknown:
        return Decision(
            EventCategory.UNKNOWN, EventDecision.AUTO_ALLOW, vehicle_type=lane_vehicle_type(lane), message="未登記車輛（車道設定自動放行）"
        )
    return Decision(
        EventCategory.UNKNOWN, EventDecision.PENDING, vehicle_type=lane_vehicle_type(lane), message="未登記車輛，請警衛確認"
    )

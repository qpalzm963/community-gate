"""出入判斷引擎：黑名單 → 住戶 → 訪客 → 未登記。純判斷，不寫資料庫。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..vision.plate import edit_distance, format_plate
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
    now,
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
    matched_plate: str = ""

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


# OCR 視覺高混淆字元群組（同組內字元在反光、角度斜視或模糊時容易互相誤讀）
_CONFUSABLE_GROUPS: tuple[str, ...] = (
    "BR8",
    "DOQ0",
    "CG6",
    "EF",
    "MN",
    "UV",
    "KX",
    "PR",
    "S5",
    "Z2",
    "ILT17J",
    "A4",
    "38",
)
_CONFUSABLE_MAP: dict[str, set[str]] = {}
for _grp in _CONFUSABLE_GROUPS:
    for _ch in _grp:
        _CONFUSABLE_MAP.setdefault(_ch, set()).update(_grp)


def _is_fuzzy_match(a: str, b: str) -> bool:
    """判斷兩張同長度車牌是否僅差 1 個視覺高混淆字元。"""
    if not a or not b or a == b or len(a) != len(b) or len(a) < 5:
        return False
    diff: tuple[str, str] | None = None
    for ca, cb in zip(a, b):
        if ca != cb:
            if diff is not None:
                return False
            diff = (ca, cb)
    if diff is None:
        return False
    return diff[1] in _CONFUSABLE_MAP.get(diff[0], ())


def _resident_valid_filters(at: datetime):
    d = at.date()
    return (
        ResidentVehicle.is_active.is_(True),
        or_(ResidentVehicle.valid_from.is_(None), ResidentVehicle.valid_from <= d),
        or_(ResidentVehicle.valid_until.is_(None), ResidentVehicle.valid_until >= d),
    )


def _visitor_valid_query(at: datetime, direction: str):
    in_window = (Visitor.authorized_from <= at) & (Visitor.authorized_until >= at)
    if direction == LaneDirection.OUT.value:
        cond = or_(Visitor.status.in_([VisitorStatus.ENTERED.value, VisitorStatus.OVERSTAY.value]), in_window)
        order = (Visitor.entered_at.is_(None), Visitor.entered_at.desc(), Visitor.authorized_from.desc())
    else:
        cond = in_window
        order = (Visitor.authorized_from.desc(),)
    return cond, order


def find_resident_vehicle(db: Session, plate: str, at: datetime) -> ResidentVehicle | None:
    return db.scalars(
        select(ResidentVehicle).where(ResidentVehicle.plate == plate, *_resident_valid_filters(at))
    ).first()


def find_visitor(db: Session, plate: str, at: datetime, direction: str) -> Visitor | None:
    cond, order = _visitor_valid_query(at, direction)
    return db.scalars(
        select(Visitor)
        .where(Visitor.plate == plate, Visitor.status != VisitorStatus.CANCELLED.value, cond)
        .order_by(*order)
    ).first()


def _find_fuzzy_whitelist(
    db: Session, plate: str, at: datetime, direction: str
) -> tuple[ResidentVehicle | None, Visitor | None]:
    """當精確比對皆未命中時，於有效住戶／訪客名單尋找唯一單字元近似車牌；若近似黑名單或多筆歧義則放棄。"""
    active_bl_plates = db.scalars(
        select(BlacklistEntry.plate).where(BlacklistEntry.is_active.is_(True))
    ).all()
    if any(edit_distance(bl_plate, plate) <= 1 for bl_plate in active_bl_plates):
        return None, None

    fuzzy_residents = [
        rv
        for rv in db.scalars(select(ResidentVehicle).where(*_resident_valid_filters(at))).all()
        if _is_fuzzy_match(rv.plate, plate)
    ]
    cond, order = _visitor_valid_query(at, direction)
    fuzzy_visitors = [
        v
        for v in db.scalars(
            select(Visitor).where(Visitor.status != VisitorStatus.CANCELLED.value, cond).order_by(*order)
        ).all()
        if _is_fuzzy_match(v.plate, plate)
    ]

    matched_plates = {rv.plate for rv in fuzzy_residents} | {v.plate for v in fuzzy_visitors}
    if len(matched_plates) != 1:
        return None, None
    if fuzzy_residents:
        return fuzzy_residents[0], None
    return None, fuzzy_visitors[0]


def decide(db: Session, plate: str, lane: Lane | None, at: datetime | None = None) -> Decision:
    at = at or now()
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

    fuzzy_rv, fuzzy_v = _find_fuzzy_whitelist(db, plate, at, direction)
    orig_display = format_plate(plate) or plate
    if fuzzy_rv is not None:
        return Decision(
            EventCategory.RESIDENT,
            EventDecision.AUTO_ALLOW,
            vehicle_type=fuzzy_rv.vehicle_type,
            vehicle=fuzzy_rv,
            household_unit=fuzzy_rv.household.unit_no if fuzzy_rv.household else "",
            message=f"住戶車輛（近似修正自 {orig_display}）",
            matched_plate=fuzzy_rv.plate,
        )
    if fuzzy_v is not None:
        return Decision(
            EventCategory.VISITOR,
            EventDecision.AUTO_ALLOW,
            vehicle_type=fuzzy_v.vehicle_type,
            visitor=fuzzy_v,
            household_unit=fuzzy_v.household.unit_no if fuzzy_v.household else "",
            message=f"訪客 {fuzzy_v.name}（近似修正自 {orig_display}）",
            matched_plate=fuzzy_v.plate,
        )

    if lane is not None and lane.auto_allow_unknown:
        return Decision(
            EventCategory.UNKNOWN, EventDecision.AUTO_ALLOW, vehicle_type=lane_vehicle_type(lane), message="未登記車輛（車道設定自動放行）"
        )
    return Decision(
        EventCategory.UNKNOWN, EventDecision.PENDING, vehicle_type=lane_vehicle_type(lane), message="未登記車輛，請警衛確認"
    )

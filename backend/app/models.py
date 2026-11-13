"""ORM 資料模型。車牌一律存正規化格式（大寫、無 '-' 與空白）。"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    # 單機系統統一使用本地時間（naive datetime）
    return datetime.now().replace(microsecond=0)


class VehicleType(str, enum.Enum):
    CAR = "CAR"
    MOTO = "MOTO"
    UNKNOWN = "UNKNOWN"


class LaneDirection(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class LaneVehicleTypes(str, enum.Enum):
    CAR = "CAR"
    MOTO = "MOTO"
    BOTH = "BOTH"


class VisitorStatus(str, enum.Enum):
    RESERVED = "RESERVED"  # 預約
    ENTERED = "ENTERED"  # 已入場
    EXITED = "EXITED"  # 已離場
    OVERSTAY = "OVERSTAY"  # 逾時（仍在場）
    CANCELLED = "CANCELLED"  # 取消


class VisitorSource(str, enum.Enum):
    RESERVATION = "RESERVATION"  # 預約
    WALK_IN = "WALK_IN"  # 現場


class EventCategory(str, enum.Enum):
    RESIDENT = "RESIDENT"
    VISITOR = "VISITOR"
    BLACKLIST = "BLACKLIST"
    UNKNOWN = "UNKNOWN"
    MANUAL = "MANUAL"  # 手動開閘（無車牌）


class EventDecision(str, enum.Enum):
    AUTO_ALLOW = "AUTO_ALLOW"
    MANUAL_ALLOW = "MANUAL_ALLOW"
    DENY = "DENY"
    PENDING = "PENDING"


class AlertType(str, enum.Enum):
    BLACKLIST = "BLACKLIST"
    UNKNOWN_VEHICLE = "UNKNOWN_VEHICLE"
    OVERSTAY = "OVERSTAY"
    CAMERA_OFFLINE = "CAMERA_OFFLINE"
    GATE_ERROR = "GATE_ERROR"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(64), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Household(Base):
    __tablename__ = "households"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    owner_name: Mapped[str] = mapped_column(String(64), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    vehicles: Mapped[list[ResidentVehicle]] = relationship(
        back_populates="household", cascade="all, delete-orphan"
    )


class ResidentVehicle(Base):
    __tablename__ = "resident_vehicles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    plate: Mapped[str] = mapped_column(String(16), index=True)
    vehicle_type: Mapped[str] = mapped_column(String(8), default=VehicleType.CAR.value)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    household: Mapped[Household] = relationship(back_populates="vehicles")


class Visitor(Base):
    __tablename__ = "visitors"
    __table_args__ = (Index("ix_visitors_plate_window", "plate", "authorized_from", "authorized_until"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(32), default="")
    plate: Mapped[str] = mapped_column(String(16), default="")
    vehicle_type: Mapped[str] = mapped_column(String(8), default=VehicleType.CAR.value)
    purpose: Mapped[str] = mapped_column(String(128), default="")
    authorized_from: Mapped[datetime] = mapped_column(DateTime)
    authorized_until: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default=VisitorStatus.RESERVED.value, index=True)
    source: Mapped[str] = mapped_column(String(16), default=VisitorSource.RESERVATION.value)
    entered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    household: Mapped[Household] = relationship()


class BlacklistEntry(Base):
    __tablename__ = "blacklist"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate: Mapped[str] = mapped_column(String(16), index=True)
    vehicle_type: Mapped[str] = mapped_column(String(8), default=VehicleType.UNKNOWN.value)
    reason: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Lane(Base):
    __tablename__ = "lanes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(4), default=LaneDirection.IN.value)
    source_url: Mapped[str] = mapped_column(String(512), default="")
    vehicle_types: Mapped[str] = mapped_column(String(8), default=LaneVehicleTypes.BOTH.value)
    gate_driver: Mapped[str] = mapped_column(String(32), default="simulated")
    gate_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # 出口車道遇到未登記車輛是否直接放行
    auto_allow_unknown: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AccessEvent(Base):
    __tablename__ = "access_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lane_id: Mapped[int | None] = mapped_column(ForeignKey("lanes.id", ondelete="SET NULL"), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(4), default=LaneDirection.IN.value)
    plate: Mapped[str] = mapped_column(String(16), default="", index=True)
    vehicle_type: Mapped[str] = mapped_column(String(8), default=VehicleType.UNKNOWN.value)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    category: Mapped[str] = mapped_column(String(16), index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    ref_vehicle_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_visitor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    household_unit: Mapped[str] = mapped_column(String(64), default="")
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    snapshot_path: Mapped[str] = mapped_column(String(512), default="")
    plate_crop_path: Mapped[str] = mapped_column(String(512), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    lane: Mapped[Lane | None] = relationship()
    operator: Mapped[User | None] = relationship()


class VehicleSession(Base):
    __tablename__ = "vehicle_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate: Mapped[str] = mapped_column(String(16), index=True)
    entry_event_id: Mapped[int | None] = mapped_column(ForeignKey("access_events.id", ondelete="SET NULL"), nullable=True)
    exit_event_id: Mapped[int | None] = mapped_column(ForeignKey("access_events.id", ondelete="SET NULL"), nullable=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    plate: Mapped[str] = mapped_column(String(16), default="")
    event_id: Mapped[int | None] = mapped_column(ForeignKey("access_events.id", ondelete="SET NULL"), nullable=True)
    visitor_id: Mapped[int | None] = mapped_column(ForeignKey("visitors.id", ondelete="SET NULL"), nullable=True)
    lane_id: Mapped[int | None] = mapped_column(ForeignKey("lanes.id", ondelete="SET NULL"), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)

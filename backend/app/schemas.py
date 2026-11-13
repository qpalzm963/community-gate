"""API 輸入 schema。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .vision.plate import clean

VehicleTypeStr = Literal["CAR", "MOTO"]
VehicleTypeAny = Literal["CAR", "MOTO", "UNKNOWN"]


def _plate(v: str, required: bool) -> str:
    p = clean(v or "")
    if not p:
        if required:
            raise ValueError("請輸入車牌")
        return ""
    if not 2 <= len(p) <= 10:
        raise ValueError("車牌長度不正確")
    return p


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=64)


class UserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)


class HouseholdIn(BaseModel):
    unit_no: str = Field(min_length=1, max_length=64)
    owner_name: str = Field(default="", max_length=64)
    phone: str = Field(default="", max_length=32)
    note: str = ""

    @field_validator("unit_no")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("請輸入戶別")
        return v


class VehicleIn(BaseModel):
    household_id: int
    plate: str
    vehicle_type: VehicleTypeStr = "CAR"
    valid_from: date | None = None
    valid_until: date | None = None
    is_active: bool = True
    note: str = ""

    @field_validator("plate")
    @classmethod
    def _p(cls, v: str) -> str:
        return _plate(v, True)

    @model_validator(mode="after")
    def _range(self):
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("有效期結束日不可早於開始日")
        return self


class VisitorIn(BaseModel):
    household_id: int
    name: str = Field(min_length=1, max_length=64)
    phone: str = Field(default="", max_length=32)
    plate: str = ""
    vehicle_type: VehicleTypeStr = "CAR"
    purpose: str = Field(default="", max_length=128)
    authorized_from: datetime
    authorized_until: datetime
    source: Literal["RESERVATION", "WALK_IN"] = "RESERVATION"

    @field_validator("plate")
    @classmethod
    def _p(cls, v: str) -> str:
        return _plate(v, False)

    @field_validator("authorized_from", "authorized_until")
    @classmethod
    def _naive(cls, v: datetime) -> datetime:
        # 前端送本地時間；若帶時區則轉為本地 naive 時間
        if v.tzinfo is not None:
            v = v.astimezone().replace(tzinfo=None)
        return v.replace(microsecond=0)

    @model_validator(mode="after")
    def _range(self):
        if self.authorized_until <= self.authorized_from:
            raise ValueError("授權結束時間必須晚於開始時間")
        return self


class BlacklistIn(BaseModel):
    plate: str
    vehicle_type: VehicleTypeAny = "UNKNOWN"
    reason: str = ""
    is_active: bool = True

    @field_validator("plate")
    @classmethod
    def _p(cls, v: str) -> str:
        return _plate(v, True)


class LaneIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    direction: Literal["IN", "OUT"] = "IN"
    source_url: str = Field(default="", max_length=512)
    vehicle_types: Literal["CAR", "MOTO", "BOTH"] = "BOTH"
    gate_driver: Literal["simulated", "http_relay", "modbus"] = "simulated"
    gate_config: dict = Field(default_factory=dict)
    auto_allow_unknown: bool = False
    enabled: bool = True


class DecisionIn(BaseModel):
    action: Literal["allow", "deny"]
    visitor_id: int | None = None
    note: str = ""


class ManualOpenIn(BaseModel):
    note: str = ""
    plate: str = ""

    @field_validator("plate")
    @classmethod
    def _p(cls, v: str) -> str:
        return _plate(v, False)


class SimulateIn(BaseModel):
    plate: str
    confidence: float = Field(default=0.99, ge=0, le=1)

    @field_validator("plate")
    @classmethod
    def _p(cls, v: str) -> str:
        return _plate(v, True)

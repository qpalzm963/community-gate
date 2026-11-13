"""住戶、住戶車輛、黑名單。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..db import get_db
from ..models import BlacklistEntry, Household, ResidentVehicle, User, Visitor
from ..schemas import BlacklistIn, HouseholdIn, VehicleIn
from ..vision.plate import clean, format_plate

router = APIRouter(prefix="/api", tags=["residents"], dependencies=[Depends(current_user)])


def vehicle_dict(v: ResidentVehicle) -> dict:
    return {
        "id": v.id,
        "household_id": v.household_id,
        "household_unit": v.household.unit_no if v.household else "",
        "plate": v.plate,
        "plate_display": format_plate(v.plate),
        "vehicle_type": v.vehicle_type,
        "valid_from": v.valid_from,
        "valid_until": v.valid_until,
        "is_active": v.is_active,
        "note": v.note,
        "created_at": v.created_at,
    }


def household_dict(h: Household, with_vehicles: bool = True) -> dict:
    d = {
        "id": h.id,
        "unit_no": h.unit_no,
        "owner_name": h.owner_name,
        "phone": h.phone,
        "note": h.note,
        "created_at": h.created_at,
        "vehicle_count": len(h.vehicles),
    }
    if with_vehicles:
        d["vehicles"] = [vehicle_dict(v) for v in sorted(h.vehicles, key=lambda x: x.id)]
    return d


def blacklist_dict(b: BlacklistEntry) -> dict:
    return {
        "id": b.id,
        "plate": b.plate,
        "plate_display": format_plate(b.plate),
        "vehicle_type": b.vehicle_type,
        "reason": b.reason,
        "is_active": b.is_active,
        "created_at": b.created_at,
    }


# ------------------------------------------------------------------ 住戶


@router.get("/households")
def list_households(q: str = "", db: Session = Depends(get_db)):
    stmt = select(Household).options(selectinload(Household.vehicles)).order_by(Household.unit_no)
    if q:
        like = f"%{q.strip()}%"
        plate_like = f"%{clean(q)}%"
        sub = select(ResidentVehicle.household_id).where(ResidentVehicle.plate.like(plate_like))
        stmt = stmt.where(
            or_(Household.unit_no.like(like), Household.owner_name.like(like), Household.phone.like(like), Household.id.in_(sub))
        )
    return [household_dict(h) for h in db.scalars(stmt).all()]


@router.post("/households")
def create_household(body: HouseholdIn, db: Session = Depends(get_db)):
    if db.scalars(select(Household).where(Household.unit_no == body.unit_no)).first():
        raise HTTPException(409, f"戶別 {body.unit_no} 已存在")
    h = Household(**body.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    return household_dict(h)


@router.put("/households/{hid}")
def update_household(hid: int, body: HouseholdIn, db: Session = Depends(get_db)):
    h = db.get(Household, hid)
    if h is None:
        raise HTTPException(404, "戶別不存在")
    dup = db.scalars(select(Household).where(Household.unit_no == body.unit_no, Household.id != hid)).first()
    if dup:
        raise HTTPException(409, f"戶別 {body.unit_no} 已存在")
    for k, v in body.model_dump().items():
        setattr(h, k, v)
    db.commit()
    db.refresh(h)
    return household_dict(h)


@router.delete("/households/{hid}")
def delete_household(hid: int, db: Session = Depends(get_db)):
    h = db.get(Household, hid)
    if h is None:
        raise HTTPException(404, "戶別不存在")
    if db.scalars(select(Visitor.id).where(Visitor.household_id == hid)).first():
        raise HTTPException(409, "此戶別仍有訪客紀錄，無法刪除（可改為移除車輛）")
    db.delete(h)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ 住戶車輛


def _check_vehicle_dup(db: Session, plate: str, exclude_id: int | None = None) -> None:
    stmt = select(ResidentVehicle).where(ResidentVehicle.plate == plate, ResidentVehicle.is_active.is_(True))
    if exclude_id:
        stmt = stmt.where(ResidentVehicle.id != exclude_id)
    other = db.scalars(stmt).first()
    if other:
        unit = other.household.unit_no if other.household else ""
        raise HTTPException(409, f"車牌 {format_plate(plate)} 已登記於 {unit}")


@router.get("/vehicles")
def list_vehicles(q: str = "", household_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(ResidentVehicle).options(selectinload(ResidentVehicle.household)).order_by(ResidentVehicle.plate)
    if household_id:
        stmt = stmt.where(ResidentVehicle.household_id == household_id)
    if q:
        stmt = stmt.where(ResidentVehicle.plate.like(f"%{clean(q)}%"))
    return [vehicle_dict(v) for v in db.scalars(stmt).all()]


@router.post("/vehicles")
def create_vehicle(body: VehicleIn, db: Session = Depends(get_db)):
    if db.get(Household, body.household_id) is None:
        raise HTTPException(404, "戶別不存在")
    if body.is_active:
        _check_vehicle_dup(db, body.plate)
    v = ResidentVehicle(**body.model_dump())
    db.add(v)
    db.commit()
    db.refresh(v)
    return vehicle_dict(v)


@router.put("/vehicles/{vid}")
def update_vehicle(vid: int, body: VehicleIn, db: Session = Depends(get_db)):
    v = db.get(ResidentVehicle, vid)
    if v is None:
        raise HTTPException(404, "車輛不存在")
    if db.get(Household, body.household_id) is None:
        raise HTTPException(404, "戶別不存在")
    if body.is_active:
        _check_vehicle_dup(db, body.plate, vid)
    for k, val in body.model_dump().items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    return vehicle_dict(v)


@router.delete("/vehicles/{vid}")
def delete_vehicle(vid: int, db: Session = Depends(get_db)):
    v = db.get(ResidentVehicle, vid)
    if v is None:
        raise HTTPException(404, "車輛不存在")
    db.delete(v)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ 黑名單


@router.get("/blacklist")
def list_blacklist(q: str = "", db: Session = Depends(get_db)):
    stmt = select(BlacklistEntry).order_by(BlacklistEntry.created_at.desc())
    if q:
        stmt = stmt.where(or_(BlacklistEntry.plate.like(f"%{clean(q)}%"), BlacklistEntry.reason.like(f"%{q}%")))
    return [blacklist_dict(b) for b in db.scalars(stmt).all()]


@router.post("/blacklist")
def create_blacklist(body: BlacklistIn, db: Session = Depends(get_db)):
    if db.scalars(select(BlacklistEntry).where(BlacklistEntry.plate == body.plate, BlacklistEntry.is_active.is_(True))).first():
        raise HTTPException(409, f"車牌 {format_plate(body.plate)} 已在黑名單")
    b = BlacklistEntry(**body.model_dump())
    db.add(b)
    db.commit()
    db.refresh(b)
    return blacklist_dict(b)


@router.put("/blacklist/{bid}")
def update_blacklist(bid: int, body: BlacklistIn, db: Session = Depends(get_db)):
    b = db.get(BlacklistEntry, bid)
    if b is None:
        raise HTTPException(404, "資料不存在")
    for k, v in body.model_dump().items():
        setattr(b, k, v)
    db.commit()
    return blacklist_dict(b)


@router.delete("/blacklist/{bid}")
def delete_blacklist(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = db.get(BlacklistEntry, bid)
    if b is None:
        raise HTTPException(404, "資料不存在")
    db.delete(b)
    db.commit()
    return {"ok": True}

"""資料庫初始化與預設資料建立。"""
from __future__ import annotations

from sqlalchemy import func, select

from .auth import create_user
from .config import get_config
from .db import Base, SessionLocal, get_engine
from .models import Lane, LaneDirection, LaneVehicleTypes, User


def upgrade_db(seed_defaults: bool = True) -> None:
    """建立資料表，並在首次啟動時建立預設入口／出口車道與選用管理員帳號。"""
    # 確保所有 ORM 模型皆已匯入註冊至 Base.metadata
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
    if not seed_defaults:
        return
    cfg = get_config()
    db = SessionLocal()
    try:
        count = db.scalar(select(func.count(Lane.id))) or 0
        if count == 0:
            db.add_all(
                [
                    Lane(
                        name="入口車道",
                        direction=LaneDirection.IN.value,
                        vehicle_types=LaneVehicleTypes.BOTH.value,
                        gate_driver="simulated",
                        enabled=True,
                    ),
                    Lane(
                        name="出口車道",
                        direction=LaneDirection.OUT.value,
                        vehicle_types=LaneVehicleTypes.BOTH.value,
                        gate_driver="simulated",
                        enabled=True,
                    ),
                ]
            )
            db.commit()
        if cfg.admin_username and cfg.admin_password:
            exists = db.scalars(select(User).where(User.username == cfg.admin_username)).first()
            if exists is None:
                create_user(db, cfg.admin_username, cfg.admin_password, cfg.admin_display_name)
    finally:
        db.close()

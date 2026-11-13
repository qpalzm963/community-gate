"""排程任務：訪客逾時未離場檢查（每分鐘）、截圖清理（每日一次）。"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select, update

from ..access.service import alert_dict, create_alert
from ..db import SessionLocal
from ..models import AccessEvent, AlertType, Visitor, VisitorStatus
from ..vision.plate import format_plate
from . import snapshots
from .events import bus
from .settings import settings_store

log = logging.getLogger(__name__)


def check_overstay(at: datetime | None = None) -> list[int]:
    """將授權時段 + 寬限已過、仍在場的訪客標記為逾時並產生警示，回傳訪客 id。"""
    at = at or datetime.now()
    grace = timedelta(minutes=int(settings_store.get("overstay_grace_min")))
    db = SessionLocal()
    flagged: list[int] = []
    alerts = []
    try:
        rows = db.scalars(
            select(Visitor).where(Visitor.status == VisitorStatus.ENTERED.value, Visitor.authorized_until < at - grace)
        ).all()
        for v in rows:
            v.status = VisitorStatus.OVERSTAY.value
            unit = v.household.unit_no if v.household else ""
            msg = f"訪客 {v.name}（{format_plate(v.plate) or '無車牌'}，拜訪 {unit}）已逾授權時間 {v.authorized_until:%m/%d %H:%M} 未離場"
            alerts.append(create_alert(db, AlertType.OVERSTAY, msg, plate=v.plate, visitor_id=v.id))
            flagged.append(v.id)
        db.commit()
        payload = [alert_dict(a) for a in alerts]
    finally:
        db.close()
    for a in payload:
        bus.publish("alert", a)
    if flagged:
        bus.publish("visitors_changed", {"ids": flagged})
    return flagged


def cleanup_snapshots(today: date | None = None) -> int:
    days = int(settings_store.get("snapshot_retention_days"))
    today = today or date.today()
    removed = snapshots.cleanup(days, today)
    # 同步清空過期事件的截圖路徑，避免前端出現破圖
    cutoff = datetime.combine(today - timedelta(days=days), datetime.min.time())
    db = SessionLocal()
    try:
        db.execute(
            update(AccessEvent)
            .where(AccessEvent.occurred_at < cutoff, (AccessEvent.snapshot_path != "") | (AccessEvent.plate_crop_path != ""))
            .values(snapshot_path="", plate_crop_path="")
        )
        db.commit()
    finally:
        db.close()
    return removed


async def run_scheduler(stop: asyncio.Event) -> None:
    last_cleanup: date | None = None
    while not stop.is_set():
        try:
            await asyncio.to_thread(check_overstay)
            today = date.today()
            if last_cleanup != today:
                await asyncio.to_thread(cleanup_snapshots, today)
                last_cleanup = today
        except Exception:  # noqa: BLE001
            log.exception("排程任務失敗")
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            pass

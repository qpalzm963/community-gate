"""排程任務：訪客逾時未離場檢查、待處理事件逾時結案（每分鐘）、截圖清理（每日一次）。"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select, update

from ..access.service import alert_dict, create_alert, event_dict
from ..db import SessionLocal
from ..models import AccessEvent, Alert, AlertType, EventDecision, Visitor, VisitorStatus, now
from ..vision.plate import format_plate
from . import snapshots
from .events import bus
from .settings import settings_store

log = logging.getLogger(__name__)


def check_overstay(at: datetime | None = None) -> list[int]:
    """將授權時段 + 寬限已過、仍在場的訪客標記為逾時並產生警示，回傳訪客 id。"""
    at = at or now()
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


def close_stale_pending(at: datetime | None = None) -> list[int]:
    """把超過 ``pending_timeout_min`` 仍未處理的待處理事件結案為拒絕（例如車子已倒車離開），回傳事件 id。

    與警衛手動處理同樣以 ``decision='PENDING'`` 做條件式更新，避免覆蓋剛被人工處理的事件。
    """
    minutes = int(settings_store.get("pending_timeout_min"))
    if minutes <= 0:
        return []
    at = at or now()
    cutoff = at - timedelta(minutes=minutes)
    note = f"逾時 {minutes} 分鐘未處理，自動結案"
    db = SessionLocal()
    closed: list[int] = []
    payload: list[dict] = []
    try:
        ids = db.scalars(
            select(AccessEvent.id).where(
                AccessEvent.decision == EventDecision.PENDING.value, AccessEvent.occurred_at < cutoff
            )
        ).all()
        for eid in ids:
            res = db.execute(
                update(AccessEvent)
                .where(AccessEvent.id == eid, AccessEvent.decision == EventDecision.PENDING.value)
                .values(decision=EventDecision.DENY.value, decided_at=at, note=note)
            )
            if res.rowcount == 1:
                closed.append(eid)
        if closed:
            db.execute(
                update(Alert)
                .where(Alert.event_id.in_(closed), Alert.acknowledged.is_(False))
                .values(acknowledged=True, acknowledged_at=at)
            )
        db.commit()
        payload = [event_dict(db.get(AccessEvent, eid)) for eid in closed]
    finally:
        db.close()
    for data in payload:
        bus.publish("access_event_updated", data)
    if closed:
        bus.publish("alerts_changed", {})
        log.info("待處理事件逾時自動結案：%s", closed)
    return closed


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
            await asyncio.to_thread(close_stale_pending)
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

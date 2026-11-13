"""車道 worker 管理：依資料庫設定啟動／重啟每個車道的攝影機辨識工作。"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..access.service import alert_dict, create_alert, handle_detection
from ..db import SessionLocal
from ..models import AlertType, Lane
from ..vision.camera import LaneWorker, WorkerOptions
from ..vision.plate import ConfirmedPlate, VoteParams
from ..vision.recognizer import get_recognizer
from .events import bus
from .settings import settings_store

log = logging.getLogger(__name__)


def options_from_settings(values: dict | None = None) -> WorkerOptions:
    s = values or settings_store.all()
    return WorkerOptions(
        recognition_fps=float(s["recognition_fps"]),
        vote=VoteParams(
            min_hits=int(s["vote_min_hits"]),
            window_sec=float(s["vote_window_sec"]),
            min_confidence=float(s["vote_min_confidence"]),
            dedup_sec=float(s["dedup_sec"]),
        ),
        strict_format=bool(s["plate_strict_format"]),
    )


class LaneManager:
    def __init__(self):
        self._workers: dict[int, LaneWorker] = {}
        self._lock = threading.Lock()
        # 事件處理（寫 DB、開閘）交給獨立執行緒，避免卡住辨識
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="access")
        settings_store.on_change(self._on_settings_change)

    # ------------------------------------------------------------ callbacks
    def _on_confirm(self, lane_id: int, c: ConfirmedPlate, frame: np.ndarray, crop: np.ndarray | None) -> None:
        log.info("車道 %s 確認車牌 %s (%.2f, %d hits)", lane_id, c.plate, c.confidence, c.hits)
        self._executor.submit(self._safe_handle, c.plate, c.confidence, lane_id, frame, crop)

    @staticmethod
    def _safe_handle(plate, conf, lane_id, frame, crop):
        try:
            handle_detection(plate, conf, lane_id, frame, crop)
        except Exception:  # noqa: BLE001
            log.exception("處理辨識事件失敗")

    def _on_status(self, lane_id: int, online: bool, error: str) -> None:
        w = self._workers.get(lane_id)
        bus.publish("lane_status", w.status() if w else {"lane_id": lane_id, "online": online, "last_error": error})
        if not online:
            db = SessionLocal()
            try:
                lane = db.get(Lane, lane_id)
                name = lane.name if lane else f"車道 {lane_id}"
                a = create_alert(db, AlertType.CAMERA_OFFLINE, f"{name} 攝影機離線：{error}", lane_id=lane_id)
                db.commit()
                bus.publish("alert", alert_dict(a))
            finally:
                db.close()

    def _on_settings_change(self, values: dict) -> None:
        opts = options_from_settings(values)
        with self._lock:
            for w in self._workers.values():
                w.update_options(opts)

    # ------------------------------------------------------------ 管理
    def _build(self, lane: Lane) -> LaneWorker:
        return LaneWorker(
            lane.id,
            lane.name,
            lane.source_url,
            get_recognizer,
            self._on_confirm,
            self._on_status,
            options_from_settings(),
        )

    def start_all(self) -> None:
        db = SessionLocal()
        try:
            lanes = db.query(Lane).filter(Lane.enabled.is_(True)).all()
        finally:
            db.close()
        for lane in lanes:
            self.restart(lane.id)

    def restart(self, lane_id: int) -> None:
        db = SessionLocal()
        try:
            lane = db.get(Lane, lane_id)
        finally:
            db.close()
        with self._lock:
            old = self._workers.pop(lane_id, None)
        if old:
            old.stop()
        if lane is None or not lane.enabled:
            return
        w = self._build(lane)
        with self._lock:
            self._workers[lane_id] = w
        w.start()
        log.info("車道 %s (%s) 啟動，來源 %s", lane.id, lane.name, lane.source_url or "(未設定)")

    def remove(self, lane_id: int) -> None:
        with self._lock:
            w = self._workers.pop(lane_id, None)
        if w:
            w.stop()

    def stop_all(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for w in workers:
            w.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def get(self, lane_id: int) -> LaneWorker | None:
        return self._workers.get(lane_id)

    def statuses(self) -> dict[int, dict]:
        return {lid: w.status() for lid, w in list(self._workers.items())}


lane_manager: LaneManager | None = None


def get_lane_manager() -> LaneManager:
    global lane_manager
    if lane_manager is None:
        lane_manager = LaneManager()
    return lane_manager

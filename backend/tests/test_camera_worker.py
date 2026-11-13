from __future__ import annotations

import numpy as np

from app.access.service import handle_detection
from app.db import SessionLocal
from app.models import AccessEvent, Household, Lane, LaneDirection, ResidentVehicle
from app.vision.camera import LaneWorker, WorkerOptions
from app.vision.plate import VoteParams
from app.vision.recognizer import PlateDetection


class FakeRecognizer:
    def __init__(self, text: str = "ABC-I234"):
        self.text = text

    def predict(self, frame: np.ndarray) -> list[PlateDetection]:
        return [PlateDetection(text=self.text, confidence=0.92, bbox=(10, 10, 150, 60), det_confidence=0.95)]


def test_lane_worker_pipeline_end_to_end(app_env):
    _client, _tmp = app_env

    db = SessionLocal()
    try:
        lane = db.query(Lane).filter(Lane.direction == LaneDirection.IN.value).first()
        hh = Household(unit_no="D棟2F")
        db.add(hh)
        db.flush()
        db.add(ResidentVehicle(household_id=hh.id, plate="ABC1234", vehicle_type="CAR", is_active=True))
        db.commit()
        lane_id = lane.id
    finally:
        db.close()

    events = []

    def on_confirm(lid, confirmed, frame, crop):
        events.append(handle_detection(confirmed.plate, confirmed.confidence, lid, frame, crop))

    rec = FakeRecognizer("ABC-I234")  # 應校正成 ABC1234
    worker = LaneWorker(
        lane_id,
        "入口車道",
        "",
        lambda: rec,
        on_confirm,
        options=WorkerOptions(vote=VoteParams(min_hits=3, window_sec=2.0, min_confidence=0.8, dedup_sec=30.0)),
    )

    frame = np.full((120, 200, 3), 180, dtype=np.uint8)
    for i in range(4):
        worker.process_frame(frame, ts=100.0 + i * 0.2)

    assert len(events) == 1
    ev = events[0]
    assert ev["plate"] == "ABC1234"
    assert ev["category"] == "RESIDENT"
    assert ev["decision"] == "AUTO_ALLOW"
    assert ev["snapshot_url"].startswith("/api/snapshots/")
    assert ev["plate_crop_url"].startswith("/api/snapshots/")

    db = SessionLocal()
    try:
        assert db.query(AccessEvent).filter(AccessEvent.plate == "ABC1234").count() == 1
    finally:
        db.close()


def test_annotated_jpeg_encodes_each_frame_once():
    """多個監控視窗與串流重送同一張影格時不可重複編碼（否則 CPU 被吃掉、串流 fps 下降），
    但推入新影格後必須產生新畫面，不能卡在舊快取。"""
    worker = LaneWorker(1, "t", "", lambda: FakeRecognizer(), on_confirm=lambda *a: None)
    worker.push_frame(np.zeros((480, 640, 3), np.uint8))
    first = worker.annotated_jpeg()
    assert first is not None
    assert worker.annotated_jpeg() is first  # 同一影格 → 直接回快取

    worker.push_frame(np.full((480, 640, 3), 255, np.uint8))
    second = worker.annotated_jpeg()
    assert second is not None and second != first

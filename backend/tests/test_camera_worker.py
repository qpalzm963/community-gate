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


def test_min_plate_width_ratio_filters_distant_plates():
    confirmed = []

    class SmallPlateRec:
        def predict(self, frame):
            # 寬度僅 40px（在 1000px 畫面佔 4%，小於預設 6%）
            return [PlateDetection(text="FAR-1234", confidence=0.95, bbox=(100, 100, 140, 120), det_confidence=0.95)]

    worker = LaneWorker(
        1,
        "入口",
        "",
        lambda: SmallPlateRec(),
        on_confirm=lambda lid, c, f, crop: confirmed.append(c.plate),
        options=WorkerOptions(
            vote=VoteParams(min_hits=2, window_sec=2.0, min_confidence=0.8, dedup_sec=30.0),
            min_plate_width_ratio=0.06,
        ),
    )
    frame = np.zeros((600, 1000, 3), dtype=np.uint8)
    for i in range(4):
        res = worker.process_frame(frame, ts=10.0 + i * 0.2)
        assert res[0][1] == "FAR1234"
    assert confirmed == []


def test_primary_plate_only_and_roi_filter():
    confirmed = []

    class MultiPlateRec:
        def predict(self, frame):
            # 後車（較小）與前車（較大）同時出現在畫面內
            return [
                PlateDetection(text="BCK-1111", confidence=0.99, bbox=(100, 100, 200, 140), det_confidence=0.98),
                PlateDetection(text="FRT-2222", confidence=0.90, bbox=(300, 300, 520, 390), det_confidence=0.95),
            ]

    worker = LaneWorker(
        1,
        "入口",
        "",
        lambda: MultiPlateRec(),
        on_confirm=lambda lid, c, f, crop: confirmed.append(c.plate),
        options=WorkerOptions(
            vote=VoteParams(min_hits=3, window_sec=2.0, min_confidence=0.8, dedup_sec=30.0),
            min_plate_width_ratio=0.05,
            primary_plate_only=True,
        ),
    )
    frame = np.zeros((600, 1000, 3), dtype=np.uint8)
    for i in range(4):
        worker.process_frame(frame, ts=20.0 + i * 0.2)
    assert confirmed == ["FRT2222"]

    # 測試 ROI 過濾：把主車排除在 ROI 之外時，只剩位於 ROI 內的 BCK-1111 會被計票
    confirmed.clear()
    worker.voter.reset()
    worker.update_options(
        WorkerOptions(
            vote=VoteParams(min_hits=2, window_sec=2.0, min_confidence=0.8, dedup_sec=30.0),
            min_plate_width_ratio=0.05,
            primary_plate_only=True,
            roi=(0.0, 0.0, 0.3, 0.4),
        )
    )
    for i in range(3):
        worker.process_frame(frame, ts=30.0 + i * 0.2)
    assert confirmed == ["BCK1111"]

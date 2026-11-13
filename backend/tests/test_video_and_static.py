from __future__ import annotations

import time
from pathlib import Path

import cv2
import httpx
import numpy as np

from app.access.service import handle_detection
from app.db import SessionLocal
from app.gate.http_relay import HttpRelayGate
from app.gate.simulated import SimulatedGate
from app.models import AccessEvent, Household, Lane, LaneDirection, ResidentVehicle
from app.vision.camera import LaneWorker, WorkerOptions
from app.vision.plate import VoteParams
from app.vision.recognizer import PlateDetection


class _StubRecognizer:
    def predict(self, frame: np.ndarray) -> list[PlateDetection]:
        return [PlateDetection(text="KLM-5678", confidence=0.94, bbox=(20, 20, 140, 60), det_confidence=0.98)]


def test_built_frontend_served(app_env):
    client, _ = app_env
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_gate_drivers(monkeypatch):
    sim = SimulatedGate(1, {})
    assert sim.open("test").ok is True

    missing = HttpRelayGate(1, {})
    assert missing.open("test").ok is False

    def fake_request(method, url, timeout=3, headers=None):
        req = httpx.Request(method, url)
        return httpx.Response(200, request=req, text="OK")

    monkeypatch.setattr(httpx, "request", fake_request)
    http_gate = HttpRelayGate(1, {"url": "http://192.168.1.50/relay/0?turn=on"})
    assert http_gate.open("test").ok is True


def test_video_file_lane_worker_e2e(app_env):
    _client, tmp_path = app_env
    video_path = Path(tmp_path) / "sample.avi"

    # 產生一段真實影片檔（MJPG AVI），確認 OpenCV VideoCapture 迴圈與辨識執行緒能完整運作
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (200, 120))
    assert writer.isOpened()
    frame = np.full((120, 200, 3), 200, dtype=np.uint8)
    for _ in range(15):
        writer.write(frame)
    writer.release()

    db = SessionLocal()
    try:
        lane = db.query(Lane).filter(Lane.direction == LaneDirection.IN.value).first()
        hh = Household(unit_no="E棟1F")
        db.add(hh)
        db.flush()
        db.add(ResidentVehicle(household_id=hh.id, plate="KLM5678", vehicle_type="CAR", is_active=True))
        db.commit()
        lane_id = lane.id
    finally:
        db.close()

    captured = []

    def on_confirm(lid, confirmed, f, crop):
        captured.append(handle_detection(confirmed.plate, confirmed.confidence, lid, f, crop))

    worker = LaneWorker(
        lane_id,
        "入口車道",
        str(video_path),
        lambda: _StubRecognizer(),
        on_confirm,
        options=WorkerOptions(
            recognition_fps=15.0,
            vote=VoteParams(min_hits=2, window_sec=3.0, min_confidence=0.8, dedup_sec=30.0),
        ),
    )
    worker.start()
    try:
        deadline = time.monotonic() + 5.0
        while not captured and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        worker.stop()

    assert len(captured) == 1
    assert captured[0]["plate"] == "KLM5678"
    assert captured[0]["decision"] == "AUTO_ALLOW"

    db = SessionLocal()
    try:
        assert db.query(AccessEvent).filter(AccessEvent.plate == "KLM5678").count() == 1
    finally:
        db.close()

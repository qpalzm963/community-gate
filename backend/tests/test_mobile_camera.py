from __future__ import annotations

import cv2
import numpy as np

from app.api.system import get_lan_ip
from app.auth import create_camera_token, verify_camera_token
from app.ssl_cert import ensure_self_signed_cert
from app.vision.camera import LaneWorker


def test_get_lan_ip():
    # 傳入合法的外部 IP 應優先採用
    assert get_lan_ip("192.168.1.100") == "192.168.1.100"
    # 傳入 169.254.x.x 應自動過濾並重選有效 IP
    assert not get_lan_ip("169.254.8.1").startswith("169.254.")
    # 傳入 localhost/127.0.0.1 應重選有效 IP
    assert get_lan_ip("localhost") != "localhost"


def test_camera_token_roundtrip():
    secret = "test-secret-key-123456"
    token = create_camera_token(1, secret)
    assert verify_camera_token(token, 1, secret) is True
    assert verify_camera_token(token, 2, secret) is False
    assert verify_camera_token("invalid-token", 1, secret) is False


def test_ensure_self_signed_cert(tmp_path):
    cert, key = ensure_self_signed_cert(tmp_path)
    assert cert.exists() and cert.stat().st_size > 0
    assert key.exists() and key.stat().st_size > 0
    # 第二次呼叫應重複使用
    c2, k2 = ensure_self_signed_cert(tmp_path)
    assert cert == c2 and key == k2


def test_lane_worker_push_frame():
    w = LaneWorker(
        lane_id=99,
        name="測試車道",
        source="",
        recognizer_factory=lambda: None,  # type: ignore
        on_confirm=lambda *_: None,
    )
    assert not w.online
    assert not w.is_pushing

    # 推播一張 dummy 影格
    dummy = np.zeros((100, 100, 3), dtype=np.uint8)
    w.push_frame(dummy)

    assert w.is_pushing is True
    assert w.online is True
    frame, _ = w.latest_frame()
    assert frame is not None
    assert frame.shape == (100, 100, 3)

    w.push_stop()
    assert w.online is False


def test_mobile_camera_api_and_ws(auth_client, monkeypatch):
    client, _ = auth_client

    # 1. 取得 token
    res = client.get("/api/lanes/1/camera-token")
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert "connect_url" in data
    token = data["token"]

    # 建立一個測試用的 LaneWorker 並掛載到 manager
    from app.services import lanes as lanes_mod
    mgr = lanes_mod.get_lane_manager()
    worker = LaneWorker(
        lane_id=1,
        name="入口車道",
        source="",
        recognizer_factory=lambda: None,  # type: ignore
        on_confirm=lambda *_: None,
    )
    mgr._workers[1] = worker
    monkeypatch.setattr("app.api.system._manager", lambda: mgr)

    # 2. 測試 WebSocket 推播二進位影格
    dummy = np.zeros((60, 80, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", dummy)
    assert ok

    # 模擬 WebSocket 連線（使用 TestClient 的 websocket_connect）
    with client.websocket_connect(f"/ws/lanes/1/push?token={token}") as ws:
        ws.send_bytes(buf.tobytes())
        # 在連線開啟且推播後，等待背景執行緒處理並更新狀態
        import time
        for _ in range(20):
            if worker.online:
                break
            time.sleep(0.05)
        assert worker.online is True
        assert worker.is_pushing is True

    # 當連線關閉時，push_stop 會被呼叫
    assert worker.online is False

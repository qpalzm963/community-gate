"""車道（攝影機 / 柵欄）、系統設定、WebSocket 推播。"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from ..access.service import AccessError, handle_detection, manual_open
from ..auth import create_camera_token, current_user, verify_camera_token, ws_user
from ..config import get_config
from ..db import get_db
from ..gate import DRIVER_LABELS, build_gate
from ..models import Lane, User
from ..schemas import LaneIn, ManualOpenIn, SimulateIn
from ..services.events import bus
from ..services.settings import SettingsError, settings_store
from ..vision.plate import format_plate, normalize_ocr
from ..vision.recognizer import get_recognizer

log = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


def _manager():
    if not get_config().enable_workers:
        return None
    from ..services.lanes import get_lane_manager

    return get_lane_manager()


def lane_dict(lane: Lane) -> dict:
    mgr = _manager()
    w = mgr.get(lane.id) if mgr else None
    return {
        "id": lane.id,
        "name": lane.name,
        "direction": lane.direction,
        "source_url": lane.source_url,
        "vehicle_types": lane.vehicle_types,
        "gate_driver": lane.gate_driver,
        "gate_config": lane.gate_config or {},
        "auto_allow_unknown": lane.auto_allow_unknown,
        "enabled": lane.enabled,
        "status": w.status() if w else {"online": False, "last_error": "未啟動" if lane.enabled else "已停用"},
    }


def _get_lane(db: Session, lane_id: int) -> Lane:
    lane = db.get(Lane, lane_id)
    if lane is None:
        raise HTTPException(404, "車道不存在")
    return lane


def _latest_frame(lane_id: int) -> np.ndarray | None:
    mgr = _manager()
    w = mgr.get(lane_id) if mgr else None
    if w is None:
        return None
    frame, _ = w.latest_frame()
    return frame


# ------------------------------------------------------------------ 公開資訊


@router.get("/api/public/info")
def public_info():
    return {"community_name": settings_store.get("community_name"), "version": "0.1.0"}


# ------------------------------------------------------------------ 車道


@router.get("/api/lanes/meta")
def lanes_meta(_: User = Depends(current_user)):
    return {"drivers": [{"value": k, "label": v} for k, v in DRIVER_LABELS.items()]}


@router.get("/api/lanes")
def list_lanes(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [lane_dict(l) for l in db.query(Lane).order_by(Lane.id).all()]


@router.post("/api/lanes")
async def create_lane(body: LaneIn, _: User = Depends(current_user), db: Session = Depends(get_db)):
    lane = Lane(**body.model_dump())
    db.add(lane)
    db.commit()
    db.refresh(lane)
    if mgr := _manager():
        await run_in_threadpool(mgr.restart, lane.id)
    return lane_dict(lane)


@router.put("/api/lanes/{lane_id}")
async def update_lane(lane_id: int, body: LaneIn, _: User = Depends(current_user), db: Session = Depends(get_db)):
    lane = _get_lane(db, lane_id)
    for k, v in body.model_dump().items():
        setattr(lane, k, v)
    db.commit()
    db.refresh(lane)
    if mgr := _manager():
        await run_in_threadpool(mgr.restart, lane.id)
    return lane_dict(lane)


@router.delete("/api/lanes/{lane_id}")
async def delete_lane(lane_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    lane = _get_lane(db, lane_id)
    if mgr := _manager():
        await run_in_threadpool(mgr.remove, lane.id)
    db.delete(lane)
    db.commit()
    return {"ok": True}


@router.post("/api/lanes/{lane_id}/open")
async def open_gate(lane_id: int, body: ManualOpenIn, user: User = Depends(current_user)):
    try:
        return await run_in_threadpool(manual_open, lane_id, user.id, body.note, body.plate, _latest_frame(lane_id))
    except AccessError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/lanes/{lane_id}/test-gate")
async def test_gate(lane_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    lane = _get_lane(db, lane_id)
    gate = build_gate(lane.gate_driver, lane.id, lane.gate_config)
    res = await run_in_threadpool(gate.open, "測試開閘")
    bus.publish("gate", {"lane_id": lane.id, "lane_name": lane.name, "ok": res.ok, "message": res.message, "event_id": None})
    return {"ok": res.ok, "message": res.message}


@router.post("/api/lanes/{lane_id}/simulate")
async def simulate(lane_id: int, body: SimulateIn, _: User = Depends(current_user)):
    """模擬一筆已確認的車牌辨識（不經攝影機，用於測試流程）。"""
    try:
        return await run_in_threadpool(handle_detection, body.plate, body.confidence, lane_id, _latest_frame(lane_id), None)
    except AccessError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/lanes/{lane_id}/recognize")
async def recognize_image(
    lane_id: int,
    file: UploadFile = File(...),
    apply: bool = False,
    _: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """上傳圖片辨識車牌；apply=true 時以信心最高的結果建立進出事件。"""
    _get_lane(db, lane_id)
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "圖片過大（上限 15MB）")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "無法讀取圖片")
    detections = await run_in_threadpool(get_recognizer().predict, img)
    strict = bool(settings_store.get("plate_strict_format"))
    results = []
    for det in detections:
        norm = normalize_ocr(det.text, strict=strict)
        results.append(
            {
                "raw_text": det.text,
                "plate": norm.plate if norm else None,
                "plate_display": format_plate(norm.plate) if norm else None,
                "corrections": norm.corrections if norm else None,
                "confidence": round(det.confidence, 4),
                "det_confidence": round(det.det_confidence, 4),
                "bbox": det.bbox,
            }
        )
    event = None
    valid = [r for r in results if r["plate"]]
    if apply and valid:
        best = max(valid, key=lambda r: r["confidence"])
        x1, y1, x2, y2 = best["bbox"]
        crop = img[max(y1, 0) : y2, max(x1, 0) : x2].copy()
        try:
            event = await run_in_threadpool(handle_detection, best["plate"], best["confidence"], lane_id, img, crop)
        except AccessError as e:
            raise HTTPException(400, str(e)) from e
    return {"detections": results, "event": event}


def _placeholder_jpeg(text: str = "NO SIGNAL") -> bytes:
    img = np.full((360, 640, 3), 40, np.uint8)
    cv2.putText(img, text, (200, 190), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (160, 160, 160), 2, cv2.LINE_AA)
    return cv2.imencode(".jpg", img)[1].tobytes()


@router.get("/api/lanes/{lane_id}/frame")
async def lane_frame(lane_id: int, _: User = Depends(current_user)):
    mgr = _manager()
    w = mgr.get(lane_id) if mgr else None
    jpg = await run_in_threadpool(w.annotated_jpeg) if w else None
    return Response(jpg or _placeholder_jpeg(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/api/lanes/{lane_id}/stream")
async def lane_stream(lane_id: int, request: Request, _: User = Depends(current_user)):
    boundary = "frame"
    placeholder = _placeholder_jpeg()

    interval = 1 / 15  # 串流上限 15fps

    async def gen():
        last_seq = -1
        last_sent = 0.0
        while not await request.is_disconnected():
            mgr = _manager()
            w = mgr.get(lane_id) if mgr else None
            online = bool(w and w.online)
            now = time.monotonic()
            # 沒有新影格就不重送（最多每秒補一張保活），有新影格才編碼送出
            if online and w.frame_seq == last_seq and now - last_sent < 1.0:
                await asyncio.sleep(0.01)
                continue
            t0 = now
            if w:
                last_seq = w.frame_seq
            jpg = await run_in_threadpool(w.annotated_jpeg) if w else None
            jpg = jpg or placeholder
            yield (
                f"--{boundary}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpg)}\r\n\r\n".encode() + jpg + b"\r\n"
            )
            last_sent = time.monotonic()
            # 扣掉編碼與送出花的時間，避免「編碼時間 + 固定 sleep」把實際 fps 拉低
            await asyncio.sleep(max(0.0, interval - (last_sent - t0)) if online else 1.0)

    return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}", headers={"Cache-Control": "no-store"})


def _is_usable_ip(ip: str) -> bool:
    """手機能否連到這個位址：排除本機迴路、未指定位址與 169.254.x.x（Link-Local / APIPA）。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_loopback or addr.is_link_local or addr.is_unspecified)


def get_lan_ip(preferred_host: str | None = None) -> str:
    """自動偵測區域網路 IP，避免挑到 127.0.0.1 或 169.254.x.x (Link-Local)"""
    if preferred_host and preferred_host != "localhost":
        try:
            if _is_usable_ip(str(ipaddress.ip_address(preferred_host))):
                return preferred_host
        except ValueError:
            # 不是 IP 而是網域名稱（例如反向代理的公網網域），直接採用
            return preferred_host

    # 1. 嘗試透過連線探測常用路由以找出對外網卡（UDP connect 不會真的送出封包）
    for target in ("8.8.8.8", "1.1.1.1", "10.255.255.255"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            s.close()
            if _is_usable_ip(ip):
                return ip
        except Exception:
            continue

    # 2. 嘗試從 hostname 列出所有候選 IP
    candidates: list[str] = []
    try:
        _, _, ips = socket.gethostbyname_ex(socket.gethostname())
        candidates = [ip for ip in ips if _is_usable_ip(ip)]
    except Exception:
        pass

    # 優先返回私有網段（192.168/16、172.16/12、10/8），公網 IP 在社區內網通常不是要給手機連的那張網卡
    for ip in candidates:
        if ipaddress.ip_address(ip).is_private:
            return ip

    return candidates[0] if candidates else "127.0.0.1"


@router.get("/api/lanes/{lane_id}/camera-token")
def lane_camera_token(lane_id: int, request: Request, _: User = Depends(current_user), db: Session = Depends(get_db)):
    lane = _get_lane(db, lane_id)
    cfg = get_config()
    token = create_camera_token(lane.id, cfg.get_secret_key())
    lan_ip = get_lan_ip(request.url.hostname)
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    scheme = request.url.scheme
    return {
        "lane_id": lane.id,
        "lane_name": lane.name,
        "token": token,
        "lan_ip": lan_ip,
        "port": port,
        "scheme": scheme,
        "connect_url": f"{scheme}://{lan_ip}:{port}/mobile-cam?lane={lane.id}&token={token}",
    }


@router.websocket("/ws/lanes/{lane_id}/push")
async def ws_lane_camera_push(ws: WebSocket, lane_id: int, token: str):
    cfg = get_config()
    if not verify_camera_token(token, lane_id, cfg.get_secret_key()):
        await ws.close(code=4403, reason="憑證無效或已過期")
        return

    await ws.accept()
    mgr = _manager()
    worker = mgr.get(lane_id) if mgr else None
    if worker is None:
        await ws.close(code=4404, reason="車道未啟動")
        return

    q = bus.subscribe()

    async def _bus_listener():
        try:
            while True:
                msg = await q.get()
                if msg.get("type") == "access_event":
                    data = msg.get("data", {})
                    if data.get("lane_id") == lane_id:
                        await ws.send_json({
                            "type": "plate_confirmed",
                            "plate": data.get("plate_display") or data.get("plate"),
                            "category": data.get("category"),
                            "decision": data.get("decision"),
                        })
        except Exception:
            pass

    bus_task = asyncio.create_task(_bus_listener())
    try:
        while True:
            message = await ws.receive()
            if "bytes" in message and message["bytes"]:
                data = message["bytes"]
                frame = await run_in_threadpool(cv2.imdecode, np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    worker.push_frame(frame)
            elif "text" in message and message["text"]:
                pass
    except Exception:
        pass
    finally:
        bus_task.cancel()
        bus.unsubscribe(q)
        worker.push_stop()


# ------------------------------------------------------------------ 系統設定


@router.get("/api/settings")
def get_settings(_: User = Depends(current_user)):
    return {"values": settings_store.all(), "meta": settings_store.describe()}


@router.put("/api/settings")
def put_settings(body: dict, _: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        values = settings_store.update(db, body)
    except SettingsError as e:
        raise HTTPException(400, str(e)) from e
    bus.publish("settings_changed", values)
    return {"values": values, "meta": settings_store.describe()}


# ------------------------------------------------------------------ WebSocket


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    user = ws_user(ws)
    if user is None:
        await ws.close(code=4401)
        return
    await ws.accept()
    q = bus.subscribe()
    try:
        await ws.send_json({"type": "hello", "data": {"user": user.username}})
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=25)
            except TimeoutError:
                msg = {"type": "ping", "data": {}}
            await ws.send_json(msg)
    except Exception:  # noqa: BLE001  連線中斷（WebSocketDisconnect / ClientDisconnected 等）
        pass
    finally:
        bus.unsubscribe(q)

"""車道（攝影機 / 柵欄）、系統設定、WebSocket 推播。"""
from __future__ import annotations

import asyncio
import logging

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from ..access.service import AccessError, handle_detection, manual_open
from ..auth import current_user, ws_user
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

    async def gen():
        while not await request.is_disconnected():
            mgr = _manager()
            w = mgr.get(lane_id) if mgr else None
            jpg = await run_in_threadpool(w.annotated_jpeg) if w else None
            jpg = jpg or placeholder
            yield (
                f"--{boundary}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpg)}\r\n\r\n".encode() + jpg + b"\r\n"
            )
            await asyncio.sleep(0.1 if w and w.online else 1.0)

    return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}", headers={"Cache-Control": "no-store"})


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

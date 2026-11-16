"""截圖儲存與清理。

截圖本體存在資料庫（snapshots 表），以「年/月/日/檔名」字串當鍵；雲端容器重新部署不會遺失。
舊版存在 snapshot_dir 磁碟上的截圖仍可讀取與依保存天數清理（單機版升級相容）。
"""
from __future__ import annotations

import logging
import secrets
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..config import get_config
from ..db import SessionLocal
from ..models import Snapshot

log = logging.getLogger(__name__)


FRAME_MAX_WIDTH = 1280
FRAME_WEBP_QUALITY = 75


def save_frame(img: np.ndarray | None, prefix: str, at: datetime | None = None, db: Session | None = None) -> str:
    """存整張現場畫面：WebP 75、寬度上限 1280px。

    同尺寸下約只有 JPEG 85 的 1/4，畫面只用來看現場狀況，車牌判讀另有特寫。
    """
    if img is None or getattr(img, "size", 0) == 0:
        return ""
    h, w = img.shape[:2]
    if w > FRAME_MAX_WIDTH:
        img = cv2.resize(img, (FRAME_MAX_WIDTH, round(h * FRAME_MAX_WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".webp", img, [int(cv2.IMWRITE_WEBP_QUALITY), FRAME_WEBP_QUALITY])
    return _store(buf.tobytes(), prefix, "webp", at, db) if ok else ""


def save_jpeg(
    img: np.ndarray | None, prefix: str, at: datetime | None = None, quality: int = 85, db: Session | None = None
) -> str:
    """存 JPEG（車牌特寫用：圖很小，保留畫質供判讀）。"""
    if img is None or getattr(img, "size", 0) == 0:
        return ""
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return _store(buf.tobytes(), prefix, "jpg", at, db) if ok else ""


def _store(data: bytes, prefix: str, ext: str, at: datetime | None, db: Session | None) -> str:
    """存入資料庫，回傳截圖鍵。

    傳入 db 時只加進該 session、由呼叫端 commit：事件寫入失敗時截圖跟著回滾，不會留下孤兒資料。
    """
    at = at or datetime.now()
    # now() 會把微秒歸零，同一秒內多筆事件靠隨機尾碼避免鍵值相撞
    rel = f"{at.strftime('%Y/%m/%d')}/{at.strftime('%H%M%S')}_{prefix}_{secrets.token_hex(4)}.{ext}"
    snap = Snapshot(path=rel, data=data, created_at=at)
    if db is not None:
        db.add(snap)
        return rel
    own = SessionLocal()
    try:
        own.add(snap)
        own.commit()
    finally:
        own.close()
    return rel


def _legacy_file(rel: str) -> Path | None:
    """舊版存在磁碟上的截圖，並防止路徑穿越。"""
    root = get_config().snapshot_dir.resolve()
    p = (root / rel).resolve()
    if root not in p.parents or not p.is_file():
        return None
    return p


def resolve(rel: str) -> bytes | None:
    """取得截圖 JPEG 內容；先查資料庫，再找舊版磁碟檔。"""
    if not rel:
        return None
    db = SessionLocal()
    try:
        snap = db.get(Snapshot, rel)
        if snap is not None:
            return snap.data
    finally:
        db.close()
    p = _legacy_file(rel)
    return p.read_bytes() if p else None


def cleanup(retention_days: int, today: date | None = None) -> int:
    """刪除超過保存天數的截圖，回傳刪除的數量（資料庫筆數 + 舊版磁碟日期資料夾數）。"""
    today = today or date.today()
    cutoff = today - timedelta(days=retention_days)
    db = SessionLocal()
    try:
        removed = db.execute(
            delete(Snapshot).where(Snapshot.created_at < datetime.combine(cutoff, datetime.min.time()))
        ).rowcount or 0
        db.commit()
    finally:
        db.close()
    removed += _cleanup_legacy_dirs(cutoff)
    if removed:
        log.info("已清除 %d 筆過期截圖（保存 %d 天）", removed, retention_days)
    return removed


def _cleanup_legacy_dirs(cutoff: date) -> int:
    """刪除舊版磁碟上早於 cutoff 的日期資料夾。"""
    root = get_config().snapshot_dir
    removed = 0
    if not root.exists():
        return 0
    for day_dir in sorted(root.glob("*/*/*")):
        if not day_dir.is_dir():
            continue
        try:
            y, m, d = (int(x) for x in day_dir.relative_to(root).parts)
            day = date(y, m, d)
        except ValueError:
            continue
        if day < cutoff:
            shutil.rmtree(day_dir, ignore_errors=True)
            removed += 1
    # 清除空的 年/月 資料夾
    for d in sorted(root.glob("*/*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    for d in sorted(root.glob("*")):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return removed

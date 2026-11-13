"""截圖儲存與清理。路徑一律存相對於 snapshot_dir 的相對路徑。"""
from __future__ import annotations

import logging
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

from ..config import get_config

log = logging.getLogger(__name__)


def save_jpeg(img: np.ndarray | None, prefix: str, at: datetime | None = None, quality: int = 85) -> str:
    if img is None or getattr(img, "size", 0) == 0:
        return ""
    at = at or datetime.now()
    root = get_config().snapshot_dir
    rel = Path(at.strftime("%Y/%m/%d")) / f"{at.strftime('%H%M%S')}_{prefix}_{at.microsecond:06d}.jpg"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return ""
    path.write_bytes(buf.tobytes())
    return rel.as_posix()


def resolve(rel: str) -> Path | None:
    """將相對路徑轉為絕對路徑，並防止路徑穿越。"""
    if not rel:
        return None
    root = get_config().snapshot_dir.resolve()
    p = (root / rel).resolve()
    if root not in p.parents or not p.is_file():
        return None
    return p


def cleanup(retention_days: int, today: date | None = None) -> int:
    """刪除超過保存天數的日期資料夾，回傳刪除的資料夾數。"""
    today = today or date.today()
    cutoff = today - timedelta(days=retention_days)
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
    if removed:
        log.info("已清除 %d 天份截圖（保存 %d 天）", removed, retention_days)
    return removed

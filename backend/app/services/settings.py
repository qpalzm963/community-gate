"""執行期可調參數（存於 settings 表，後台「系統設定」頁可修改，即時生效）。"""
from __future__ import annotations

import json
import threading
from typing import Any

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Setting

# key → (預設值, 型別, 說明, 最小值, 最大值)
DEFAULTS: dict[str, tuple[Any, type, str, float | None, float | None]] = {
    "community_name": ("社區出入管理系統", str, "社區名稱（顯示於標題）", None, None),
    "snapshot_retention_days": (90, int, "截圖保存天數（超過自動刪除）", 1, 3650),
    "recognition_fps": (5.0, float, "每車道每秒辨識張數", 0.5, 30),
    "vote_min_hits": (3, int, "多幀投票：確認所需最少次數", 1, 20),
    "vote_window_sec": (2.0, float, "多幀投票：時間視窗（秒）", 0.5, 30),
    "vote_min_confidence": (0.8, float, "多幀投票：平均信心值門檻（0~1）", 0, 1),
    "dedup_sec": (30.0, float, "同車道同車牌去重秒數", 1, 3600),
    "overstay_grace_min": (15, int, "訪客逾時寬限（分鐘）", 0, 1440),
    "pending_timeout_min": (10, int, "待處理事件逾時自動結案（分鐘，0 = 不自動結案）", 0, 1440),
    "plate_strict_format": (True, bool, "只接受符合台灣車牌格式的辨識結果", None, None),
    "alert_sound": (True, bool, "警示時播放音效", None, None),
}


class SettingsError(ValueError):
    pass


def _coerce(key: str, value: Any) -> Any:
    if key not in DEFAULTS:
        raise SettingsError(f"未知的設定：{key}")
    default, typ, _desc, lo, hi = DEFAULTS[key]
    try:
        if typ is bool:
            if isinstance(value, str):
                v: Any = value.strip().lower() in ("1", "true", "yes", "on")
            else:
                v = bool(value)
        elif typ is int:
            v = int(value)
        elif typ is float:
            v = float(value)
        else:
            v = str(value)
    except (TypeError, ValueError) as e:
        raise SettingsError(f"{key} 格式錯誤") from e
    if typ in (int, float):
        if lo is not None and v < lo:
            raise SettingsError(f"{key} 不可小於 {lo}")
        if hi is not None and v > hi:
            raise SettingsError(f"{key} 不可大於 {hi}")
    return v


class SettingsStore:
    def __init__(self):
        self._cache: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._listeners: list = []

    def on_change(self, fn) -> None:
        self._listeners.append(fn)

    def _load(self, db: Session) -> dict[str, Any]:
        values = {k: d[0] for k, d in DEFAULTS.items()}
        for row in db.query(Setting).all():
            if row.key in DEFAULTS:
                try:
                    values[row.key] = _coerce(row.key, json.loads(row.value))
                except (SettingsError, json.JSONDecodeError):
                    pass
        return values

    def all(self) -> dict[str, Any]:
        with self._lock:
            if self._cache is None:
                db = SessionLocal()
                try:
                    self._cache = self._load(db)
                finally:
                    db.close()
            return dict(self._cache)

    def get(self, key: str) -> Any:
        return self.all()[key]

    def update(self, db: Session, changes: dict[str, Any]) -> dict[str, Any]:
        coerced = {k: _coerce(k, v) for k, v in changes.items()}
        for k, v in coerced.items():
            row = db.get(Setting, k)
            if row is None:
                db.add(Setting(key=k, value=json.dumps(v)))
            else:
                row.value = json.dumps(v)
        db.commit()
        with self._lock:
            self._cache = None
        values = self.all()
        for fn in self._listeners:
            fn(values)
        return values

    def invalidate(self) -> None:
        with self._lock:
            self._cache = None

    @staticmethod
    def describe() -> list[dict[str, Any]]:
        return [
            {"key": k, "default": d[0], "type": d[1].__name__, "description": d[2], "min": d[3], "max": d[4]}
            for k, d in DEFAULTS.items()
        ]


settings_store = SettingsStore()

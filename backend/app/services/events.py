"""事件匯流排：任何執行緒都可 publish，WebSocket 連線各自訂閱一個 asyncio.Queue。"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import date, datetime
from typing import Any

log = logging.getLogger(__name__)


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


class EventBus:
    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self.history: list[dict] = []  # 測試 / 除錯用：最近訊息

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._queues.discard(q)

    def _deliver(self, msg: dict) -> None:
        with self._lock:
            queues = list(self._queues)
        for q in queues:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(msg)

    def publish(self, type_: str, data: dict | None = None) -> None:
        msg = {"type": type_, "data": _jsonable(data or {}), "ts": datetime.now().isoformat(timespec="seconds")}
        self.history.append(msg)
        del self.history[:-100]
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._deliver(msg)
        else:
            loop.call_soon_threadsafe(self._deliver, msg)


bus = EventBus()

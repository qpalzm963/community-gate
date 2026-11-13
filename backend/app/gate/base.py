"""柵欄控制器抽象介面。所有驅動皆為同步呼叫（由背景執行緒或 threadpool 呼叫）。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GateResult:
    ok: bool
    message: str = ""


class GateController(ABC):
    driver_name: str = "base"

    def __init__(self, lane_id: int, config: dict | None = None):
        self.lane_id = lane_id
        self.config = config or {}

    @abstractmethod
    def open(self, reason: str = "") -> GateResult: ...

    def health(self) -> GateResult:
        return GateResult(True, "ok")

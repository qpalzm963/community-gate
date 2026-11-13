from __future__ import annotations

import logging

from .base import GateController, GateResult

log = logging.getLogger(__name__)


class SimulatedGate(GateController):
    """模擬柵欄：只寫 log，前端透過 gate 事件顯示開啟動畫。"""

    driver_name = "simulated"

    def open(self, reason: str = "") -> GateResult:
        log.info("[模擬柵欄] 車道 %s 開啟（%s）", self.lane_id, reason)
        return GateResult(True, "模擬開啟")

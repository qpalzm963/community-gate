from __future__ import annotations

from .base import GateController, GateResult
from .http_relay import HttpRelayGate
from .modbus import ModbusRelayGate
from .simulated import SimulatedGate

DRIVERS: dict[str, type[GateController]] = {
    SimulatedGate.driver_name: SimulatedGate,
    HttpRelayGate.driver_name: HttpRelayGate,
    ModbusRelayGate.driver_name: ModbusRelayGate,
}

DRIVER_LABELS = {
    "simulated": "模擬柵欄",
    "http_relay": "HTTP 繼電器",
    "modbus": "Modbus TCP 繼電器",
}


def build_gate(driver: str, lane_id: int, config: dict | None) -> GateController:
    cls = DRIVERS.get(driver or "simulated", SimulatedGate)
    return cls(lane_id, config or {})


__all__ = ["GateController", "GateResult", "build_gate", "DRIVERS", "DRIVER_LABELS"]

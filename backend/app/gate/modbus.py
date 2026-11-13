from __future__ import annotations

import time

from .base import GateController, GateResult


class ModbusRelayGate(GateController):
    """Modbus TCP 繼電器（預留，需安裝 `uv sync --extra modbus`）。

    gate_config 範例::

        {"host": "192.168.1.60", "port": 502, "unit": 1, "coil": 0, "pulse_sec": 1.0}

    以「寫 coil=ON → 等待 pulse_sec → 寫 coil=OFF」的脈衝方式觸發柵欄。
    """

    driver_name = "modbus"

    def _client(self):
        try:
            from pymodbus.client import ModbusTcpClient
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("未安裝 pymodbus，請執行 uv sync --extra modbus") from e
        return ModbusTcpClient(self.config.get("host", "127.0.0.1"), port=int(self.config.get("port", 502)), timeout=3)

    def open(self, reason: str = "") -> GateResult:
        try:
            client = self._client()
        except RuntimeError as e:
            return GateResult(False, str(e))
        coil = int(self.config.get("coil", 0))
        unit = int(self.config.get("unit", 1))
        pulse = float(self.config.get("pulse_sec", 1.0))
        try:
            if not client.connect():
                return GateResult(False, "Modbus 連線失敗")
            def write(value: bool):
                try:
                    return client.write_coil(coil, value, device_id=unit)  # pymodbus >= 3.10
                except TypeError:
                    return client.write_coil(coil, value, slave=unit)  # 舊版

            r = write(True)
            if r.isError():
                return GateResult(False, f"Modbus 寫入失敗：{r}")
            time.sleep(pulse)
            write(False)
            return GateResult(True, "Modbus 脈衝完成")
        except Exception as e:  # noqa: BLE001
            return GateResult(False, f"Modbus 錯誤：{e}")
        finally:
            client.close()

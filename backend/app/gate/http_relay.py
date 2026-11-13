from __future__ import annotations

import httpx

from .base import GateController, GateResult


class HttpRelayGate(GateController):
    """HTTP 繼電器（如 ESP32 自製韌體、Shelly）。

    gate_config 範例::

        {"url": "http://192.168.1.50/relay/0?turn=on&timer=2", "method": "GET", "timeout": 3,
         "health_url": "http://192.168.1.50/status"}
    """

    driver_name = "http_relay"

    def open(self, reason: str = "") -> GateResult:
        url = self.config.get("url")
        if not url:
            return GateResult(False, "未設定繼電器 URL")
        method = str(self.config.get("method", "GET")).upper()
        timeout = float(self.config.get("timeout", 3))
        try:
            resp = httpx.request(method, url, timeout=timeout, headers=self.config.get("headers") or None)
        except httpx.HTTPError as e:
            return GateResult(False, f"繼電器連線失敗：{e}")
        if resp.status_code >= 400:
            return GateResult(False, f"繼電器回應 HTTP {resp.status_code}")
        return GateResult(True, f"HTTP {resp.status_code}")

    def health(self) -> GateResult:
        url = self.config.get("health_url")
        if not url:
            return GateResult(True, "未設定健康檢查 URL")
        try:
            resp = httpx.get(url, timeout=float(self.config.get("timeout", 3)))
            return GateResult(resp.status_code < 400, f"HTTP {resp.status_code}")
        except httpx.HTTPError as e:
            return GateResult(False, str(e))

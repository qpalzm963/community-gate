"""台灣車牌正規化、格式校正與多幀投票。

正規化格式：大寫英數字、無 '-' 與空白，例如 ``ABC-1234`` → ``ABC1234``。
"""
from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

# 格式樣板：L = 英文字母，D = 數字。順序即優先序（同成本時取前者）。
# 汽車：LLL-DDDD（2012 後新式）、LL-DDDD / DDDD-LL（舊式）
# 機車：LLL-DDDD（新式，與汽車相同）、LLL-DDD、DDD-LLL（舊式 / 輕型）
TW_TEMPLATES: list[str] = [
    "LLLDDDD",
    "LLDDDD",
    "DDDDLL",
    "LLLDDD",
    "DDDLLL",
    "DDLLLL",  # 部分舊式營業 / 特殊車
    "LLDDD",  # 部分舊式機車
]

# 位置為「字母」但 OCR 讀成數字時的修正
_DIGIT_TO_LETTER = {"8": "B", "5": "S", "2": "Z", "6": "G", "0": "D", "4": "A", "1": "T", "7": "T"}
# 位置為「數字」但 OCR 讀成字母時的修正
_LETTER_TO_DIGIT = {
    "O": "0", "D": "0", "Q": "0", "U": "0",
    "I": "1", "L": "1", "T": "1", "J": "1",
    "Z": "2", "S": "5", "B": "8", "G": "6", "A": "4",
}

_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def clean(text: str) -> str:
    """大寫並移除所有非英數字（使用者輸入用，不做字元修正）。"""
    return _NON_ALNUM.sub("", (text or "").upper())


def _template_of(plate: str) -> str:
    return "".join("L" if c.isalpha() else "D" for c in plate)


def _fit(text: str, template: str) -> tuple[str, int] | None:
    """將 text 套入樣板，回傳 (修正後字串, 修正字元數)；無法套用則 None。"""
    if len(text) != len(template):
        return None
    out: list[str] = []
    cost = 0
    for ch, kind in zip(text, template):
        if kind == "L":
            if ch.isalpha():
                out.append(ch)
            elif ch in _DIGIT_TO_LETTER:
                out.append(_DIGIT_TO_LETTER[ch])
                cost += 1
            else:
                return None
        else:
            if ch.isdigit():
                out.append(ch)
            elif ch in _LETTER_TO_DIGIT:
                out.append(_LETTER_TO_DIGIT[ch])
                cost += 1
            else:
                return None
    return "".join(out), cost


@dataclass(frozen=True)
class NormalizedPlate:
    plate: str
    template: str | None
    corrections: int


def normalize_ocr(text: str, strict: bool = True, max_corrections: int = 2) -> NormalizedPlate | None:
    """正規化 OCR 讀到的車牌文字。

    - strict=True：必須能套入台灣車牌樣板（允許最多 ``max_corrections`` 個易混淆字元修正），否則回傳 None。
    - strict=False：套不進樣板時，只要是 4~8 碼英數字仍原樣接受。
    """
    raw = clean(text)
    if not raw:
        return None
    best: tuple[str, int, int, str] | None = None  # (plate, cost, priority, template)
    for prio, tpl in enumerate(TW_TEMPLATES):
        fit = _fit(raw, tpl)
        if fit is None:
            continue
        plate, cost = fit
        if cost > max_corrections:
            continue
        key = (cost, prio)
        if best is None or key < (best[1], best[2]):
            best = (plate, cost, prio, tpl)
    if best is not None:
        return NormalizedPlate(best[0], best[3], best[1])
    if not strict and 4 <= len(raw) <= 8:
        return NormalizedPlate(raw, None, 0)
    return None


def format_plate(plate: str) -> str:
    """顯示用格式：在英文段與數字段之間補 '-'，例如 ABC1234 → ABC-1234。"""
    p = clean(plate)
    if not p:
        return ""
    runs = re.findall(r"[A-Z]+|[0-9]+", p)
    if len(runs) == 2:
        return f"{runs[0]}-{runs[1]}"
    return p


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 2:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------------------
# 多幀投票
# ---------------------------------------------------------------------------


@dataclass
class Observation:
    plate: str
    confidence: float
    ts: float
    payload: Any = None  # 例如 (frame, crop, bbox)，確認時回傳信心最高的那筆


@dataclass
class ConfirmedPlate:
    plate: str
    confidence: float  # 視窗內平均信心值
    hits: int
    best: Observation


@dataclass
class VoteParams:
    min_hits: int = 3
    window_sec: float = 2.0
    min_confidence: float = 0.8
    dedup_sec: float = 30.0


@dataclass
class PlateVoter:
    """單一車道的多幀投票器（執行緒安全）。

    - 視窗 ``window_sec`` 內同一車牌出現 ≥ ``min_hits`` 次且平均信心值 ≥ ``min_confidence`` 才確認。
    - 已確認的車牌（及編輯距離 ≤ 1 的近似誤讀）只要持續被看到，就不會重複觸發；
      最後一次看到後超過 ``dedup_sec`` 秒才會再次觸發。
    """

    params: VoteParams = field(default_factory=VoteParams)
    _obs: deque[Observation] = field(default_factory=deque)
    _recent: dict[str, float] = field(default_factory=dict)  # 已確認車牌 → 最後看到時間
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _recently_confirmed(self, plate: str, ts: float) -> str | None:
        for p, last in self._recent.items():
            if ts - last <= self.params.dedup_sec and edit_distance(p, plate) <= 1:
                return p
        return None

    def add(self, plate: str, confidence: float, ts: float | None = None, payload: Any = None) -> ConfirmedPlate | None:
        ts = time.monotonic() if ts is None else ts
        p = self.params
        with self._lock:
            # 清掉過期資料
            while self._obs and ts - self._obs[0].ts > p.window_sec:
                self._obs.popleft()
            self._recent = {k: v for k, v in self._recent.items() if ts - v <= p.dedup_sec}

            dup = self._recently_confirmed(plate, ts)
            if dup is not None:
                self._recent[dup] = ts  # 持續看到 → 延長去重
                return None

            obs = Observation(plate, confidence, ts, payload)
            self._obs.append(obs)
            same = [o for o in self._obs if o.plate == plate]
            if len(same) < p.min_hits:
                return None
            avg = sum(o.confidence for o in same) / len(same)
            if avg < p.min_confidence:
                return None
            best = max(same, key=lambda o: o.confidence)
            self._recent[plate] = ts
            # 移除視窗內所有近似觀測，避免誤讀版本再被確認
            self._obs = deque(o for o in self._obs if edit_distance(o.plate, plate) > 1)
            return ConfirmedPlate(plate, round(avg, 4), len(same), best)

    def reset(self) -> None:
        with self._lock:
            self._obs.clear()
            self._recent.clear()

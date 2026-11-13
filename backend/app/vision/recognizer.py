"""車牌辨識器介面與 fast-alpr 實作（可抽換）。"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlateDetection:
    text: str  # 原始 OCR 文字
    confidence: float  # OCR 平均信心值 0~1
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    det_confidence: float = 1.0


class Recognizer(Protocol):
    def predict(self, frame: np.ndarray) -> list[PlateDetection]: ...


class FastAlprRecognizer:
    """fast-alpr：YOLOv9 車牌偵測 + fast-plate-ocr 全球模型（ONNX Runtime，CPU）。

    首次使用時才載入模型（首次執行會下載模型檔，之後離線可用）。
    """

    def __init__(self, detector_model: str, ocr_model: str, detector_conf: float = 0.4):
        self._detector_model = detector_model
        self._ocr_model = ocr_model
        self._detector_conf = detector_conf
        self._alpr = None
        self._lock = threading.Lock()

    def _ensure(self):
        if self._alpr is None:
            with self._lock:
                if self._alpr is None:
                    from fast_alpr import ALPR

                    log.info("載入辨識模型 detector=%s ocr=%s", self._detector_model, self._ocr_model)
                    self._alpr = ALPR(
                        detector_model=self._detector_model,
                        detector_conf_thresh=self._detector_conf,
                        ocr_model=self._ocr_model,
                        ocr_device="cpu",
                    )
        return self._alpr

    def warmup(self) -> None:
        self._ensure()

    def predict(self, frame: np.ndarray) -> list[PlateDetection]:
        alpr = self._ensure()
        results = alpr.predict(frame)
        out: list[PlateDetection] = []
        for r in results:
            if r.ocr is None or not r.ocr.text:
                continue
            conf = r.ocr.confidence
            if isinstance(conf, (list, tuple)):
                conf = float(np.mean(conf)) if len(conf) else 0.0
            bb = r.detection.bounding_box
            out.append(
                PlateDetection(
                    text=r.ocr.text,
                    confidence=float(conf),
                    bbox=(int(bb.x1), int(bb.y1), int(bb.x2), int(bb.y2)),
                    det_confidence=float(r.detection.confidence),
                )
            )
        return out


_recognizer: Recognizer | None = None
_rec_lock = threading.Lock()


def get_recognizer() -> Recognizer:
    global _recognizer
    if _recognizer is None:
        with _rec_lock:
            if _recognizer is None:
                from ..config import get_config

                cfg = get_config()
                _recognizer = FastAlprRecognizer(cfg.alpr_detector_model, cfg.alpr_ocr_model)
    return _recognizer


def set_recognizer(rec: Recognizer | None) -> None:
    """測試或替換辨識引擎用。"""
    global _recognizer
    _recognizer = rec

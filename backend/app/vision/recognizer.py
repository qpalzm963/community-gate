"""車牌辨識器介面與 fast-alpr 實作（可抽換）。"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


def default_intra_threads() -> int:
    """依 CPU 核心數計算單一 ONNX Session 的預設 intra-op 執行緒數。"""
    cpus = os.cpu_count() or 2
    return max(1, min(4, cpus // 2))


def _build_session_options(intra_threads: int):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = max(1, intra_threads)
    opts.inter_op_num_threads = 1
    return opts


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

    def __init__(
        self,
        detector_model: str,
        ocr_model: str,
        detector_conf: float = 0.4,
        intra_threads: int = 0,
        max_concurrent: int = 2,
    ):
        self._detector_model = detector_model
        self._ocr_model = ocr_model
        self._detector_conf = detector_conf
        self._intra_threads = intra_threads if intra_threads > 0 else default_intra_threads()
        self._max_concurrent = max_concurrent
        self._sem = threading.Semaphore(max_concurrent) if max_concurrent > 0 else None
        self._alpr = None
        self._lock = threading.Lock()
        self._warmup_lock = threading.Lock()
        self._warmed_up = False

    def _ensure(self):
        if self._alpr is None:
            with self._lock:
                if self._alpr is None:
                    from fast_alpr import ALPR

                    sess_opts = _build_session_options(self._intra_threads)
                    log.info(
                        "載入辨識模型 detector=%s ocr=%s (intra_threads=%d, max_concurrent=%d)",
                        self._detector_model,
                        self._ocr_model,
                        self._intra_threads,
                        self._max_concurrent,
                    )
                    self._alpr = ALPR(
                        detector_model=self._detector_model,
                        detector_conf_thresh=self._detector_conf,
                        detector_sess_options=sess_opts,
                        ocr_model=self._ocr_model,
                        ocr_device="cpu",
                        ocr_sess_options=sess_opts,
                    )
        return self._alpr

    def warmup(self) -> None:
        if self._warmed_up:
            return
        with self._warmup_lock:
            if self._warmed_up:
                return
            self._ensure()
            # 執行一次空白影格推論，讓 ONNX Runtime 完成記憶體與算子配置，避免首幀延遲
            self.predict(np.zeros((384, 384, 3), dtype=np.uint8))
            self._warmed_up = True

    def predict(self, frame: np.ndarray) -> list[PlateDetection]:
        alpr = self._ensure()
        guard = self._sem if self._sem is not None else nullcontext()
        with guard:
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
                _recognizer = FastAlprRecognizer(
                    cfg.alpr_detector_model,
                    cfg.alpr_ocr_model,
                    intra_threads=cfg.alpr_intra_threads,
                    max_concurrent=cfg.alpr_max_concurrent,
                )
    return _recognizer


def warmup_recognizer() -> None:
    """安全地預熱目前辨識器（若支援 warmup）。"""
    rec = get_recognizer()
    warmup = getattr(rec, "warmup", None)
    if callable(warmup):
        try:
            warmup()
        except Exception:  # noqa: BLE001
            log.warning("辨識模型預熱失敗，將於首次辨識時重試", exc_info=True)


def set_recognizer(rec: Recognizer | None) -> None:
    """測試或替換辨識引擎用。"""
    global _recognizer
    with _rec_lock:
        _recognizer = rec

"""攝影機擷取與辨識背景工作（每車道一組）。

- 擷取執行緒：持續讀影格，只保留最新一張（避免延遲累積）；斷線時指數退避自動重連。
- 辨識執行緒：依設定頻率取最新影格 → 辨識 → 台灣格式校正 → 多幀投票 → 確認後交給 on_confirm。
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .plate import ConfirmedPlate, PlateVoter, VoteParams, format_plate, normalize_ocr
from .recognizer import PlateDetection, Recognizer

log = logging.getLogger(__name__)

OnConfirm = Callable[[int, ConfirmedPlate, np.ndarray, np.ndarray | None], None]
OnStatus = Callable[[int, bool, str], None]


def parse_source(src: str) -> int | str:
    s = (src or "").strip()
    return int(s) if s.isdigit() else s


def is_file_source(src: str) -> bool:
    s = (src or "").strip()
    return bool(s) and "://" not in s and not s.isdigit() and Path(s).exists()


@dataclass
class OverlayBox:
    bbox: tuple[int, int, int, int]
    label: str
    ok: bool


@dataclass
class WorkerOptions:
    recognition_fps: float = 5.0
    vote: VoteParams = field(default_factory=VoteParams)
    strict_format: bool = True


class LaneWorker:
    def __init__(
        self,
        lane_id: int,
        name: str,
        source: str,
        recognizer_factory: Callable[[], Recognizer],
        on_confirm: OnConfirm,
        on_status: OnStatus | None = None,
        options: WorkerOptions | None = None,
    ):
        self.lane_id = lane_id
        self.name = name
        self.source = source
        self._recognizer_factory = recognizer_factory
        self._on_confirm = on_confirm
        self._on_status = on_status
        self.options = options or WorkerOptions()
        self.voter = PlateVoter(self.options.vote)

        self._stop = threading.Event()
        self._frame_lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_ts: float = 0.0
        self._frame_seq = 0
        self._overlay: list[OverlayBox] = []
        self._overlay_ts = 0.0
        self._jpeg_cache: tuple[tuple, bytes] | None = None

        self.online = False
        self.last_error = ""
        self.capture_fps = 0.0
        self.last_plate = ""
        self.last_plate_at = 0.0
        self._threads: list[threading.Thread] = []

        self._last_push_ts = 0.0
        self._push_count = 0
        self._push_t0 = time.monotonic()

    # ------------------------------------------------------------------ 推播串流
    @property
    def is_pushing(self) -> bool:
        return (time.monotonic() - self._last_push_ts) < 4.0

    def push_frame(self, frame: np.ndarray) -> None:
        with self._frame_lock:
            self._frame = frame
            self._frame_ts = time.monotonic()
            self._frame_seq += 1
        now = time.monotonic()
        self._last_push_ts = now
        if not self.online:
            self._set_status(True)
        self._push_count += 1
        el = now - self._push_t0
        if el >= 2.0:
            self.capture_fps = round(self._push_count / el, 1)
            self._push_count = 0
            self._push_t0 = now

    def push_stop(self) -> None:
        self._last_push_ts = 0.0
        if not self.source:
            self._set_status(False, "手機攝影機已離線")

    # ------------------------------------------------------------------ 控制
    def start(self) -> None:
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._capture_loop, name=f"cap-{self.lane_id}", daemon=True),
            threading.Thread(target=self._process_loop, name=f"rec-{self.lane_id}", daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout)
        self._threads = []

    def update_options(self, options: WorkerOptions) -> None:
        self.options = options
        self.voter.params = options.vote

    # ------------------------------------------------------------------ 影格
    def latest_frame(self) -> tuple[np.ndarray | None, float]:
        with self._frame_lock:
            return (None if self._frame is None else self._frame.copy()), self._frame_ts

    @property
    def frame_seq(self) -> int:
        return self._frame_seq

    def annotated_jpeg(self, max_width: int = 960, quality: int = 75) -> bytes | None:
        # 同一張影格 + 同一組框只編碼一次：多個監控視窗共用，也避免串流重送舊影格時白白重編碼
        overlay_on = time.monotonic() - self._overlay_ts < 1.0
        key = (self._frame_seq, self._overlay_ts if overlay_on else 0.0, max_width, quality)
        cached = self._jpeg_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        frame, _ = self.latest_frame()
        if frame is None:
            return None
        if overlay_on:
            for box in self._overlay:
                x1, y1, x2, y2 = box.bbox
                color = (60, 200, 60) if box.ok else (0, 165, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                cv2.putText(frame, box.label, (x1, max(y1 - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)
        h, w = frame.shape[:2]
        if w > max_width:
            frame = cv2.resize(frame, (max_width, int(h * max_width / w)))
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            return None
        jpg = buf.tobytes()
        self._jpeg_cache = (key, jpg)
        return jpg

    def _set_status(self, online: bool, error: str = "") -> None:
        changed = online != self.online
        self.online = online
        self.last_error = error
        if changed and self._on_status:
            try:
                self._on_status(self.lane_id, online, error)
            except Exception:  # noqa: BLE001
                log.exception("on_status 失敗")

    # ------------------------------------------------------------------ 擷取
    def _capture_loop(self) -> None:
        backoff = 1.0
        first_fail_reported = False
        while not self._stop.is_set():
            if self.is_pushing:
                self._stop.wait(1.0)
                continue
            if not self.source:
                if not self.online:
                    self._set_status(False, "未設定攝影機來源")
                self._stop.wait(2)
                continue
            file_mode = is_file_source(self.source)
            cap = cv2.VideoCapture(parse_source(self.source))
            if not cap.isOpened():
                cap.release()
                err = f"無法連線：{self.source}"
                if self.online or not first_fail_reported:
                    first_fail_reported = True
                    self.online = True  # 讓 _set_status 觸發 offline 通知
                self._set_status(False, err)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30)
                continue
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:  # noqa: BLE001
                pass
            native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            if native_fps <= 0 or native_fps > 120:
                native_fps = 25.0
            backoff = 1.0
            self._set_status(True)
            count, t0 = 0, time.monotonic()
            fails = 0
            while not self._stop.is_set():
                if self.is_pushing:
                    break
                ok, frame = cap.read()
                if not ok or frame is None:
                    if file_mode:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # 影片檔循環播放
                        fails += 1
                        if fails < 3:
                            continue
                    break
                fails = 0
                with self._frame_lock:
                    self._frame = frame
                    self._frame_ts = time.monotonic()
                    self._frame_seq += 1
                count += 1
                el = time.monotonic() - t0
                if el >= 2:
                    self.capture_fps = round(count / el, 1)
                    count, t0 = 0, time.monotonic()
                if file_mode:
                    time.sleep(1.0 / native_fps)
            cap.release()
            if not self._stop.is_set() and not self.is_pushing:
                self._set_status(False, "影像中斷，重新連線中")
                self._stop.wait(backoff)

    # ------------------------------------------------------------------ 辨識
    def process_frame(self, frame: np.ndarray, ts: float | None = None) -> list[tuple[PlateDetection, str | None]]:
        """對單張影格做辨識 + 投票（擷取迴圈與測試共用）。"""
        recognizer = self._recognizer_factory()
        detections = recognizer.predict(frame)
        results: list[tuple[PlateDetection, str | None]] = []
        overlay: list[OverlayBox] = []
        for det in detections:
            norm = normalize_ocr(det.text, strict=self.options.strict_format)
            plate = norm.plate if norm else None
            results.append((det, plate))
            label = f"{format_plate(plate)} {det.confidence:.2f}" if plate else f"? {det.text}"
            overlay.append(OverlayBox(det.bbox, label, plate is not None))
            if plate is None:
                continue
            x1, y1, x2, y2 = det.bbox
            confirmed = self.voter.add(plate, det.confidence, ts, payload=(frame, (x1, y1, x2, y2)))
            if confirmed is not None:
                best_frame, (bx1, by1, bx2, by2) = confirmed.best.payload
                h, w = best_frame.shape[:2]
                pad = 6
                crop = best_frame[max(by1 - pad, 0) : min(by2 + pad, h), max(bx1 - pad, 0) : min(bx2 + pad, w)].copy()
                self.last_plate = confirmed.plate
                self.last_plate_at = time.time()
                try:
                    self._on_confirm(self.lane_id, confirmed, best_frame, crop)
                except Exception:  # noqa: BLE001
                    log.exception("on_confirm 失敗")
        self._overlay = overlay
        self._overlay_ts = time.monotonic()
        return results

    def _process_loop(self) -> None:
        last_seq = -1
        while not self._stop.is_set():
            interval = 1.0 / max(self.options.recognition_fps, 0.1)
            t0 = time.monotonic()
            with self._frame_lock:
                seq = self._frame_seq
                frame = self._frame
            if frame is not None and seq != last_seq:
                last_seq = seq
                try:
                    self.process_frame(frame)
                except Exception as e:  # noqa: BLE001
                    log.exception("車道 %s 辨識失敗", self.lane_id)
                    self.last_error = f"辨識錯誤：{e}"
                    self._stop.wait(2)
            self._stop.wait(max(0.0, interval - (time.monotonic() - t0)))

    def status(self) -> dict:
        return {
            "lane_id": self.lane_id,
            "name": self.name,
            "online": self.online,
            "last_error": self.last_error,
            "capture_fps": self.capture_fps,
            "last_plate": format_plate(self.last_plate),
            "last_plate_at": self.last_plate_at or None,
            "is_push": self.is_pushing,
        }

from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace

import numpy as np

from app.auth import create_camera_token
from app.config import get_config
from app.db import SessionLocal
from app.models import Lane
from app.vision.recognizer import FastAlprRecognizer, default_intra_threads, set_recognizer, warmup_recognizer


def _install_fake_fast_alpr(monkeypatch, *, delay_sec: float = 0.0):
    """將 fast_alpr.ALPR 替換為可追蹤呼叫次數與併發數的假物件。"""
    state = {
        "init_calls": 0,
        "init_kwargs": [],
        "predict_calls": 0,
        "active": 0,
        "max_active": 0,
        "lock": threading.Lock(),
    }

    class FakeALPR:
        def __init__(self, **kwargs):
            with state["lock"]:
                state["init_calls"] += 1
                state["init_kwargs"].append(kwargs)

        def predict(self, frame):
            with state["lock"]:
                state["predict_calls"] += 1
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            try:
                if delay_sec:
                    time.sleep(delay_sec)
                return []
            finally:
                with state["lock"]:
                    state["active"] -= 1

    monkeypatch.setitem(sys.modules, "fast_alpr", SimpleNamespace(ALPR=FakeALPR))
    return state


def test_warmup_runs_once_and_sets_session_options(monkeypatch):
    state = _install_fake_fast_alpr(monkeypatch)
    rec = FastAlprRecognizer("det-m", "ocr-m", intra_threads=2, max_concurrent=1)

    threads = [threading.Thread(target=rec.warmup) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state["init_calls"] == 1
    assert state["predict_calls"] == 1  # 只執行一次 dummy 推論
    kwargs = state["init_kwargs"][0]
    assert kwargs["detector_sess_options"].intra_op_num_threads == 2
    assert kwargs["detector_sess_options"].inter_op_num_threads == 1
    assert kwargs["ocr_sess_options"].intra_op_num_threads == 2
    assert kwargs["ocr_sess_options"].inter_op_num_threads == 1

    # 再次呼叫 warmup 不應重跑
    rec.warmup()
    assert state["predict_calls"] == 1


def test_predict_respects_max_concurrent(monkeypatch):
    state = _install_fake_fast_alpr(monkeypatch, delay_sec=0.05)
    rec = FastAlprRecognizer("det-m", "ocr-m", intra_threads=1, max_concurrent=2)
    rec.warmup()

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    threads = [threading.Thread(target=rec.predict, args=(frame,)) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state["max_active"] <= 2
    assert state["predict_calls"] == 7  # 1 次 warmup + 6 次 predict


def test_predict_unlimited_when_max_concurrent_zero(monkeypatch):
    state = _install_fake_fast_alpr(monkeypatch)
    rec = FastAlprRecognizer("det-m", "ocr-m", intra_threads=0, max_concurrent=0)
    rec.warmup()
    assert rec._sem is None
    assert state["init_kwargs"][0]["detector_sess_options"].intra_op_num_threads == default_intra_threads()


def test_warmup_failure_allows_retry(monkeypatch):
    calls = {"n": 0}

    class FlakyALPR:
        def __init__(self, **kwargs):
            pass

        def predict(self, frame):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient error")
            return []

    monkeypatch.setitem(sys.modules, "fast_alpr", SimpleNamespace(ALPR=FlakyALPR))
    rec = FastAlprRecognizer("det-m", "ocr-m")
    try:
        rec.warmup()
    except RuntimeError:
        pass
    assert rec._warmed_up is False

    rec.warmup()
    assert rec._warmed_up is True
    assert calls["n"] == 2


def test_get_recognizer_passes_config(monkeypatch):
    monkeypatch.setenv("GATE_ALPR_INTRA_THREADS", "3")
    monkeypatch.setenv("GATE_ALPR_MAX_CONCURRENT", "4")
    get_config.cache_clear()
    set_recognizer(None)
    try:
        from app.vision.recognizer import get_recognizer

        rec = get_recognizer()
        assert isinstance(rec, FastAlprRecognizer)
        assert rec._intra_threads == 3
        assert rec._max_concurrent == 4
    finally:
        set_recognizer(None)
        get_config.cache_clear()


def test_default_intra_threads_bounded():
    n = default_intra_threads()
    assert 1 <= n <= 4


def test_warmup_recognizer_swallows_errors():
    class BrokenRec:
        def warmup(self):
            raise RuntimeError("model download failed")

        def predict(self, frame):
            return []

    set_recognizer(BrokenRec())
    try:
        warmup_recognizer()  # 不應拋出例外
    finally:
        set_recognizer(None)


def test_mobile_push_ws_triggers_warmup(auth_client, monkeypatch):
    client, _tmp = auth_client

    warmed = threading.Event()

    class DummyRec:
        def warmup(self):
            warmed.set()

        def predict(self, frame):
            return []

    set_recognizer(DummyRec())

    from app.api import system as sys_api

    class FakeWorker:
        def push_frame(self, frame):
            pass

        def push_stop(self):
            pass

    class FakeManager:
        def get(self, lid):
            return FakeWorker()

    monkeypatch.setenv("GATE_ENABLE_WORKERS", "true")
    get_config.cache_clear()
    monkeypatch.setattr(sys_api, "_manager", lambda: FakeManager())

    db = SessionLocal()
    try:
        lane_id = db.query(Lane).first().id
    finally:
        db.close()

    token = create_camera_token(lane_id, get_config().get_secret_key())
    with client.websocket_connect(f"/ws/lanes/{lane_id}/push?token={token}"):
        assert warmed.wait(timeout=2.0)

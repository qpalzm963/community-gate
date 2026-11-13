"""待處理事件（未登記車輛）的處理正確性：搶單、逾時結案、寫入失敗清截圖。"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta

import numpy as np
import pytest

from app.access import service
from app.db import SessionLocal
from app.models import AccessEvent, Alert, EventDecision, VehicleSession
from app.services.scheduler import close_stale_pending
from app.services.snapshots import resolve


@pytest.fixture
def gate_calls(monkeypatch):
    """記錄實際送出的開閘指令，取代真的去動柵欄。"""
    calls: list[int | None] = []

    def fake_open_gate(lane, reason, event_id):
        calls.append(event_id)
        return True, "ok"

    monkeypatch.setattr(service, "_open_gate", fake_open_gate)
    return calls


def _in_lane_id(client) -> int:
    return next(l for l in client.get("/api/lanes").json() if l["direction"] == "IN")["id"]


def _pending_event(client, plate: str = "NEW-9999") -> int:
    r = client.post(f"/api/lanes/{_in_lane_id(client)}/simulate", json={"plate": plate})
    assert r.status_code == 200 and r.json()["decision"] == "PENDING"
    return r.json()["id"]


def _session_count(plate: str) -> int:
    db = SessionLocal()
    try:
        return db.query(VehicleSession).filter(VehicleSession.plate == plate).count()
    finally:
        db.close()


def test_double_allow_opens_gate_once(auth_client, gate_calls):
    """兩位警衛先後對同一事件按放行：柵欄只能動一次、在場紀錄只能一筆。

    重複開閘代表柵欄異常動作（可能讓後車跟車進入），且 VehicleSession 會多一筆幽靈在場紀錄。
    """
    client, _ = auth_client
    eid = _pending_event(client)

    r1 = client.post(f"/api/events/{eid}/decision", json={"action": "allow"})
    assert r1.status_code == 200 and r1.json()["decision"] == "MANUAL_ALLOW"

    r2 = client.post(f"/api/events/{eid}/decision", json={"action": "allow"})
    assert r2.status_code == 400
    assert "已處理" in r2.json()["detail"]

    assert gate_calls == [eid]
    assert _session_count("NEW9999") == 1


def test_concurrent_allow_only_one_wins(auth_client, gate_calls):
    """兩個請求真的同時進來（都已讀到 PENDING）時，也只能有一個搶到。"""
    client, _ = auth_client
    eid = _pending_event(client, "RACE-001")

    barrier = threading.Barrier(2)
    results: list[str] = []

    def guard(op_note: str):
        barrier.wait()
        try:
            service.manual_decision(eid, "allow", None, note=op_note)
            results.append("ok")
        except service.AccessError:
            results.append("handled")

    threads = [threading.Thread(target=guard, args=(f"警衛{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["handled", "ok"]
    assert gate_calls == [eid]
    assert _session_count("RACE001") == 1


def _set_occurred_at(eid: int, at: datetime) -> None:
    db = SessionLocal()
    try:
        db.get(AccessEvent, eid).occurred_at = at
        db.commit()
    finally:
        db.close()


def test_stale_pending_closed_by_timeout(auth_client, gate_calls):
    """沒人處理的待處理事件（例如車子已倒車離開）逾時後要自動結案，不能永遠卡在警衛清單上；
    未逾時的不能被誤關，否則警衛還在看的車會突然消失。"""
    client, _ = auth_client
    assert client.put("/api/settings", json={"pending_timeout_min": 10}).status_code == 200

    now = datetime(2026, 11, 13, 18, 0, 0)
    stale = _pending_event(client, "OLD-0001")
    db = SessionLocal()
    try:
        original_note = db.get(AccessEvent, stale).note
    finally:
        db.close()
    assert original_note
    fresh = _pending_event(client, "NEW-0002")
    _set_occurred_at(stale, now - timedelta(minutes=11))
    _set_occurred_at(fresh, now - timedelta(minutes=9))

    assert close_stale_pending(at=now) == [stale]

    db = SessionLocal()
    try:
        ev = db.get(AccessEvent, stale)
        assert ev.decision == EventDecision.DENY.value
        assert ev.decided_at == now
        assert "逾時" in ev.note
        # 原本的判斷原因要保留，事後查紀錄才知道這台車當初為何待處理
        assert ev.note.startswith(original_note)
        # 對應的未登記車輛警示一併結案，不再算未讀
        assert all(a.acknowledged for a in db.query(Alert).filter(Alert.event_id == stale))
        assert db.get(AccessEvent, fresh).decision == EventDecision.PENDING.value
    finally:
        db.close()

    pending_ids = [e["id"] for e in client.get("/api/events/pending").json()]
    assert stale not in pending_ids and fresh in pending_ids
    # 逾時結案是拒絕，不可開閘
    assert gate_calls == []

    # 已結案的事件警衛再按放行要被擋下
    assert client.post(f"/api/events/{stale}/decision", json={"action": "allow"}).status_code == 400


def test_pending_timeout_zero_disables(auth_client):
    client, _ = auth_client
    assert client.put("/api/settings", json={"pending_timeout_min": 0}).status_code == 200
    eid = _pending_event(client, "KEEP-001")
    _set_occurred_at(eid, datetime(2000, 1, 1))
    assert close_stale_pending() == []


def test_failed_commit_removes_snapshots(auth_client, monkeypatch):
    """事件寫入資料庫失敗時，剛存下的截圖要刪掉，否則會累積沒有任何紀錄指向的孤兒檔。"""
    client, tmp_path = auth_client
    lane_id = _in_lane_id(client)
    saved: list[str] = []
    real_save = service.save_jpeg

    def spy_save(*args, **kwargs):
        rel = real_save(*args, **kwargs)
        saved.append(rel)
        return rel

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(service, "save_jpeg", spy_save)
    monkeypatch.setattr("sqlalchemy.orm.Session.commit", boom)

    img = np.zeros((40, 60, 3), dtype=np.uint8)
    with pytest.raises(RuntimeError):
        service.handle_detection("ORP1234", 0.9, lane_id, frame=img, crop=img)

    monkeypatch.undo()
    assert len(saved) == 2 and all(saved)
    assert all(resolve(rel) is None for rel in saved)


def test_error_after_commit_keeps_snapshots(auth_client, monkeypatch):
    """事件已寫進資料庫後才出錯（例如讀回事件失敗），紀錄仍指向這些截圖，不能被當成孤兒檔刪掉。"""
    client, _ = auth_client
    lane_id = _in_lane_id(client)
    saved: list[str] = []
    real_save = service.save_jpeg

    def spy_save(*args, **kwargs):
        rel = real_save(*args, **kwargs)
        saved.append(rel)
        return rel

    def boom(*args, **kwargs):
        raise RuntimeError("serialize failed")

    monkeypatch.setattr(service, "save_jpeg", spy_save)
    monkeypatch.setattr(service, "event_dict", boom)

    img = np.zeros((40, 60, 3), dtype=np.uint8)
    with pytest.raises(RuntimeError):
        service.handle_detection("KEP1234", 0.9, lane_id, frame=img, crop=img)

    monkeypatch.undo()
    assert len(saved) == 2 and all(saved)
    assert all(resolve(rel) is not None for rel in saved)
    db = SessionLocal()
    try:
        ev = db.query(AccessEvent).filter(AccessEvent.plate == "KEP1234").one()
        assert ev.snapshot_path == saved[0]
    finally:
        db.close()

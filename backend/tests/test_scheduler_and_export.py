from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np

from app.db import SessionLocal
from app.models import Alert, AlertType, Household, Visitor, VisitorStatus
from app.services.scheduler import check_overstay, cleanup_snapshots
from app.services.snapshots import resolve, save_jpeg


def test_overstay_and_snapshot_retention(auth_client):
    client, _ = auth_client

    # 修改保留天數為 30 天（即時生效）
    res = client.put("/api/settings", json={"snapshot_retention_days": 30, "overstay_grace_min": 10})
    assert res.status_code == 200
    assert res.json()["values"]["snapshot_retention_days"] == 30

    # 建立一筆已逾時的在場訪客
    now = datetime(2026, 11, 13, 18, 0, 0)
    db = SessionLocal()
    try:
        hh = Household(unit_no="C棟1F")
        db.add(hh)
        db.flush()
        v = Visitor(
            household_id=hh.id,
            name="逾時先生",
            plate="OVR1234",
            authorized_from=now - timedelta(hours=3),
            authorized_until=now - timedelta(minutes=20),
            status=VisitorStatus.ENTERED.value,
            entered_at=now - timedelta(hours=2),
        )
        db.add(v)
        db.commit()
        vid = v.id
    finally:
        db.close()

    flagged = check_overstay(at=now)
    assert flagged == [vid]

    db = SessionLocal()
    try:
        v = db.get(Visitor, vid)
        assert v.status == VisitorStatus.OVERSTAY.value
        assert db.query(Alert).filter(Alert.visitor_id == vid, Alert.type == AlertType.OVERSTAY.value).count() == 1
    finally:
        db.close()

    # 測試截圖清理：40 天前的會被刪，5 天前的保留
    img = np.zeros((40, 60, 3), dtype=np.uint8)
    old_rel = save_jpeg(img, "old", at=datetime(2026, 10, 1, 12, 0, 0))
    new_rel = save_jpeg(img, "new", at=datetime(2026, 11, 8, 12, 0, 0))
    assert resolve(old_rel) is not None and resolve(new_rel) is not None

    removed = cleanup_snapshots(today=date(2026, 11, 13))
    assert removed == 1
    assert resolve(old_rel) is None
    assert resolve(new_rel) is not None

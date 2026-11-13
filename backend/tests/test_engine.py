from __future__ import annotations

from datetime import date, datetime, timedelta

from app.access.engine import decide
from app.access.service import handle_detection, manual_decision
from app.db import SessionLocal
from app.models import (
    BlacklistEntry,
    EventCategory,
    EventDecision,
    Household,
    Lane,
    LaneDirection,
    ResidentVehicle,
    VehicleSession,
    Visitor,
    VisitorStatus,
)


def test_decision_priority_and_sessions(app_env):
    _client, _tmp = app_env
    now_dt = datetime(2026, 11, 13, 14, 0, 0)

    db = SessionLocal()
    try:
        in_lane = db.query(Lane).filter(Lane.direction == LaneDirection.IN.value).first()
        out_lane = db.query(Lane).filter(Lane.direction == LaneDirection.OUT.value).first()
        assert in_lane and out_lane

        hh = Household(unit_no="A棟5F-2", owner_name="王小明")
        db.add(hh)
        db.flush()

        # 住戶機車（有效）
        db.add(
            ResidentVehicle(
                household_id=hh.id,
                plate="MKR567",
                vehicle_type="MOTO",
                valid_from=date(2026, 1, 1),
                valid_until=date(2026, 12, 31),
                is_active=True,
            )
        )
        # 住戶汽車（已過期）
        db.add(
            ResidentVehicle(
                household_id=hh.id,
                plate="EXP1111",
                vehicle_type="CAR",
                valid_until=date(2026, 11, 12),
                is_active=True,
            )
        )
        # 同時在白名單與黑名單 → 黑名單優先
        db.add(
            ResidentVehicle(household_id=hh.id, plate="BLK9999", vehicle_type="CAR", is_active=True)
        )
        db.add(BlacklistEntry(plate="BLK9999", vehicle_type="CAR", reason="欠費停權", is_active=True))

        # 有效訪客
        vis = Visitor(
            household_id=hh.id,
            name="李訪客",
            plate="VIS2222",
            vehicle_type="CAR",
            authorized_from=now_dt - timedelta(hours=1),
            authorized_until=now_dt + timedelta(hours=2),
            status=VisitorStatus.RESERVED.value,
        )
        db.add(vis)
        db.commit()
        in_id, out_id, vis_id = in_lane.id, out_lane.id, vis.id

        # 純判斷驗證
        d_blk = decide(db, "BLK9999", in_lane, now_dt)
        assert d_blk.category == EventCategory.BLACKLIST and d_blk.decision == EventDecision.DENY

        d_exp = decide(db, "EXP1111", in_lane, now_dt)
        assert d_exp.category == EventCategory.UNKNOWN and d_exp.decision == EventDecision.PENDING

        d_res = decide(db, "MKR567", in_lane, now_dt)
        assert d_res.category == EventCategory.RESIDENT and d_res.vehicle_type == "MOTO"
    finally:
        db.close()

    # 訪客進場 → 狀態變 ENTERED 且建立在場 session
    ev_in = handle_detection("VIS2222", 0.95, in_id, at=now_dt)
    assert ev_in["category"] == "VISITOR" and ev_in["decision"] == "AUTO_ALLOW"

    db = SessionLocal()
    try:
        v = db.get(Visitor, vis_id)
        assert v.status == VisitorStatus.ENTERED.value
        assert db.query(VehicleSession).filter(VehicleSession.plate == "VIS2222", VehicleSession.exited_at.is_(None)).count() == 1
    finally:
        db.close()

    # 訪客即使逾時後離場仍要放行並結束 session
    ev_out = handle_detection("VIS2222", 0.95, out_id, at=now_dt + timedelta(hours=5))
    assert ev_out["decision"] == "AUTO_ALLOW"

    db = SessionLocal()
    try:
        v = db.get(Visitor, vis_id)
        assert v.status == VisitorStatus.EXITED.value
        assert db.query(VehicleSession).filter(VehicleSession.plate == "VIS2222", VehicleSession.exited_at.is_(None)).count() == 0
    finally:
        db.close()

    # 未登記車輛 → PENDING → 警衛人工放行
    ev_unk = handle_detection("UNK7777", 0.88, in_id, at=now_dt)
    assert ev_unk["decision"] == "PENDING"
    updated = manual_decision(ev_unk["id"], "allow", operator_id=1, note="快遞臨停")
    assert updated["decision"] == "MANUAL_ALLOW"

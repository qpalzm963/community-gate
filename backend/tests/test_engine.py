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


def test_fuzzy_whitelist_unique_match_for_resident_and_visitor(app_env):
    _client, _tmp = app_env
    now_dt = datetime(2026, 11, 25, 10, 0, 0)

    db = SessionLocal()
    try:
        in_lane = db.query(Lane).filter(Lane.direction == LaneDirection.IN.value).first()
        hh = Household(unit_no="B棟3F", owner_name="陳大文")
        db.add(hh)
        db.flush()
        db.add(ResidentVehicle(household_id=hh.id, plate="ABC1234", vehicle_type="CAR", is_active=True))
        # 已過期住戶不可參與近似匹配
        db.add(
            ResidentVehicle(
                household_id=hh.id,
                plate="EXP8888",
                vehicle_type="CAR",
                valid_until=date(2026, 11, 1),
                is_active=True,
            )
        )
        vis = Visitor(
            household_id=hh.id,
            name="林訪客",
            plate="VIS2222",
            vehicle_type="CAR",
            authorized_from=now_dt - timedelta(hours=1),
            authorized_until=now_dt + timedelta(hours=2),
            status=VisitorStatus.RESERVED.value,
        )
        db.add(vis)
        db.commit()
        in_id, vis_id = in_lane.id, vis.id
    finally:
        db.close()

    # 住戶 ABC1234 被誤讀為 ARC1234 → 唯一命中並自動修正放行
    ev_res = handle_detection("ARC1234", 0.91, in_id, at=now_dt)
    assert ev_res["plate"] == "ABC1234"
    assert ev_res["category"] == "RESIDENT"
    assert ev_res["decision"] == "AUTO_ALLOW"
    assert "ARC-1234" in ev_res["note"]

    # 訪客 VIS2222 被誤讀為 V1S2222（I/1 高混淆）→ 唯一命中並自動修正放行且更新訪客狀態
    ev_vis = handle_detection("V1S2222", 0.89, in_id, at=now_dt)
    assert ev_vis["plate"] == "VIS2222"
    assert ev_vis["category"] == "VISITOR"
    assert ev_vis["decision"] == "AUTO_ALLOW"
    assert "V1S2222" in ev_vis["note"]

    db = SessionLocal()
    try:
        assert db.get(Visitor, vis_id).status == VisitorStatus.ENTERED.value
        assert db.query(VehicleSession).filter(VehicleSession.plate == "ABC1234", VehicleSession.exited_at.is_(None)).count() == 1
        # 過期住戶不應被近似救回（EXP8888 vs EXP8B88 雖為 8/B 高混淆仍不得放行）
        in_lane = db.get(Lane, in_id)
        d_exp = decide(db, "EXP8B88", in_lane, now_dt)
        assert d_exp.decision == EventDecision.PENDING

        # 非高混淆字元（如連號 ABC1235 vs ABC1234）不可誤放行
        d_non_conf = decide(db, "ABC1235", in_lane, now_dt)
        assert d_non_conf.decision == EventDecision.PENDING
    finally:
        db.close()


def test_fuzzy_whitelist_skips_ambiguous_or_blacklist_near_match(app_env):
    _client, _tmp = app_env
    now_dt = datetime(2026, 11, 25, 10, 0, 0)

    db = SessionLocal()
    try:
        in_lane = db.query(Lane).filter(Lane.direction == LaneDirection.IN.value).first()
        hh = Household(unit_no="C棟1F")
        db.add(hh)
        db.flush()
        # 兩筆高混淆近似住戶：ABC1234 與 APC1234，與 ARC1234 皆差 1 個高混淆字元（R↔B、R↔P）
        db.add(ResidentVehicle(household_id=hh.id, plate="ABC1234", vehicle_type="CAR", is_active=True))
        db.add(ResidentVehicle(household_id=hh.id, plate="APC1234", vehicle_type="CAR", is_active=True))
        # 黑名單近似衝突：住戶為 BLK9990，黑名單為 BLK9999；辨識為 BLK9998 時同時近似黑名單
        db.add(ResidentVehicle(household_id=hh.id, plate="BLK9990", vehicle_type="CAR", is_active=True))
        db.add(BlacklistEntry(plate="BLK9999", vehicle_type="CAR", reason="違規", is_active=True))
        db.commit()

        d_ambig = decide(db, "ARC1234", in_lane, now_dt)
        assert d_ambig.category == EventCategory.UNKNOWN
        assert d_ambig.decision == EventDecision.PENDING

        d_bl_near = decide(db, "BLK9998", in_lane, now_dt)
        assert d_bl_near.category == EventCategory.UNKNOWN
        assert d_bl_near.decision == EventDecision.PENDING

        d_bl_exact = decide(db, "BLK9999", in_lane, now_dt)
        assert d_bl_exact.category == EventCategory.BLACKLIST
        assert d_bl_exact.decision == EventDecision.DENY
    finally:
        db.close()

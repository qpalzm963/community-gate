from __future__ import annotations

import io
from datetime import datetime, timedelta

from openpyxl import load_workbook


def test_auth_protection(app_env):
    client, _ = app_env
    assert client.get("/api/households").status_code == 401
    assert client.get("/api/public/info").status_code == 200
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "password123"}).status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "admin"


def test_env_admin_autoseed(tmp_path, monkeypatch):
    from app.config import get_config
    from app.db import SessionLocal, init_engine
    from app.migrate import upgrade_db
    from app.models import User

    (tmp_path / "envseed").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GATE_DATA_DIR", str(tmp_path / "envseed"))
    monkeypatch.setenv("GATE_ADMIN_USERNAME", "guard01")
    monkeypatch.setenv("GATE_ADMIN_PASSWORD", "secret123")
    get_config.cache_clear()
    init_engine(f"sqlite:///{tmp_path / 'envseed' / 'app.db'}")
    upgrade_db()
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == "guard01").first()
        assert u is not None
    finally:
        db.close()
    get_config.cache_clear()


def test_crud_simulate_and_export(auth_client):
    client, _ = auth_client

    # 建立住戶與車輛（含機車）
    h = client.post("/api/households", json={"unit_no": "B棟3F", "owner_name": "陳大華", "phone": "0912345678"}).json()
    v1 = client.post(
        "/api/vehicles",
        json={"household_id": h["id"], "plate": "abc-1234", "vehicle_type": "CAR"},
    )
    assert v1.status_code == 200 and v1.json()["plate"] == "ABC1234"

    v2 = client.post(
        "/api/vehicles",
        json={"household_id": h["id"], "plate": "123-xyz", "vehicle_type": "MOTO"},
    )
    assert v2.status_code == 200 and v2.json()["vehicle_type"] == "MOTO"

    # 重複車牌禁止
    dup = client.post("/api/vehicles", json={"household_id": h["id"], "plate": "ABC1234", "vehicle_type": "CAR"})
    assert dup.status_code == 409

    # 訪客登記
    now = datetime.now()
    vis = client.post(
        "/api/visitors",
        json={
            "household_id": h["id"],
            "name": "張訪客",
            "plate": "VIS-888",
            "vehicle_type": "MOTO",
            "purpose": "拜訪",
            "authorized_from": (now - timedelta(minutes=10)).isoformat(),
            "authorized_until": (now + timedelta(hours=2)).isoformat(),
            "source": "WALK_IN",
        },
    )
    assert vis.status_code == 200

    # 黑名單
    bl = client.post("/api/blacklist", json={"plate": "BAD-0001", "reason": "違規"})
    assert bl.status_code == 200

    # 模擬辨識（使用預設入口車道）
    lanes = client.get("/api/lanes").json()
    in_lane = next(l for l in lanes if l["direction"] == "IN")

    r1 = client.post(f"/api/lanes/{in_lane['id']}/simulate", json={"plate": "ABC-1234"})
    assert r1.status_code == 200 and r1.json()["decision"] == "AUTO_ALLOW"

    r2 = client.post(f"/api/lanes/{in_lane['id']}/simulate", json={"plate": "BAD-0001"})
    assert r2.status_code == 200 and r2.json()["decision"] == "DENY"

    r3 = client.post(f"/api/lanes/{in_lane['id']}/simulate", json={"plate": "NEW-9999"})
    assert r3.status_code == 200 and r3.json()["decision"] == "PENDING"

    # 儀表板與在場車輛
    dash = client.get("/api/dashboard").json()
    assert dash["today_in"] >= 1
    assert dash["today_denied"] >= 1
    assert dash["pending"] >= 1
    assert dash["unack_alerts"] >= 2

    pres = client.get("/api/presence").json()
    assert any(p["plate"] == "ABC1234" for p in pres)

    # 匯出 CSV 與 XLSX
    csv_res = client.get("/api/events/export?format=csv")
    assert csv_res.status_code == 200
    csv_text = csv_res.content.decode("utf-8-sig")
    assert "ABC-1234" in csv_text and "BAD-0001" in csv_text

    xlsx_res = client.get("/api/events/export?format=xlsx")
    assert xlsx_res.status_code == 200
    wb = load_workbook(io.BytesIO(xlsx_res.content))
    ws = wb.active
    assert ws.max_row >= 4
    assert ws.cell(1, 4).value == "車牌"

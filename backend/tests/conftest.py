from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import create_user
from app.config import get_config
from app.db import SessionLocal, init_engine
from app.main import create_app
from app.services.events import bus
from app.services.settings import settings_store
from app.vision.recognizer import set_recognizer


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GATE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GATE_ENABLE_WORKERS", "false")
    monkeypatch.setenv("GATE_SECRET_KEY", "test-secret-key-for-pytest")
    get_config.cache_clear()
    settings_store.invalidate()
    bus.history.clear()
    set_recognizer(None)

    init_engine(f"sqlite:///{tmp_path / 'data' / 'app.db'}")
    app = create_app(start_background=False)

    db = SessionLocal()
    try:
        create_user(db, "admin", "password123", "管理員")
    finally:
        db.close()

    with TestClient(app) as client:
        yield client, tmp_path

    set_recognizer(None)
    get_config.cache_clear()
    settings_store.invalidate()


@pytest.fixture
def auth_client(app_env):
    client, tmp_path = app_env
    res = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    assert res.status_code == 200
    return client, tmp_path

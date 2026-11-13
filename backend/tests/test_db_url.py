from __future__ import annotations

import ssl

from app.config import get_config
from app.db import normalize_db_url


def test_normalize_mysql_url_with_sslaccept():
    sa_url, kwargs = normalize_db_url(
        "mysql://app_204ad2fdb7f4:secret123@10.3.176.3:3306/aiborn_carstop?sslaccept=accept_invalid_certs"
    )
    assert sa_url == "mysql+pymysql://app_204ad2fdb7f4:secret123@10.3.176.3:3306/aiborn_carstop"
    assert isinstance(kwargs.get("ssl"), ssl.SSLContext)
    assert kwargs["ssl"].verify_mode == ssl.CERT_NONE


def test_snapshot_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GATE_SNAPSHOT_DIR", str(tmp_path / "gcs_snaps"))
    get_config.cache_clear()
    cfg = get_config()
    assert cfg.snapshot_dir == tmp_path / "gcs_snaps"
    get_config.cache_clear()

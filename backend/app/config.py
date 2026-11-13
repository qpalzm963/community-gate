"""應用程式設定（啟動參數）。執行期可調的參數存在資料庫 settings 表（見 services/settings.py）。"""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATE_", env_file=PROJECT_ROOT / ".env", extra="ignore")

    data_dir: Path = PROJECT_ROOT / "data"
    host: str = "127.0.0.1"
    port: int = 8000
    # 用於簽署 session cookie；未設定時自動產生並存在 data/secret.key
    secret_key: str | None = None
    session_max_age_sec: int = 12 * 3600
    # 是否啟動攝影機 workers（測試時關閉）
    enable_workers: bool = True
    # 辨識模型
    alpr_detector_model: str = "yolo-v9-t-384-license-plate-end2end"
    alpr_ocr_model: str = "cct-xs-v2-global-model"
    # 容器／首次部署可用環境變數自動建立預設管理員
    admin_username: str | None = None
    admin_password: str | None = None
    admin_display_name: str = "管理員"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def snapshot_dir(self) -> Path:
        return self.data_dir / "snapshots"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def get_secret_key(self) -> str:
        if self.secret_key:
            return self.secret_key
        self.ensure_dirs()
        key_file = self.data_dir / "secret.key"
        if not key_file.exists():
            key_file.write_text(secrets.token_urlsafe(48))
            key_file.chmod(0o600)
        self.secret_key = key_file.read_text().strip()
        return self.secret_key


@lru_cache
def get_config() -> AppConfig:
    return AppConfig()

"""設定管理。"""

import json
import logging
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".cal-notion"
CONFIG_FILE = CONFIG_DIR / "config.json"

# 每個 Provider 的必填欄位
PROVIDER_REQUIRED_FIELDS: dict[str, list[str]] = {
    "apple": ["apple_id", "apple_app_password"],
    "google": ["google_credentials_file"],
}

# 所有 Provider 都需要的欄位
COMMON_REQUIRED_FIELDS = ["notion_token", "notion_database_id"]

DEFAULT_CONFIG = {
    "provider": "apple",
    "apple_id": "",
    "apple_app_password": "",
    "google_credentials_file": "",
    "notion_token": "",
    "notion_database_id": "",
    "sync_days_back": 7,
    "sync_days_forward": 30,
    "sync_direction": "calendar_to_notion",  # calendar_to_notion / notion_to_calendar / bidirectional
    "conflict_strategy": "newest_wins",  # newest_wins / calendar_wins / notion_wins
    "daemon_interval_minutes": 15,
    "timezone": "Asia/Taipei",
}

# 敏感欄位，顯示時遮蔽
SENSITIVE_FIELDS = {"apple_app_password", "notion_token", "google_credentials_file"}


class Config:
    """管理 cal-notion 設定，支援 config.json 和 .env 兩種方式。"""

    def __init__(self):
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        # 優先讀取 config.json
        if CONFIG_FILE.exists():
            try:
                self._data = {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text())}
                return
            except (json.JSONDecodeError, OSError):
                pass

        # 否則從 .env 讀取（向後相容）
        load_dotenv()
        import os

        self._data = {
            "provider": os.getenv("PROVIDER", "apple"),
            "apple_id": os.getenv("APPLE_ID", ""),
            "apple_app_password": os.getenv("APPLE_APP_PASSWORD", ""),
            "google_credentials_file": os.getenv("GOOGLE_CREDENTIALS_FILE", ""),
            "notion_token": os.getenv("NOTION_TOKEN", ""),
            "notion_database_id": os.getenv("NOTION_DATABASE_ID", ""),
            "sync_days_back": int(os.getenv("SYNC_DAYS_BACK", 7)),
            "sync_days_forward": int(os.getenv("SYNC_DAYS_FORWARD", 30)),
            "sync_direction": os.getenv("SYNC_DIRECTION", "calendar_to_notion"),
            "conflict_strategy": os.getenv("CONFLICT_STRATEGY", "newest_wins"),
            "daemon_interval_minutes": int(os.getenv("DAEMON_INTERVAL_MINUTES", 15)),
            "timezone": os.getenv("TIMEZONE", "Asia/Taipei"),
        }

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))
        log.info(f"設定已儲存至 {CONFIG_FILE}")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value

    def is_configured(self) -> bool:
        """根據當前 provider 檢查必填欄位是否都已填。"""
        provider = self._data.get("provider", "apple")
        required = COMMON_REQUIRED_FIELDS + PROVIDER_REQUIRED_FIELDS.get(provider, [])
        return all(self._data.get(k) for k in required)

    def get_provider_config(self) -> dict:
        """取得當前 provider 需要的設定，讓呼叫端不需要知道 provider 特定參數。"""
        provider = self._data.get("provider", "apple")
        if provider == "apple":
            return {"username": self._data["apple_id"], "password": self._data["apple_app_password"]}
        elif provider == "google":
            return {"credentials_file": self._data["google_credentials_file"]}
        return {}

    def to_dict(self) -> dict:
        safe = {**self._data}
        for field in SENSITIVE_FIELDS:
            val = safe.get(field, "")
            if val:
                safe[field] = val[:6] + "****" if len(val) > 6 else "****"
        return safe

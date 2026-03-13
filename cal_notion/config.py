"""設定管理。"""

import json
import logging
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".cal-notion"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "provider": "apple",
    "apple_id": "",
    "apple_app_password": "",
    "notion_token": "",
    "notion_database_id": "",
    "sync_days_back": 7,
    "sync_days_forward": 30,
    "timezone": "Asia/Taipei",
}


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
            "notion_token": os.getenv("NOTION_TOKEN", ""),
            "notion_database_id": os.getenv("NOTION_DATABASE_ID", ""),
            "sync_days_back": int(os.getenv("SYNC_DAYS_BACK", 7)),
            "sync_days_forward": int(os.getenv("SYNC_DAYS_FORWARD", 30)),
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
        required = ["apple_id", "apple_app_password", "notion_token", "notion_database_id"]
        return all(self._data.get(k) for k in required)

    def to_dict(self) -> dict:
        safe = {**self._data}
        # 隱藏敏感資訊
        if safe.get("apple_app_password"):
            safe["apple_app_password"] = "****"
        if safe.get("notion_token"):
            safe["notion_token"] = safe["notion_token"][:10] + "****"
        return safe

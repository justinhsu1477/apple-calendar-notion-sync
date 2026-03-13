"""增量同步狀態追蹤（v2 — 支援雙向同步）。

記錄每個事件在 Calendar 和 Notion 兩側的 content_hash，
作為 three-way merge 的 baseline，讓下次同步時能精確判斷哪邊改了。
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_STATE_FILE = Path.home() / ".cal-notion" / "sync_state.json"


class SyncState:
    """管理雙向同步狀態的持久化存儲。"""

    def __init__(self, state_file: Path | None = None):
        self._file = state_file or DEFAULT_STATE_FILE
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text())
                if data.get("version", 1) < 2:
                    return self._migrate_v1_to_v2(data)
                return data
            except (json.JSONDecodeError, OSError) as e:
                log.warning(f"讀取同步狀態失敗，將重新建立: {e}")
        return self._empty_state()

    @staticmethod
    def _empty_state() -> dict:
        return {"version": 2, "last_sync": None, "records": {}}

    @staticmethod
    def _migrate_v1_to_v2(old: dict) -> dict:
        """從 v1 格式遷移到 v2。"""
        log.info("遷移同步狀態 v1 → v2")
        records = {}
        for uid, info in old.get("synced_uids", {}).items():
            records[uid] = {
                "calendar_hash": None,
                "notion_hash": None,
                "notion_page_id": None,
                "calendar_name": "",
                "source": "calendar",
                "last_modified": info.get("last_modified"),
                "synced_at": info.get("synced_at"),
            }
        return {
            "version": 2,
            "last_sync": old.get("last_sync"),
            "records": records,
        }

    def save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    @property
    def last_sync(self) -> datetime | None:
        ts = self._data.get("last_sync")
        if ts:
            return datetime.fromisoformat(ts)
        return None

    # ── Record 操作 ───────────────────────────────────

    def get_record(self, uid: str) -> dict | None:
        """取得某 UID 的同步紀錄。"""
        return self._data["records"].get(uid)

    def set_record(
        self,
        uid: str,
        calendar_hash: str | None = None,
        notion_hash: str | None = None,
        notion_page_id: str | None = None,
        calendar_name: str = "",
        source: str = "calendar",
        last_modified: str | None = None,
    ) -> None:
        """建立或更新一筆同步紀錄。"""
        self._data["records"][uid] = {
            "calendar_hash": calendar_hash,
            "notion_hash": notion_hash,
            "notion_page_id": notion_page_id,
            "calendar_name": calendar_name,
            "source": source,
            "last_modified": last_modified,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

    def remove_record(self, uid: str) -> None:
        self._data["records"].pop(uid, None)

    def get_all_records(self) -> dict[str, dict]:
        return self._data["records"]

    def get_tracked_uids(self) -> set[str]:
        return set(self._data["records"].keys())

    # ── 向後相容方法（供單向同步使用）────────────────────

    def is_modified(self, uid: str, last_modified: str | None) -> bool:
        record = self._data["records"].get(uid)
        if record is None:
            return True
        if last_modified and record.get("last_modified") != last_modified:
            return True
        return False

    def mark_synced(self, uid: str, last_modified: str | None = None) -> None:
        existing = self._data["records"].get(uid, {})
        existing["last_modified"] = last_modified
        existing["synced_at"] = datetime.now(timezone.utc).isoformat()
        self._data["records"][uid] = existing

    def get_synced_uids(self) -> set[str]:
        return self.get_tracked_uids()

    def remove_uid(self, uid: str) -> None:
        self.remove_record(uid)

    # ── 通用方法 ──────────────────────────────────────

    def update_last_sync(self) -> None:
        self._data["last_sync"] = datetime.now(timezone.utc).isoformat()

    def reset(self) -> None:
        self._data = self._empty_state()
        self.save()

"""增量同步狀態追蹤。

記錄上次同步時間與已同步事件的 UID，
讓下次同步時只處理新增或修改的事件。
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_STATE_FILE = Path.home() / ".cal-notion" / "sync_state.json"


class SyncState:
    """管理同步狀態的持久化存儲。"""

    def __init__(self, state_file: Path | None = None):
        self._file = state_file or DEFAULT_STATE_FILE
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._file.exists():
            try:
                return json.loads(self._file.read_text())
            except (json.JSONDecodeError, OSError) as e:
                log.warning(f"讀取同步狀態失敗，將重新建立: {e}")
        return {"last_sync": None, "synced_uids": {}}

    def save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    @property
    def last_sync(self) -> datetime | None:
        ts = self._data.get("last_sync")
        if ts:
            return datetime.fromisoformat(ts)
        return None

    def mark_synced(self, uid: str, last_modified: str | None = None) -> None:
        self._data["synced_uids"][uid] = {
            "last_modified": last_modified,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

    def is_modified(self, uid: str, last_modified: str | None) -> bool:
        """判斷事件是否有變更（新的或 last_modified 不同）。"""
        record = self._data["synced_uids"].get(uid)
        if record is None:
            return True  # 新事件
        if last_modified and record.get("last_modified") != last_modified:
            return True  # 已修改
        return False

    def get_synced_uids(self) -> set[str]:
        return set(self._data["synced_uids"].keys())

    def remove_uid(self, uid: str) -> None:
        self._data["synced_uids"].pop(uid, None)

    def update_last_sync(self) -> None:
        self._data["last_sync"] = datetime.now(timezone.utc).isoformat()

    def reset(self) -> None:
        self._data = {"last_sync": None, "synced_uids": {}}
        self.save()

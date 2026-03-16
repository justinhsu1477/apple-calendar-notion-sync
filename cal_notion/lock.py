"""同步鎖定機制，防止重複執行。"""
import fcntl
import logging
import os
from pathlib import Path

from cal_notion.config import CONFIG_DIR

log = logging.getLogger(__name__)
LOCK_FILE = CONFIG_DIR / "sync.lock"


class SyncLock:
    """File-based lock to prevent concurrent sync."""

    def __init__(self):
        self._lock_file = None

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True if successful."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self._lock_file = open(LOCK_FILE, "w")
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_file.write(str(os.getpid()))
            self._lock_file.flush()
            return True
        except (IOError, OSError):
            log.warning("另一個同步程序正在執行中")
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None
            return False

    def release(self) -> None:
        """Release the lock."""
        if self._lock_file:
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
            except (IOError, OSError):
                pass
            self._lock_file = None
            LOCK_FILE.unlink(missing_ok=True)

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("無法取得同步鎖定，另一個同步程序正在執行中")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

"""Tests for SyncLock."""

import fcntl
from unittest.mock import patch, MagicMock

import pytest


class TestSyncLock:
    """Test SyncLock using tmp_path to avoid touching the real config dir."""

    def _make_lock(self, tmp_path):
        """Create a SyncLock with patched paths."""
        with patch("cal_notion.lock.CONFIG_DIR", tmp_path), \
             patch("cal_notion.lock.LOCK_FILE", tmp_path / "sync.lock"):
            from cal_notion.lock import SyncLock
            return SyncLock()

    def test_acquire_and_release(self, tmp_path):
        with patch("cal_notion.lock.CONFIG_DIR", tmp_path), \
             patch("cal_notion.lock.LOCK_FILE", tmp_path / "sync.lock"):
            from cal_notion.lock import SyncLock
            lock = SyncLock()
            assert lock.acquire() is True
            lock.release()
            assert lock._lock_file is None

    def test_double_acquire_same_process(self, tmp_path):
        """Same process can acquire twice because it reuses the fd."""
        with patch("cal_notion.lock.CONFIG_DIR", tmp_path), \
             patch("cal_notion.lock.LOCK_FILE", tmp_path / "sync.lock"):
            from cal_notion.lock import SyncLock
            lock = SyncLock()
            assert lock.acquire() is True
            # Release and reacquire should work
            lock.release()
            assert lock.acquire() is True
            lock.release()

    def test_context_manager_works(self, tmp_path):
        with patch("cal_notion.lock.CONFIG_DIR", tmp_path), \
             patch("cal_notion.lock.LOCK_FILE", tmp_path / "sync.lock"):
            from cal_notion.lock import SyncLock
            lock = SyncLock()
            with lock:
                assert lock._lock_file is not None
            assert lock._lock_file is None

    def test_context_manager_raises_on_failure(self, tmp_path):
        with patch("cal_notion.lock.CONFIG_DIR", tmp_path), \
             patch("cal_notion.lock.LOCK_FILE", tmp_path / "sync.lock"):
            from cal_notion.lock import SyncLock
            lock = SyncLock()
            # Mock fcntl.flock to raise IOError (simulate another process holding lock)
            with patch("cal_notion.lock.fcntl.flock", side_effect=IOError("locked")):
                with pytest.raises(RuntimeError, match="無法取得同步鎖定"):
                    with lock:
                        pass

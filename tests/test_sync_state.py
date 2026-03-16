"""Tests for SyncState."""

import json
from pathlib import Path

import pytest

from cal_notion.sync_state import SyncState


@pytest.fixture
def state_file(tmp_path) -> Path:
    return tmp_path / "sync_state.json"


@pytest.fixture
def state(state_file) -> SyncState:
    return SyncState(state_file=state_file)


class TestEmptyState:
    def test_no_records(self, state):
        assert state.get_all_records() == {}

    def test_no_tracked_uids(self, state):
        assert state.get_tracked_uids() == set()

    def test_last_sync_is_none(self, state):
        assert state.last_sync is None

    def test_get_record_returns_none(self, state):
        assert state.get_record("nonexistent") is None


class TestSetAndGetRecord:
    def test_set_and_get(self, state):
        state.set_record("uid-1", calendar_hash="abc", notion_hash="def",
                         notion_page_id="page-1", calendar_name="Work",
                         source="calendar")
        record = state.get_record("uid-1")
        assert record is not None
        assert record["calendar_hash"] == "abc"
        assert record["notion_hash"] == "def"
        assert record["notion_page_id"] == "page-1"
        assert record["calendar_name"] == "Work"
        assert record["source"] == "calendar"
        assert "synced_at" in record

    def test_overwrite_record(self, state):
        state.set_record("uid-1", calendar_hash="old")
        state.set_record("uid-1", calendar_hash="new")
        assert state.get_record("uid-1")["calendar_hash"] == "new"


class TestRemoveRecord:
    def test_remove_existing(self, state):
        state.set_record("uid-1", calendar_hash="abc")
        state.remove_record("uid-1")
        assert state.get_record("uid-1") is None

    def test_remove_nonexistent_is_safe(self, state):
        state.remove_record("nonexistent")  # should not raise


class TestGetAllRecords:
    def test_returns_all(self, state):
        state.set_record("uid-1")
        state.set_record("uid-2")
        records = state.get_all_records()
        assert set(records.keys()) == {"uid-1", "uid-2"}


class TestGetTrackedUids:
    def test_returns_set_of_uids(self, state):
        state.set_record("a")
        state.set_record("b")
        assert state.get_tracked_uids() == {"a", "b"}


class TestIsModified:
    def test_new_uid_is_modified(self, state):
        assert state.is_modified("new-uid", "2025-01-01") is True

    def test_same_last_modified_not_modified(self, state):
        state.set_record("uid-1", last_modified="2025-01-01T00:00:00")
        assert state.is_modified("uid-1", "2025-01-01T00:00:00") is False

    def test_different_last_modified_is_modified(self, state):
        state.set_record("uid-1", last_modified="2025-01-01T00:00:00")
        assert state.is_modified("uid-1", "2025-01-02T00:00:00") is True

    def test_none_last_modified_not_modified(self, state):
        state.set_record("uid-1", last_modified=None)
        assert state.is_modified("uid-1", None) is False


class TestMarkSynced:
    def test_mark_new_uid(self, state):
        state.mark_synced("uid-1", last_modified="2025-03-10")
        record = state.get_record("uid-1")
        assert record is not None
        assert record["last_modified"] == "2025-03-10"
        assert "synced_at" in record

    def test_mark_existing_uid_updates_timestamp(self, state):
        state.mark_synced("uid-1", last_modified="old")
        state.mark_synced("uid-1", last_modified="new")
        assert state.get_record("uid-1")["last_modified"] == "new"


class TestUpdateLastSync:
    def test_sets_last_sync(self, state):
        assert state.last_sync is None
        state.update_last_sync()
        assert state.last_sync is not None


class TestReset:
    def test_clears_everything(self, state, state_file):
        state.set_record("uid-1")
        state.update_last_sync()
        state.reset()
        assert state.get_all_records() == {}
        assert state.last_sync is None
        # File should exist (reset calls save)
        assert state_file.exists()


class TestV1ToV2Migration:
    def test_migration(self, state_file):
        v1_data = {
            "version": 1,
            "last_sync": "2025-01-01T00:00:00+00:00",
            "synced_uids": {
                "uid-1": {"last_modified": "2025-01-01", "synced_at": "2025-01-01T00:00:00"},
                "uid-2": {"last_modified": "2025-01-02", "synced_at": "2025-01-02T00:00:00"},
            },
        }
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(v1_data))

        state = SyncState(state_file=state_file)
        assert state.get_record("uid-1") is not None
        assert state.get_record("uid-1")["last_modified"] == "2025-01-01"
        assert state.get_record("uid-1")["calendar_hash"] is None
        assert state.get_record("uid-1")["source"] == "calendar"
        assert state.get_tracked_uids() == {"uid-1", "uid-2"}


class TestSaveAndReload:
    def test_persistence(self, state_file):
        state1 = SyncState(state_file=state_file)
        state1.set_record("uid-1", calendar_hash="hash1", notion_page_id="page-1")
        state1.update_last_sync()
        state1.save()

        state2 = SyncState(state_file=state_file)
        assert state2.get_record("uid-1")["calendar_hash"] == "hash1"
        assert state2.last_sync is not None

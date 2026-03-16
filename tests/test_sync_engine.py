"""Tests for BidirectionalSyncEngine._process_uid."""

from unittest.mock import Mock, MagicMock, patch

import pytest

from cal_notion.models import CalendarEvent
from cal_notion.sync_engine import BidirectionalSyncEngine, SyncStats


def _make_event(uid="uid-1", summary="Event", source="calendar",
                content_hash="hash_a", last_modified="2025-03-10T10:00:00",
                notion_page_id=None, calendar_name="Work", **kw) -> CalendarEvent:
    event = CalendarEvent(
        uid=uid,
        summary=summary,
        start="2025-03-10T09:00:00+08:00",
        end="2025-03-10T10:00:00+08:00",
        source=source,
        last_modified=last_modified,
        notion_page_id=notion_page_id,
        calendar_name=calendar_name,
        content_hash=content_hash,
        **kw,
    )
    return event


@pytest.fixture
def engine():
    provider = Mock()
    provider.supports_write = True
    notion = Mock()
    state = Mock()
    state.set_record = Mock()
    state.remove_record = Mock()

    eng = BidirectionalSyncEngine(
        provider=provider,
        notion=notion,
        state=state,
        conflict_strategy="newest_wins",
        default_calendar="Personal",
    )
    return eng, provider, notion, state


class TestCase1BothUnchanged:
    def test_skip(self, engine):
        eng, provider, notion, state = engine
        stats = SyncStats()
        cal_event = _make_event(content_hash="hash_a")
        notion_event = _make_event(source="notion", content_hash="hash_b",
                                   notion_page_id="page-1")
        record = {"calendar_hash": "hash_a", "notion_hash": "hash_b"}

        eng._process_uid("uid-1", cal_event, notion_event, record, stats)

        assert stats.skipped == 1
        notion.update_page.assert_not_called()
        provider.update_event.assert_not_called()


class TestCase2CalendarChanged:
    def test_push_to_notion(self, engine):
        eng, provider, notion, state = engine
        stats = SyncStats()
        cal_event = _make_event(content_hash="hash_new")
        notion_event = _make_event(source="notion", content_hash="hash_b",
                                   notion_page_id="page-1")
        record = {"calendar_hash": "hash_old", "notion_hash": "hash_b"}

        eng._process_uid("uid-1", cal_event, notion_event, record, stats)

        assert stats.cal_to_notion == 1
        notion.update_page.assert_called_once_with("page-1", cal_event)


class TestCase3NotionChanged:
    def test_push_to_calendar(self, engine):
        eng, provider, notion, state = engine
        stats = SyncStats()
        cal_event = _make_event(content_hash="hash_a")
        notion_event = _make_event(source="notion", content_hash="hash_new",
                                   notion_page_id="page-1")
        record = {"calendar_hash": "hash_a", "notion_hash": "hash_old"}

        eng._process_uid("uid-1", cal_event, notion_event, record, stats)

        assert stats.notion_to_cal == 1
        provider.update_event.assert_called_once()


class TestCase4BothChanged:
    def test_conflict_resolution(self, engine):
        eng, provider, notion, state = engine
        stats = SyncStats()
        # Calendar event is newer
        cal_event = _make_event(content_hash="cal_new",
                                last_modified="2025-03-10T12:00:00")
        notion_event = _make_event(source="notion", content_hash="notion_new",
                                   notion_page_id="page-1",
                                   last_modified="2025-03-10T11:00:00")
        record = {"calendar_hash": "cal_old", "notion_hash": "notion_old"}

        eng._process_uid("uid-1", cal_event, notion_event, record, stats)

        assert stats.conflicts == 1
        # Calendar is newer, should push to notion
        notion.update_page.assert_called_once()


class TestCase5NewInCalendar:
    def test_create_in_notion(self, engine):
        eng, provider, notion, state = engine
        stats = SyncStats()
        cal_event = _make_event(content_hash="hash_a")
        notion.create_page.return_value = "new-page-id"

        eng._process_uid("uid-1", cal_event, None, None, stats)

        assert stats.created_in_notion == 1
        notion.create_page.assert_called_once_with(cal_event)
        state.set_record.assert_called_once()


class TestCase6NewInNotion:
    def test_create_in_calendar(self, engine):
        eng, provider, notion, state = engine
        stats = SyncStats()
        notion_event = _make_event(source="notion", content_hash="hash_b",
                                   notion_page_id="page-1",
                                   calendar_name="Work")

        eng._process_uid("uid-1", None, notion_event, None, stats)

        assert stats.created_in_cal == 1
        provider.create_event.assert_called_once_with(notion_event, "Work")

    def test_skip_when_provider_readonly(self, engine):
        eng, provider, notion, state = engine
        provider.supports_write = False
        stats = SyncStats()
        notion_event = _make_event(source="notion", content_hash="hash_b",
                                   notion_page_id="page-1")

        eng._process_uid("uid-1", None, notion_event, None, stats)

        assert stats.skipped == 1
        provider.create_event.assert_not_called()


class TestCase7DeletedFromNotion:
    def test_delete_from_calendar(self, engine):
        eng, provider, notion, state = engine
        stats = SyncStats()
        cal_event = _make_event(content_hash="hash_a", calendar_name="Work")
        record = {"calendar_hash": "hash_a", "notion_hash": "hash_b"}

        eng._process_uid("uid-1", cal_event, None, record, stats)

        assert stats.deleted_from_cal == 1
        provider.delete_event.assert_called_once_with("uid-1", "Work")
        state.remove_record.assert_called_once_with("uid-1")


class TestCase8DeletedFromCalendar:
    def test_delete_from_notion(self, engine):
        eng, provider, notion, state = engine
        stats = SyncStats()
        notion_event = _make_event(source="notion", content_hash="hash_b",
                                   notion_page_id="page-1")
        record = {"calendar_hash": "hash_a", "notion_hash": "hash_b",
                  "notion_page_id": "page-1"}

        eng._process_uid("uid-1", None, notion_event, record, stats)

        assert stats.deleted_from_notion == 1
        notion.mark_cancelled.assert_called_once_with("page-1")
        state.remove_record.assert_called_once_with("uid-1")

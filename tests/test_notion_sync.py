"""Tests for NotionSync (dry-run mode and static helpers)."""

from unittest.mock import patch, MagicMock

import pytest

from cal_notion.models import CalendarEvent
from cal_notion.notion_sync import NotionSync


@pytest.fixture
def dry_sync():
    """Create a NotionSync in dry-run mode with mocked Notion client."""
    with patch("cal_notion.notion_sync.NotionClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.databases.retrieve.return_value = {"data_sources": []}
        MockClient.return_value = mock_instance
        return NotionSync(token="fake-token", database_id="fake-db-id", dry_run=True)


def _make_event(**overrides) -> CalendarEvent:
    defaults = dict(
        uid="test-uid",
        summary="Test Event",
        start="2025-03-10T09:00:00+08:00",
        end="2025-03-10T10:00:00+08:00",
        description="A description",
        location="Room 1",
        calendar_name="Work",
        status="Upcoming",
    )
    defaults.update(overrides)
    return CalendarEvent(**defaults)


class TestDryRunMode:
    def test_create_page_returns_dry_run_id(self, dry_sync):
        event = _make_event()
        result = dry_sync.create_page(event)
        assert result == "dry-run-id"

    def test_update_page_does_nothing(self, dry_sync):
        event = _make_event()
        # Should not raise, should not call API
        dry_sync.update_page("page-123", event)
        dry_sync._notion.pages.update.assert_not_called()

    def test_mark_cancelled_does_nothing(self, dry_sync):
        dry_sync.mark_cancelled("page-123")
        dry_sync._notion.pages.update.assert_not_called()


class TestBuildProperties:
    def test_builds_correct_structure(self, dry_sync):
        event = _make_event(
            summary="Sprint Planning",
            uid="uid-123",
            description="Plan the sprint",
            calendar_name="Work",
            start="2025-03-10T09:00:00",
            end="2025-03-10T10:00:00",
        )
        props = dry_sync._build_properties(event)

        # Title
        assert props["名稱"]["title"][0]["text"]["content"] == "Sprint Planning"
        # UID
        assert props["UID"]["rich_text"][0]["text"]["content"] == "uid-123"
        # Source
        assert props["來源"]["select"]["name"] == "Apple Calendar"
        # Description
        assert props["備註"]["rich_text"][0]["text"]["content"] == "Plan the sprint"
        # Category (Work -> 工作)
        assert props["類別"]["select"]["name"] == "工作"
        # Dates
        assert props["開始"]["date"]["start"] == "2025-03-10T09:00:00"
        assert props["結束"]["date"]["start"] == "2025-03-10T10:00:00"

    def test_no_description_omits_field(self, dry_sync):
        event = _make_event(description="")
        props = dry_sync._build_properties(event)
        assert "備註" not in props

    def test_no_calendar_name_omits_category(self, dry_sync):
        event = _make_event(calendar_name="")
        props = dry_sync._build_properties(event)
        assert "類別" not in props

    def test_no_end_omits_end_field(self, dry_sync):
        event = _make_event(end=None)
        props = dry_sync._build_properties(event)
        assert "結束" not in props


class TestExtractHelpers:
    def test_extract_text(self):
        page = {
            "properties": {
                "UID": {"rich_text": [{"plain_text": "uid-abc"}]},
            }
        }
        assert NotionSync._extract_text(page, "UID") == "uid-abc"

    def test_extract_text_empty(self):
        page = {"properties": {"UID": {"rich_text": []}}}
        assert NotionSync._extract_text(page, "UID") == ""

    def test_extract_text_missing_prop(self):
        page = {"properties": {}}
        assert NotionSync._extract_text(page, "UID") == ""

    def test_extract_title(self):
        page = {
            "properties": {
                "名稱": {"title": [{"plain_text": "Meeting"}]},
            }
        }
        assert NotionSync._extract_title(page, "名稱") == "Meeting"

    def test_extract_title_empty(self):
        page = {"properties": {"名稱": {"title": []}}}
        assert NotionSync._extract_title(page, "名稱") == ""

    def test_extract_select(self):
        page = {
            "properties": {
                "類別": {"select": {"name": "工作"}},
            }
        }
        assert NotionSync._extract_select(page, "類別") == "工作"

    def test_extract_select_none(self):
        page = {"properties": {"類別": {"select": None}}}
        assert NotionSync._extract_select(page, "類別") is None

    def test_extract_date_datetime(self):
        page = {
            "properties": {
                "開始": {"date": {"start": "2025-03-10T09:00:00+08:00"}},
            }
        }
        val, is_dt = NotionSync._extract_date(page, "開始")
        assert val == "2025-03-10T09:00:00+08:00"
        assert is_dt is True

    def test_extract_date_date_only(self):
        page = {
            "properties": {
                "開始": {"date": {"start": "2025-03-10"}},
            }
        }
        val, is_dt = NotionSync._extract_date(page, "開始")
        assert val == "2025-03-10"
        assert is_dt is False

    def test_extract_date_none(self):
        page = {"properties": {"開始": {"date": None}}}
        val, is_dt = NotionSync._extract_date(page, "開始")
        assert val is None
        assert is_dt is False

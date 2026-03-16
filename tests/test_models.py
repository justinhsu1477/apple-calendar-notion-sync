"""Tests for CalendarEvent model."""

from cal_notion.models import CalendarEvent


def _make_event(**overrides) -> CalendarEvent:
    defaults = dict(
        uid="test-uid-1",
        summary="Team standup",
        start="2025-03-10T09:00:00+08:00",
        end="2025-03-10T10:00:00+08:00",
        description="Daily sync",
        location="Room A",
        calendar_name="Work",
        status="Upcoming",
    )
    defaults.update(overrides)
    return CalendarEvent(**defaults)


class TestComputeContentHash:
    def test_returns_consistent_hash(self):
        event = _make_event()
        h1 = event.compute_content_hash()
        h2 = event.compute_content_hash()
        assert h1 == h2
        assert len(h1) == 16  # truncated SHA-256

    def test_hash_changes_when_summary_changes(self):
        e1 = _make_event(summary="Meeting A")
        e2 = _make_event(summary="Meeting B")
        assert e1.compute_content_hash() != e2.compute_content_hash()

    def test_hash_changes_when_start_changes(self):
        e1 = _make_event(start="2025-03-10T09:00:00+08:00")
        e2 = _make_event(start="2025-03-10T10:00:00+08:00")
        assert e1.compute_content_hash() != e2.compute_content_hash()

    def test_hash_changes_when_status_changes(self):
        e1 = _make_event(status="Upcoming")
        e2 = _make_event(status="Cancelled")
        assert e1.compute_content_hash() != e2.compute_content_hash()

    def test_hash_stored_on_instance(self):
        event = _make_event()
        h = event.compute_content_hash()
        assert event.content_hash == h


class TestToDict:
    def test_includes_all_fields(self):
        event = _make_event()
        d = event.to_dict()
        expected_keys = {
            "uid", "summary", "start", "start_is_datetime", "end",
            "end_is_datetime", "description", "location", "calendar_name",
            "status", "last_modified", "source", "notion_page_id",
            "provider_id", "content_hash",
        }
        assert set(d.keys()) == expected_keys

    def test_values_match(self):
        event = _make_event()
        d = event.to_dict()
        assert d["uid"] == "test-uid-1"
        assert d["summary"] == "Team standup"
        assert d["location"] == "Room A"


class TestDefaults:
    def test_default_values(self):
        event = CalendarEvent(uid="x", summary="y", start="2025-01-01")
        assert event.start_is_datetime is True
        assert event.end is None
        assert event.end_is_datetime is True
        assert event.description == ""
        assert event.location == ""
        assert event.calendar_name == ""
        assert event.status == "Upcoming"
        assert event.last_modified is None
        assert event.source == "calendar"
        assert event.notion_page_id is None
        assert event.provider_id is None
        assert event.content_hash is None

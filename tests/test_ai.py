"""Tests for AI module (all API calls mocked)."""

import json
from unittest.mock import patch, MagicMock

import pytest

from cal_notion import ai


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the global client before each test."""
    ai._client = None
    yield
    ai._client = None


def _mock_claude_response(text: str) -> MagicMock:
    """Create a mock Anthropic response."""
    mock_msg = MagicMock()
    mock_content = MagicMock()
    mock_content.text = text
    mock_msg.content = [mock_content]
    return mock_msg


class TestClassifyEvent:
    @patch.object(ai, "_call_claude", return_value="工作")
    def test_returns_valid_category(self, mock_call):
        result = ai.classify_event("Sprint planning", "Discuss next sprint")
        assert result == "工作"
        mock_call.assert_called_once()

    @patch.object(ai, "_call_claude", return_value="生活")
    def test_category_from_list(self, mock_call):
        result = ai.classify_event("Grocery shopping", available_categories=["工作", "生活"])
        assert result == "生活"

    @patch.object(ai, "_call_claude", side_effect=Exception("API down"))
    def test_fallback_on_error(self, mock_call):
        result = ai.classify_event("Meeting")
        assert result == "一般"


class TestBatchClassifyEvents:
    @patch.object(ai, "_call_claude")
    def test_parses_json_response(self, mock_call):
        mock_call.return_value = json.dumps({"uid-1": "工作", "uid-2": "生活"})
        events = [
            {"uid": "uid-1", "summary": "Sprint"},
            {"uid": "uid-2", "summary": "Dinner"},
        ]
        result = ai.batch_classify_events(events)
        assert result == {"uid-1": "工作", "uid-2": "生活"}

    def test_empty_list_returns_empty(self):
        result = ai.batch_classify_events([])
        assert result == {}

    @patch.object(ai, "_call_claude", side_effect=Exception("API down"))
    def test_error_returns_empty(self, mock_call):
        events = [{"uid": "uid-1", "summary": "Test"}]
        result = ai.batch_classify_events(events)
        assert result == {}


class TestCalculateMeetingCosts:
    def test_with_sample_events(self):
        events = [
            {"summary": "Standup", "start": "2025-03-10T09:00:00", "end": "2025-03-10T09:30:00"},
            {"summary": "Workshop", "start": "2025-03-10T14:00:00", "end": "2025-03-10T16:00:00"},
        ]
        result = ai.calculate_meeting_costs(events, hourly_rate=1000.0)
        assert len(result) == 2
        # Workshop (2h) should be first (sorted by cost desc)
        assert result[0]["summary"] == "Workshop"
        assert result[0]["hours"] == 2.0
        assert result[0]["cost"] == 2000.0
        assert result[1]["summary"] == "Standup"
        assert result[1]["hours"] == 0.5
        assert result[1]["cost"] == 500.0

    def test_empty_list(self):
        result = ai.calculate_meeting_costs([])
        assert result == []

    def test_default_duration_when_no_times(self):
        events = [{"summary": "Quick chat"}]
        result = ai.calculate_meeting_costs(events, hourly_rate=500.0)
        assert len(result) == 1
        assert result[0]["hours"] == 1.0
        assert result[0]["cost"] == 500.0


class TestDetectDuplicates:
    @patch.object(ai, "_call_claude")
    def test_returns_empty_array(self, mock_call):
        mock_call.return_value = "[]"
        events = [
            {"uid": "1", "summary": "A", "start": "2025-03-10T09:00:00"},
            {"uid": "2", "summary": "B", "start": "2025-03-11T09:00:00"},
        ]
        result = ai.detect_duplicates(events)
        assert result == []

    @patch.object(ai, "_call_claude")
    def test_returns_duplicates(self, mock_call):
        mock_call.return_value = json.dumps([
            {"uid1": "1", "uid2": "2", "confidence": 0.95, "reason": "same event"}
        ])
        events = [
            {"uid": "1", "summary": "Meeting", "start": "2025-03-10T09:00:00"},
            {"uid": "2", "summary": "Meeting", "start": "2025-03-10T09:00:00"},
        ]
        result = ai.detect_duplicates(events)
        assert len(result) == 1
        assert result[0] == ("1", "2", 0.95)

    def test_fewer_than_two_events(self):
        assert ai.detect_duplicates([]) == []
        assert ai.detect_duplicates([{"uid": "1", "summary": "A"}]) == []

"""Tests for NLP event parsing."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from cal_notion.nlp import parse_event_text


class TestParseEventText:
    def test_friday_afternoon_coffee(self):
        """'週五下午3點 和 Sam 喝咖啡' extracts time and summary."""
        today = date.today()
        result = parse_event_text("週五下午3點 和 Sam 喝咖啡")
        assert result is not None
        assert "Sam" in result.summary or "喝咖啡" in result.summary
        assert "15:00" in result.start or "T15:" in result.start

    def test_tomorrow_morning_meeting_with_duration(self):
        """'明天早上10點 開會 2小時' gets correct duration."""
        result = parse_event_text("明天早上10點 開會 2小時")
        assert result is not None
        tomorrow = date.today() + timedelta(days=1)
        assert tomorrow.isoformat() in result.start
        assert "10:00" in result.start or "T10:" in result.start
        # End should be 2 hours later (12:00)
        assert "12:00" in result.end or "T12:" in result.end

    def test_absolute_date(self):
        """'3/20 14:00 牙醫' parses absolute date."""
        result = parse_event_text("3/20 14:00 牙醫")
        assert result is not None
        assert "牙醫" in result.summary
        # Should contain March 20
        assert "-03-20" in result.start
        assert "14:00" in result.start or "T14:" in result.start

    def test_next_week_weekday(self):
        """'下週二晚上7點 聚餐' gets next week's Tuesday."""
        result = parse_event_text("下週二晚上7點 聚餐")
        assert result is not None
        assert "聚餐" in result.summary
        assert "19:00" in result.start or "T19:" in result.start
        # Should be next week's Tuesday (at least 7 days from today)
        from datetime import datetime
        start_date = datetime.fromisoformat(result.start).date()
        assert start_date.weekday() == 1  # Tuesday
        assert start_date > date.today() + timedelta(days=6)

    def test_empty_string_returns_none(self):
        assert parse_event_text("") is None
        assert parse_event_text("   ") is None

    def test_time_only_meeting(self):
        """'14:00 meeting' parses time, defaults to today."""
        result = parse_event_text("14:00 meeting")
        assert result is not None
        assert "meeting" in result.summary
        assert "14:00" in result.start or "T14:" in result.start

    def test_chinese_time_afternoon(self):
        """'下午3點半' parses to 15:30."""
        result = parse_event_text("下午3點半 開會")
        assert result is not None
        assert "15:30" in result.start or "T15:30" in result.start

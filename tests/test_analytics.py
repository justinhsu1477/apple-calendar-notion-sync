"""Tests for TimeAnalytics."""

from datetime import date

import pytest

from cal_notion.analytics import TimeAnalytics
from cal_notion.models import CalendarEvent


def _event(summary, start, end=None, calendar_name="Work"):
    return CalendarEvent(
        uid=f"uid-{summary}",
        summary=summary,
        start=start,
        end=end,
        calendar_name=calendar_name,
    )


class TestWeeklySummary:
    def test_with_sample_events(self):
        # Monday 2025-03-10 to Sunday 2025-03-16
        events = [
            _event("Meeting", "2025-03-10T09:00:00", "2025-03-10T11:00:00"),
            _event("Lunch", "2025-03-10T12:00:00", "2025-03-10T13:00:00", "Personal"),
            _event("Sprint", "2025-03-12T14:00:00", "2025-03-12T16:00:00"),
        ]
        analytics = TimeAnalytics(events)
        result = analytics.weekly_summary(target_date=date(2025, 3, 12))

        assert result["week_start"] == "2025-03-10"
        assert result["week_end"] == "2025-03-16"
        assert result["total_events"] == 3
        assert result["total_hours"] == 5.0
        assert "Work" in result["by_category"]
        assert "Personal" in result["by_category"]
        assert result["by_category"]["Work"]["count"] == 2
        assert result["by_category"]["Work"]["hours"] == 4.0

    def test_busiest_day(self):
        events = [
            _event("A", "2025-03-10T09:00:00", "2025-03-10T12:00:00"),  # Mon 3h
            _event("B", "2025-03-12T09:00:00", "2025-03-12T10:00:00"),  # Wed 1h
        ]
        analytics = TimeAnalytics(events)
        result = analytics.weekly_summary(target_date=date(2025, 3, 10))
        assert result["busiest_day"] == "週一"


class TestMonthlySummary:
    def test_with_sample_events(self):
        events = [
            _event("A", "2025-03-05T09:00:00", "2025-03-05T10:00:00"),
            _event("B", "2025-03-15T14:00:00", "2025-03-15T16:00:00"),
            _event("C", "2025-03-25T10:00:00", "2025-03-25T11:30:00"),
        ]
        analytics = TimeAnalytics(events)
        result = analytics.monthly_summary(year=2025, month=3)

        assert result["year"] == 2025
        assert result["month"] == 3
        assert result["total_events"] == 3
        assert result["total_hours"] == 4.5


class TestCategoryBreakdown:
    def test_breakdown(self):
        events = [
            _event("Work1", "2025-03-10T09:00:00", "2025-03-10T11:00:00", "Work"),
            _event("Work2", "2025-03-11T09:00:00", "2025-03-11T10:00:00", "Work"),
            _event("Fun", "2025-03-10T18:00:00", "2025-03-10T20:00:00", "Personal"),
        ]
        analytics = TimeAnalytics(events)
        breakdown = analytics.category_breakdown()

        assert len(breakdown) == 2
        # Sorted by hours descending
        assert breakdown[0]["category"] == "Work"
        assert breakdown[0]["count"] == 2
        assert breakdown[0]["hours"] == 3.0
        assert breakdown[1]["category"] == "Personal"
        assert breakdown[1]["hours"] == 2.0
        # Percentages should sum to 100
        total_pct = sum(b["percentage"] for b in breakdown)
        assert abs(total_pct - 100.0) < 0.1


class TestEmptyEvents:
    def test_weekly_summary_empty(self):
        analytics = TimeAnalytics([])
        result = analytics.weekly_summary(target_date=date(2025, 3, 10))
        assert result["total_events"] == 0
        assert result["total_hours"] == 0.0
        assert result["busiest_day"] == "無"

    def test_category_breakdown_empty(self):
        analytics = TimeAnalytics([])
        assert analytics.category_breakdown() == []


class TestEventsWithNoEndTime:
    def test_defaults_to_one_hour(self):
        events = [_event("NoEnd", "2025-03-10T09:00:00", end=None)]
        analytics = TimeAnalytics(events)
        result = analytics.weekly_summary(target_date=date(2025, 3, 10))
        assert result["total_hours"] == 1.0


class TestAllDayEvents:
    def test_all_day_event_duration(self):
        events = [
            CalendarEvent(
                uid="allday-1",
                summary="Conference",
                start="2025-03-10",
                start_is_datetime=False,
                end="2025-03-12",
                end_is_datetime=False,
                calendar_name="Work",
            )
        ]
        analytics = TimeAnalytics(events)
        result = analytics.weekly_summary(target_date=date(2025, 3, 10))
        # 2-day all-day event = 2 * 8 = 16 hours
        assert result["total_hours"] == 16.0

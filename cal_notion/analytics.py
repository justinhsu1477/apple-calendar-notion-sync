"""時間分析模組 — 分析行事曆事件，產出時間分佈報表。"""

import logging
from collections import defaultdict
from datetime import datetime, date, timedelta
from typing import Any

from cal_notion.models import CalendarEvent

log = logging.getLogger(__name__)


class TimeAnalytics:
    """分析行事曆事件，產出時間統計與洞察。"""

    def __init__(self, events: list[CalendarEvent]):
        self._events = events

    def weekly_summary(self, target_date: date | None = None) -> dict[str, Any]:
        """產出指定週的時間分析摘要。

        Returns dict with:
        - week_start, week_end: date strings
        - total_events: int
        - total_hours: float
        - by_category: {category: {count, hours}}
        - by_day: {day_name: {count, hours}}
        - busiest_day: str
        - avg_hours_per_day: float
        """
        target = target_date or date.today()
        # Monday = 0
        week_start = target - timedelta(days=target.weekday())
        week_end = week_start + timedelta(days=6)

        week_events = self._filter_by_date_range(week_start, week_end)

        by_category: dict[str, dict] = defaultdict(lambda: {"count": 0, "hours": 0.0})
        by_day: dict[str, dict] = defaultdict(lambda: {"count": 0, "hours": 0.0})
        day_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

        total_hours = 0.0
        for event in week_events:
            hours = self._event_hours(event)
            total_hours += hours

            cat = event.calendar_name or "未分類"
            by_category[cat]["count"] += 1
            by_category[cat]["hours"] += hours

            event_date = self._parse_date(event.start)
            if event_date:
                day_idx = event_date.weekday()
                day_name = day_names[day_idx]
                by_day[day_name]["count"] += 1
                by_day[day_name]["hours"] += hours

        # Round hours
        total_hours = round(total_hours, 1)
        for cat_data in by_category.values():
            cat_data["hours"] = round(cat_data["hours"], 1)
        for day_data in by_day.values():
            day_data["hours"] = round(day_data["hours"], 1)

        busiest_day = max(by_day, key=lambda d: by_day[d]["hours"]) if by_day else "無"

        return {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "total_events": len(week_events),
            "total_hours": total_hours,
            "by_category": dict(by_category),
            "by_day": dict(by_day),
            "busiest_day": busiest_day,
            "avg_hours_per_day": round(total_hours / 7, 1),
        }

    def monthly_summary(self, year: int | None = None, month: int | None = None) -> dict[str, Any]:
        """產出指定月的時間分析。"""
        today = date.today()
        y = year or today.year
        m = month or today.month

        month_start = date(y, m, 1)
        if m == 12:
            month_end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(y, m + 1, 1) - timedelta(days=1)

        month_events = self._filter_by_date_range(month_start, month_end)

        by_category: dict[str, dict] = defaultdict(lambda: {"count": 0, "hours": 0.0})
        by_week: dict[int, dict] = defaultdict(lambda: {"count": 0, "hours": 0.0})
        total_hours = 0.0

        for event in month_events:
            hours = self._event_hours(event)
            total_hours += hours

            cat = event.calendar_name or "未分類"
            by_category[cat]["count"] += 1
            by_category[cat]["hours"] += hours

            event_date = self._parse_date(event.start)
            if event_date:
                week_num = event_date.isocalendar()[1]
                by_week[week_num]["count"] += 1
                by_week[week_num]["hours"] += hours

        total_hours = round(total_hours, 1)
        for cat_data in by_category.values():
            cat_data["hours"] = round(cat_data["hours"], 1)
        for week_data in by_week.values():
            week_data["hours"] = round(week_data["hours"], 1)

        return {
            "year": y,
            "month": m,
            "total_events": len(month_events),
            "total_hours": total_hours,
            "by_category": dict(by_category),
            "by_week": dict(by_week),
            "avg_hours_per_week": round(total_hours / 4, 1),
        }

    def category_breakdown(self) -> list[dict]:
        """所有事件按類別分組的完整統計。"""
        by_category: dict[str, dict] = defaultdict(lambda: {"count": 0, "hours": 0.0, "events": []})
        total_hours = 0.0

        for event in self._events:
            hours = self._event_hours(event)
            total_hours += hours
            cat = event.calendar_name or "未分類"
            by_category[cat]["count"] += 1
            by_category[cat]["hours"] += hours
            by_category[cat]["events"].append(event.summary)

        result = []
        for cat, data in sorted(by_category.items(), key=lambda x: -x[1]["hours"]):
            pct = round(data["hours"] / total_hours * 100, 1) if total_hours > 0 else 0
            result.append({
                "category": cat,
                "count": data["count"],
                "hours": round(data["hours"], 1),
                "percentage": pct,
            })
        return result

    def _filter_by_date_range(self, start: date, end: date) -> list[CalendarEvent]:
        """Filter events within a date range."""
        result = []
        for event in self._events:
            event_date = self._parse_date(event.start)
            if event_date and start <= event_date <= end:
                result.append(event)
        return result

    @staticmethod
    def _parse_date(iso_str: str | None) -> date | None:
        if not iso_str:
            return None
        try:
            if "T" in iso_str:
                return datetime.fromisoformat(iso_str).date()
            return date.fromisoformat(iso_str)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _event_hours(event: CalendarEvent) -> float:
        """Calculate event duration in hours."""
        if not event.start or not event.end:
            return 1.0  # Default 1 hour for events without end time
        try:
            if "T" in event.start and "T" in (event.end or ""):
                start_dt = datetime.fromisoformat(event.start)
                end_dt = datetime.fromisoformat(event.end)
                delta = (end_dt - start_dt).total_seconds() / 3600
                return max(0, delta)
            else:
                # All-day event
                start_d = date.fromisoformat(event.start[:10])
                end_d = date.fromisoformat(event.end[:10]) if event.end else start_d
                return max(1, (end_d - start_d).days) * 8  # 8 hours per all-day event
        except (ValueError, TypeError):
            return 1.0

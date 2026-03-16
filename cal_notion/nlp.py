"""自然語言事件解析 — 將中文/英文描述轉為 CalendarEvent。"""

import re
import logging
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo

from cal_notion.models import CalendarEvent

log = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Asia/Taipei")

# 中文星期映射
WEEKDAY_MAP = {
    "週一": 0, "周一": 0, "星期一": 0, "Monday": 0,
    "週二": 1, "周二": 1, "星期二": 1, "Tuesday": 1,
    "週三": 2, "周三": 2, "星期三": 2, "Wednesday": 2,
    "週四": 3, "周四": 3, "星期四": 3, "Thursday": 3,
    "週五": 4, "周五": 4, "星期五": 4, "Friday": 4,
    "週六": 5, "周六": 5, "星期六": 5, "Saturday": 5,
    "週日": 6, "周日": 6, "星期日": 6, "Sunday": 6,
    "星期天": 6,
}

# 中文時間表達
RELATIVE_DATE_MAP = {
    "今天": 0, "明天": 1, "後天": 2, "大後天": 3,
    "today": 0, "tomorrow": 1,
}

TIME_PERIOD_MAP = {
    "早上": 9, "上午": 10, "中午": 12, "下午": 14,
    "傍晚": 17, "晚上": 19, "凌晨": 2,
}


def parse_event_text(text: str) -> CalendarEvent | None:
    """Parse natural language text into a CalendarEvent.

    Examples:
        "週五下午3點 和 Sam 喝咖啡"
        "明天早上10點 開會 2小時"
        "3/20 14:00 牙醫"
        "下週二晚上7點 跟朋友聚餐"

    Returns CalendarEvent or None if parsing fails.
    """
    text = text.strip()
    if not text:
        return None

    parsed_date = None
    parsed_time = None
    duration_hours = 1.0  # default
    summary = text  # will be refined

    # 1. Extract duration (X小時, Xhr)
    dur_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:小時|hrs?|hours?)', text)
    if dur_match:
        duration_hours = float(dur_match.group(1))
        text = text[:dur_match.start()] + text[dur_match.end():]

    # 2. Parse date
    # Try absolute date: YYYY/MM/DD, MM/DD, YYYY-MM-DD
    date_match = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', text)
    if date_match:
        parsed_date = date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
        text = text[:date_match.start()] + text[date_match.end():]

    if not parsed_date:
        date_match = re.search(r'(\d{1,2})[/](\d{1,2})', text)
        if date_match:
            m, d = int(date_match.group(1)), int(date_match.group(2))
            year = date.today().year
            try:
                parsed_date = date(year, m, d)
                if parsed_date < date.today():
                    parsed_date = date(year + 1, m, d)
            except ValueError:
                pass
            else:
                text = text[:date_match.start()] + text[date_match.end():]

    # Try relative date: 今天, 明天, etc.
    if not parsed_date:
        for word, offset in RELATIVE_DATE_MAP.items():
            if word in text:
                parsed_date = date.today() + timedelta(days=offset)
                text = text.replace(word, "", 1)
                break

    # Try weekday: 週一, 下週三, etc.
    if not parsed_date:
        next_week = "下週" in text or "下周" in text
        for word, wd in WEEKDAY_MAP.items():
            if word in text:
                today = date.today()
                days_ahead = wd - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                if next_week:
                    days_ahead += 7
                parsed_date = today + timedelta(days=days_ahead)
                text = text.replace("下週", "", 1).replace("下周", "", 1).replace(word, "", 1)
                break

    if not parsed_date:
        parsed_date = date.today()  # default to today

    # 3. Parse time
    # Try explicit time: 14:00, 3:30, etc.
    time_match = re.search(r'(\d{1,2}):(\d{2})', text)
    if time_match:
        h, m = int(time_match.group(1)), int(time_match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            parsed_time = time(h, m)
            text = text[:time_match.start()] + text[time_match.end():]

    # Try Chinese time: 下午3點, 早上10點半
    if not parsed_time:
        for period, base_hour in TIME_PERIOD_MAP.items():
            pattern = rf'{period}\s*(\d{{1,2}})\s*(?:點|時)(?:(\d{{1,2}})\s*分|半)?'
            match = re.search(pattern, text)
            if match:
                h = int(match.group(1))
                m = int(match.group(2)) if match.group(2) else 0
                if "半" in match.group(0):
                    m = 30
                # Adjust for period
                if h <= 12 and base_hour >= 12 and period in ("下午", "晚上"):
                    h += 12
                elif h == 12 and period == "中午":
                    pass
                elif period in ("早上", "上午", "凌晨") and h <= 12:
                    pass
                parsed_time = time(min(h, 23), m)
                text = text[:match.start()] + text[match.end():]
                break

    # Try simple time: 3點, 10點半
    if not parsed_time:
        simple_match = re.search(r'(\d{1,2})\s*(?:點|時)(?:(\d{1,2})\s*分|半)?', text)
        if simple_match:
            h = int(simple_match.group(1))
            m = int(simple_match.group(2)) if simple_match.group(2) else 0
            if "半" in simple_match.group(0):
                m = 30
            if h < 8:
                h += 12  # assume PM for small hours
            parsed_time = time(min(h, 23), m)
            text = text[:simple_match.start()] + text[simple_match.end():]

    if not parsed_time:
        parsed_time = time(9, 0)  # default 9 AM

    # 4. Clean up remaining text as summary
    summary = re.sub(r'\s+', ' ', text).strip()
    # Remove leading/trailing punctuation
    summary = summary.strip(' ,，、。')
    if not summary:
        summary = "新事件"

    # 5. Build CalendarEvent
    import uuid
    start_dt = datetime.combine(parsed_date, parsed_time, tzinfo=LOCAL_TZ)
    end_dt = start_dt + timedelta(hours=duration_hours)

    return CalendarEvent(
        uid=f"{uuid.uuid4()}@cal-notion",
        summary=summary,
        start=start_dt.isoformat(),
        start_is_datetime=True,
        end=end_dt.isoformat(),
        end_is_datetime=True,
        source="manual",
    )

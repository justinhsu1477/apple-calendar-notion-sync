"""Apple iCloud CalDAV Provider。"""

import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import caldav
from icalendar import Calendar, Event as ICalEvent

from cal_notion.models import CalendarEvent
from cal_notion.providers.base import AuthenticationError, CalendarProvider

log = logging.getLogger(__name__)

CALDAV_URL = "https://caldav.icloud.com"
LOCAL_TZ = ZoneInfo("Asia/Taipei")

ICAL_STATUS_MAP = {
    "CONFIRMED": "Upcoming",
    "TENTATIVE": "Upcoming",
    "CANCELLED": "Cancelled",
}

# Notion status → iCal STATUS 反向映射
NOTION_TO_ICAL_STATUS = {
    "Upcoming": "CONFIRMED",
    "Completed": "CONFIRMED",
    "Cancelled": "CANCELLED",
}


class AppleCalendarProvider(CalendarProvider):
    """Apple iCloud CalDAV 行事曆 Provider（支援讀寫）。"""

    def __init__(self, username: str, password: str, **kwargs):
        self._username = username
        self._password = password
        self._client: caldav.DAVClient | None = None
        self._principal = None
        self._calendars_by_name: dict[str, caldav.Calendar] = {}

    @property
    def name(self) -> str:
        return "apple"

    @property
    def supports_write(self) -> bool:
        return True

    def authenticate(self) -> None:
        try:
            self._client = caldav.DAVClient(
                url=CALDAV_URL,
                username=self._username,
                password=self._password,
            )
            self._principal = self._client.principal()
            # 快取行事曆名稱對應，供寫入方法使用
            for cal in self._principal.calendars():
                name = cal.name or "Unknown"
                self._calendars_by_name[name] = cal
            log.info("iCloud CalDAV 認證成功")
        except Exception as e:
            raise AuthenticationError(f"iCloud 認證失敗: {e}") from e

    def list_calendars(self) -> list[str]:
        if self._principal is None:
            self.authenticate()
        return list(self._calendars_by_name.keys())

    def fetch_events(
        self,
        start: datetime,
        end: datetime,
        calendar_names: list[str] | None = None,
    ) -> list[CalendarEvent]:
        if self._principal is None:
            self.authenticate()

        events: list[CalendarEvent] = []

        for cal_name, cal in self._calendars_by_name.items():
            if calendar_names and cal_name not in calendar_names:
                continue

            log.info(f"讀取行事曆: {cal_name}")
            try:
                results = cal.search(start=start, end=end, event=True, expand=True)
            except Exception as e:
                log.warning(f"無法讀取 {cal_name}: {e}")
                continue

            for event_obj in results:
                parsed = self._parse_event(event_obj, cal_name)
                if parsed:
                    parsed.compute_content_hash()
                    events.append(parsed)

        log.info(f"共讀取 {len(events)} 個事件")
        return events

    # ── 寫入方法 ──────────────────────────────────────

    def create_event(self, event: CalendarEvent, calendar_name: str) -> str:
        """在指定行事曆建立新事件，回傳 UID。"""
        if self._principal is None:
            self.authenticate()

        cal = self._calendars_by_name.get(calendar_name)
        if cal is None:
            raise ValueError(f"找不到行事曆: {calendar_name}")

        uid = event.uid or f"{uuid.uuid4()}@cal-notion"
        ical_str = self._build_ical(event, uid)

        cal.save_event(ical_str)
        log.info(f"已建立事件: {event.summary} → {calendar_name}")
        return uid

    def update_event(self, event: CalendarEvent) -> None:
        """更新現有事件（依 UID 查找）。"""
        if self._principal is None:
            self.authenticate()

        cal = self._calendars_by_name.get(event.calendar_name)
        if cal is None:
            raise ValueError(f"找不到行事曆: {event.calendar_name}")

        try:
            existing = cal.event_by_uid(event.uid)
            existing.data = self._build_ical(event, event.uid)
            existing.save()
            log.info(f"已更新事件: {event.summary}")
        except Exception as e:
            log.error(f"更新事件失敗 {event.uid}: {e}")
            raise

    def delete_event(self, uid: str, calendar_name: str) -> None:
        """刪除指定事件。"""
        if self._principal is None:
            self.authenticate()

        cal = self._calendars_by_name.get(calendar_name)
        if cal is None:
            raise ValueError(f"找不到行事曆: {calendar_name}")

        try:
            existing = cal.event_by_uid(uid)
            existing.delete()
            log.info(f"已刪除事件: {uid}")
        except Exception as e:
            log.error(f"刪除事件失敗 {uid}: {e}")
            raise

    # ── 內部方法 ──────────────────────────────────────

    @staticmethod
    def _build_ical(event: CalendarEvent, uid: str) -> str:
        """從 CalendarEvent 建構 iCalendar 格式字串。"""
        cal = Calendar()
        cal.add("prodid", "-//cal-notion//EN")
        cal.add("version", "2.0")

        vevent = ICalEvent()
        vevent.add("uid", uid)
        vevent.add("summary", event.summary)

        if event.start:
            if event.start_is_datetime:
                dt = datetime.fromisoformat(event.start)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=LOCAL_TZ)
                vevent.add("dtstart", dt)
            else:
                from datetime import date
                vevent.add("dtstart", date.fromisoformat(event.start))

        if event.end:
            if event.end_is_datetime:
                dt = datetime.fromisoformat(event.end)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=LOCAL_TZ)
                vevent.add("dtend", dt)
            else:
                from datetime import date
                vevent.add("dtend", date.fromisoformat(event.end))

        if event.description:
            vevent.add("description", event.description)
        if event.location:
            vevent.add("location", event.location)

        ical_status = NOTION_TO_ICAL_STATUS.get(event.status, "CONFIRMED")
        vevent.add("status", ical_status)
        vevent.add("dtstamp", datetime.now(LOCAL_TZ))

        cal.add_component(vevent)
        return cal.to_ical().decode("utf-8")

    def _parse_event(self, event_obj, calendar_name: str) -> CalendarEvent | None:
        try:
            cal = Calendar.from_ical(event_obj.data)
        except Exception as e:
            log.warning(f"解析事件失敗: {e}")
            return None

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            uid = str(component.get("UID", ""))
            summary = str(component.get("SUMMARY", "（無標題）"))
            description = str(component.get("DESCRIPTION", ""))
            location = str(component.get("LOCATION", ""))
            status = str(component.get("STATUS", "CONFIRMED"))

            start_str, start_is_dt = self._normalize_dt(component.get("DTSTART"))
            end_str, end_is_dt = self._normalize_dt(component.get("DTEND"))

            last_modified = None
            lm = component.get("LAST-MODIFIED")
            if lm:
                lm_str, _ = self._normalize_dt(lm)
                last_modified = lm_str

            return CalendarEvent(
                uid=uid,
                summary=summary,
                description=description,
                location=location,
                start=start_str or "",
                start_is_datetime=start_is_dt,
                end=end_str,
                end_is_datetime=end_is_dt,
                calendar_name=calendar_name,
                status=ICAL_STATUS_MAP.get(status.upper(), "Upcoming"),
                last_modified=last_modified,
                source="calendar",
            )

        return None

    @staticmethod
    def _normalize_dt(dt_prop) -> tuple[str | None, bool]:
        if dt_prop is None:
            return None, False
        dt = dt_prop.dt
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=LOCAL_TZ)
            return dt.isoformat(), True
        return dt.isoformat(), False

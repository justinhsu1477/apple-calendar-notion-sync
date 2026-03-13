"""Apple iCloud CalDAV Provider。"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import caldav
from icalendar import Calendar

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


class AppleCalendarProvider(CalendarProvider):
    """Apple iCloud CalDAV 行事曆 Provider。"""

    def __init__(self, username: str, password: str, **kwargs):
        self._username = username
        self._password = password
        self._client: caldav.DAVClient | None = None
        self._principal = None

    @property
    def name(self) -> str:
        return "apple"

    def authenticate(self) -> None:
        try:
            self._client = caldav.DAVClient(
                url=CALDAV_URL,
                username=self._username,
                password=self._password,
            )
            self._principal = self._client.principal()
            log.info("iCloud CalDAV 認證成功")
        except Exception as e:
            raise AuthenticationError(f"iCloud 認證失敗: {e}") from e

    def list_calendars(self) -> list[str]:
        if self._principal is None:
            self.authenticate()
        calendars = self._principal.calendars()
        return [cal.name or "Unknown" for cal in calendars]

    def fetch_events(
        self,
        start: datetime,
        end: datetime,
        calendar_names: list[str] | None = None,
    ) -> list[CalendarEvent]:
        if self._principal is None:
            self.authenticate()

        calendars = self._principal.calendars()
        events: list[CalendarEvent] = []

        for cal in calendars:
            cal_name = cal.name or "Unknown"
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
                    events.append(parsed)

        log.info(f"共讀取 {len(events)} 個事件")
        return events

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

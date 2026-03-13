"""Google Calendar Provider。

需要額外安裝：pip install cal-notion[google]
"""

import logging
from datetime import datetime
from pathlib import Path

from cal_notion.models import CalendarEvent
from cal_notion.providers.base import AuthenticationError, CalendarProvider

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = Path.home() / ".cal-notion" / "google_token.json"

GOOGLE_STATUS_MAP = {
    "confirmed": "Upcoming",
    "tentative": "Upcoming",
    "cancelled": "Cancelled",
}

NOTION_TO_GOOGLE_STATUS = {
    "Upcoming": "confirmed",
    "Completed": "confirmed",
    "Cancelled": "cancelled",
}


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar API Provider（支援讀寫）。"""

    def __init__(self, credentials_file: str, **kwargs):
        self._credentials_file = credentials_file
        self._service = None

    @property
    def name(self) -> str:
        return "google"

    @property
    def supports_write(self) -> bool:
        return True

    def authenticate(self) -> None:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError:
            raise AuthenticationError(
                "Google Calendar 需要額外套件，請執行: pip install cal-notion[google]"
            )

        creds = None
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_FILE.write_text(creds.to_json())

        self._service = build("calendar", "v3", credentials=creds)
        log.info("Google Calendar 認證成功")

    def list_calendars(self) -> list[str]:
        if self._service is None:
            self.authenticate()
        result = self._service.calendarList().list().execute()
        return [cal["summary"] for cal in result.get("items", [])]

    def fetch_events(
        self,
        start: datetime,
        end: datetime,
        calendar_names: list[str] | None = None,
    ) -> list[CalendarEvent]:
        if self._service is None:
            self.authenticate()

        calendars = self._service.calendarList().list().execute().get("items", [])
        events: list[CalendarEvent] = []

        for cal in calendars:
            cal_name = cal["summary"]
            cal_id = cal["id"]

            if calendar_names and cal_name not in calendar_names:
                continue

            log.info(f"讀取行事曆: {cal_name}")
            try:
                result = self._service.events().list(
                    calendarId=cal_id,
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
            except Exception as e:
                log.warning(f"無法讀取 {cal_name}: {e}")
                continue

            for item in result.get("items", []):
                parsed = self._parse_event(item, cal_name)
                if parsed:
                    parsed.compute_content_hash()
                    events.append(parsed)

        log.info(f"共讀取 {len(events)} 個事件")
        return events

    # ── 寫入方法 ──────────────────────────────────────

    def create_event(self, event: CalendarEvent, calendar_name: str) -> str:
        if self._service is None:
            self.authenticate()

        cal_id = self._get_calendar_id(calendar_name)
        body = self._build_google_event(event)
        result = self._service.events().insert(calendarId=cal_id, body=body).execute()
        log.info(f"已建立事件: {event.summary} → {calendar_name}")
        return result.get("iCalUID", result["id"])

    def update_event(self, event: CalendarEvent) -> None:
        if self._service is None:
            self.authenticate()

        cal_id = self._get_calendar_id(event.calendar_name)
        event_id = event.provider_id
        if not event_id:
            # 用 iCalUID 查找 eventId
            event_id = self._find_event_id(cal_id, event.uid)
            if not event_id:
                raise ValueError(f"找不到事件: {event.uid}")

        body = self._build_google_event(event)
        self._service.events().update(
            calendarId=cal_id, eventId=event_id, body=body
        ).execute()
        log.info(f"已更新事件: {event.summary}")

    def delete_event(self, uid: str, calendar_name: str) -> None:
        if self._service is None:
            self.authenticate()

        cal_id = self._get_calendar_id(calendar_name)
        event_id = self._find_event_id(cal_id, uid)
        if event_id:
            self._service.events().delete(calendarId=cal_id, eventId=event_id).execute()
            log.info(f"已刪除事件: {uid}")

    # ── 內部方法 ──────────────────────────────────────

    def _get_calendar_id(self, calendar_name: str) -> str:
        """根據行事曆名稱取得 calendar ID。"""
        calendars = self._service.calendarList().list().execute().get("items", [])
        for cal in calendars:
            if cal["summary"] == calendar_name:
                return cal["id"]
        return "primary"

    def _find_event_id(self, cal_id: str, uid: str) -> str | None:
        """根據 iCalUID 查找 Google 的 eventId。"""
        try:
            result = self._service.events().list(
                calendarId=cal_id, iCalUID=uid
            ).execute()
            items = result.get("items", [])
            if items:
                return items[0]["id"]
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_event(item: dict, calendar_name: str) -> CalendarEvent | None:
        uid = item.get("iCalUID", item.get("id", ""))
        summary = item.get("summary", "（無標題）")
        description = item.get("description", "")
        location = item.get("location", "")
        status = item.get("status", "confirmed")

        start_raw = item.get("start", {})
        end_raw = item.get("end", {})

        if "dateTime" in start_raw:
            start = start_raw["dateTime"]
            start_is_dt = True
        elif "date" in start_raw:
            start = start_raw["date"]
            start_is_dt = False
        else:
            return None

        end = None
        end_is_dt = False
        if "dateTime" in end_raw:
            end = end_raw["dateTime"]
            end_is_dt = True
        elif "date" in end_raw:
            end = end_raw["date"]
            end_is_dt = False

        return CalendarEvent(
            uid=uid,
            summary=summary,
            start=start,
            start_is_datetime=start_is_dt,
            end=end,
            end_is_datetime=end_is_dt,
            description=description,
            location=location,
            calendar_name=calendar_name,
            status=GOOGLE_STATUS_MAP.get(status, "Upcoming"),
            last_modified=item.get("updated"),
            source="calendar",
            provider_id=item.get("id"),
        )

    @staticmethod
    def _build_google_event(event: CalendarEvent) -> dict:
        body: dict = {"summary": event.summary}

        if event.start_is_datetime:
            body["start"] = {"dateTime": event.start}
        else:
            body["start"] = {"date": event.start}

        if event.end:
            if event.end_is_datetime:
                body["end"] = {"dateTime": event.end}
            else:
                body["end"] = {"date": event.end}
        else:
            body["end"] = body["start"]

        if event.description:
            body["description"] = event.description
        if event.location:
            body["location"] = event.location

        body["status"] = NOTION_TO_GOOGLE_STATUS.get(event.status, "confirmed")
        return body

"""事件資料模型。"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CalendarEvent:
    """統一的行事曆事件格式，所有 Provider 都輸出這個。"""

    uid: str
    summary: str
    start: str  # ISO-8601
    start_is_datetime: bool = True
    end: str | None = None
    end_is_datetime: bool = True
    description: str = ""
    location: str = ""
    calendar_name: str = ""
    status: str = "Upcoming"  # Upcoming / Completed / Cancelled
    last_modified: str | None = None  # ISO-8601, 用於增量同步

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "summary": self.summary,
            "start": self.start,
            "start_is_datetime": self.start_is_datetime,
            "end": self.end,
            "end_is_datetime": self.end_is_datetime,
            "description": self.description,
            "location": self.location,
            "calendar_name": self.calendar_name,
            "status": self.status,
            "last_modified": self.last_modified,
        }

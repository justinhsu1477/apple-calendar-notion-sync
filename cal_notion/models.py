"""事件資料模型。"""

import hashlib
from dataclasses import dataclass


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
    last_modified: str | None = None  # ISO-8601, 用於增量同步與衝突比較
    source: str = "calendar"  # "calendar" 或 "notion"，標記事件來源
    notion_page_id: str | None = None  # Notion page ID（雙向同步用）
    provider_id: str | None = None  # Provider 原生 ID（如 Google eventId）
    content_hash: str | None = None  # 內容 hash，用於變更偵測

    def compute_content_hash(self) -> str:
        """計算可變欄位的 SHA-256 hash，用於偵測實際內容變更。

        不依賴時間戳（時間戳跨系統可能不一致），
        而是直接 hash 內容來判斷「資料是否真的改了」。
        """
        content = "|".join([
            self.summary,
            self.start or "",
            self.end or "",
            self.description,
            self.location,
            self.status,
        ])
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.content_hash

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
            "source": self.source,
            "notion_page_id": self.notion_page_id,
            "provider_id": self.provider_id,
            "content_hash": self.content_hash,
        }

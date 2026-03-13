"""CalendarProvider 抽象介面。

所有行事曆來源（Apple、Google、Outlook 等）都必須實作這個介面。
這讓系統可以用統一的方式操作不同來源，也讓社群能輕鬆貢獻新的 Provider。

使用方式（唯讀）：
    class MyProvider(CalendarProvider):
        def authenticate(self) -> None: ...
        def fetch_events(self, start, end) -> list[CalendarEvent]: ...
        def list_calendars(self) -> list[str]: ...

使用方式（讀寫）：
    class MyWritableProvider(CalendarProvider):
        @property
        def supports_write(self) -> bool:
            return True
        def create_event(self, event, calendar_name) -> str: ...
        def update_event(self, event) -> None: ...
        def delete_event(self, uid, calendar_name) -> None: ...
"""

from abc import ABC, abstractmethod
from datetime import datetime

from cal_notion.models import CalendarEvent


class CalendarProvider(ABC):
    """行事曆來源的統一抽象介面。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名稱，例如 'apple', 'google'。"""
        ...

    @abstractmethod
    def authenticate(self) -> None:
        """驗證連線。驗證失敗應拋出 AuthenticationError。"""
        ...

    @abstractmethod
    def fetch_events(
        self,
        start: datetime,
        end: datetime,
        calendar_names: list[str] | None = None,
    ) -> list[CalendarEvent]:
        """取得指定時間範圍內的事件。

        Args:
            start: 開始時間（含）
            end: 結束時間（含）
            calendar_names: 只取特定行事曆，None 表示全部

        Returns:
            CalendarEvent 列表
        """
        ...

    @abstractmethod
    def list_calendars(self) -> list[str]:
        """列出此帳號下所有行事曆名稱。"""
        ...

    # ── 寫入介面（可選實作）──────────────────────────────

    @property
    def supports_write(self) -> bool:
        """此 Provider 是否支援寫入事件。預設 False。"""
        return False

    def create_event(self, event: CalendarEvent, calendar_name: str) -> str:
        """在指定行事曆建立新事件。

        Args:
            event: 要建立的事件
            calendar_name: 目標行事曆名稱

        Returns:
            新事件的 UID
        """
        raise NotImplementedError(f"{self.name} provider 不支援寫入")

    def update_event(self, event: CalendarEvent) -> None:
        """更新現有事件。依 event.uid 查找並更新。"""
        raise NotImplementedError(f"{self.name} provider 不支援寫入")

    def delete_event(self, uid: str, calendar_name: str) -> None:
        """刪除指定事件。

        Args:
            uid: 事件 UID
            calendar_name: 事件所在行事曆名稱
        """
        raise NotImplementedError(f"{self.name} provider 不支援寫入")


class AuthenticationError(Exception):
    """認證失敗時拋出。"""

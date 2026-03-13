from cal_notion.providers.base import CalendarProvider
from cal_notion.providers.apple import AppleCalendarProvider

PROVIDERS: dict[str, type[CalendarProvider]] = {
    "apple": AppleCalendarProvider,
}


def get_provider(name: str, **kwargs) -> CalendarProvider:
    """根據名稱取得 CalendarProvider 實例。"""
    cls = PROVIDERS.get(name)
    if cls is None:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(f"Unknown provider: {name}. Available: {available}")
    return cls(**kwargs)

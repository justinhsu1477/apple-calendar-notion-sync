from cal_notion.providers.base import CalendarProvider
from cal_notion.providers.apple import AppleCalendarProvider

PROVIDERS: dict[str, type[CalendarProvider]] = {
    "apple": AppleCalendarProvider,
}

# Google Provider（需額外安裝 pip install cal-notion[google]）
try:
    from cal_notion.providers.google import GoogleCalendarProvider
    PROVIDERS["google"] = GoogleCalendarProvider
except ImportError:
    pass


def get_provider(name: str, config: dict | None = None, **kwargs) -> CalendarProvider:
    """根據名稱取得 CalendarProvider 實例。

    Args:
        name: Provider 名稱（apple, google）
        config: Provider 設定 dict（來自 Config.get_provider_config()）
        **kwargs: 向後相容的直接參數
    """
    cls = PROVIDERS.get(name)
    if cls is None:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(f"Unknown provider: {name}. Available: {available}")

    if config:
        return cls(**config)
    return cls(**kwargs)

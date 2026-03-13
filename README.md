# cal-notion

將行事曆事件自動同步到 Notion 資料庫。支援多種行事曆來源，透過統一的 Provider 介面擴展。

## 功能

- **多來源支援** — 透過 `CalendarProvider` 介面，可擴展支援任意行事曆來源
- **Apple iCloud** — 內建 CalDAV Provider，直接連接 iCloud
- **增量同步** — 只同步有變更的事件，提升效能
- **刪除偵測** — iCloud 刪除的事件會在 Notion 自動標記為 Cancelled
- **CLI 工具** — 完整的命令列介面，支援 `sync`、`setup`、`status` 等指令
- **UID 去重** — 同一事件不會重複建立

## 架構

```
┌─────────────────────────────────────────┐
│           CalendarProvider (ABC)        │ ← 統一介面
├──────────┬──────────┬───────────────────┤
│  Apple   │  Google  │   Outlook  ...    │ ← 各來源實作
│ (CalDAV) │  (API)   │   (Graph)         │
└────┬─────┴────┬─────┴────┬──────────────┘
     │          │          │
     └──────────┼──────────┘
                ↓
        CalendarEvent (統一資料模型)
                ↓
         NotionSync (同步引擎)
                ↓
         Notion Database
```

## 安裝

### 方法一：pip install（推薦）

```bash
git clone https://github.com/justinhsu1477/apple-calendar-notion-sync.git
cd apple-calendar-notion-sync
pip install -e .
```

安裝後可直接使用 `cal-notion` 指令。

### 方法二：直接執行

```bash
pip install -r requirements.txt
python -m cal_notion.cli sync
```

## 快速開始

### 1. 前置準備

**Apple App-Specific Password：**
1. 前往 [appleid.apple.com](https://appleid.apple.com)
2. 登入 → 登入與安全性 → App 專用密碼 → 產生

**Notion Integration Token：**
1. 前往 [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. 建立新的 Integration，取得 token
3. 在 Notion 開啟目標資料庫 → `⋯` → Connections → 加入 Integration

### 2. 互動式設定

```bash
cal-notion setup
```

依照提示輸入 Apple ID、密碼、Notion Token 等資訊。設定會儲存在 `~/.cal-notion/config.json`。

### 3. 開始同步

```bash
cal-notion sync
```

## CLI 指令

```bash
cal-notion sync        # 同步行事曆到 Notion
cal-notion sync -f     # 強制全量同步（忽略增量檢查）
cal-notion setup       # 互動式設定
cal-notion status      # 查看同步狀態
cal-notion calendars   # 列出帳號下所有行事曆
cal-notion providers   # 列出支援的行事曆來源
cal-notion reset       # 重置同步狀態
```

## Notion 資料庫欄位

| 欄位名稱     | 類型       | 說明                                    |
|-------------|-----------|----------------------------------------|
| Event Name  | Title     | 事件名稱                                 |
| Start Date  | Date      | 開始時間                                 |
| End Date    | Date      | 結束時間                                 |
| Location    | Rich Text | 地點                                    |
| Description | Rich Text | 描述                                    |
| Calendar    | Select    | 行事曆分類（Personal / Work / Other）      |
| Status      | Select    | 狀態（Upcoming / Completed / Cancelled）  |
| UID         | Rich Text | CalDAV 事件唯一識別碼（用於去重）             |

## 自訂 Provider（擴展新的行事曆來源）

實作 `CalendarProvider` 介面即可：

```python
from cal_notion.providers.base import CalendarProvider
from cal_notion.models import CalendarEvent

class GoogleCalendarProvider(CalendarProvider):
    @property
    def name(self) -> str:
        return "google"

    def authenticate(self) -> None:
        # Google OAuth 認證邏輯
        ...

    def fetch_events(self, start, end, calendar_names=None) -> list[CalendarEvent]:
        # 呼叫 Google Calendar API
        ...

    def list_calendars(self) -> list[str]:
        # 列出 Google 行事曆
        ...
```

然後在 `cal_notion/providers/__init__.py` 註冊：

```python
PROVIDERS["google"] = GoogleCalendarProvider
```

## 排程自動同步

```bash
crontab -e
```

```
0 * * * * cal-notion sync
```

## 專案結構

```
cal_notion/
├── __init__.py          # 版本資訊
├── cli.py               # CLI 入口（typer）
├── config.py            # 設定管理
├── models.py            # CalendarEvent 資料模型
├── notion_sync.py       # Notion 同步引擎
├── sync_state.py        # 增量同步狀態追蹤
└── providers/
    ├── __init__.py      # Provider 註冊表
    ├── base.py          # CalendarProvider 抽象介面
    └── apple.py         # Apple iCloud CalDAV 實作
```

## Tech Stack

- Python 3.11+
- [caldav](https://github.com/python-caldav/caldav) — CalDAV 協議操作
- [icalendar](https://github.com/collective/icalendar) — iCal 格式解析
- [notion-client](https://github.com/ramnes/notion-sdk-py) — Notion API SDK
- [typer](https://github.com/tiangolo/typer) — CLI 框架

## Contributing

歡迎貢獻！特別是以下方向：
- 新增 Provider（Google Calendar、Outlook 等）
- 雙向同步支援
- Recurring Events（RRULE）處理
- Docker 化部署

## License

MIT

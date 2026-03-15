# cal-notion

行事曆與 Notion 的雙向同步工具。支援 Apple iCloud (CalDAV)、Google Calendar (API)，透過統一的 Provider 介面可擴展任意來源。

## 功能

- **雙向同步** — Calendar ↔ Notion，任一端修改都會同步到另一端
- **多來源支援** — Apple iCloud、Google Calendar，可擴展
- **智慧變更偵測** — content hash + three-way merge，只同步有改動的事件
- **衝突解決** — newest_wins / calendar_wins / notion_wins
- **背景服務** — macOS LaunchAgent 自動定時同步
- **CLI 工具** — 完整命令列介面

## 架構

```
CalendarProvider (Strategy Pattern)
  ├── Apple (CalDAV)
  └── Google (Calendar API)
          │
          ▼
    CalendarEvent (統一資料模型)
          │
          ▼
  BidirectionalSyncEngine (three-way merge)
          │
          ▼
    NotionSync ←→ Notion Database
```

## 安裝

```bash
git clone https://github.com/justinhsu1477/apple-calendar-notion-sync.git
cd apple-calendar-notion-sync
pip install -e .

# Google Calendar 額外安裝
pip install -e ".[google]"
```

## 快速開始

### 1. 前置準備

| 來源 | 步驟 |
|------|------|
| **Apple** | [appleid.apple.com](https://appleid.apple.com) → 登入與安全性 → App 專用密碼 |
| **Google** | [Cloud Console](https://console.cloud.google.com/) → OAuth 2.0 credentials → 下載 `credentials.json` |
| **Notion** | [notion.so/my-integrations](https://www.notion.so/my-integrations) → 建立 Integration → 到資料庫 `⋯` → Connections 加入 |

### 2. 設定並同步

```bash
cal-notion setup                          # 互動式設定
cal-notion sync                           # 單向同步（Calendar → Notion）
cal-notion sync -d bidirectional          # 雙向同步
cal-notion sync --force                   # 強制全量同步
```

### 3. 背景服務

```bash
cal-notion daemon start                   # 啟動（每 15 分鐘自動同步）
cal-notion daemon stop                    # 停止
cal-notion daemon status                  # 查看狀態
cal-notion daemon logs                    # 查看日誌
```

## CLI 指令

| 指令 | 說明 |
|------|------|
| `cal-notion sync [-d direction] [-f] [--conflict strategy]` | 同步事件 |
| `cal-notion setup` | 互動式設定 |
| `cal-notion status` | 查看同步狀態 |
| `cal-notion calendars` | 列出行事曆 |
| `cal-notion providers` | 列出支援的來源 |
| `cal-notion reset` | 重置同步狀態 |
| `cal-notion daemon start/stop/status/logs` | 背景服務管理 |

## 同步原理

使用 **content hash + three-way merge**，對每個事件比對 Calendar 側、Notion 側、上次同步的 baseline：

| 情境 | 動作 |
|------|------|
| 兩邊 hash 都沒變 | 略過 |
| Calendar 變了、Notion 沒變 | Calendar → Notion |
| Notion 變了、Calendar 沒變 | Notion → Calendar |
| 兩邊都變了 | 依衝突策略解決 |
| 只存在一邊（無 baseline） | 新事件，建到另一邊 |
| 只存在一邊（有 baseline） | 對方刪除了，同步刪除 |

## 自訂 Provider

實作 `CalendarProvider` 介面即可擴展新來源：

```python
from cal_notion.providers.base import CalendarProvider
from cal_notion.models import CalendarEvent

class OutlookProvider(CalendarProvider):
    @property
    def name(self) -> str:
        return "outlook"

    def authenticate(self) -> None: ...
    def fetch_events(self, start, end, calendar_names=None) -> list[CalendarEvent]: ...
    def list_calendars(self) -> list[str]: ...

    # 可選：實作寫入支援
    @property
    def supports_write(self) -> bool:
        return True
    def create_event(self, event, calendar_name) -> str: ...
    def update_event(self, event) -> None: ...
    def delete_event(self, uid, calendar_name) -> None: ...
```

## Tech Stack

Python 3.11+ / [caldav](https://github.com/python-caldav/caldav) / [icalendar](https://github.com/collective/icalendar) / [notion-client](https://github.com/ramnes/notion-sdk-py) / [typer](https://github.com/tiangolo/typer) / [google-api-python-client](https://github.com/googleapis/google-api-python-client) (optional)

## Contributing

歡迎貢獻！特別是新 Provider (Outlook, CalDAV 通用)、Recurring Events (RRULE) 處理、Docker 部署。

## License

MIT

# cal-notion

行事曆與 Notion 的雙向同步工具。支援 Apple iCloud、Google Calendar，透過統一的 Provider 介面可擴展任意來源。

## 功能

- **雙向同步** — Calendar ↔ Notion，在任一端修改都會同步到另一端
- **多來源支援** — Apple iCloud (CalDAV)、Google Calendar (API)，可擴展
- **衝突解決** — 支援 newest_wins / calendar_wins / notion_wins 策略
- **增量同步** — 用 content hash 偵測變更，只同步有改動的事件
- **刪除偵測** — 任一端刪除事件會自動同步到另一端
- **背景服務** — macOS LaunchAgent，自動定時同步
- **CLI 工具** — 完整命令列介面

## 架構

```
┌─────────────────────────────────────────┐
│          CalendarProvider (ABC)          │
│   authenticate / fetch / create / update / delete
├──────────┬──────────────────────────────┤
│  Apple   │        Google               │
│ (CalDAV) │   (Calendar API)            │
└────┬─────┴────┬─────────────────────────┘
     └──────────┘
          ↓
   CalendarEvent (統一資料模型)
          ↓
  BidirectionalSyncEngine
    ├── content hash 比對 (three-way merge)
    ├── 衝突解決策略
    └── 新增 / 更新 / 刪除 分類
          ↓
     NotionSync ←→ Notion Database
```

## 安裝

```bash
git clone https://github.com/justinhsu1477/apple-calendar-notion-sync.git
cd apple-calendar-notion-sync
pip install -e .
```

Google Calendar 額外安裝：
```bash
pip install -e ".[google]"
```

## 快速開始

### 1. 前置準備

**Apple Calendar：**
1. [appleid.apple.com](https://appleid.apple.com) → 登入與安全性 → App 專用密碼 → 產生

**Google Calendar：**
1. [Google Cloud Console](https://console.cloud.google.com/) → 建立 OAuth 2.0 credentials → 下載 `credentials.json`

**Notion：**
1. [notion.so/my-integrations](https://www.notion.so/my-integrations) → 建立 Integration
2. 在 Notion 資料庫 → `⋯` → Connections → 加入 Integration

### 2. 設定

```bash
cal-notion setup
```

### 3. 同步

```bash
# 單向同步（行事曆 → Notion）
cal-notion sync

# 雙向同步
cal-notion sync --direction bidirectional

# 強制全量同步
cal-notion sync --force
```

## CLI 指令

```bash
cal-notion sync [OPTIONS]         # 同步事件
  --direction / -d                #   calendar_to_notion / bidirectional / notion_to_calendar
  --force / -f                    #   強制全量同步
  --conflict                      #   newest_wins / calendar_wins / notion_wins

cal-notion setup                  # 互動式設定
cal-notion status                 # 查看同步狀態
cal-notion calendars              # 列出行事曆
cal-notion providers              # 列出支援的來源
cal-notion reset                  # 重置同步狀態

cal-notion daemon start           # 啟動背景服務
cal-notion daemon stop            # 停止背景服務
cal-notion daemon status          # 查看服務狀態
cal-notion daemon logs            # 查看服務日誌
```

## 雙向同步原理

使用 **content hash + three-way merge** 偵測變更：

| Calendar 側 | Notion 側 | Baseline | 動作 |
|-------------|-----------|----------|------|
| hash 相同 | hash 相同 | 存在 | 略過 |
| hash 不同 | hash 相同 | 存在 | Calendar → Notion |
| hash 相同 | hash 不同 | 存在 | Notion → Calendar |
| 都不同 | — | 存在 | 衝突（依策略解決） |
| 存在 | 不存在 | 不存在 | 新事件 → 建到 Notion |
| 不存在 | 存在 | 不存在 | 新事件 → 建到 Calendar |

## 自訂 Provider

實作 `CalendarProvider` 介面：

```python
from cal_notion.providers.base import CalendarProvider
from cal_notion.models import CalendarEvent

class OutlookProvider(CalendarProvider):
    @property
    def name(self) -> str:
        return "outlook"

    @property
    def supports_write(self) -> bool:
        return True

    def authenticate(self) -> None: ...
    def fetch_events(self, start, end, calendar_names=None) -> list[CalendarEvent]: ...
    def list_calendars(self) -> list[str]: ...
    def create_event(self, event, calendar_name) -> str: ...
    def update_event(self, event) -> None: ...
    def delete_event(self, uid, calendar_name) -> None: ...
```

## 專案結構

```
cal_notion/
├── __init__.py           # 版本
├── cli.py                # CLI（typer）
├── config.py             # 設定管理
├── models.py             # CalendarEvent + content hash
├── notion_sync.py        # Notion 讀寫
├── sync_engine.py        # 雙向同步引擎 + 衝突解決
├── sync_state.py         # 同步狀態追蹤（v2 three-way merge）
├── daemon.py             # 背景同步服務
├── launchd.py            # macOS LaunchAgent 管理
└── providers/
    ├── __init__.py       # Provider 註冊表
    ├── base.py           # CalendarProvider 抽象介面
    ├── apple.py          # Apple iCloud CalDAV（讀寫）
    └── google.py         # Google Calendar API（讀寫）
```

## Tech Stack

- Python 3.11+
- [caldav](https://github.com/python-caldav/caldav) — CalDAV
- [icalendar](https://github.com/collective/icalendar) — iCal 解析
- [notion-client](https://github.com/ramnes/notion-sdk-py) — Notion API
- [typer](https://github.com/tiangolo/typer) — CLI
- [google-api-python-client](https://github.com/googleapis/google-api-python-client) — Google Calendar（optional）

## Contributing

歡迎貢獻！特別是：
- 新 Provider（Outlook、CalDAV 通用等）
- Recurring Events（RRULE）處理
- Docker 化部署
- Web UI dashboard

## License

MIT

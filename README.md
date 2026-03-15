# cal-notion

Apple Calendar (iCloud CalDAV) 與 Notion 的雙向同步工具。自動將行事曆事件同步到 Notion 資料庫，支援 Google Calendar，透過 Provider 介面可擴展。

## 功能

- **雙向同步** — Calendar ↔ Notion，任一端修改都會同步
- **多來源支援** — Apple iCloud (CalDAV)、Google Calendar (API)
- **智慧變更偵測** — content hash + three-way merge，只同步有改動的事件
- **衝突解決** — newest_wins / calendar_wins / notion_wins
- **背景服務** — macOS LaunchAgent 每 15 分鐘自動同步
- **CLI 工具** — 完整命令列介面

## Notion 資料庫欄位

對應 Notion「行程摘要」資料庫：

| Notion 欄位 | 類型 | 來源 |
|-------------|------|------|
| 名稱 | title | 事件標題 |
| 開始 | date | 開始時間 |
| 結束 | date | 結束時間 |
| 備註 | text | 事件描述 |
| 類別 | select | 工作 / 專案 / 生活 |
| 來源 | select | Apple Calendar |
| UID | text | 同步配對用（需手動新增） |

> **注意**：資料庫需要手動新增 **UID** 欄位（文字類型），用於配對行事曆與 Notion 事件。

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
    NotionSync ←→ Notion 行程摘要
```

## 安裝

```bash
git clone https://github.com/justinhsu1477/apple-calendar-notion-sync.git
cd apple-calendar-notion-sync
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Google Calendar 額外安裝
pip install -e ".[google]"
```

## 快速開始

### 1. 前置準備

| 項目 | 步驟 |
|------|------|
| **Apple App 專用密碼** | [appleid.apple.com](https://appleid.apple.com) → 登入與安全性 → App 專用密碼 |
| **Notion Integration** | [notion.so/my-integrations](https://www.notion.so/my-integrations) → 建立 Internal Integration |
| **連結資料庫** | 到「行程摘要」→ `⋯` → Connections → 加入 Integration |
| **新增 UID 欄位** | 在「行程摘要」資料庫新增一個「UID」文字欄位 |

### 2. 設定並同步

```bash
cal-notion setup                          # 互動式設定
cal-notion sync                           # Calendar → Notion
cal-notion sync -d bidirectional          # 雙向同步
cal-notion sync --force                   # 強制全量同步
```

### 3. 背景服務

```bash
cal-notion daemon start                   # 啟動
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

使用 **content hash + three-way merge**：

| 情境 | 動作 |
|------|------|
| 兩邊都沒變 | 略過 |
| Calendar 變了 | Calendar → Notion |
| Notion 變了 | Notion → Calendar |
| 兩邊都變了 | 依衝突策略解決 |
| 只存在一邊（新事件） | 建到另一邊 |
| 只存在一邊（有 baseline） | 同步刪除 |

## 自訂 Provider

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
```

## Tech Stack

Python 3.11+ / [caldav](https://github.com/python-caldav/caldav) / [icalendar](https://github.com/collective/icalendar) / [notion-client](https://github.com/ramnes/notion-sdk-py) / [typer](https://github.com/tiangolo/typer)

## License

MIT

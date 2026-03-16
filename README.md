# cal-notion

Apple Calendar (iCloud CalDAV) 與 Notion 的雙向同步工具，內建 AI 智慧分析。自動將行事曆事件同步到 Notion 資料庫，支援 Google Calendar，透過 Provider 介面可擴展。

## 功能

### 核心同步
- **雙向同步** — Calendar ↔ Notion，任一端修改都會同步
- **多來源支援** — Apple iCloud (CalDAV)、Google Calendar (API)
- **智慧變更偵測** — content hash + three-way merge，只同步有改動的事件
- **衝突解決** — newest_wins / calendar_wins / notion_wins
- **背景服務** — macOS LaunchAgent 自動定時同步
- **Dry-run 模式** — 預覽同步結果，不實際寫入
- **行事曆篩選** — 只同步指定行事曆
- **重試機制** — API 失敗自動指數退避重試
- **同步鎖定** — 防止多個同步程序同時執行

### 智慧功能
- **時間分析報表** — 週報/月報，按類別統計時間分佈
- **自然語言新增** — `cal-notion add "週五下午3點 和 Sam 喝咖啡"`
- **Web 儀表板** — 即時查看同步狀態、事件統計
- **同步通知** — LINE Notify / Slack Webhook

### AI 功能 (Claude API)
- **AI 自動分類** — 根據事件標題智慧判斷類別
- **AI 時間洞察** — 個人化時間管理建議
- **AI 週報生成** — 自動產出完整週報
- **AI 重複偵測** — 找出可能重複的事件
- **時間成本計算** — 依費率計算每個事件的成本

## Notion 資料庫欄位

對應 Notion「行程摘要」資料庫：

| Notion 欄位 | 類型 | 來源 |
|-------------|------|------|
| 名稱 | title | 事件標題 |
| 開始 | date | 開始時間 |
| 結束 | date | 結束時間 |
| 備註 | text | 事件描述 |
| 類別 | select | iOS 行事曆名稱映射 |
| 來源 | select | Apple Calendar |
| UID | text | 同步配對用（需手動新增） |

## 安裝

```bash
git clone https://github.com/justinhsu1477/apple-calendar-notion-sync.git
cd apple-calendar-notion-sync
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 可選安裝
pip install -e ".[google]"    # Google Calendar 支援
pip install -e ".[web]"       # Web 儀表板
pip install -e ".[ai]"        # AI 功能 (Claude API)
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
cal-notion setup                              # 互動式設定
cal-notion sync                               # Calendar → Notion
cal-notion sync -d bidirectional              # 雙向同步
cal-notion sync --force                       # 強制全量同步
cal-notion sync --dry-run                     # 預覽不寫入
cal-notion sync -c "工作,生活"                  # 只同步指定行事曆
cal-notion sync --from 2025-01-01 --to 2026-12-31  # 指定日期範圍
```

### 3. 背景服務

```bash
cal-notion daemon start                       # 啟動
cal-notion daemon stop                        # 停止
cal-notion daemon status                      # 查看狀態
cal-notion daemon logs                        # 查看日誌
```

## CLI 完整指令

| 指令 | 說明 |
|------|------|
| `cal-notion sync` | 同步事件 (`--dry-run`, `-c`, `--from`, `--to`, `-f`, `-d`, `--conflict`) |
| `cal-notion setup` | 互動式設定 |
| `cal-notion status` | 查看同步狀態 |
| `cal-notion calendars` | 列出行事曆 |
| `cal-notion add "事件描述"` | 自然語言新增事件 |
| `cal-notion analytics [-p week/month/all]` | 時間分析報表 |
| `cal-notion dashboard` | 啟動 Web 儀表板 (port 5566) |
| `cal-notion ai classify` | AI 事件分類 |
| `cal-notion ai insights` | AI 時間洞察 |
| `cal-notion ai report` | AI 週報生成 |
| `cal-notion ai duplicates` | AI 重複偵測 |
| `cal-notion ai cost [-r 費率]` | 時間成本計算 |
| `cal-notion daemon start/stop/status/logs` | 背景服務管理 |
| `cal-notion reset` | 重置同步狀態 |

## .env 設定

```bash
# 必填
APPLE_ID=your@icloud.com
APPLE_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
NOTION_TOKEN=ntn_xxxxx
NOTION_DATABASE_ID=76691a8515d14dc29e5b8c42361e23d7

# AI 功能 (選填)
ANTHROPIC_API_KEY=sk-ant-xxxxx

# 通知 (選填)
LINE_NOTIFY_TOKEN=xxxxx
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxxxx
```

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
          │
    ┌─────┼─────────┐
    ▼     ▼         ▼
Analytics  AI     Web Dashboard
```

## 測試

```bash
pytest tests/ -v    # 106 tests
```

## Tech Stack

Python 3.11+ / caldav / icalendar / notion-client / typer / Flask / Anthropic Claude API

## License

MIT

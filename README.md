# Apple Calendar → Notion Sync

將 Apple 行事曆（iCloud CalDAV）的事件自動同步到 Notion 資料庫。

## 功能

- 透過 CalDAV 協議直接連接 iCloud，讀取所有行事曆事件
- 同步至 Notion 資料庫，包含事件名稱、時間、地點、描述、行事曆分類
- 以事件 UID 去重，避免重複建立
- 已存在的事件會自動更新，新事件自動新增
- 可自訂同步的時間範圍（預設過去 7 天 + 未來 30 天）

## 架構

```
Apple Calendar (iCloud)
    ↓ CalDAV Protocol
Python Script (caldav + icalendar)
    ↓ Notion API
Notion Database
```

## 前置準備

### 1. Apple App-Specific Password

1. 前往 [appleid.apple.com](https://appleid.apple.com)
2. 登入 → 登入與安全性 → App 專用密碼
3. 點選「產生」，取得一組密碼（格式：`xxxx-xxxx-xxxx-xxxx`）

### 2. Notion Integration Token

1. 前往 [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. 建立新的 Integration，取得 `secret_xxx` token
3. 在 Notion 中開啟目標資料庫 → 點右上角 `⋯` → Connections → 加入你建立的 Integration

### 3. Notion 資料庫

建立一個 Notion 資料庫，包含以下欄位：

| 欄位名稱     | 類型       | 說明                          |
|-------------|-----------|-------------------------------|
| Event Name  | Title     | 事件名稱                       |
| Start Date  | Date      | 開始時間                       |
| End Date    | Date      | 結束時間                       |
| Location    | Rich Text | 地點                          |
| Description | Rich Text | 描述                          |
| Calendar    | Select    | 行事曆分類（Personal / Work / Other） |
| Status      | Select    | 狀態（Upcoming / Completed / Cancelled） |
| UID         | Rich Text | CalDAV 事件唯一識別碼（用於去重）    |

## 安裝

```bash
git clone https://github.com/justinhsu1477/apple-calendar-notion-sync.git
cd apple-calendar-notion-sync
pip install -r requirements.txt
```

## 設定

```bash
cp .env.example .env
```

編輯 `.env` 填入你的認證資訊：

```env
APPLE_ID=your_apple_id@icloud.com
APPLE_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
NOTION_TOKEN=secret_xxxxxxxx
NOTION_DATABASE_ID=your_database_id
SYNC_DAYS_BACK=7
SYNC_DAYS_FORWARD=30
```

## 使用

```bash
python sync_calendar.py
```

### 設定排程自動執行（macOS cron）

```bash
crontab -e
```

加入以下內容（每小時同步一次）：

```
0 * * * * cd /path/to/apple-calendar-notion-sync && /usr/bin/python3 sync_calendar.py
```

## Tech Stack

- Python 3.11+
- [caldav](https://github.com/python-caldav/caldav) — CalDAV 協議操作
- [icalendar](https://github.com/collective/icalendar) — iCal 格式解析
- [notion-client](https://github.com/ramnes/notion-sdk-py) — Notion API SDK

## License

MIT

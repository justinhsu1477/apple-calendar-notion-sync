"""
Apple Calendar (iCloud CalDAV) → Notion 同步腳本
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import caldav
from icalendar import Calendar
from notion_client import Client as NotionClient
from dotenv import load_dotenv

load_dotenv()

# ── 設定 ──────────────────────────────────────────────
APPLE_ID = os.getenv("APPLE_ID")
APPLE_APP_PASSWORD = os.getenv("APPLE_APP_PASSWORD")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
SYNC_DAYS_BACK = int(os.getenv("SYNC_DAYS_BACK", 7))
SYNC_DAYS_FORWARD = int(os.getenv("SYNC_DAYS_FORWARD", 30))
LOCAL_TZ = ZoneInfo("Asia/Taipei")

CALDAV_URL = "https://caldav.icloud.com"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── CalDAV：讀取 iCloud 行事曆事件 ──────────────────────
def fetch_apple_events() -> list[dict]:
    """從 iCloud CalDAV 讀取指定時間範圍內的事件。"""
    client = caldav.DAVClient(
        url=CALDAV_URL,
        username=APPLE_ID,
        password=APPLE_APP_PASSWORD,
    )
    principal = client.principal()
    calendars = principal.calendars()

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=SYNC_DAYS_BACK)
    end = now + timedelta(days=SYNC_DAYS_FORWARD)

    events = []
    for cal in calendars:
        cal_name = cal.name or "Unknown"
        log.info(f"讀取行事曆: {cal_name}")

        try:
            results = cal.search(
                start=start,
                end=end,
                event=True,
                expand=True,
            )
        except Exception as e:
            log.warning(f"無法讀取 {cal_name}: {e}")
            continue

        for event_obj in results:
            parsed = _parse_event(event_obj, cal_name)
            if parsed:
                events.append(parsed)

    log.info(f"共讀取 {len(events)} 個事件")
    return events


def _parse_event(event_obj, calendar_name: str) -> dict | None:
    """解析單一 CalDAV 事件為 dict。"""
    try:
        cal = Calendar.from_ical(event_obj.data)
    except Exception as e:
        log.warning(f"解析事件失敗: {e}")
        return None

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        uid = str(component.get("UID", ""))
        summary = str(component.get("SUMMARY", "（無標題）"))
        description = str(component.get("DESCRIPTION", ""))
        location = str(component.get("LOCATION", ""))

        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        status = str(component.get("STATUS", "CONFIRMED"))

        start_dt, start_is_datetime = _normalize_dt(dtstart)
        end_dt, end_is_datetime = _normalize_dt(dtend)

        return {
            "uid": uid,
            "summary": summary,
            "description": description,
            "location": location,
            "start": start_dt,
            "start_is_datetime": start_is_datetime,
            "end": end_dt,
            "end_is_datetime": end_is_datetime,
            "calendar": calendar_name,
            "status": _map_status(status),
        }

    return None


def _normalize_dt(dt_prop) -> tuple[str | None, bool]:
    """將 icalendar 的日期/時間轉為 ISO 字串。"""
    if dt_prop is None:
        return None, False

    dt = dt_prop.dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LOCAL_TZ)
        return dt.isoformat(), True
    else:
        # date only
        return dt.isoformat(), False


def _map_status(ical_status: str) -> str:
    """將 iCal STATUS 對應到 Notion select 值。"""
    mapping = {
        "CONFIRMED": "Upcoming",
        "TENTATIVE": "Upcoming",
        "CANCELLED": "Cancelled",
    }
    return mapping.get(ical_status.upper(), "Upcoming")


# ── Notion：寫入事件 ──────────────────────────────────
def get_existing_uids(notion: NotionClient) -> dict[str, str]:
    """查詢 Notion 資料庫中已存在的 UID → page_id 對應。"""
    existing = {}
    has_more = True
    start_cursor = None

    while has_more:
        resp = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            start_cursor=start_cursor,
        )
        for page in resp["results"]:
            # 行程摘要資料庫的 UID 欄位
            uid_prop = page["properties"].get("UID", {})
            rich_text = uid_prop.get("rich_text", [])
            if rich_text:
                uid = rich_text[0]["plain_text"]
                existing[uid] = page["id"]

        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")

    return existing


CATEGORY_MAP = {
    "Personal": "生活",
    "Work": "工作",
    "Family": "生活",
}


def _build_properties(event: dict) -> dict:
    """將事件 dict 轉為 Notion page properties（對應行程摘要資料庫）。"""
    props = {
        "名稱": {"title": [{"text": {"content": event["summary"]}}]},
        "UID": {"rich_text": [{"text": {"content": event["uid"]}}]},
        "來源": {"select": {"name": "Apple Calendar"}},
    }

    if event["description"]:
        props["備註"] = {
            "rich_text": [{"text": {"content": event["description"][:2000]}}]
        }

    cal_name = event["calendar"]
    category = CATEGORY_MAP.get(cal_name, "生活")
    props["類別"] = {"select": {"name": category}}

    if event["start"]:
        props["開始"] = {"date": {"start": event["start"]}}

    if event["end"]:
        props["結束"] = {"date": {"start": event["end"]}}

    return props


def sync_to_notion(events: list[dict]):
    """將事件同步至 Notion 資料庫（新增或更新）。"""
    notion = NotionClient(auth=NOTION_TOKEN)

    log.info("查詢 Notion 現有事件...")
    existing = get_existing_uids(notion)
    log.info(f"Notion 中已有 {len(existing)} 個事件")

    created, updated, skipped = 0, 0, 0

    for event in events:
        uid = event["uid"]
        props = _build_properties(event)

        if uid in existing:
            # 更新現有事件
            try:
                notion.pages.update(page_id=existing[uid], properties=props)
                updated += 1
                log.info(f"更新: {event['summary']}")
            except Exception as e:
                log.error(f"更新失敗 {event['summary']}: {e}")
                skipped += 1
        else:
            # 新增事件
            try:
                notion.pages.create(
                    parent={"database_id": NOTION_DATABASE_ID},
                    properties=props,
                )
                created += 1
                log.info(f"新增: {event['summary']}")
            except Exception as e:
                log.error(f"新增失敗 {event['summary']}: {e}")
                skipped += 1

    log.info(f"同步完成 — 新增: {created}, 更新: {updated}, 跳過: {skipped}")


# ── 主程式 ────────────────────────────────────────────
def main():
    log.info("開始同步 Apple Calendar → Notion")

    if not all([APPLE_ID, APPLE_APP_PASSWORD, NOTION_TOKEN, NOTION_DATABASE_ID]):
        log.error("請確認 .env 中的所有必要設定都已填寫")
        return

    events = fetch_apple_events()
    if events:
        sync_to_notion(events)
    else:
        log.info("沒有事件需要同步")

    log.info("完成")


if __name__ == "__main__":
    main()

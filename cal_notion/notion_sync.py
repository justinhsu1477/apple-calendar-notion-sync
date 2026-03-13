"""Notion 同步邏輯。"""

import logging

from notion_client import Client as NotionClient

from cal_notion.models import CalendarEvent
from cal_notion.sync_state import SyncState

log = logging.getLogger(__name__)


class NotionSync:
    """處理事件與 Notion 資料庫的同步（支援雙向讀寫）。"""

    def __init__(self, token: str, database_id: str):
        self._notion = NotionClient(auth=token)
        self._database_id = database_id

    # ── 讀取 ──────────────────────────────────────────

    def get_existing_uids(self) -> dict[str, str]:
        """查詢 Notion 資料庫中已存在的 UID → page_id。"""
        existing: dict[str, str] = {}
        for page in self._query_all_pages():
            uid = self._extract_text(page, "UID")
            if uid:
                existing[uid] = page["id"]
        return existing

    def fetch_all_events(self) -> list[CalendarEvent]:
        """從 Notion 資料庫反向映射所有事件為 CalendarEvent。

        用於雙向同步：讀取 Notion 側的完整事件狀態。
        """
        events: list[CalendarEvent] = []
        for page in self._query_all_pages():
            event = self._page_to_event(page)
            if event:
                events.append(event)
        log.info(f"從 Notion 讀取 {len(events)} 個事件")
        return events

    def _query_all_pages(self) -> list[dict]:
        """分頁查詢 Notion 資料庫所有頁面。"""
        pages: list[dict] = []
        has_more = True
        start_cursor = None

        while has_more:
            resp = self._notion.databases.query(
                database_id=self._database_id,
                start_cursor=start_cursor,
            )
            pages.extend(resp["results"])
            has_more = resp.get("has_more", False)
            start_cursor = resp.get("next_cursor")

        return pages

    def _page_to_event(self, page: dict) -> CalendarEvent | None:
        """將 Notion page 反向映射為 CalendarEvent。"""
        uid = self._extract_text(page, "UID")
        if not uid:
            return None

        summary = self._extract_title(page, "Event Name")
        description = self._extract_text(page, "Description")
        location = self._extract_text(page, "Location")
        status = self._extract_select(page, "Status") or "Upcoming"
        calendar_name = self._extract_select(page, "Calendar") or ""

        start, start_is_dt = self._extract_date(page, "Start Date")
        end, end_is_dt = self._extract_date(page, "End Date")

        event = CalendarEvent(
            uid=uid,
            summary=summary or "（無標題）",
            start=start or "",
            start_is_datetime=start_is_dt,
            end=end,
            end_is_datetime=end_is_dt,
            description=description,
            location=location,
            calendar_name=calendar_name,
            status=status,
            last_modified=page.get("last_edited_time"),
            source="notion",
            notion_page_id=page["id"],
        )
        event.compute_content_hash()
        return event

    # ── 寫入 ──────────────────────────────────────────

    def create_page(self, event: CalendarEvent) -> str:
        """在 Notion 建立新事件頁面，回傳 page_id。"""
        props = self._build_properties(event)
        resp = self._notion.pages.create(
            parent={"database_id": self._database_id},
            properties=props,
        )
        log.info(f"Notion 新增: {event.summary}")
        return resp["id"]

    def update_page(self, page_id: str, event: CalendarEvent) -> None:
        """更新 Notion 事件頁面。"""
        props = self._build_properties(event)
        self._notion.pages.update(page_id=page_id, properties=props)
        log.info(f"Notion 更新: {event.summary}")

    def mark_cancelled(self, page_id: str) -> None:
        """將事件標記為 Cancelled。"""
        self._notion.pages.update(
            page_id=page_id,
            properties={"Status": {"select": {"name": "Cancelled"}}},
        )

    # ── 單向同步（向後相容）────────────────────────────

    def sync_events(
        self,
        events: list[CalendarEvent],
        state: SyncState,
        force: bool = False,
    ) -> dict[str, int]:
        """單向同步事件到 Notion（向後相容方法）。"""
        log.info("查詢 Notion 現有事件...")
        existing = self.get_existing_uids()
        log.info(f"Notion 中已有 {len(existing)} 個事件")

        stats = {"created": 0, "updated": 0, "skipped": 0, "deleted": 0}
        current_uids: set[str] = set()

        for event in events:
            current_uids.add(event.uid)

            if not force and not state.is_modified(event.uid, event.last_modified):
                stats["skipped"] += 1
                continue

            props = self._build_properties(event)

            if event.uid in existing:
                try:
                    self._notion.pages.update(
                        page_id=existing[event.uid], properties=props
                    )
                    stats["updated"] += 1
                    log.info(f"更新: {event.summary}")
                except Exception as e:
                    log.error(f"更新失敗 {event.summary}: {e}")
                    stats["skipped"] += 1
                    continue
            else:
                try:
                    self._notion.pages.create(
                        parent={"database_id": self._database_id},
                        properties=props,
                    )
                    stats["created"] += 1
                    log.info(f"新增: {event.summary}")
                except Exception as e:
                    log.error(f"新增失敗 {event.summary}: {e}")
                    stats["skipped"] += 1
                    continue

            state.mark_synced(event.uid, event.last_modified)

        deleted_uids = state.get_synced_uids() - current_uids
        for uid in deleted_uids:
            if uid in existing:
                try:
                    self.mark_cancelled(existing[uid])
                    stats["deleted"] += 1
                    log.info(f"標記已刪除: {uid}")
                except Exception as e:
                    log.warning(f"標記刪除失敗 {uid}: {e}")
            state.remove_uid(uid)

        state.update_last_sync()
        state.save()

        log.info(
            f"同步完成 — 新增: {stats['created']}, "
            f"更新: {stats['updated']}, "
            f"跳過: {stats['skipped']}, "
            f"刪除: {stats['deleted']}"
        )
        return stats

    # ── Property 建構與解析 ────────────────────────────

    @staticmethod
    def _build_properties(event: CalendarEvent) -> dict:
        props: dict = {
            "Event Name": {"title": [{"text": {"content": event.summary}}]},
            "UID": {"rich_text": [{"text": {"content": event.uid}}]},
            "Status": {"select": {"name": event.status}},
        }

        if event.description:
            props["Description"] = {
                "rich_text": [{"text": {"content": event.description[:2000]}}]
            }

        if event.location:
            props["Location"] = {
                "rich_text": [{"text": {"content": event.location}}]
            }

        if event.calendar_name:
            props["Calendar"] = {"select": {"name": event.calendar_name}}

        if event.start:
            props["Start Date"] = {"date": {"start": event.start}}

        if event.end:
            props["End Date"] = {"date": {"start": event.end}}

        return props

    @staticmethod
    def _extract_text(page: dict, prop_name: str) -> str:
        prop = page.get("properties", {}).get(prop_name, {})
        rich_text = prop.get("rich_text", [])
        if rich_text:
            return rich_text[0].get("plain_text", "")
        return ""

    @staticmethod
    def _extract_title(page: dict, prop_name: str) -> str:
        prop = page.get("properties", {}).get(prop_name, {})
        title = prop.get("title", [])
        if title:
            return title[0].get("plain_text", "")
        return ""

    @staticmethod
    def _extract_select(page: dict, prop_name: str) -> str | None:
        prop = page.get("properties", {}).get(prop_name, {})
        select = prop.get("select")
        if select:
            return select.get("name")
        return None

    @staticmethod
    def _extract_date(page: dict, prop_name: str) -> tuple[str | None, bool]:
        prop = page.get("properties", {}).get(prop_name, {})
        date = prop.get("date")
        if date and date.get("start"):
            start = date["start"]
            is_datetime = "T" in start
            return start, is_datetime
        return None, False

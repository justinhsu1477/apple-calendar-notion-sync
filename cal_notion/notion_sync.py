"""Notion 同步邏輯。"""

import logging

from notion_client import Client as NotionClient

from cal_notion.models import CalendarEvent
from cal_notion.sync_state import SyncState

log = logging.getLogger(__name__)


class NotionSync:
    """處理事件與 Notion 資料庫的同步。"""

    def __init__(self, token: str, database_id: str):
        self._notion = NotionClient(auth=token)
        self._database_id = database_id

    def get_existing_uids(self) -> dict[str, str]:
        """查詢 Notion 資料庫中已存在的 UID → page_id。"""
        existing: dict[str, str] = {}
        has_more = True
        start_cursor = None

        while has_more:
            resp = self._notion.databases.query(
                database_id=self._database_id,
                start_cursor=start_cursor,
            )
            for page in resp["results"]:
                uid_prop = page["properties"].get("UID", {})
                rich_text = uid_prop.get("rich_text", [])
                if rich_text:
                    uid = rich_text[0]["plain_text"]
                    existing[uid] = page["id"]

            has_more = resp.get("has_more", False)
            start_cursor = resp.get("next_cursor")

        return existing

    def sync_events(
        self,
        events: list[CalendarEvent],
        state: SyncState,
        force: bool = False,
    ) -> dict[str, int]:
        """同步事件到 Notion。

        Args:
            events: 要同步的事件列表
            state: 同步狀態追蹤器
            force: True 則忽略增量檢查，強制全部同步

        Returns:
            {"created": N, "updated": N, "skipped": N, "deleted": N}
        """
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

        # 偵測已刪除的事件（在 Notion 中有但 iCloud 已不存在）
        deleted_uids = state.get_synced_uids() - current_uids
        for uid in deleted_uids:
            if uid in existing:
                try:
                    self._notion.pages.update(
                        page_id=existing[uid],
                        properties={"Status": {"select": {"name": "Cancelled"}}},
                    )
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

"""雙向同步引擎。

核心邏輯：用 content_hash 做 three-way merge，
比對 Calendar 側、Notion 側、以及上次同步時的 baseline，
精確判斷哪邊改了、哪邊是新的、哪邊被刪了。
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from cal_notion.models import CalendarEvent
from cal_notion.notion_sync import NotionSync
from cal_notion.providers.base import CalendarProvider
from cal_notion.sync_state import SyncState

log = logging.getLogger(__name__)


@dataclass
class SyncStats:
    cal_to_notion: int = 0
    notion_to_cal: int = 0
    created_in_notion: int = 0
    created_in_cal: int = 0
    deleted_from_notion: int = 0
    deleted_from_cal: int = 0
    conflicts: int = 0
    skipped: int = 0
    errors: int = 0

    def summary(self) -> str:
        parts = []
        if self.cal_to_notion:
            parts.append(f"Calendar→Notion: {self.cal_to_notion}")
        if self.notion_to_cal:
            parts.append(f"Notion→Calendar: {self.notion_to_cal}")
        if self.created_in_notion:
            parts.append(f"Notion 新增: {self.created_in_notion}")
        if self.created_in_cal:
            parts.append(f"Calendar 新增: {self.created_in_cal}")
        if self.deleted_from_notion:
            parts.append(f"Notion 刪除: {self.deleted_from_notion}")
        if self.deleted_from_cal:
            parts.append(f"Calendar 刪除: {self.deleted_from_cal}")
        if self.conflicts:
            parts.append(f"衝突解決: {self.conflicts}")
        if self.skipped:
            parts.append(f"略過: {self.skipped}")
        if self.errors:
            parts.append(f"錯誤: {self.errors}")
        return ", ".join(parts) or "無變更"


class BidirectionalSyncEngine:
    """雙向同步引擎。"""

    def __init__(
        self,
        provider: CalendarProvider,
        notion: NotionSync,
        state: SyncState,
        conflict_strategy: str = "newest_wins",
        default_calendar: str = "Personal",
    ):
        self._provider = provider
        self._notion = notion
        self._state = state
        self._conflict_strategy = conflict_strategy
        self._default_calendar = default_calendar

    def sync(self, start: datetime, end: datetime) -> SyncStats:
        """執行雙向同步。"""
        stats = SyncStats()

        # Step 1: 從兩側取得所有事件
        log.info("從 Calendar 讀取事件...")
        cal_events_list = self._provider.fetch_events(start, end)
        cal_events = {e.uid: e for e in cal_events_list}

        log.info("從 Notion 讀取事件...")
        notion_events_list = self._notion.fetch_all_events()
        notion_events = {e.uid: e for e in notion_events_list}

        records = self._state.get_all_records()

        # Step 2: 收集所有 UID
        all_uids = set(cal_events.keys()) | set(notion_events.keys()) | set(records.keys())

        # Step 3: 逐一分類並執行動作
        for uid in all_uids:
            cal_event = cal_events.get(uid)
            notion_event = notion_events.get(uid)
            record = records.get(uid)

            try:
                self._process_uid(uid, cal_event, notion_event, record, stats)
            except Exception as e:
                log.error(f"處理 {uid} 時發生錯誤: {e}")
                stats.errors += 1

        # Step 4: 儲存狀態
        self._state.update_last_sync()
        self._state.save()

        log.info(f"雙向同步完成 — {stats.summary()}")
        return stats

    def _process_uid(
        self,
        uid: str,
        cal_event: CalendarEvent | None,
        notion_event: CalendarEvent | None,
        record: dict | None,
        stats: SyncStats,
    ) -> None:
        """處理單一 UID 的同步邏輯。"""

        # 確保 hash 已計算
        cal_hash = cal_event.content_hash if cal_event else None
        notion_hash = notion_event.content_hash if notion_event else None

        has_record = record is not None
        baseline_cal_hash = record.get("calendar_hash") if record else None
        baseline_notion_hash = record.get("notion_hash") if record else None

        # ── Case 1: 兩邊都有，且有 baseline ──
        if cal_event and notion_event and has_record:
            cal_changed = cal_hash != baseline_cal_hash
            notion_changed = notion_hash != baseline_notion_hash

            if not cal_changed and not notion_changed:
                stats.skipped += 1
                return

            if cal_changed and not notion_changed:
                # Calendar 改了 → 推到 Notion
                self._push_to_notion(cal_event, notion_event.notion_page_id)
                self._update_record(uid, cal_event, notion_event.notion_page_id, cal_hash)
                stats.cal_to_notion += 1

            elif not cal_changed and notion_changed:
                # Notion 改了 → 推到 Calendar
                self._push_to_calendar(notion_event, cal_event)
                self._update_record(uid, cal_event, notion_event.notion_page_id, notion_hash=notion_hash)
                stats.notion_to_cal += 1

            else:
                # 兩邊都改了 → 衝突
                winner = self._resolve_conflict(cal_event, notion_event)
                if winner.source == "calendar":
                    self._push_to_notion(winner, notion_event.notion_page_id)
                else:
                    self._push_to_calendar(winner, cal_event)
                self._update_record(uid, cal_event, notion_event.notion_page_id,
                                    winner.content_hash, winner.content_hash)
                stats.conflicts += 1

        # ── Case 2: 只在 Calendar，沒有 baseline → 新事件 ──
        elif cal_event and not notion_event and not has_record:
            page_id = self._notion.create_page(cal_event)
            self._update_record(uid, cal_event, page_id, cal_hash, cal_hash)
            stats.created_in_notion += 1

        # ── Case 3: 只在 Notion，沒有 baseline → 新事件 ──
        elif not cal_event and notion_event and not has_record:
            if self._provider.supports_write:
                cal_name = notion_event.calendar_name or self._default_calendar
                self._provider.create_event(notion_event, cal_name)
                self._update_record(uid, notion_event, notion_event.notion_page_id,
                                    notion_hash, notion_hash)
                stats.created_in_cal += 1
            else:
                log.warning(f"Provider 不支援寫入，略過 Notion 新事件: {notion_event.summary}")
                stats.skipped += 1

        # ── Case 4: 只在 Calendar，有 baseline → Notion 側刪除了 ──
        elif cal_event and not notion_event and has_record:
            if self._provider.supports_write:
                cal_name = cal_event.calendar_name or self._default_calendar
                self._provider.delete_event(uid, cal_name)
                stats.deleted_from_cal += 1
            self._state.remove_record(uid)

        # ── Case 5: 只在 Notion，有 baseline → Calendar 側刪除了 ──
        elif not cal_event and notion_event and has_record:
            page_id = notion_event.notion_page_id or record.get("notion_page_id")
            if page_id:
                self._notion.mark_cancelled(page_id)
            self._state.remove_record(uid)
            stats.deleted_from_notion += 1

        # ── Case 6: 兩邊都沒有，有 baseline → 都刪了 ──
        elif not cal_event and not notion_event and has_record:
            self._state.remove_record(uid)

        # ── Case 7: 兩邊都有，沒有 baseline → 首次看到 ──
        elif cal_event and notion_event and not has_record:
            # 用 Calendar 版本更新 Notion（Calendar 較權威）
            self._push_to_notion(cal_event, notion_event.notion_page_id)
            self._update_record(uid, cal_event, notion_event.notion_page_id, cal_hash, cal_hash)
            stats.cal_to_notion += 1

    # ── 同步動作 ──────────────────────────────────────

    def _push_to_notion(self, event: CalendarEvent, page_id: str | None) -> None:
        if page_id:
            self._notion.update_page(page_id, event)
        else:
            self._notion.create_page(event)

    def _push_to_calendar(self, event: CalendarEvent, existing_cal_event: CalendarEvent | None) -> None:
        if not self._provider.supports_write:
            log.warning(f"Provider 不支援寫入，略過: {event.summary}")
            return

        # 需要把 Notion 的變更合併到 calendar event 上
        if existing_cal_event:
            existing_cal_event.summary = event.summary
            existing_cal_event.start = event.start
            existing_cal_event.start_is_datetime = event.start_is_datetime
            existing_cal_event.end = event.end
            existing_cal_event.end_is_datetime = event.end_is_datetime
            existing_cal_event.description = event.description
            existing_cal_event.location = event.location
            existing_cal_event.status = event.status
            self._provider.update_event(existing_cal_event)
        else:
            cal_name = event.calendar_name or self._default_calendar
            self._provider.create_event(event, cal_name)

    def _update_record(
        self,
        uid: str,
        event: CalendarEvent,
        notion_page_id: str | None,
        cal_hash: str | None = None,
        notion_hash: str | None = None,
    ) -> None:
        self._state.set_record(
            uid=uid,
            calendar_hash=cal_hash or event.content_hash,
            notion_hash=notion_hash or event.content_hash,
            notion_page_id=notion_page_id,
            calendar_name=event.calendar_name,
            source=event.source,
            last_modified=event.last_modified,
        )

    # ── 衝突解決 ──────────────────────────────────────

    def _resolve_conflict(
        self,
        cal_event: CalendarEvent,
        notion_event: CalendarEvent,
    ) -> CalendarEvent:
        """根據策略解決衝突，回傳勝出的事件。"""
        strategy = self._conflict_strategy

        if strategy == "calendar_wins":
            log.info(f"衝突 [{cal_event.summary}]: Calendar 優先")
            return cal_event

        if strategy == "notion_wins":
            log.info(f"衝突 [{cal_event.summary}]: Notion 優先")
            return notion_event

        # newest_wins（預設）
        cal_time = self._parse_time(cal_event.last_modified)
        notion_time = self._parse_time(notion_event.last_modified)

        if cal_time and notion_time:
            if notion_time > cal_time:
                log.info(f"衝突 [{cal_event.summary}]: Notion 較新，Notion 優先")
                return notion_event
            else:
                log.info(f"衝突 [{cal_event.summary}]: Calendar 較新或相同，Calendar 優先")
                return cal_event

        # 無法比較時間 → Calendar 優先
        log.info(f"衝突 [{cal_event.summary}]: 無法比較時間，Calendar 優先")
        return cal_event

    @staticmethod
    def _parse_time(iso_str: str | None) -> datetime | None:
        if not iso_str:
            return None
        try:
            return datetime.fromisoformat(iso_str)
        except (ValueError, TypeError):
            return None

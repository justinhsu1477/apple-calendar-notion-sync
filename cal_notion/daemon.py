"""背景同步服務。"""

import json
import logging
import signal
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from cal_notion.config import Config, CONFIG_DIR
from cal_notion.notion_sync import NotionSync
from cal_notion.providers import get_provider
from cal_notion.sync_engine import BidirectionalSyncEngine
from cal_notion.sync_state import SyncState

LOG_FILE = CONFIG_DIR / "daemon.log"
PID_FILE = CONFIG_DIR / "daemon.pid"
STATUS_FILE = CONFIG_DIR / "daemon_status.json"

log = logging.getLogger("cal_notion.daemon")


class SyncDaemon:
    """背景同步 Daemon，由 macOS LaunchAgent 管理。"""

    def __init__(self, config: Config):
        self._config = config
        self._running = True
        self._setup_logging()
        self._setup_signals()

    def _setup_logging(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)

    def _setup_signals(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame) -> None:
        log.info(f"收到信號 {signum}，準備關閉...")
        self._running = False

    def run(self) -> None:
        """主迴圈：同步 → sleep → 重複。"""
        import os
        PID_FILE.write_text(str(os.getpid()))
        interval = self._config.get("daemon_interval_minutes", 15) * 60
        log.info(f"Daemon 啟動，間隔 {interval // 60} 分鐘")

        try:
            while self._running:
                self._run_sync()
                # 分段 sleep 以便快速回應 signal
                for _ in range(interval):
                    if not self._running:
                        break
                    time.sleep(1)
        finally:
            PID_FILE.unlink(missing_ok=True)
            log.info("Daemon 已關閉")

    def _run_sync(self) -> None:
        """執行一次同步。"""
        try:
            config = self._config
            provider = get_provider(config.get("provider"), config=config.get_provider_config())
            provider.authenticate()

            now = datetime.now(timezone.utc)
            start = now - timedelta(days=config.get("sync_days_back", 7))
            end = now + timedelta(days=config.get("sync_days_forward", 30))

            state = SyncState()
            notion = NotionSync(
                token=config.get("notion_token"),
                database_id=config.get("notion_database_id"),
            )

            direction = config.get("sync_direction", "calendar_to_notion")

            if direction == "bidirectional":
                engine = BidirectionalSyncEngine(
                    provider=provider,
                    notion=notion,
                    state=state,
                    conflict_strategy=config.get("conflict_strategy", "newest_wins"),
                )
                stats = engine.sync(start, end)
                log.info(f"雙向同步完成: {stats.summary()}")
            else:
                events = provider.fetch_events(start, end)
                if events:
                    result = notion.sync_events(events, state)
                    log.info(f"單向同步完成: {result}")
                else:
                    log.info("無事件需要同步")

            self._write_status(success=True)

        except Exception as e:
            log.error(f"同步失敗: {e}", exc_info=True)
            self._write_status(success=False, error=str(e))

    @staticmethod
    def _write_status(success: bool, error: str = "") -> None:
        status = {
            "last_run": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "error": error,
        }
        STATUS_FILE.write_text(json.dumps(status, indent=2))

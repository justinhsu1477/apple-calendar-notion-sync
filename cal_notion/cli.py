"""cal-notion CLI 工具。"""

import logging
from datetime import datetime, timedelta, timezone

import typer

from cal_notion import __version__
from cal_notion.config import Config
from cal_notion.notion_sync import NotionSync
from cal_notion.providers import PROVIDERS, get_provider
from cal_notion.sync_state import SyncState

app = typer.Typer(
    name="cal-notion",
    help="將行事曆事件同步到 Notion 資料庫（支援雙向同步）。",
    add_completion=False,
)

daemon_app = typer.Typer(help="背景服務管理。")
app.add_typer(daemon_app, name="daemon")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def _get_time_range(config: Config) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=config.get("sync_days_back", 7))
    end = now + timedelta(days=config.get("sync_days_forward", 30))
    return start, end


# ── sync ──────────────────────────────────────────────
@app.command()
def sync(
    direction: str = typer.Option(
        None, "--direction", "-d",
        help="同步方向: calendar_to_notion / notion_to_calendar / bidirectional",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="忽略增量檢查，強制全量同步"),
    conflict: str = typer.Option(None, "--conflict", help="衝突策略: newest_wins / calendar_wins / notion_wins"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="顯示詳細日誌"),
):
    """同步行事曆事件到 Notion。"""
    _setup_logging(verbose)
    config = Config()

    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    sync_direction = direction or config.get("sync_direction", "calendar_to_notion")
    conflict_strategy = conflict or config.get("conflict_strategy", "newest_wins")

    provider = get_provider(config.get("provider"), config=config.get_provider_config())
    provider.authenticate()

    start, end = _get_time_range(config)
    state = SyncState()
    notion = NotionSync(
        token=config.get("notion_token"),
        database_id=config.get("notion_database_id"),
    )

    if sync_direction == "bidirectional":
        from cal_notion.sync_engine import BidirectionalSyncEngine

        engine = BidirectionalSyncEngine(
            provider=provider,
            notion=notion,
            state=state,
            conflict_strategy=conflict_strategy,
        )
        stats = engine.sync(start, end)
        typer.echo(f"\n✅ 雙向同步完成 — {stats.summary()}")

    elif sync_direction == "notion_to_calendar":
        if not provider.supports_write:
            typer.echo(f"❌ {provider.name} provider 不支援寫入")
            raise typer.Exit(1)

        notion_events = notion.fetch_all_events()
        created = 0
        for event in notion_events:
            if not state.get_record(event.uid):
                cal_name = event.calendar_name or "Personal"
                try:
                    provider.create_event(event, cal_name)
                    state.set_record(
                        uid=event.uid,
                        notion_hash=event.content_hash,
                        calendar_hash=event.content_hash,
                        notion_page_id=event.notion_page_id,
                        calendar_name=cal_name,
                        source="notion",
                    )
                    created += 1
                except Exception as e:
                    logging.error(f"建立失敗 {event.summary}: {e}")

        state.update_last_sync()
        state.save()
        typer.echo(f"\n✅ Notion → Calendar 完成 — 新增: {created}")

    else:
        # calendar_to_notion（原始單向同步）
        events = provider.fetch_events(start, end)
        if not events:
            typer.echo("沒有事件需要同步。")
            return
        stats = notion.sync_events(events, state, force=force)
        typer.echo(
            f"\n✅ 同步完成 — "
            f"新增: {stats['created']}, "
            f"更新: {stats['updated']}, "
            f"跳過: {stats['skipped']}, "
            f"刪除: {stats['deleted']}"
        )


# ── setup ─────────────────────────────────────────────
@app.command()
def setup():
    """互動式設定 cal-notion。"""
    typer.echo("🔧 cal-notion 設定精靈\n")
    config = Config()

    # Provider
    provider_names = list(PROVIDERS.keys())
    typer.echo(f"支援的行事曆來源: {', '.join(provider_names)}")
    provider = typer.prompt("行事曆來源", default="apple")
    config.set("provider", provider)

    # Provider 認證
    if provider == "apple":
        config.set("apple_id", typer.prompt("Apple ID (iCloud 信箱)"))
        config.set("apple_app_password", typer.prompt("App-Specific Password", hide_input=True))
    elif provider == "google":
        config.set("google_credentials_file", typer.prompt("Google OAuth credentials.json 路徑"))

    # Notion
    config.set("notion_token", typer.prompt("Notion Integration Token", hide_input=True))
    config.set("notion_database_id", typer.prompt("Notion Database ID"))

    # 同步設定
    config.set("sync_days_back", int(typer.prompt("同步過去幾天的事件", default="7")))
    config.set("sync_days_forward", int(typer.prompt("同步未來幾天的事件", default="30")))

    # 同步方向
    typer.echo("\n同步方向:")
    typer.echo("  1. calendar_to_notion（單向：行事曆 → Notion）")
    typer.echo("  2. bidirectional（雙向同步）")
    typer.echo("  3. notion_to_calendar（單向：Notion → 行事曆）")
    direction = typer.prompt("選擇同步方向", default="bidirectional")
    config.set("sync_direction", direction)

    # 衝突策略
    if direction == "bidirectional":
        typer.echo("\n衝突處理策略:")
        typer.echo("  newest_wins — 較新的修改優先（預設）")
        typer.echo("  calendar_wins — 行事曆永遠優先")
        typer.echo("  notion_wins — Notion 永遠優先")
        strategy = typer.prompt("衝突策略", default="newest_wins")
        config.set("conflict_strategy", strategy)

    config.save()
    typer.echo("\n✅ 設定完成！執行 cal-notion sync 開始同步。")


# ── status ────────────────────────────────────────────
@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="顯示詳細資訊"),
):
    """查看同步狀態與設定。"""
    config = Config()
    state = SyncState()

    typer.echo(f"cal-notion v{__version__}\n")

    if config.is_configured():
        typer.echo(f"📋 Provider: {config.get('provider')}")
        typer.echo(f"🔄 同步方向: {config.get('sync_direction', 'calendar_to_notion')}")
        typer.echo(f"⚡ 衝突策略: {config.get('conflict_strategy', 'newest_wins')}")
        typer.echo(f"📅 同步範圍: 過去 {config.get('sync_days_back')} 天 ~ 未來 {config.get('sync_days_forward')} 天")
    else:
        typer.echo("⚠️  尚未設定，請執行: cal-notion setup")

    last = state.last_sync
    if last:
        typer.echo(f"\n🕐 上次同步: {last.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        typer.echo(f"📊 追蹤事件數: {len(state.get_tracked_uids())}")
    else:
        typer.echo("\n🕐 尚未同步過")

    if verbose:
        typer.echo(f"\n設定詳情: {config.to_dict()}")


# ── providers ─────────────────────────────────────────
@app.command()
def providers():
    """列出支援的行事曆來源。"""
    typer.echo("支援的行事曆 Provider:\n")
    for name, cls in PROVIDERS.items():
        write_tag = " [讀寫]" if hasattr(cls, 'supports_write') else " [唯讀]"
        typer.echo(f"  • {name}{write_tag} — {cls.__doc__ or ''}")


# ── calendars ─────────────────────────────────────────
@app.command()
def calendars():
    """列出帳號下所有行事曆。"""
    config = Config()
    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    provider = get_provider(config.get("provider"), config=config.get_provider_config())
    provider.authenticate()

    names = provider.list_calendars()
    typer.echo(f"找到 {len(names)} 個行事曆:\n")
    for name in names:
        typer.echo(f"  📅 {name}")


# ── reset ─────────────────────────────────────────────
@app.command()
def reset():
    """重置同步狀態（不影響 Notion 資料）。"""
    confirm = typer.confirm("確定要重置同步狀態嗎？下次同步將重新比對所有事件。")
    if confirm:
        state = SyncState()
        state.reset()
        typer.echo("✅ 同步狀態已重置。")


# ── daemon 子指令 ─────────────────────────────────────

@daemon_app.command("start")
def daemon_start():
    """安裝並啟動背景同步服務（macOS LaunchAgent）。"""
    from cal_notion.launchd import install

    config = Config()
    interval = config.get("daemon_interval_minutes", 15)
    install(interval_minutes=interval)
    typer.echo(f"✅ 背景服務已啟動（每 {interval} 分鐘同步一次）")


@daemon_app.command("stop")
def daemon_stop():
    """停止背景同步服務。"""
    from cal_notion.launchd import uninstall
    uninstall()
    typer.echo("✅ 背景服務已停止")


@daemon_app.command("status")
def daemon_status():
    """查看背景服務狀態。"""
    from cal_notion.launchd import status as launchd_status
    info = launchd_status()
    if info["running"]:
        typer.echo(f"🟢 背景服務運作中 (PID: {info.get('pid', 'unknown')})")
    else:
        typer.echo("🔴 背景服務未啟動")


@daemon_app.command("logs")
def daemon_logs(
    lines: int = typer.Option(50, "--lines", "-n", help="顯示最後幾行"),
):
    """查看背景服務日誌。"""
    from cal_notion.daemon import LOG_FILE
    if not LOG_FILE.exists():
        typer.echo("尚無日誌")
        return
    all_lines = LOG_FILE.read_text().splitlines()
    for line in all_lines[-lines:]:
        typer.echo(line)


@daemon_app.command("run")
def daemon_run():
    """直接執行同步迴圈（由 launchd 呼叫）。"""
    from cal_notion.daemon import SyncDaemon
    config = Config()
    daemon = SyncDaemon(config)
    daemon.run()


def main():
    app()


if __name__ == "__main__":
    main()

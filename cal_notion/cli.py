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
    help="將行事曆事件同步到 Notion 資料庫。",
    add_completion=False,
)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


# ── sync ──────────────────────────────────────────────
@app.command()
def sync(
    force: bool = typer.Option(False, "--force", "-f", help="忽略增量檢查，強制全量同步"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="顯示詳細日誌"),
):
    """同步行事曆事件到 Notion。"""
    _setup_logging(verbose)
    config = Config()

    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    # 初始化 Provider
    provider = get_provider(
        config.get("provider"),
        username=config.get("apple_id"),
        password=config.get("apple_app_password"),
    )
    provider.authenticate()

    # 取得事件
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=config.get("sync_days_back", 7))
    end = now + timedelta(days=config.get("sync_days_forward", 30))

    events = provider.fetch_events(start, end)

    if not events:
        typer.echo("沒有事件需要同步。")
        return

    # 同步到 Notion
    state = SyncState()
    notion = NotionSync(
        token=config.get("notion_token"),
        database_id=config.get("notion_database_id"),
    )

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

    # Apple 認證
    if provider == "apple":
        config.set("apple_id", typer.prompt("Apple ID (iCloud 信箱)"))
        config.set("apple_app_password", typer.prompt("App-Specific Password", hide_input=True))

    # Notion
    config.set("notion_token", typer.prompt("Notion Integration Token", hide_input=True))
    config.set("notion_database_id", typer.prompt("Notion Database ID"))

    # 同步範圍
    config.set("sync_days_back", int(typer.prompt("同步過去幾天的事件", default="7")))
    config.set("sync_days_forward", int(typer.prompt("同步未來幾天的事件", default="30")))

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

    # 設定狀態
    if config.is_configured():
        typer.echo(f"📋 Provider: {config.get('provider')}")
        typer.echo(f"📅 同步範圍: 過去 {config.get('sync_days_back')} 天 ~ 未來 {config.get('sync_days_forward')} 天")
    else:
        typer.echo("⚠️  尚未設定，請執行: cal-notion setup")

    # 同步狀態
    last = state.last_sync
    if last:
        typer.echo(f"\n🕐 上次同步: {last.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        typer.echo(f"📊 已同步事件數: {len(state.get_synced_uids())}")
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
        typer.echo(f"  • {name} — {cls.__doc__ or ''}")


# ── calendars ─────────────────────────────────────────
@app.command()
def calendars():
    """列出帳號下所有行事曆。"""
    config = Config()
    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    provider = get_provider(
        config.get("provider"),
        username=config.get("apple_id"),
        password=config.get("apple_app_password"),
    )
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


def main():
    app()


if __name__ == "__main__":
    main()

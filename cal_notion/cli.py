"""cal-notion CLI 工具。"""

import logging
from datetime import datetime, timedelta, timezone

import typer

from cal_notion import __version__
from cal_notion.config import Config
from cal_notion.lock import SyncLock
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
    dry_run: bool = typer.Option(False, "--dry-run", help="預覽同步結果，不實際寫入"),
    calendars: str = typer.Option(None, "--calendars", "-c", help="只同步指定行事曆（逗號分隔，如: 工作,生活）"),
    date_from: str = typer.Option(None, "--from", help="同步起始日期 (YYYY-MM-DD)"),
    date_to: str = typer.Option(None, "--to", help="同步結束日期 (YYYY-MM-DD)"),
):
    """同步行事曆事件到 Notion。"""
    _setup_logging(verbose)
    config = Config()

    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    lock = SyncLock()
    if not lock.acquire():
        typer.echo("❌ 另一個同步程序正在執行中")
        raise typer.Exit(1)

    try:
        sync_direction = direction or config.get("sync_direction", "calendar_to_notion")
        conflict_strategy = conflict or config.get("conflict_strategy", "newest_wins")

        if date_from or date_to:
            from datetime import timezone as tz
            start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=tz.utc) if date_from else _get_time_range(config)[0]
            end = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=tz.utc) if date_to else _get_time_range(config)[1]
        else:
            start, end = _get_time_range(config)

        calendar_filter = [c.strip() for c in calendars.split(",")] if calendars else None

        provider = get_provider(config.get("provider"), config=config.get_provider_config())
        provider.authenticate()

        state = SyncState()
        notion = NotionSync(
            token=config.get("notion_token"),
            database_id=config.get("notion_database_id"),
            dry_run=dry_run,
        )

        if dry_run:
            typer.echo("🔍 DRY-RUN 模式：不會實際寫入任何資料\n")

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
                        if dry_run:
                            logging.info(f"[DRY-RUN] 將建立行事曆事件: {event.summary}")
                        else:
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

            if not dry_run:
                state.update_last_sync()
                state.save()
            typer.echo(f"\n✅ Notion → Calendar 完成 — 新增: {created}")

        else:
            # calendar_to_notion（原始單向同步）
            events = provider.fetch_events(start, end, calendar_names=calendar_filter)
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
    finally:
        lock.release()


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


# ── analytics ────────────────────────────────────────
@app.command()
def analytics(
    period: str = typer.Option("week", "--period", "-p", help="分析期間: week / month / all"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="顯示詳細資訊"),
):
    """查看時間分析報表。"""
    _setup_logging(verbose)
    config = Config()
    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    provider = get_provider(config.get("provider"), config=config.get_provider_config())
    provider.authenticate()
    start, end = _get_time_range(config)

    # Extend range for analytics
    now = datetime.now(timezone.utc)
    if period == "month":
        start = now - timedelta(days=31)
    elif period == "all":
        start = now - timedelta(days=365)

    events = provider.fetch_events(start, end)

    from cal_notion.analytics import TimeAnalytics
    analyzer = TimeAnalytics(events)

    if period == "week":
        data = analyzer.weekly_summary()
        typer.echo(f"\n📊 週報 ({data['week_start']} ~ {data['week_end']})\n")
        typer.echo(f"  總事件: {data['total_events']} 個")
        typer.echo(f"  總時數: {data['total_hours']} 小時")
        typer.echo(f"  最忙日: {data['busiest_day']}")
        typer.echo(f"  日均:   {data['avg_hours_per_day']} 小時\n")
        typer.echo("  按類別:")
        for cat, info in data["by_category"].items():
            typer.echo(f"    {cat}: {info['count']} 個 / {info['hours']}h")

    elif period == "month":
        data = analyzer.monthly_summary()
        typer.echo(f"\n📊 月報 ({data['year']}/{data['month']:02d})\n")
        typer.echo(f"  總事件: {data['total_events']} 個")
        typer.echo(f"  總時數: {data['total_hours']} 小時")
        typer.echo(f"  週均:   {data['avg_hours_per_week']} 小時\n")
        typer.echo("  按類別:")
        for cat, info in data["by_category"].items():
            typer.echo(f"    {cat}: {info['count']} 個 / {info['hours']}h")

    else:
        breakdown = analyzer.category_breakdown()
        typer.echo(f"\n📊 全部事件統計 (共 {len(events)} 個)\n")
        for item in breakdown:
            bar = "█" * int(item["percentage"] / 5)
            typer.echo(f"  {item['category']}: {item['count']}個 / {item['hours']}h ({item['percentage']}%) {bar}")


# ── add (NLP) ────────────────────────────────────────
@app.command()
def add(
    text: str = typer.Argument(..., help="自然語言描述事件，如: 週五下午3點 和 Sam 喝咖啡"),
    calendar: str = typer.Option(None, "--calendar", help="指定行事曆名稱"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="顯示詳細資訊"),
):
    """用自然語言快速新增行事曆事件。"""
    _setup_logging(verbose)

    from cal_notion.nlp import parse_event_text
    event = parse_event_text(text)
    if not event:
        typer.echo("❌ 無法解析事件描述")
        raise typer.Exit(1)

    typer.echo(f"\n📅 解析結果:")
    typer.echo(f"  名稱: {event.summary}")
    typer.echo(f"  開始: {event.start}")
    typer.echo(f"  結束: {event.end}")

    confirm = typer.confirm("\n確定要新增這個事件嗎？")
    if not confirm:
        typer.echo("已取消")
        return

    config = Config()
    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    event.calendar_name = calendar or "一般"
    event.compute_content_hash()

    # Add to Notion
    notion = NotionSync(
        token=config.get("notion_token"),
        database_id=config.get("notion_database_id"),
    )
    page_id = notion.create_page(event)
    typer.echo(f"\n✅ 已新增到 Notion: {event.summary}")

    # Optionally add to calendar
    try:
        provider = get_provider(config.get("provider"), config=config.get_provider_config())
        provider.authenticate()
        if provider.supports_write:
            provider.create_event(event, event.calendar_name)
            typer.echo(f"✅ 已新增到行事曆: {event.calendar_name}")
    except Exception as e:
        typer.echo(f"⚠️ 新增到行事曆失敗: {e}")


# ── ai ────────────────────────────────────────────────
ai_app = typer.Typer(help="AI 智慧分析功能。")
app.add_typer(ai_app, name="ai")


@ai_app.command("classify")
def ai_classify(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """AI 自動分類所有未分類事件。"""
    _setup_logging(verbose)
    config = Config()
    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    provider = get_provider(config.get("provider"), config=config.get_provider_config())
    provider.authenticate()
    start, end = _get_time_range(config)
    events = provider.fetch_events(start, end)

    from cal_notion.ai import batch_classify_events
    event_dicts = [{"uid": e.uid, "summary": e.summary} for e in events]

    typer.echo(f"🤖 正在分析 {len(events)} 個事件...")
    results = batch_classify_events(event_dicts)

    if results:
        typer.echo(f"\n分類結果 ({len(results)} 個):\n")
        for uid, category in results.items():
            event = next((e for e in events if e.uid == uid), None)
            if event:
                typer.echo(f"  {event.summary} → {category}")
    else:
        typer.echo("❌ 分類失敗，請確認 ANTHROPIC_API_KEY 設定正確")


@ai_app.command("insights")
def ai_insights(
    period: str = typer.Option("week", "--period", "-p", help="分析期間: week / month"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """AI 時間管理洞察。"""
    _setup_logging(verbose)
    config = Config()
    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    provider = get_provider(config.get("provider"), config=config.get_provider_config())
    provider.authenticate()
    start, end = _get_time_range(config)
    events = provider.fetch_events(start, end)

    from cal_notion.analytics import TimeAnalytics
    from cal_notion.ai import generate_time_insights

    analyzer = TimeAnalytics(events)
    data = analyzer.weekly_summary() if period == "week" else analyzer.monthly_summary()

    typer.echo("🤖 正在生成 AI 洞察...\n")
    insights = generate_time_insights(data)
    typer.echo(insights)


@ai_app.command("report")
def ai_report(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """AI 週報自動生成。"""
    _setup_logging(verbose)
    config = Config()
    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    provider = get_provider(config.get("provider"), config=config.get_provider_config())
    provider.authenticate()
    start, end = _get_time_range(config)
    events = provider.fetch_events(start, end)

    from cal_notion.analytics import TimeAnalytics
    from cal_notion.ai import generate_weekly_report

    analyzer = TimeAnalytics(events)
    data = analyzer.weekly_summary()

    event_dicts = [e.to_dict() for e in events]

    typer.echo("🤖 正在生成 AI 週報...\n")
    report = generate_weekly_report(event_dicts, data, data["week_start"], data["week_end"])
    typer.echo(report)


@ai_app.command("duplicates")
def ai_duplicates(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """AI 偵測可能重複的事件。"""
    _setup_logging(verbose)
    config = Config()
    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    provider = get_provider(config.get("provider"), config=config.get_provider_config())
    provider.authenticate()
    start, end = _get_time_range(config)
    events = provider.fetch_events(start, end)

    from cal_notion.ai import detect_duplicates

    event_dicts = [{"uid": e.uid, "summary": e.summary, "start": e.start} for e in events]

    typer.echo(f"🤖 正在分析 {len(events)} 個事件...\n")
    duplicates = detect_duplicates(event_dicts)

    if duplicates:
        typer.echo(f"找到 {len(duplicates)} 組可能重複的事件:\n")
        for uid1, uid2, confidence in duplicates:
            e1 = next((e for e in events if e.uid == uid1), None)
            e2 = next((e for e in events if e.uid == uid2), None)
            if e1 and e2:
                typer.echo(f"  🔄 [{confidence*100:.0f}%] {e1.summary} ↔ {e2.summary}")
    else:
        typer.echo("✅ 未發現重複事件")


@ai_app.command("cost")
def ai_cost(
    rate: float = typer.Option(500.0, "--rate", "-r", help="每小時費率 (NTD)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """計算行事曆事件的時間成本。"""
    _setup_logging(verbose)
    config = Config()
    if not config.is_configured():
        typer.echo("尚未設定，請先執行: cal-notion setup")
        raise typer.Exit(1)

    provider = get_provider(config.get("provider"), config=config.get_provider_config())
    provider.authenticate()
    start, end = _get_time_range(config)
    events = provider.fetch_events(start, end)

    from cal_notion.ai import calculate_meeting_costs

    event_dicts = [e.to_dict() for e in events]
    results = calculate_meeting_costs(event_dicts, hourly_rate=rate)

    total_cost = sum(r["cost"] for r in results)
    total_hours = sum(r["hours"] for r in results)

    typer.echo(f"\n💰 時間成本分析 (費率: NT${rate:.0f}/hr)\n")
    typer.echo(f"  總時數: {total_hours:.1f} 小時")
    typer.echo(f"  總成本: NT${total_cost:,.0f}\n")

    typer.echo("  前 10 名最高成本事件:")
    for r in results[:10]:
        typer.echo(f"    NT${r['cost']:>8,.0f} | {r['hours']:>5.1f}h | {r['summary']}")


# ── dashboard ────────────────────────────────────────
@app.command()
def dashboard(
    port: int = typer.Option(5566, "--port", "-p", help="Web 伺服器埠號"),
    host: str = typer.Option("127.0.0.1", "--host", help="Web 伺服器地址"),
):
    """啟動 Web 儀表板。"""
    from cal_notion.web import run_dashboard
    run_dashboard(host=host, port=port)


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

"""Web 儀表板 — 提供同步狀態、時間分析、設定管理的 Web 介面。"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template_string

from cal_notion.config import Config, CONFIG_DIR
from cal_notion.sync_state import SyncState

log = logging.getLogger(__name__)

app = Flask(__name__)

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>cal-notion 儀表板</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f0f0f; color: #e0e0e0; padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { font-size: 24px; margin-bottom: 24px; color: #fff; }
        h2 { font-size: 18px; margin-bottom: 12px; color: #aaa; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .card {
            background: #1a1a1a; border: 1px solid #333; border-radius: 12px;
            padding: 20px; transition: border-color 0.2s;
        }
        .card:hover { border-color: #555; }
        .card h3 { font-size: 14px; color: #888; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }
        .card .value { font-size: 32px; font-weight: 700; color: #fff; }
        .card .sub { font-size: 13px; color: #666; margin-top: 4px; }
        .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
        .status-dot.green { background: #22c55e; }
        .status-dot.red { background: #ef4444; }
        .status-dot.yellow { background: #eab308; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid #222; }
        th { color: #888; font-weight: 500; font-size: 13px; }
        td { color: #ccc; font-size: 14px; }
        .bar-container { width: 100%; height: 24px; background: #222; border-radius: 4px; overflow: hidden; display: flex; }
        .bar-segment { height: 100%; transition: width 0.3s; }
        .legend { display: flex; gap: 16px; margin-top: 8px; flex-wrap: wrap; }
        .legend-item { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #888; }
        .legend-dot { width: 10px; height: 10px; border-radius: 2px; }
        .colors { --c1: #3b82f6; --c2: #22c55e; --c3: #eab308; --c4: #ef4444; --c5: #8b5cf6; --c6: #ec4899; }
        .refresh-btn {
            background: #333; color: #ccc; border: 1px solid #555; border-radius: 8px;
            padding: 8px 16px; cursor: pointer; font-size: 13px; float: right;
        }
        .refresh-btn:hover { background: #444; }
        .footer { text-align: center; color: #444; font-size: 12px; margin-top: 40px; padding: 20px; }
    </style>
</head>
<body class="colors">
<div class="container">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
        <h1>📅 cal-notion 儀表板</h1>
        <button class="refresh-btn" onclick="location.reload()">🔄 重新整理</button>
    </div>

    <div class="grid" id="status-cards">
        <div class="card">
            <h3>同步狀態</h3>
            <div class="value" id="sync-status">載入中...</div>
            <div class="sub" id="last-sync"></div>
        </div>
        <div class="card">
            <h3>追蹤事件</h3>
            <div class="value" id="event-count">-</div>
            <div class="sub">在 Notion 資料庫中</div>
        </div>
        <div class="card">
            <h3>Provider</h3>
            <div class="value" id="provider">-</div>
            <div class="sub" id="direction"></div>
        </div>
        <div class="card">
            <h3>Daemon</h3>
            <div class="value" id="daemon-status">-</div>
            <div class="sub" id="daemon-info"></div>
        </div>
    </div>

    <div class="card" style="margin-bottom: 24px;">
        <h2>📊 類別分佈</h2>
        <div class="bar-container" id="category-bar"></div>
        <div class="legend" id="category-legend"></div>
    </div>

    <div class="card" style="margin-bottom: 24px;">
        <h2>📋 最近同步的事件</h2>
        <table>
            <thead><tr><th>名稱</th><th>開始</th><th>類別</th><th>同步時間</th></tr></thead>
            <tbody id="recent-events"></tbody>
        </table>
    </div>

    <div class="card">
        <h2>⚙️ 設定</h2>
        <table id="config-table">
            <thead><tr><th>參數</th><th>值</th></tr></thead>
            <tbody id="config-body"></tbody>
        </table>
    </div>

    <div class="footer">cal-notion v{{ version }} | 儀表板</div>
</div>

<script>
const COLORS = ['#3b82f6', '#22c55e', '#eab308', '#ef4444', '#8b5cf6', '#ec4899', '#f97316', '#06b6d4'];

async function loadData() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();

        // Status cards
        const syncOk = data.daemon_status?.success !== false;
        document.getElementById('sync-status').innerHTML =
            `<span class="status-dot ${syncOk ? 'green' : 'red'}"></span>${syncOk ? '正常' : '異常'}`;
        document.getElementById('last-sync').textContent =
            data.last_sync ? `上次: ${new Date(data.last_sync).toLocaleString('zh-TW')}` : '尚未同步';
        document.getElementById('event-count').textContent = data.tracked_events || 0;
        document.getElementById('provider').textContent = (data.config?.provider || '-').toUpperCase();
        document.getElementById('direction').textContent = data.config?.sync_direction || '-';

        // Daemon
        const daemonRunning = data.daemon_status?.last_run;
        document.getElementById('daemon-status').innerHTML =
            daemonRunning ? '<span class="status-dot green"></span>運作中' : '<span class="status-dot yellow"></span>未啟動';
        document.getElementById('daemon-info').textContent =
            data.config?.daemon_interval_minutes ? `每 ${data.config.daemon_interval_minutes} 分鐘` : '';

        // Category bar
        const cats = data.categories || {};
        const total = Object.values(cats).reduce((a, b) => a + b, 0);
        const bar = document.getElementById('category-bar');
        const legend = document.getElementById('category-legend');
        bar.innerHTML = '';
        legend.innerHTML = '';
        Object.entries(cats).forEach(([name, count], i) => {
            const pct = total > 0 ? (count / total * 100) : 0;
            const color = COLORS[i % COLORS.length];
            bar.innerHTML += `<div class="bar-segment" style="width:${pct}%;background:${color}"></div>`;
            legend.innerHTML += `<div class="legend-item"><div class="legend-dot" style="background:${color}"></div>${name} (${count})</div>`;
        });

        // Recent events
        const tbody = document.getElementById('recent-events');
        tbody.innerHTML = '';
        (data.recent_events || []).slice(0, 20).forEach(e => {
            tbody.innerHTML += `<tr><td>${e.summary || '-'}</td><td>${e.start || '-'}</td><td>${e.category || '-'}</td><td>${e.synced_at || '-'}</td></tr>`;
        });

        // Config
        const configBody = document.getElementById('config-body');
        configBody.innerHTML = '';
        Object.entries(data.config || {}).forEach(([k, v]) => {
            configBody.innerHTML += `<tr><td>${k}</td><td>${v}</td></tr>`;
        });
    } catch (e) {
        document.getElementById('sync-status').innerHTML = '<span class="status-dot red"></span>連線失敗';
    }
}

loadData();
setInterval(loadData, 30000);
</script>
</body>
</html>
'''


@app.route("/")
def dashboard():
    from cal_notion import __version__
    return render_template_string(DASHBOARD_HTML, version=__version__)


@app.route("/api/status")
def api_status():
    config = Config()
    state = SyncState()

    # Daemon status
    daemon_status = {}
    status_file = CONFIG_DIR / "daemon_status.json"
    if status_file.exists():
        try:
            daemon_status = json.loads(status_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Category distribution from sync state
    records = state.get_all_records()
    categories: dict[str, int] = {}
    recent_events: list[dict] = []

    for uid, record in records.items():
        cal_name = record.get("calendar_name", "未分類")
        categories[cal_name] = categories.get(cal_name, 0) + 1
        recent_events.append({
            "uid": uid,
            "summary": uid[:20],  # UID as fallback
            "category": cal_name,
            "start": record.get("last_modified", ""),
            "synced_at": record.get("synced_at", ""),
        })

    # Sort recent events by synced_at
    recent_events.sort(key=lambda x: x.get("synced_at", ""), reverse=True)

    return jsonify({
        "last_sync": state.last_sync.isoformat() if state.last_sync else None,
        "tracked_events": len(records),
        "config": config.to_dict(),
        "daemon_status": daemon_status,
        "categories": categories,
        "recent_events": recent_events[:20],
    })


def run_dashboard(host: str = "127.0.0.1", port: int = 5566):
    """Start the web dashboard."""
    print(f"\n🌐 cal-notion 儀表板: http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False)

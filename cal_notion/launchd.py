"""macOS LaunchAgent 管理。

產生、安裝、移除 LaunchAgent plist，
讓 cal-notion daemon 以背景服務方式在 macOS 上運行。
"""

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

PLIST_NAME = "com.cal-notion.sync"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_NAME}.plist"


def _generate_plist(interval_minutes: int) -> str:
    """產生 LaunchAgent plist XML。"""
    import shutil
    cal_notion_path = shutil.which("cal-notion") or "cal-notion"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{cal_notion_path}</string>
        <string>daemon</string>
        <string>run</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval_minutes * 60}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{Path.home() / ".cal-notion" / "daemon_stdout.log"}</string>
    <key>StandardErrorPath</key>
    <string>{Path.home() / ".cal-notion" / "daemon_stderr.log"}</string>
</dict>
</plist>"""


def install(interval_minutes: int = 15) -> None:
    """安裝並載入 LaunchAgent。"""
    # 先移除舊的
    if PLIST_PATH.exists():
        uninstall()

    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(_generate_plist(interval_minutes))
    log.info(f"已寫入 plist: {PLIST_PATH}")

    subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=True)
    log.info("LaunchAgent 已載入")


def uninstall() -> None:
    """卸載並移除 LaunchAgent。"""
    if PLIST_PATH.exists():
        subprocess.run(["launchctl", "unload", str(PLIST_PATH)], check=False)
        PLIST_PATH.unlink()
        log.info("LaunchAgent 已移除")
    else:
        log.info("LaunchAgent 不存在")


def status() -> dict:
    """檢查 LaunchAgent 狀態。"""
    result = subprocess.run(
        ["launchctl", "list"],
        capture_output=True, text=True,
    )
    running = PLIST_NAME in result.stdout

    pid = None
    if running:
        for line in result.stdout.splitlines():
            if PLIST_NAME in line:
                parts = line.split()
                if parts[0] != "-":
                    pid = parts[0]
                break

    return {"running": running, "pid": pid, "plist_path": str(PLIST_PATH)}

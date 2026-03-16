"""同步通知模組 — 支援 LINE Notify 和 Slack Webhook。"""

import json
import logging
import urllib.parse
import urllib.request
import urllib.error

log = logging.getLogger(__name__)


class Notifier:
    """Sends sync notifications via configured channels."""

    def __init__(self, line_token: str | None = None, slack_webhook: str | None = None):
        self._line_token = line_token
        self._slack_webhook = slack_webhook

    @property
    def enabled(self) -> bool:
        return bool(self._line_token or self._slack_webhook)

    def send(self, message: str) -> None:
        """Send notification to all configured channels."""
        if self._line_token:
            self._send_line(message)
        if self._slack_webhook:
            self._send_slack(message)

    def _send_line(self, message: str) -> None:
        """Send via LINE Notify API."""
        try:
            data = urllib.parse.urlencode({"message": message}).encode()
            req = urllib.request.Request(
                "https://notify-api.line.me/api/notify",
                data=data,
                headers={"Authorization": f"Bearer {self._line_token}"},
            )
            urllib.request.urlopen(req, timeout=10)
            log.info("LINE Notify 發送成功")
        except Exception as e:
            log.error(f"LINE Notify 發送失敗: {e}")

    def _send_slack(self, message: str) -> None:
        """Send via Slack Incoming Webhook."""
        try:
            payload = json.dumps({"text": message}).encode()
            req = urllib.request.Request(
                self._slack_webhook,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            log.info("Slack 通知發送成功")
        except Exception as e:
            log.error(f"Slack 通知發送失敗: {e}")

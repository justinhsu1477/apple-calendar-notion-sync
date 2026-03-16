"""Tests for Notifier."""

from unittest.mock import patch, MagicMock

from cal_notion.notify import Notifier


class TestEnabled:
    def test_disabled_when_no_tokens(self):
        n = Notifier()
        assert n.enabled is False

    def test_enabled_with_line_token(self):
        n = Notifier(line_token="test-token")
        assert n.enabled is True

    def test_enabled_with_slack_webhook(self):
        n = Notifier(slack_webhook="https://hooks.slack.com/test")
        assert n.enabled is True

    def test_enabled_with_both(self):
        n = Notifier(line_token="tok", slack_webhook="https://hooks.slack.com/x")
        assert n.enabled is True


class TestSendLine:
    @patch("cal_notion.notify.urllib.request.urlopen")
    def test_calls_urllib_with_correct_headers(self, mock_urlopen):
        mock_urlopen.return_value = MagicMock()
        n = Notifier(line_token="my-line-token")
        n.send("Hello LINE")

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://notify-api.line.me/api/notify"
        assert req.get_header("Authorization") == "Bearer my-line-token"
        assert b"message=Hello" in req.data or b"message=" in req.data


class TestSendSlack:
    @patch("cal_notion.notify.urllib.request.urlopen")
    def test_calls_urllib_with_correct_payload(self, mock_urlopen):
        mock_urlopen.return_value = MagicMock()
        webhook = "https://hooks.slack.com/services/T00/B00/xxx"
        n = Notifier(slack_webhook=webhook)
        n.send("Hello Slack")

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == webhook
        assert req.get_header("Content-type") == "application/json"
        import json
        payload = json.loads(req.data)
        assert payload["text"] == "Hello Slack"

"""Tests for retry module."""

from unittest.mock import patch, MagicMock

import pytest

from cal_notion.retry import (
    classify_error,
    with_retry,
    AuthError,
    NetworkError,
    RateLimitError,
    DataError,
    SyncError,
)


class TestClassifyError:
    def test_401_is_auth_error(self):
        assert isinstance(classify_error(Exception("401 Unauthorized")), AuthError)

    def test_403_is_auth_error(self):
        assert isinstance(classify_error(Exception("403 Forbidden")), AuthError)

    def test_429_is_rate_limit(self):
        assert isinstance(classify_error(Exception("429 rate limit")), RateLimitError)

    def test_rate_keyword(self):
        assert isinstance(classify_error(Exception("Rate limit exceeded")), RateLimitError)

    def test_timeout_is_network(self):
        assert isinstance(classify_error(Exception("Connection timeout")), NetworkError)

    def test_connection_is_network(self):
        assert isinstance(classify_error(Exception("Connection refused")), NetworkError)

    def test_validation_is_data(self):
        assert isinstance(classify_error(Exception("validation error")), DataError)

    def test_400_is_data(self):
        assert isinstance(classify_error(Exception("400 Bad Request")), DataError)

    def test_generic_is_sync_error(self):
        err = classify_error(Exception("something else"))
        assert type(err) is SyncError


class TestWithRetry:
    @patch("cal_notion.retry.time.sleep")
    def test_succeeds_first_try(self, mock_sleep):
        @with_retry(max_retries=3)
        def good():
            return "ok"

        assert good() == "ok"
        mock_sleep.assert_not_called()

    @patch("cal_notion.retry.time.sleep")
    def test_retries_on_network_error(self, mock_sleep):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection timeout")
            return "recovered"

        assert flaky() == "recovered"
        assert call_count == 3
        assert mock_sleep.call_count == 2

    @patch("cal_notion.retry.time.sleep")
    def test_retries_on_rate_limit(self, mock_sleep):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def rate_limited():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("429 rate limit exceeded")
            return "ok"

        assert rate_limited() == "ok"
        assert call_count == 2

    @patch("cal_notion.retry.time.sleep")
    def test_no_retry_on_auth_error(self, mock_sleep):
        @with_retry(max_retries=3)
        def auth_fail():
            raise Exception("401 Unauthorized")

        with pytest.raises(AuthError):
            auth_fail()
        mock_sleep.assert_not_called()

    @patch("cal_notion.retry.time.sleep")
    def test_no_retry_on_data_error(self, mock_sleep):
        @with_retry(max_retries=3)
        def data_fail():
            raise Exception("validation failed")

        with pytest.raises(DataError):
            data_fail()
        mock_sleep.assert_not_called()

    @patch("cal_notion.retry.time.sleep")
    def test_respects_max_retries(self, mock_sleep):
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise Exception("network error")

        with pytest.raises(SyncError):
            always_fail()
        # 1 initial + 2 retries = 3 total calls
        assert call_count == 3
        assert mock_sleep.call_count == 2

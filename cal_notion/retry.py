"""API 重試機制。"""
import functools
import logging
import time

log = logging.getLogger(__name__)


class SyncError(Exception):
    """同步錯誤基礎類別。"""
    pass


class AuthError(SyncError):
    """認證錯誤。"""
    pass


class NetworkError(SyncError):
    """網路錯誤。"""
    pass


class RateLimitError(SyncError):
    """API 速率限制。"""
    pass


class DataError(SyncError):
    """資料格式錯誤。"""
    pass


def classify_error(e: Exception) -> SyncError:
    """Classify a raw exception into a SyncError subtype."""
    msg = str(e).lower()
    if "unauthorized" in msg or "401" in msg or "403" in msg or "認證" in msg:
        return AuthError(str(e))
    if "rate" in msg or "429" in msg:
        return RateLimitError(str(e))
    if "timeout" in msg or "connection" in msg or "network" in msg:
        return NetworkError(str(e))
    if "validation" in msg or "invalid" in msg or "400" in msg:
        return DataError(str(e))
    return SyncError(str(e))


def with_retry(max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
    """Decorator for retrying API calls with exponential backoff.
    Only retries on NetworkError and RateLimitError. Auth and Data errors fail immediately.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    classified = classify_error(e)
                    if isinstance(classified, (AuthError, DataError)):
                        raise classified from e
                    last_error = classified
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        log.warning(f"重試 {attempt + 1}/{max_retries}: {e} (等待 {delay:.1f}s)")
                        time.sleep(delay)
            raise last_error
        return wrapper
    return decorator

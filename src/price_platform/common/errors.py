"""错误分类与重试决策：决定一次失败是重试、进 DLQ 还是停用商品。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorType(str, Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    HTTP_4XX = "http_4xx"
    HTTP_5XX = "http_5xx"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    PARSE = "parse"
    INTERNAL = "internal"


RETRYABLE: frozenset[ErrorType] = frozenset(
    {ErrorType.NETWORK, ErrorType.TIMEOUT, ErrorType.HTTP_5XX, ErrorType.BLOCKED, ErrorType.INTERNAL}
)

TERMINAL_STATUS = {ErrorType.TIMEOUT: "timeout"}


class ScrapeError(Exception):
    """采集类错误的基类；子类只声明 error_type。"""

    error_type: ErrorType = ErrorType.INTERNAL
    retryable: bool = True

    def __init__(self, message: str = "", *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class NetworkError(ScrapeError):
    error_type = ErrorType.NETWORK


class TimeoutError_(ScrapeError):
    error_type = ErrorType.TIMEOUT


class Http4xxError(ScrapeError):
    error_type = ErrorType.HTTP_4XX
    retryable = False


class Http5xxError(ScrapeError):
    error_type = ErrorType.HTTP_5XX


class BlockedError(ScrapeError):
    error_type = ErrorType.BLOCKED


class NotFoundError(ScrapeError):
    error_type = ErrorType.NOT_FOUND
    retryable = False


class ParseError(ScrapeError):
    error_type = ErrorType.PARSE
    retryable = False


class InternalError(ScrapeError):
    error_type = ErrorType.INTERNAL


_NETWORK_HINTS = (
    "err_connection",
    "err_name_not_resolved",
    "err_network",
    "err_internet_disconnected",
    "err_timed_out",
    "err_address_unreachable",
    "err_ssl",
    "connection reset",
    "connection refused",
    "server disconnected",
)
_TIMEOUT_HINTS = ("timeout", "timed out", "timeouterror")


def classify(exc: BaseException) -> ErrorType:
    if isinstance(exc, ScrapeError):
        return exc.error_type

    name = type(exc).__name__.lower()
    text = f"{name} {exc}".lower()

    if isinstance(exc, (TimeoutError, OSError)) and "timeout" in text:
        return ErrorType.TIMEOUT
    if "timeout" in name or any(h in text for h in _TIMEOUT_HINTS):
        return ErrorType.TIMEOUT
    if any(h in text for h in _NETWORK_HINTS):
        return ErrorType.NETWORK
    if "captcha" in text or "验证码" in text or "access denied" in text:
        return ErrorType.BLOCKED
    return ErrorType.INTERNAL


def http_error(status: int, message: str = "") -> ScrapeError:
    if status == 404 or status == 410:
        return NotFoundError(message or f"http {status}", http_status=status)
    if status in (401, 403):
        return BlockedError(message or f"http {status}", http_status=status)
    if status == 429:
        return BlockedError(message or "http 429", http_status=status)
    if 400 <= status < 500:
        return Http4xxError(message or f"http {status}", http_status=status)
    return Http5xxError(message or f"http {status}", http_status=status)


@dataclass(frozen=True, slots=True)
class RetryDecision:
    status: str
    error_type: ErrorType
    retry: bool


def decide(error_type: ErrorType, attempt: int, max_retry: int) -> RetryDecision:
    retryable = error_type in RETRYABLE
    will_retry = retryable and attempt < max_retry
    if will_retry:
        status = "retry_wait"
    else:
        status = TERMINAL_STATUS.get(error_type, "failed")
    return RetryDecision(status=status, error_type=error_type, retry=will_retry)

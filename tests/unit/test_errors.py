from __future__ import annotations

import pytest

from price_platform.common.errors import (
    BlockedError,
    ErrorType,
    NetworkError,
    NotFoundError,
    ParseError,
    classify,
    decide,
    http_error,
)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (NetworkError("boom"), ErrorType.NETWORK),
        (TimeoutError("read timeout"), ErrorType.TIMEOUT),
        (ParseError("no price"), ErrorType.PARSE),
        (BlockedError("captcha"), ErrorType.BLOCKED),
        (NotFoundError("404"), ErrorType.NOT_FOUND),
        (RuntimeError("unexpected"), ErrorType.INTERNAL),
    ],
)
def test_classify(exc: BaseException, expected: ErrorType) -> None:
    assert classify(exc) is expected


def test_classify_playwright_like_error() -> None:
    class Error(Exception):
        pass

    err = Error("Page.goto: net::ERR_CONNECTION_REFUSED at http://x")
    assert classify(err) is ErrorType.NETWORK


def test_decide_retries_until_max() -> None:
    first = decide(ErrorType.NETWORK, attempt=1, max_retry=3)
    assert first.retry is True
    assert first.status == "retry_wait"

    last = decide(ErrorType.NETWORK, attempt=3, max_retry=3)
    assert last.retry is False
    assert last.status == "failed"


def test_decide_timeout_terminal_status() -> None:
    d = decide(ErrorType.TIMEOUT, attempt=3, max_retry=3)
    assert d.status == "timeout"
    assert d.retry is False


def test_decide_non_retryable_goes_failed() -> None:
    d = decide(ErrorType.PARSE, attempt=1, max_retry=3)
    assert d.retry is False
    assert d.status == "failed"


@pytest.mark.parametrize(
    ("status", "expected"),
    [(404, ErrorType.NOT_FOUND), (403, ErrorType.BLOCKED), (429, ErrorType.BLOCKED),
     (500, ErrorType.HTTP_5XX), (400, ErrorType.HTTP_4XX)],
)
def test_http_error_mapping(status: int, expected: ErrorType) -> None:
    err = http_error(status)
    assert classify(err) is expected

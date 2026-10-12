"""Tests for the wait time derived from a 429 response."""

from __future__ import annotations

from datetime import timedelta

from custom_components.skoda_api_connect.api import _rate_limit_wait

DETAIL = "Rate limit exceeded. Retry after 2740 seconds."


def test_retry_after_header_wins() -> None:
    headers = {"Retry-After": "30", "RateLimit-Reset": "2742"}
    assert _rate_limit_wait(headers, DETAIL) == timedelta(seconds=30)


def test_rate_limit_reset_header() -> None:
    assert _rate_limit_wait({"RateLimit-Reset": "2742"}, DETAIL) == timedelta(seconds=2742)


def test_detail_fallback() -> None:
    assert _rate_limit_wait({}, DETAIL) == timedelta(seconds=2740)


def test_unknown() -> None:
    assert _rate_limit_wait({}, "Too Many Requests") is None


def test_poll_result_has_retry_at_after_rate_limit() -> None:
    from custom_components.skoda_api_connect.api import SkodaRateLimitError
    from custom_components.skoda_api_connect.coordinator import _poll_result

    result = _poll_result(
        SkodaRateLimitError("x", status=429, retry_after=timedelta(seconds=2740))
    )
    assert result.retry_at is not None
    assert result.retry_at - result.time == timedelta(seconds=2740)


def test_poll_result_without_rate_limit_has_no_retry_at() -> None:
    from custom_components.skoda_api_connect.api import SkodaApiError
    from custom_components.skoda_api_connect.coordinator import _poll_result

    assert _poll_result(SkodaApiError("x", status=500)).retry_at is None


def test_rate_limit_info_from_headers() -> None:
    from custom_components.skoda_api_connect.api import _rate_limit_info

    info = _rate_limit_info(
        {"RateLimit-Limit": "20", "RateLimit-Remaining": "12", "RateLimit-Reset": "2700"}
    )
    assert info is not None
    assert (info.limit, info.remaining) == (20, 12)
    assert info.reset_at is not None
    assert info.reset_at - info.updated == timedelta(seconds=2700)
    assert _rate_limit_info({}) is None

"""Account-gate contention is a 409 with Retry-After, never a 500."""

from utils.other.account_gate_http import (
    ACCOUNT_GATE_BUSY_DETAIL,
    ACCOUNT_GATE_BUSY_RETRY_AFTER_SECONDS,
    account_gate_busy_http_exception,
)


def test_account_gate_busy_http_exception_is_409_with_short_retry_after():
    error = account_gate_busy_http_exception()
    assert error.status_code == 409
    assert error.detail == ACCOUNT_GATE_BUSY_DETAIL
    assert error.headers["Retry-After"] == str(ACCOUNT_GATE_BUSY_RETRY_AFTER_SECONDS)
    assert 1 <= ACCOUNT_GATE_BUSY_RETRY_AFTER_SECONDS <= 3

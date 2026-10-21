"""HTTP mapping for the per-account destructive-operation gate.

User-facing delete routes must not let ``DestructiveOperationInProgress``
escape as a 500. The gate stays exclusive; callers retry after a short wait.
"""

from fastapi import HTTPException

ACCOUNT_GATE_BUSY_DETAIL = "account_gate_busy"
ACCOUNT_GATE_BUSY_RETRY_AFTER_SECONDS = 2


def account_gate_busy_http_exception() -> HTTPException:
    """409 Conflict so clients back off instead of treating contention as a fault."""

    return HTTPException(
        status_code=409,
        detail=ACCOUNT_GATE_BUSY_DETAIL,
        headers={"Retry-After": str(ACCOUNT_GATE_BUSY_RETRY_AFTER_SECONDS)},
    )

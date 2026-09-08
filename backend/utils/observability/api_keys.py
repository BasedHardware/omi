import logging
from collections.abc import Collection
from typing import Literal

from utils.observability.fallback import record_fallback

ApiKeyKind = Literal["mcp", "dev"]
ApiKeyRepairOperation = Literal["list", "auth"]


def record_api_key_repairs(
    *,
    key_kind: ApiKeyKind,
    operation: ApiKeyRepairOperation,
    repairs: Collection[object],
    log: logging.Logger,
) -> None:
    """Record one bounded event when a key operation repairs internal state."""
    if not repairs:
        return
    repair_values = {getattr(repair, "value", repair) for repair in repairs}
    outcome = "degraded" if operation == "list" or (key_kind == "dev" and "scopes" in repair_values) else "recovered"
    record_fallback(
        component="other",
        from_mode=f"{key_kind}_stored_{operation}",
        to_mode=f"{key_kind}_safe_{operation}",
        reason="local_heal",
        outcome=outcome,
        log=log,
    )


def record_api_key_revocation_exhausted(*, key_kind: ApiKeyKind, log: logging.Logger) -> None:
    """Record a revocation that stopped before deleting persistent state."""
    record_fallback(
        component="other",
        from_mode=f"{key_kind}_revocation_cache",
        to_mode=f"{key_kind}_revocation_blocked",
        reason="auth",
        outcome="exhausted",
        log=log,
    )

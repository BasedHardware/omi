"""Bounded visibility of sync intake awaiting a same-capture live bridge.

This is independent of enrichment's quiet hold and of episode admission.
The deadline is never renewed by appends or retries; expiry is enforced by
readers as well as workers, so a lost worker cannot hide a recording forever.
"""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from utils.conversations.fragment_visibility import is_user_curated, is_completed_rule_discard

FIELD = 'sync_bridge_pending'
MAX_WAIT_SECONDS = 600


def current_time() -> float:
    return datetime.now(timezone.utc).timestamp()


def hidden(row: Mapping[str, Any], *, now: float | None = None) -> bool:
    state = row.get(FIELD)
    if not isinstance(state, Mapping) or is_user_curated(row):
        return False
    deadline = state.get('expires_at')
    return isinstance(deadline, (float, int)) and deadline > (current_time() if now is None else now)


def hidden_from_default_detail(row: Mapping[str, Any]) -> bool:
    """Default detail reads preserve the same bridge/noise visibility as Home."""
    return hidden(row) or is_completed_rule_discard(row)


def live_finalization_owns(row: Mapping[str, Any]) -> bool:
    """Open capture or a bound processing job owns live finalization.

    A bare processing row can belong to sync's own retry; it must remain
    reprocessable rather than waiting for a durable owner that does not exist.
    """
    return bool(
        row.get('sync_live_target')
        and (
            row.get('status') == 'in_progress' or (row.get('status') == 'processing' and row.get('finalization_job_id'))
        )
    )

"""Universal first-summary deadlines with independent repair and preservation controls."""

from config.refactor_switches import default_off as rollout_default_off

from contextvars import ContextVar
from collections.abc import Mapping
import math
import os

from typing import Any

ADMITTED_OWNER: ContextVar[str | None] = ContextVar('admitted_first_summary_owner', default=None)


def repair_enabled() -> bool:
    return rollout_default_off(
        'SUMMARY_DEBT_REPAIR_ENABLED', os.getenv('SUMMARY_DEBT_REPAIR_ENABLED', 'false').strip().lower() == 'true'
    )


def deadline_seconds() -> int:
    try:
        return max(60, min(120, int(os.getenv('FIRST_SUMMARY_DEADLINE_SECONDS', '120'))))
    except ValueError:
        return 120


# One global leased scan per interval, irrespective of replica count.
REPAIR_INTERVAL_SECONDS = 120
REPAIR_SCAN_LIMIT = 100
REPAIR_ADMISSION_LIMIT = 10


def preserves_admitted(row: Mapping[str, Any]) -> bool:
    """A durable deadline retains its policy after percent/allowlist rollback."""
    deadline = row.get('summary_deadline_at')
    return (
        rollout_default_off(
            'FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED',
            os.getenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', 'false').strip().lower() == 'true',
        )
        and not row.get('summary_seen')
        and not row.get('effects_only')
        and isinstance(deadline, (int, float))
        and not isinstance(deadline, bool)
        and math.isfinite(deadline)
    )


def first_summary_pending(row: Mapping[str, Any]) -> bool:
    if row.get('first_summary_policy') is not None:
        from config.policy import FirstSummaryPolicy

        return bool(
            not row.get('effects_only')
            and not row.get('summary_seen')
            and FirstSummaryPolicy.from_dict(row['first_summary_policy']).first_summary_enabled
        )
    return not row.get('effects_only') and not row.get('summary_seen')

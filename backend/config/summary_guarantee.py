"""Universal first-summary deadlines with independent repair and preservation controls."""

from config.refactor_modes import default_on
from config.refactor_switches import default_off as rollout_default_off

from contextvars import ContextVar
from collections.abc import Mapping
import math
import os
import time
from datetime import datetime, timezone

from typing import Any

ADMITTED_OWNER: ContextVar[str | None] = ContextVar('admitted_first_summary_owner', default=None)


def repair_enabled(*, environ: Mapping[str, str] | None = None) -> bool:
    values = os.environ if environ is None else environ
    return rollout_default_off(
        'SUMMARY_DEBT_REPAIR_ENABLED',
        values.get('SUMMARY_DEBT_REPAIR_ENABLED', 'false').strip().lower() == 'true',
        environ=environ,
    )


def deadline_seconds() -> int:
    try:
        return max(60, min(120, int(os.getenv('FIRST_SUMMARY_DEADLINE_SECONDS', '120'))))
    except ValueError:
        return 120


def _repair_limit(value: str, *, default: int, maximum: int) -> int:
    try:
        return max(1, min(maximum, int(value)))
    except ValueError:
        return default


# One global leased scan per interval, irrespective of replica count.
REPAIR_INTERVAL_SECONDS = 120
REPAIR_SCAN_LIMIT = _repair_limit(os.getenv('SUMMARY_DEBT_REPAIR_SCAN_LIMIT', '100'), default=100, maximum=5000)
REPAIR_QUERY_PAGE_LIMIT = 500
# Stop starting scan work before the 120-second lease ends; in-flight RPCs may finish later.
REPAIR_SCAN_TIME_BUDGET_SECONDS = 90
REPAIR_ADMISSION_LIMIT = _repair_limit(os.getenv('SUMMARY_DEBT_REPAIR_ADMISSION_LIMIT', '8'), default=8, maximum=60)
REPAIR_PER_OWNER_TICK_LIMIT = _repair_limit(
    os.getenv('SUMMARY_DEBT_REPAIR_PER_OWNER_LIMIT', '3'), default=3, maximum=10
)
# Five ticks (10 minutes): up to 40 attempts at the default admission limit
# before expiry at the configured cadence. This is headroom, not a throughput
# guarantee when urgent arrivals exceed capacity or admissions are blocked.
REPAIR_NEAR_EXPIRY_SECONDS = 5 * REPAIR_INTERVAL_SECONDS


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


# --- First-week guarantee (SCA-4790) -------------------------------------
# A conversation created by a new paid subscription inside its first window keeps
# its first-summary obligation open until the window closes, instead of being
# closed by the 72 h historical age gate, the repair age bound, or the 30-minute
# fresh-lane demotion. The window is stored on the row (``first_week_summary``)
# and never recomputed from wall-clock age at read time.
FIRST_WEEK_ENABLED_ENV = 'FIRST_WEEK_SUMMARY_GUARANTEE_ENABLED'
FIRST_WEEK_WINDOW_ENV = 'FIRST_WEEK_SUMMARY_DEADLINE_HOURS'
FIRST_WEEK_POLICY_ID = 'first_week_summary.v1'
FIRST_WEEK_INTERVALS = ('monthly', 'yearly', 'unknown')
FIRST_WEEK_DEFAULT_HOURS = 168


def first_week_enabled(*, environ: Mapping[str, str] | None = None) -> bool:
    """Kill switch, default on. Off restores the previous deadline and lane priority."""
    return default_on(FIRST_WEEK_ENABLED_ENV, environ=environ)


def first_week_window_seconds(*, environ: Mapping[str, str] | None = None) -> int:
    raw = (os.environ if environ is None else environ).get(FIRST_WEEK_WINDOW_ENV, '').strip()
    if not raw:
        return FIRST_WEEK_DEFAULT_HOURS * 3600
    try:
        hours = float(raw)
    except ValueError:
        return FIRST_WEEK_DEFAULT_HOURS * 3600
    if not math.isfinite(hours) or hours < 0:
        return FIRST_WEEK_DEFAULT_HOURS * 3600
    return int(hours * 3600)


def _epoch(value: Any) -> float | None:
    if isinstance(value, datetime):
        value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        value = value.timestamp()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def first_week_interval(period_start: Any, period_end: Any) -> str:
    """Monthly/yearly from the paid period length; never a catalog read."""
    start, end = _epoch(period_start), _epoch(period_end)
    if start is None or end is None or end <= start:
        return 'unknown'
    days = (end - start) / 86400
    if days <= 45:
        return 'monthly'
    if days >= 300:
        return 'yearly'
    return 'unknown'


def first_week_stamp(
    paid_since: Any,
    created_at: Any,
    *,
    interval: str = 'unknown',
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    """The stored first-week window for a conversation created inside a paid window.

    ``paid_since`` is the commercial first-paid epoch (never a renewal period
    start). A missing epoch or a conversation outside the window returns ``None``,
    which leaves today's behavior: existing payers are never covered.
    """
    if not first_week_enabled(environ=environ):
        return None
    window = first_week_window_seconds(environ=environ)
    start, created = _epoch(paid_since), _epoch(created_at)
    if window <= 0 or start is None or created is None:
        return None
    end = int(start + window)
    if created < start or created >= end:
        return None
    return {
        'policy_id': FIRST_WEEK_POLICY_ID,
        'paid_since': int(start),
        'window_end_at': end,
        'interval': interval if interval in FIRST_WEEK_INTERVALS else 'unknown',
    }


def first_week_window_end(row: Mapping[str, Any]) -> float | None:
    """The stored window end from a conversation or outbox row copy."""
    stamp = row.get('first_week_summary')
    if not isinstance(stamp, Mapping):
        return None
    end = _epoch(stamp.get('window_end_at'))
    return end


def first_week_open(row: Mapping[str, Any], *, now: float | None = None) -> bool:
    """True while a stamped first-week obligation is still inside its window."""
    if not first_week_enabled():
        return False
    end = first_week_window_end(row)
    if end is None:
        return False
    return (time.time() if now is None else now) < end

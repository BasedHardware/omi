"""Historical processing tier (T1+): the age rule and its kill switches.

Sync backfill or batch audio whose capture started more than the tier age ago
is stored with a transcript, speakers and a deterministic title, and gets its
summary only when the owner opens it (``POST /v1/conversations/{id}/summary/open``).
No memories, tasks, apps, folders, webhooks or notifications ever run for it.

Lifecycle: ops_kill; owner sync lane; permanent env kill switches, on unless set
to a false word. Env is read at the call boundary, never at import.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any

from config.refactor_modes import default_on

TIER = 'historical'
TIER_ENABLED_ENV = 'SYNC_HISTORICAL_TIER_ENABLED'
OPEN_ENABLED_ENV = 'HISTORICAL_SUMMARY_ON_OPEN_ENABLED'
VECTOR_ENABLED_ENV = 'HISTORICAL_SUMMARY_VECTOR_ENABLED'
MIN_AGE_ENV = 'SYNC_HISTORICAL_TIER_MIN_AGE_SECONDS'
GLOBAL_DAILY_LIMIT_ENV = 'HISTORICAL_SUMMARY_GLOBAL_DAILY_LIMIT'

# Matches the 11-04 enrichment age gate (ENRICHMENT_MAX_AGE_HOURS=72): older
# backfill already gets no automatic LLM work, so this is the tier boundary.
DEFAULT_MIN_AGE_SECONDS = 72 * 3600
MIN_AGE_FLOOR_SECONDS = 72 * 3600
MIN_AGE_CEILING_SECONDS = 60 * 86400
DEFAULT_GLOBAL_DAILY_LIMIT = 10000
UNTRUSTED = 'untrusted'
TERMINAL_NO_DERIVED_EFFECTS_FIELD = 'terminal_no_derived_effects'
BLOCKED_REASON = 'historical_on_open'


def tier_enabled() -> bool:
    """Stamp new old-capture rows historical. False restores full processing for new rows."""
    return default_on(TIER_ENABLED_ENV)


def open_enabled() -> bool:
    """Serve summary-on-open. False answers 503 and stops advertising ``summary_on_open``."""
    return default_on(OPEN_ENABLED_ENV)


def vector_enabled() -> bool:
    """Index the summary vector after an open-time summary lands."""
    return default_on(VECTOR_ENABLED_ENV)


def min_age_seconds() -> int:
    raw = os.getenv(MIN_AGE_ENV, '').strip()
    try:
        value = float(raw) if raw else float(DEFAULT_MIN_AGE_SECONDS)
    except ValueError:
        return DEFAULT_MIN_AGE_SECONDS
    if not math.isfinite(value):
        return DEFAULT_MIN_AGE_SECONDS
    return int(min(max(value, MIN_AGE_FLOOR_SECONDS), MIN_AGE_CEILING_SECONDS))


def global_daily_limit() -> int:
    """Fleet-wide open-time summaries per day; 0 disables the cap. Invalid keeps the default."""
    raw = os.getenv(GLOBAL_DAILY_LIMIT_ENV, '').strip()
    try:
        value = int(raw) if raw else DEFAULT_GLOBAL_DAILY_LIMIT
    except ValueError:
        return DEFAULT_GLOBAL_DAILY_LIMIT
    return max(value, 0)


def _epoch(value: Any) -> float | None:
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return moment.timestamp()
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
        return float(value)
    return None


def applies(capture_start: Any, trust: Any, now: Any = None) -> bool:
    """True when a trusted capture clock started more than the tier age before ``now``.

    A clamped, estimated or otherwise untrusted clock proves no age (the row
    carries receipt time), so it always keeps full processing.
    """
    if getattr(trust, 'value', trust) == UNTRUSTED:
        return False
    started = _epoch(capture_start)
    current = _epoch(now) if now is not None else datetime.now(timezone.utc).timestamp()
    if started is None or current is None:
        return False
    # Strictly older, like the enrichment age gate: a row exactly at the
    # boundary is still enriched there, so it keeps full processing here.
    return current - started > min_age_seconds()


def is_historical(row: Any) -> bool:
    value = row.get('processing_tier') if isinstance(row, dict) else getattr(row, 'processing_tier', None)
    return value == TIER

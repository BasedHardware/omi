"""Usage period and partial projection charge boundaries."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

_USAGE_PERIOD = re.compile(r'(\d{4})-(\d{2})')


def usage_stamp(now: datetime, usage_period: Any) -> datetime:
    """Hour stamp for projection usage: ``now``, backdated into ``usage_period`` only across a rollover.

    A cap-hold unit admitted under the owner's funded choice in month M is billed to M even when
    projection completes in M+1 (lane 6, Subscription ruling B(a)). The stamp moves only backwards, to
    the period's last second, and the hourly doc id/year/month/day/hour all derive from it, so the
    month query reads it as M (transcription has no day rollup). Missing or malformed periods keep now.
    """
    match = _USAGE_PERIOD.fullmatch(usage_period) if isinstance(usage_period, str) else None
    if match is None or not 1 <= int(match.group(2)) <= 12:
        return now
    start = datetime(int(match.group(1)), int(match.group(2)), 1, tzinfo=timezone.utc)
    end = (start + timedelta(days=32)).replace(day=1)
    return end - timedelta(seconds=1) if now >= end else now


def charge_chain(ledger: dict) -> tuple[list[float], list[float | None]]:
    """A partial ledger's charge boundaries (from 0.0) and each step's commit time.

    A step without a recorded time (an unknown age) is never re-issued: its
    fair-use once-key may already have expired.
    """
    steps = ledger.get('usage_steps')
    if not (isinstance(steps, list) and steps and steps[0] == 0.0):
        committed = ledger.get('usage_committed_seconds', 0.0)
        steps = [0.0, committed] if committed else [0.0]
    times = ledger.get('usage_step_times')
    if not (isinstance(times, list) and len(times) == len(steps) - 1):
        times = [None] * (len(steps) - 1)
    return list(steps), list(times)


def extend_chain(steps, times, seconds: float, now: float) -> tuple[list[float], list[float | None]]:
    if seconds > steps[-1]:
        return [*steps, seconds], [*times, now]
    return list(steps), list(times)

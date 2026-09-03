"""Durable-queue substrate adapter for the daily memory sweep UID batch.

The scheduler in daily_memory_sweep.py already isolates per UID; this module is
the shared drain so a poison UID cannot be reimplemented as an aborting loop.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterable, List, Optional, Sequence

from database.durable_queue import OutcomeKind, ProcessOutcome, drain_isolated, oldest_ready_age_seconds
from utils.durable_queue_metrics import observe_oldest_ready_age


def drain_sweep_uids(
    uids: Sequence[str],
    process_one: Callable[[str], ProcessOutcome],
    *,
    ready_created_at: Optional[Iterable[Optional[datetime]]] = None,
    now: Optional[datetime] = None,
) -> List[str]:
    """Process each UID independently and return the ones that acknowledged."""
    results = drain_isolated(uids, process_one)
    observe_oldest_ready_age(
        'daily_memory_sweep',
        oldest_ready_age_seconds(list(ready_created_at or []), now=now or datetime.now(timezone.utc)),
    )
    return [str(result.item) for result in results if result.outcome.kind == OutcomeKind.ACK]

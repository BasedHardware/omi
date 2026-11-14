"""Scheduler-owned census pass: sample every registered stock, then publish gauges.

The scheduler endpoint is the only caller. One entry at a time is dispatched to
the shared ``db_executor`` behind a small semaphore: concurrency is bounded and
no ad-hoc thread pool is created. Gauges are published in the process that runs
this pass, so GMP sees one replica with fresh values and the others with no
series (or an older observation timestamp). Alerts read the newest observation,
never a sum across replicas.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from config.batch_census import ENTRIES, CensusEntry
from database import batch_census_export
from utils.executors import db_executor, run_blocking
from utils.observability.batch_census import publish

logger = logging.getLogger(__name__)

# A failed stock is reported, not raised: one broken query must not hide the
# other stocks the same pass measured.
OUTCOME_OK = 'ok'
OUTCOME_PARTIAL = 'partial'
OUTCOME_DISABLED = 'disabled'
CONCURRENCY = 4


def _firestore_client() -> Any:
    from database._client import get_data_plane_firestore_client

    return get_data_plane_firestore_client()


def _prepare(firestore_client: Any) -> tuple[Any, float]:
    """Sync leaf: kill switch, client and RPC budget, off the event loop.

    Reading the switch and the budget here keeps them at the call boundary
    instead of snapshotted at import, and keeps the async coordinator free of
    module-level config calls that the async-blocker gate cannot classify.
    A disabled census keeps the configured budget so the return type stays one
    shape; the caller never samples in that case.
    """
    budget = batch_census_export.rpc_timeout_seconds()
    if not batch_census_export.enabled():
        return None, budget
    return (firestore_client or _firestore_client()), budget


def _sample(client: Any, entry: CensusEntry, moment: float, budget: float) -> Any:
    try:
        return batch_census_export.sample_entry(client, entry, now=moment, timeout=budget)
    except Exception as error:  # One stock's failure must not blind the others.
        logger.warning(
            'event=batch_census_sample outcome=error key=%s exception_type=%s', entry.key, type(error).__name__
        )
        return None


async def snapshot(
    *,
    firestore_client: Any = None,
    now: float | None = None,
    timeout: float | None = None,
    concurrency: int = CONCURRENCY,
    entries: tuple[CensusEntry, ...] = ENTRIES,
) -> dict[str, Any]:
    """One census pass. Returns counts-only metadata; no uid or content."""
    client, configured_budget = await run_blocking(db_executor, _prepare, firestore_client)
    if client is None:
        return {'status': OUTCOME_DISABLED, 'stocks': 0, 'failed': 0, 'units': 0}
    moment = time.time() if now is None else now
    budget = configured_budget if timeout is None else timeout
    gate = asyncio.Semaphore(max(1, concurrency))

    async def one(entry: CensusEntry) -> tuple[str, Any]:
        async with gate:
            sample = await run_blocking(db_executor, _sample, client, entry, moment, budget)
        return entry.key, sample

    samples: dict[str, Any] = {}
    failures: list[str] = []
    for key, sample in await asyncio.gather(*(one(entry) for entry in entries)):
        if sample is None:
            failures.append(key)
        else:
            samples[key] = sample
    published = publish(samples, failures=failures, now=now)
    units = sum(int(sample.units) for sample in samples.values())
    outcome = OUTCOME_PARTIAL if failures else OUTCOME_OK
    logger.info(
        'event=batch_census outcome=%s stocks=%d failed=%d units=%d',
        outcome,
        published,
        len(failures),
        units,
    )
    return {'status': outcome, 'stocks': published, 'failed': len(failures), 'units': units}

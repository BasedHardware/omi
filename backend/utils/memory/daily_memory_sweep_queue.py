"""Durable-queue drain for the daily memory sweep UID batch.

The scheduler supplies per-UID work; this module owns the process loop so a
poison UID cannot be reimplemented as an aborting ``for``/``try``/``except``.
Cleanup and the #12533 process loop both drain through ``drain_isolated``.
"""

from __future__ import annotations

from typing import Callable, List, Sequence

from utils.durable_queue_policy import OutcomeKind, ProcessOutcome, drain_isolated


def drain_sweep_uids(
    uids: Sequence[str],
    process_one: Callable[[str], ProcessOutcome],
) -> List[str]:
    """Process each UID independently and return the ones that acknowledged."""
    results = drain_isolated(uids, process_one)
    return [str(result.item) for result in results if result.outcome.kind == OutcomeKind.ACK]


__all__ = ['ProcessOutcome', 'drain_sweep_uids']

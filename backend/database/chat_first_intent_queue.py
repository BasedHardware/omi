"""Chat-first ready-intent drain: substrate sort plus per-item isolation.

Kept out of ``chat_first_intents.py`` so that 1,500-line file does not grow.
"""

from __future__ import annotations

import itertools
from typing import Any, Callable, Iterable, List, Sequence, TypeVar

from database.durable_queue import ProcessOutcome, drain_isolated, ready_sort_key

T = TypeVar('T')


def sort_ready_intents(
    intents: Sequence[Any],
    *,
    priority_of: Callable[[Any], int],
) -> List[Any]:
    if not isinstance(intents, (list, tuple)):
        raise ValueError("intents must be a sequence")
    if not callable(priority_of):
        raise ValueError("priority_of must be callable")
    return sorted(
        intents,
        key=lambda intent: ready_sort_key(
            priority=priority_of(intent),
            created_at=intent.created_at,
            item_id=intent.intent_id,
            enable_priority=True,
        ),
    )


def drain_intent_batch(
    items: Iterable[T],
    process_one: Callable[[T], ProcessOutcome],
    *,
    max_items: int | None = None,
) -> None:
    if not callable(process_one):
        raise ValueError("process_one must be callable")
    if max_items is not None:
        if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 0:
            raise ValueError("max_items must be a non-negative integer")
    if items is None:
        return
    if max_items is not None:
        to_drain: Iterable[T] = itertools.islice(items, max_items)
    else:
        to_drain = items
    drain_isolated(to_drain, process_one)

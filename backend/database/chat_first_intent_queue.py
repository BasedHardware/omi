"""Chat-first ready-intent drain: substrate sort plus per-item isolation.

Kept out of ``chat_first_intents.py`` so that 1,500-line file does not grow.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, List, Sequence, TypeVar

from database.durable_queue import ProcessOutcome, drain_isolated, ready_sort_key

T = TypeVar('T')


def sort_ready_intents(
    intents: Sequence[Any],
    *,
    priority_of: Callable[[Any], int],
) -> List[Any]:
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
) -> None:
    drain_isolated(items, process_one)

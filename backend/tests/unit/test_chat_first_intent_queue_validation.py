from datetime import datetime, timezone
from types import SimpleNamespace
from typing import List
import pytest

from database.chat_first_intent_queue import drain_intent_batch, sort_ready_intents
from database.durable_queue import ProcessOutcome


def test_sort_ready_intents_rejects_non_callable_priority_of():
    """sort_ready_intents must fail fast if priority_of is not callable, even with empty intents."""
    with pytest.raises(TypeError, match="priority_of must be callable"):
        sort_ready_intents([], priority_of=None)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="priority_of must be callable"):
        sort_ready_intents([], priority_of="not_a_function")  # type: ignore[arg-type]


def test_sort_ready_intents_rejects_non_sequence_intents():
    """sort_ready_intents must fail fast if intents is not a sequence."""
    with pytest.raises(TypeError, match="intents must be a sequence"):
        sort_ready_intents(None, priority_of=lambda x: 1)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="intents must be a sequence"):
        sort_ready_intents(12345, priority_of=lambda x: 1)  # type: ignore[arg-type]

    # Generators are iterables but not sequences; must raise TypeError
    with pytest.raises(TypeError, match="intents must be a sequence"):
        sort_ready_intents((x for x in [1, 2, 3]), priority_of=lambda x: 1)  # type: ignore[arg-type]


def test_drain_intent_batch_rejects_non_callable_process_one():
    """drain_intent_batch must fail fast with TypeError if process_one is not callable."""
    item = SimpleNamespace(intent_id="intent_1", created_at=datetime.now(timezone.utc))
    with pytest.raises(TypeError, match="process_one must be callable"):
        drain_intent_batch([item], process_one=None)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="process_one must be callable"):
        drain_intent_batch([item], process_one="not_callable")  # type: ignore[arg-type]


def test_sort_ready_intents_sorts_correctly():
    """Valid intents are sorted according to priority and substrate sort key."""
    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    item_low_priority = SimpleNamespace(intent_id="low", created_at=t1, prio=10)
    item_high_priority = SimpleNamespace(intent_id="high", created_at=t2, prio=1)

    result = sort_ready_intents(
        [item_low_priority, item_high_priority],
        priority_of=lambda x: x.prio,
    )
    assert [x.intent_id for x in result] == ["high", "low"]


def test_drain_intent_batch_processes_items():
    """Valid process_one is executed for each item."""
    processed: List[str] = []

    def processor(item: SimpleNamespace) -> ProcessOutcome:
        processed.append(item.intent_id)
        return ProcessOutcome.ack()

    items = [SimpleNamespace(intent_id="a"), SimpleNamespace(intent_id="b")]
    drain_intent_batch(items, processor)
    assert processed == ["a", "b"]

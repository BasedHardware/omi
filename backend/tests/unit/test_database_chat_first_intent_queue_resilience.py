"""Unit tests verifying defensive boundary guards in chat_first_intent_queue."""

import pytest

from database.chat_first_intent_queue import drain_intent_batch, sort_ready_intents
from database.durable_queue import ProcessOutcome


class DummyIntent:
    def __init__(self, intent_id: str, priority: int = 1, created_at: object = None):
        self.intent_id = intent_id
        self.priority = priority
        self.created_at = created_at


def test_sort_ready_intents_rejects_non_sequence():
    """Verify sort_ready_intents rejects non-sequence inputs."""
    with pytest.raises(ValueError, match="intents must be a sequence"):
        sort_ready_intents("not-a-sequence", priority_of=lambda x: 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="intents must be a sequence"):
        sort_ready_intents(None, priority_of=lambda x: 1)  # type: ignore[arg-type]


def test_sort_ready_intents_rejects_non_callable_priority():
    """Verify sort_ready_intents rejects non-callable priority_of."""
    with pytest.raises(ValueError, match="priority_of must be callable"):
        sort_ready_intents([], priority_of=None)  # type: ignore[arg-type]


def test_sort_ready_intents_orders_correctly():
    """Verify sort_ready_intents orders intents by priority and id."""
    i1 = DummyIntent("b", priority=2)
    i2 = DummyIntent("a", priority=1)
    i3 = DummyIntent("c", priority=1)

    result = sort_ready_intents([i1, i2, i3], priority_of=lambda x: x.priority)
    assert [x.intent_id for x in result] == ["a", "c", "b"]


def test_drain_intent_batch_none_items_noop():
    """Verify drain_intent_batch gracefully handles None items when args are valid."""
    processed = []
    drain_intent_batch(None, lambda x: processed.append(x) or ProcessOutcome.ack())  # type: ignore[arg-type]
    assert processed == []


def test_drain_intent_batch_none_items_validates_callable_and_max_items():
    """Verify drain_intent_batch fails fast on invalid process_one or max_items even when items is None."""
    with pytest.raises(ValueError, match="process_one must be callable"):
        drain_intent_batch(None, None)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="max_items must be a non-negative integer"):
        drain_intent_batch(None, lambda x: ProcessOutcome.ack(), max_items=-1)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="max_items must be a non-negative integer"):
        drain_intent_batch(None, lambda x: ProcessOutcome.ack(), max_items=True)  # type: ignore[arg-type]


def test_drain_intent_batch_lazy_bounded_consumption():
    """Verify max_items uses lazy bounded consumption and does not exhaust generators."""
    consumed_count = 0

    def infinite_counter():
        nonlocal consumed_count
        while True:
            consumed_count += 1
            yield consumed_count

    processed = []

    def handle(item):
        processed.append(item)
        return ProcessOutcome.ack()

    drain_intent_batch(infinite_counter(), handle, max_items=3)
    assert processed == [1, 2, 3]
    # itertools.islice takes exactly 3 items without pulling further
    assert consumed_count == 3


def test_drain_intent_batch_rejects_non_callable():
    """Verify drain_intent_batch rejects non-callable process_one."""
    with pytest.raises(ValueError, match="process_one must be callable"):
        drain_intent_batch([1, 2], None)  # type: ignore[arg-type]


def test_drain_intent_batch_clamps_max_items():
    """Verify max_items clamps number of processed elements."""
    processed = []

    def handle(item):
        processed.append(item)
        return ProcessOutcome.ack()

    drain_intent_batch([1, 2, 3, 4, 5], handle, max_items=2)
    assert processed == [1, 2]


def test_drain_intent_batch_rejects_invalid_max_items():
    """Verify max_items rejects negative numbers and booleans."""
    with pytest.raises(ValueError, match="max_items must be a non-negative integer"):
        drain_intent_batch([], lambda x: ProcessOutcome.ack(), max_items=-1)
    with pytest.raises(ValueError, match="max_items must be a non-negative integer"):
        drain_intent_batch([], lambda x: ProcessOutcome.ack(), max_items=True)  # type: ignore[arg-type]


def test_drain_intent_batch_isolates_exceptions():
    """Verify drain_intent_batch continues on exception in process_one."""
    processed = []

    def handle(item):
        processed.append(item)
        if item == 2:
            raise RuntimeError("Item 2 failed")
        return ProcessOutcome.ack()

    drain_intent_batch([1, 2, 3], handle)
    assert processed == [1, 2, 3]

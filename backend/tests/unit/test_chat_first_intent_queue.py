import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from database.chat_first_intent_queue import drain_intent_batch, sort_ready_intents
from database.durable_queue import ProcessOutcome


class DummyIntent:
    def __init__(self, intent_id: str, created_at: datetime, priority_val: int = 1):
        self.intent_id = intent_id
        self.created_at = created_at
        self.priority_val = priority_val


class TestChatFirstIntentQueue(unittest.TestCase):
    def test_sort_ready_intents_empty(self):
        res = sort_ready_intents([], priority_of=lambda x: 0)
        self.assertEqual(res, [])

    def test_sort_ready_intents_ordering(self):
        t1 = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 30, 10, 5, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 30, 10, 10, 0, tzinfo=timezone.utc)

        # Higher priority (lower int in ready_sort_key) should come first
        i1 = DummyIntent(intent_id="id1", created_at=t2, priority_val=2)
        i2 = DummyIntent(intent_id="id2", created_at=t1, priority_val=1)
        i3 = DummyIntent(intent_id="id3", created_at=t3, priority_val=1)

        intents = [i1, i2, i3]
        sorted_intents = sort_ready_intents(intents, priority_of=lambda x: x.priority_val)

        # i2 (priority 1, created earlier t1) -> i3 (priority 1, created later t3) -> i1 (priority 2)
        self.assertEqual([i.intent_id for i in sorted_intents], ["id2", "id3", "id1"])

    @patch("database.chat_first_intent_queue.drain_isolated")
    def test_drain_intent_batch(self, mock_drain_isolated):
        items = ["item1", "item2"]
        process_fn = MagicMock(return_value=ProcessOutcome.ack())

        drain_intent_batch(items, process_fn)
        mock_drain_isolated.assert_called_once_with(items, process_fn)


if __name__ == "__main__":
    unittest.main()

"""The C3 maintenance entry must reach lost wakes beyond a healthy backlog."""

from copy import deepcopy
from types import SimpleNamespace
import pytest

from database.outbox_firestore import ENRICHMENT_OUTBOX
from tests.unit.test_sync_reprocess_coalesce import state  # noqa: F401
from utils.enrichment import custody, outbox, scan


@pytest.mark.parametrize('expired_lease', [False, True])
def test_c3_watchdog_advances_past_valid_prefix_and_wraps(state, monkeypatch, expired_lease):  # noqa: F811
    rows, wakes = state
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    monkeypatch.setattr(custody, 'discard_blocked', lambda _: False)
    for index in range(7):
        outbox.mark('synthetic-owner', str(index), 'en', now=index)
    lost = outbox.key('synthetic-owner', '6')
    original = rows[lost]['task_token']
    if expired_lease:
        rows[lost].update(owner='abandoned-worker', lease_until=999)
    wakes.clear()
    monkeypatch.setattr(outbox, '_wake_exists', lambda row: row['document_id'] != lost)

    checkpoint = [None]
    monkeypatch.setattr(scan, 'begin', lambda *_: (None, checkpoint[0]))

    def finish(_previous, last, exhausted):
        checkpoint[0] = None if exhausted else (last.to_dict()['due_at'], last.id)

    monkeypatch.setattr(scan, 'finish', finish)

    class Query:
        def __init__(self, after=None, size=100):
            self.after, self.size = after, size

        def where(self, *_):
            return self

        def order_by(self, *_):
            return self

        def limit(self, size):
            return Query(self.after, size)

        def start_after(self, position):
            if not isinstance(position, tuple):
                position = (position.to_dict()['due_at'], position.id)
            return Query(position, self.size)

        def stream(self):
            ordered = sorted((row['due_at'], key) for key, row in rows.items())
            selected = [pair for pair in ordered if self.after is None or pair > self.after][: self.size]
            return [SimpleNamespace(id=key, to_dict=lambda key=key: deepcopy(rows[key])) for _, key in selected]

    monkeypatch.setattr(outbox, 'get_firestore_client', lambda: SimpleNamespace(collection=lambda _: Query()))
    for _ in range(4):
        assert ENRICHMENT_OUTBOX.sweep(now=1000, limit=2).errors == 0
    assert len(wakes) == 1 and wakes[0]['document_id'] == lost
    assert rows[lost]['task_token'] != original
    assert rows[lost]['first_pending_at'] == 6 and rows[lost]['summary_deadline_at'] == 126
    assert checkpoint[0] is None  # the short final page wraps for newly overdue work

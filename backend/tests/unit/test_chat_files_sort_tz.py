"""database.chat.get_chat_files_desc must not TypeError sorting files with mixed tz-aware/missing created_at.

In the >30-file chunked merge path, the per-file sort key used a bare naive datetime.min default. Stored
created_at is tz-aware (datetime.now(timezone.utc)), so a file doc missing created_at made the sort compare
a naive sentinel with an aware value -> "can't compare offset-naive and offset-aware datetimes" TypeError
-> 500. The sentinel is now tz-aware, mirroring the sort keys in action_items / task_recommendations /
memory_ledger. database.chat is light (module-level db proxy), so the test drives it directly.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from datetime import datetime, timezone
from unittest.mock import MagicMock

import database.chat as chat


def _doc(data):
    doc = MagicMock()
    doc.to_dict.return_value = data
    return doc


def _fake_db(stream_batches):
    fake = MagicMock()
    for attr in ('collection', 'document', 'where', 'order_by', 'limit'):
        getattr(fake, attr).return_value = fake
    fake.stream.side_effect = stream_batches  # one batch per 30-id chunk
    return fake


def _many_ids(n=31):
    return [f'f{i}' for i in range(n)]  # >30 -> triggers the chunked merge + manual sort


def test_sort_tolerates_missing_created_at_across_chunks(monkeypatch):
    aware_old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    aware_new = datetime(2026, 2, 1, tzinfo=timezone.utc)
    chunk1 = [_doc({'id': 'new', 'created_at': aware_new}), _doc({'id': 'missing'})]
    chunk2 = [_doc({'id': 'old', 'created_at': aware_old})]
    monkeypatch.setattr(chat, 'db', _fake_db([chunk1, chunk2]))
    # Before the fix this raised TypeError (naive datetime.min default vs tz-aware created_at).
    result = chat.get_chat_files_desc('u1', files_id=_many_ids(), limit=100)
    assert [r['id'] for r in result] == ['new', 'old', 'missing']  # missing sorts last, no 500


def test_sort_orders_newest_first_across_chunks(monkeypatch):
    aware_old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    aware_new = datetime(2026, 2, 1, tzinfo=timezone.utc)
    chunk1 = [_doc({'id': 'old', 'created_at': aware_old})]
    chunk2 = [_doc({'id': 'new', 'created_at': aware_new})]
    monkeypatch.setattr(chat, 'db', _fake_db([chunk1, chunk2]))
    result = chat.get_chat_files_desc('u1', files_id=_many_ids(), limit=100)
    assert [r['id'] for r in result] == ['new', 'old']  # merged descending across chunks

"""get_action_items must read only as far as the requested page.

The conversations query carries no limit, so the function streamed and decrypted
every completed conversation a user has ever had and only then sliced the flattened
items down to `limit`. The `limit` argument bounded the response, not the work, on a
read that routers/action_items.py, chat_first.py, developer.py, integration.py,
mcp.py, mcp_sse.py and tools.py all call.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from database import conversations as conversations_db


class _Doc:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


class _Query:
    """Records how many documents the caller actually pulled off the stream."""

    def __init__(self, docs, counter):
        self._docs = docs
        self._counter = counter

    def where(self, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def stream(self):
        for doc in self._docs:
            self._counter['read'] += 1
            yield doc


def _conversation(index, item_count=2, completed=False, deleted=False):
    created = datetime(2026, 9, 20, tzinfo=timezone.utc) - timedelta(hours=index)
    return {
        'id': f'conv-{index}',
        'created_at': created,
        'status': 'completed',
        'structured': {
            'title': f'Conversation {index}',
            'action_items': [
                {'description': f'item {index}-{n}', 'completed': completed, 'deleted': deleted}
                for n in range(item_count)
            ],
        },
    }


@pytest.fixture
def scan(monkeypatch):
    counter = {'read': 0}

    def _install(conversation_payloads):
        docs = [_Doc(payload) for payload in conversation_payloads]
        db = MagicMock()
        db.collection.return_value.document.return_value.collection.return_value = _Query(docs, counter)
        monkeypatch.setattr(conversations_db, 'db', db)
        monkeypatch.setattr(conversations_db, 'prepare_conversation_for_read', lambda data, _uid: data)
        return counter

    return _install


def test_a_small_page_does_not_read_the_whole_history(scan):
    counter = scan([_conversation(i) for i in range(200)])

    items = conversations_db.get_action_items('uid', limit=10)

    assert len(items) == 10
    # 2 eligible items per conversation, so 5 conversations cover the page.
    assert counter['read'] <= 6


def test_the_page_is_the_same_one_the_full_scan_returned(scan):
    payloads = [_conversation(i) for i in range(20)]
    scan(payloads)

    items = conversations_db.get_action_items('uid', limit=6)

    assert [item['id'] for item in items] == ['conv-0_0', 'conv-0_1', 'conv-1_0', 'conv-1_1', 'conv-2_0', 'conv-2_1']


def test_an_offset_page_still_reads_far_enough(scan):
    counter = scan([_conversation(i) for i in range(200)])

    items = conversations_db.get_action_items('uid', limit=4, offset=8)

    assert [item['id'] for item in items] == ['conv-4_0', 'conv-4_1', 'conv-5_0', 'conv-5_1']
    assert counter['read'] <= 7


def test_filtered_out_items_do_not_count_towards_the_page(scan):
    payloads = [_conversation(i, completed=True) for i in range(5)] + [_conversation(i + 5) for i in range(5)]
    scan(payloads)

    items = conversations_db.get_action_items('uid', limit=4, include_completed=False)

    # The first five conversations contribute nothing, so the page comes from later ones.
    assert [item['conversation_id'] for item in items] == ['conv-5', 'conv-5', 'conv-6', 'conv-6']


def test_a_user_with_fewer_items_than_the_page_still_gets_them_all(scan):
    scan([_conversation(i) for i in range(3)])

    items = conversations_db.get_action_items('uid', limit=50)

    assert len(items) == 6

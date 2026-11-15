"""Projected MCP list, search hydration and detail share the pending hold."""

from functools import partial

import pytest

from database import conversations as db
from tests.unit.test_mcp_conversation_cards_dream_duplicates import UID, _Client, _row
from utils.mcp_server.handlers import conversations as handlers
from utils.mcp_server.handlers.conversations import ToolExecutionError
from utils.sync import bridge_pending


@pytest.mark.parametrize('release', ['pending', 'expired', 'kept'])
def test_mcp_surfaces_respect_pending_hold(monkeypatch, release):
    monkeypatch.setattr(bridge_pending, 'current_time', lambda: 100)
    row = _row(2, sync_bridge_pending={'expires_at': 99 if release == 'expired' else 200})
    if release == 'kept':
        row['sync_relevance_user_kept'] = True
    client = _Client([_row(3), row, _row(1)])
    monkeypatch.setattr(handlers.mcp_conversation_pages, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(
        db, 'get_mcp_conversations_by_id', partial(db.get_mcp_conversations_by_id, firestore_client=client)
    )
    expected = ['c3', 'c1'] if release == 'pending' else ['c3', 'c2', 'c1']
    for args in ({'limit': 5}, {'limit': 5, 'offset': 1}):
        result = handlers.get_conversations(UID, args)
        assert [card['id'] for card in result['conversations']] == (expected[1:] if 'offset' in args else expected)
    monkeypatch.setattr(handlers, 'resolve_mcp_conversation_search_ids', lambda *a, **kw: ['c3', 'c2', 'c1'])
    rows = handlers.search_conversations_core(UID, 'speech', limit=5, start_dt=None, end_dt=None)
    assert [row['id'] for row in rows] == expected
    batch = handlers.get_conversations_by_ids(UID, {'conversation_ids': ['c3', 'c2', 'c1']})
    assert batch['not_found'] == (['c2'] if release == 'pending' else [])
    if release == 'pending':
        assert handlers.fetch_conversation_for_detail(UID, 'c2') is None
        with pytest.raises(ToolExecutionError):
            handlers.get_conversation_by_id(UID, {'conversation_id': 'c2'})
    else:
        assert handlers.get_conversation_by_id(UID, {'conversation_id': 'c2'})['conversation']['id'] == 'c2'

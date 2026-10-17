"""Regression tests for #21863 — developer API + MCP action-item guards.

Covers: Pinecone vector sync on create/batch/update/delete, FCM skipping
for completed tasks, tombstone 404s, tz-naive conversation rejection,
PATCH conversation transcript stripping + participants hydration, and
MCP locked-task filtering across list/sync/search.
"""

import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

import routers.developer as dev
import utils.mcp_action_items as mcp_ai
import utils.mcp_server.handlers.action_items as mcp_handlers


def _req(desc='task', completed=False, due=None):
    r = MagicMock()
    r.description = desc
    r.completed = completed
    r.due_at = due
    return r


def _item(id='a1', **kw):
    return {
        'id': id,
        'description': kw.get('description', 'd'),
        'completed': kw.get('completed', False),
        'due_at': kw.get('due_at'),
        'status': kw.get('status'),
        'deleted': kw.get('deleted', False),
        'is_locked': kw.get('is_locked', False),
        'conversation_id': None,
    }


# ---------- 1. vector sync + FCM completed guard (create / batch) ----------


def test_create_upserts_vector_and_skips_fcm_when_completed(monkeypatch):
    calls = {'fcm': 0, 'upsert': []}
    due = MagicMock()
    due.isoformat.return_value = 't'
    monkeypatch.setattr(dev.action_items_db, 'create_action_item', lambda u, d: 'a1')
    monkeypatch.setattr(dev.action_items_db, 'get_action_item', lambda u, i: _item('a1', completed=True, due_at=due))
    monkeypatch.setattr(dev, 'send_action_item_data_message', lambda **k: calls.__setitem__('fcm', calls['fcm'] + 1))
    monkeypatch.setattr(dev.vector_db, 'upsert_action_item_vector', lambda u, i, d: calls['upsert'].append(i))

    req = _req(completed=True, due=due)
    dev.create_action_item(req, uid='u')
    assert calls['fcm'] == 0
    assert calls['upsert'] == ['a1']


def test_create_sends_fcm_for_open_task_with_due(monkeypatch):
    calls = {'fcm': 0}
    due = MagicMock()
    due.isoformat.return_value = 't'
    monkeypatch.setattr(dev.action_items_db, 'create_action_item', lambda u, d: 'a1')
    monkeypatch.setattr(dev.action_items_db, 'get_action_item', lambda u, i: _item('a1', due_at=due))
    monkeypatch.setattr(dev, 'send_action_item_data_message', lambda **k: calls.__setitem__('fcm', calls['fcm'] + 1))
    monkeypatch.setattr(dev.vector_db, 'upsert_action_item_vector', lambda *a: None)

    dev.create_action_item(_req(due=due), uid='u')
    assert calls['fcm'] == 1


def test_batch_upserts_vectors_and_skips_completed_fcm(monkeypatch):
    calls = {'fcm': 0, 'batch': None}
    due = MagicMock()
    due.isoformat.return_value = 't'
    items = [_item('a1', due_at=due), _item('a2', completed=True, due_at=due)]
    monkeypatch.setattr(dev.action_items_db, 'create_action_items_batch', lambda u, d: ['a1', 'a2'])
    monkeypatch.setattr(dev.action_items_db, 'get_action_items_by_ids', lambda u, ids: items)
    monkeypatch.setattr(dev, 'send_action_item_data_message', lambda **k: calls.__setitem__('fcm', calls['fcm'] + 1))
    monkeypatch.setattr(
        dev.vector_db, 'upsert_action_item_vectors_batch', lambda u, xs: calls.__setitem__('batch', len(xs))
    )

    req = MagicMock()
    req.action_items = [_req(due=due), _req(completed=True, due=due)]
    dev.create_action_items_batch(req, uid='u')
    assert calls['fcm'] == 1  # only the open task
    assert calls['batch'] == 2


# ---------- 2. tombstone 404 + delete vector ----------


def test_delete_rejects_tombstone(monkeypatch):
    monkeypatch.setattr(dev.action_items_db, 'get_action_item', lambda u, i: _item('a1', deleted=True))
    import fastapi

    with pytest.raises(fastapi.HTTPException) as exc:
        dev.delete_action_item('a1', uid='u')
    assert exc.value.status_code == 404


def test_delete_removes_vector(monkeypatch):
    calls = []
    monkeypatch.setattr(dev.action_items_db, 'get_action_item', lambda u, i: _item('a1'))
    monkeypatch.setattr(dev.action_items_db, 'delete_action_item', lambda u, i: None)
    monkeypatch.setattr(dev.vector_db, 'delete_action_item_vector', lambda u, i: calls.append(i))
    monkeypatch.setattr(dev, 'sync_action_item_reminder', lambda **k: None)
    dev.delete_action_item('a1', uid='u')
    assert calls == ['a1']


def test_update_rejects_tombstone(monkeypatch):
    monkeypatch.setattr(dev.action_items_db, 'get_action_item', lambda u, i: _item('a1', deleted=True))
    import fastapi

    req = MagicMock()
    req.description = 'x'
    req.completed = None
    req.model_fields_set = {'description'}
    with pytest.raises(fastapi.HTTPException) as exc:
        dev.update_action_item('a1', req, uid='u')
    assert exc.value.status_code == 404


def test_update_description_upserts_vector(monkeypatch):
    calls = []
    monkeypatch.setattr(dev.action_items_db, 'get_action_item', lambda u, i: _item('a1'))
    monkeypatch.setattr(dev.action_items_db, 'update_action_item', lambda u, i, d: True)
    monkeypatch.setattr(dev.vector_db, 'upsert_action_item_vector', lambda u, i, d: calls.append((i, d)))
    monkeypatch.setattr(dev, 'sync_action_item_reminder', lambda **k: None)
    req = MagicMock()
    req.description = 'new'
    req.completed = None
    req.model_fields_set = {'description'}
    dev.update_action_item('a1', req, uid='u')
    assert calls == [('a1', 'new')]


# ---------- 3. timezone validator ----------


def test_create_conversation_request_rejects_naive_datetime():
    from datetime import datetime

    with pytest.raises(ValidationError):
        dev.CreateConversationRequest(text='hello', started_at=datetime(2026, 1, 1, 12, 0, 0))


def test_create_conversation_request_accepts_aware_datetime():
    from datetime import datetime, timezone

    r = dev.CreateConversationRequest(text='hello', started_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
    assert r.started_at.tzinfo is not None


# ---------- 4. PATCH conversation hardening ----------


def test_patch_conversation_strips_transcript_and_hydrates(monkeypatch):
    conv = {'id': 'c1', 'transcript_segments': [{'x': 1}], 'user_speech_profiles': {}, 'users': {}, 'people': {}}
    monkeypatch.setattr(dev.conversations_db, 'get_conversation', lambda u, c: dict(conv))
    monkeypatch.setattr(dev.conversations_db, 'update_conversation_title', lambda *a: None)
    monkeypatch.setattr(dev, 'populate_folder_names', lambda u, cs: None)
    monkeypatch.setattr(
        'utils.mcp_server.helpers.conversation_participants',
        lambda c: {'participants': [{'id': 'p1'}], 'person_ids': ['p1'], 'participants_included': True},
    )
    req = MagicMock()
    req.title = 'new'
    req.discarded = None
    out = dev.update_conversation_endpoint('c1', req, uid='u')
    assert 'transcript_segments' not in out
    assert out['transcript_included'] is False
    assert out['participants'] == [{'id': 'p1'}]


def test_patch_conversation_404s_when_deleted_mid_write(monkeypatch):
    calls = [0]

    def get_conv(u, c):
        calls[0] += 1
        return {'id': 'c1'} if calls[0] == 1 else None  # gone on the second read

    monkeypatch.setattr(dev.conversations_db, 'get_conversation', get_conv)
    monkeypatch.setattr(dev.conversations_db, 'update_conversation_title', lambda *a: None)
    monkeypatch.setattr(dev, 'populate_folder_names', lambda u, cs: None)
    import fastapi

    req = MagicMock()
    req.title = 'x'
    req.discarded = None
    with pytest.raises(fastapi.HTTPException) as exc:
        dev.update_conversation_endpoint('c1', req, uid='u')
    assert exc.value.status_code == 404


# ---------- 5. MCP locked filters ----------


def test_mcp_search_filters_locked(monkeypatch):
    monkeypatch.setattr(mcp_ai, 'search_action_items_by_vector', lambda u, q, limit: ['a1', 'a2', 'a3'])
    monkeypatch.setattr(
        mcp_ai.action_items_db,
        'get_action_items_by_ids',
        lambda u, ids: [_item('a1'), _item('a2', is_locked=True), _item('a3', deleted=True)],
    )
    monkeypatch.setattr(mcp_ai, 'clean_action_item', lambda i: i)
    out = mcp_ai.search_action_items('u', 'task', limit=10)
    assert [i['id'] for i in out] == ['a1']


def test_mcp_list_page_filters_locked(monkeypatch):
    monkeypatch.setattr(
        mcp_handlers.action_items_db, 'get_action_items', lambda u, **k: [_item('a1'), _item('a2', is_locked=True)]
    )
    monkeypatch.setattr(mcp_handlers, 'clean_action_item', lambda i: i)
    monkeypatch.setattr(mcp_handlers, 'resolve_offset_cursor', lambda *a, **k: 0)
    monkeypatch.setattr(mcp_handlers, 'offset_page', lambda items, limit: (items, len(items), False))
    page, _ = mcp_handlers.action_items_list_page_core(
        'u', completed=None, due_start=None, due_end=None, limit=10, cursor_kind='x'
    )
    assert [i['id'] for i in page] == ['a1']


def test_mcp_sync_page_filters_locked(monkeypatch):
    rows = [_item('a1'), _item('a2', is_locked=True)]
    monkeypatch.setattr(mcp_handlers.action_item_sync_db, 'get_action_items_sync_page', lambda u, **k: (rows, None))
    monkeypatch.setattr(mcp_handlers, 'clean_action_item', lambda i: dict(i))
    items, _ = mcp_handlers.action_items_sync_page_core(
        'u', updated_since=MagicMock(isoformat=lambda: 't'), limit=10, cursor_kind='x'
    )
    assert [i['id'] for i in items] == ['a1']


def test_clean_action_item_drops_locked_description_entirely():
    """Review follow-up: a locked item reaching the MCP shaper must not
    leak even a truncated description — exclusion parity, not redaction."""
    from utils.mcp_data import clean_action_item

    locked = _item('l1', is_locked=True)
    locked['description'] = 'x' * 200
    out = clean_action_item(locked)
    assert out['description'] == ''

    unlocked = _item('u1')
    unlocked['description'] = 'full text here'
    assert clean_action_item(unlocked)['description'] == 'full text here'

"""Exercise authenticated create boundaries with synthetic account-scoped rows."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversations as conversations_db
from routers import action_items as routes
from utils.conversations import action_item_extraction as extraction
from utils.conversations import process_conversation as pc
from utils.retrieval.tool_services import action_items as service
from utils.retrieval.tools import action_item_tools as tools
from utils.task_intelligence import task_source_validation as sources
from utils.task_intelligence import conversation_capture as capture


@pytest.fixture
def store(monkeypatch):
    rows = {
        ('owner', 'valid'): {'id': 'valid'},
        ('foreign', 'foreign-only'): {'id': 'foreign-only'},
        ('owner', 'deleted'): {'id': 'deleted', 'deleted': True},
    }
    reads = []

    def get(uid, cid):
        reads.append((uid, cid))
        return rows.get((uid, cid))

    monkeypatch.setattr(conversations_db, 'get_conversation', get)
    write = MagicMock(return_value='task')
    batch = MagicMock(return_value=['task'])
    monkeypatch.setattr(service.action_items_db, 'create_action_item', write)
    monkeypatch.setattr(service.action_items_db, 'create_action_items_batch', batch)
    return rows, reads, write, batch


@pytest.mark.parametrize('cid', ['absent', 'deleted', 'foreign-only', '', 'users/foreign'])
def test_shared_create_rejects_bad_sources_without_writing(store, cid):
    _, reads, write, batch = store
    with pytest.raises(sources.TaskSourceValidationError):
        service.create_action_item('owner', {'description': 'Buy milk', 'conversation_id': cid})
    assert all(uid == 'owner' for uid, _ in reads)
    write.assert_not_called()
    batch.assert_not_called()


def test_standalone_and_linked_preserve_manual_text_and_metadata(store):
    _, reads, write, _ = store
    service.create_action_item('owner', {'description': 'Send it', 'conversation_id': None}, idempotency_key='manual')
    assert not reads
    assert write.call_args.kwargs == {'idempotency_key': 'manual'}
    data = {'description': 'Send it', 'conversation_id': 'valid', 'exported': True, 'apple_reminder_id': 'reminder'}
    service.create_action_item('owner', data, idempotency_key='retry')
    assert write.call_args.args[1] == data


def test_batch_validates_all_before_first_write_and_reuses_reads(store):
    _, reads, write, batch = store
    good = {
        'description': 'Buy milk',
        'conversation_id': 'valid',
        'provenance': [{'kind': 'conversation', 'id': 'valid'}],
    }
    bad = {'description': 'Buy eggs', 'conversation_id': 'foreign-only'}
    with pytest.raises(sources.TaskSourceValidationError):
        service.create_action_items_batch('owner', [good, good, bad])
    assert reads.count(('owner', 'valid')) == 1
    batch.assert_not_called()
    write.assert_not_called()


def test_canonical_provenance_and_kill_switch(store, monkeypatch):
    with pytest.raises(sources.TaskSourceValidationError):
        service.create_action_item(
            'owner', {'description': 'Buy milk', 'provenance': [{'kind': 'conversation', 'id': 'deleted'}]}
        )
    monkeypatch.setenv(sources.SOURCE_LINKS_ENABLED_ENV, 'false')
    service.create_action_item('owner', {'description': 'Buy milk', 'conversation_id': 'absent'})
    assert store[2].called


@pytest.mark.parametrize('batch', [False, True])
def test_app_wire_rejects_unavailable_link(store, monkeypatch, batch):
    monkeypatch.setattr(routes.task_links, 'validate_task_links', lambda *a, **k: None)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'owner'
    payload = {'description': 'Send it', 'conversation_id': 'foreign-only'}
    path = '/v1/action-items/batch' if batch else '/v1/action-items'
    response = TestClient(app).post(path, json=[payload] if batch else payload)
    assert response.status_code == 404
    assert response.json() == {'detail': 'Task source conversation is unavailable.'}
    store[2].assert_not_called()
    store[3].assert_not_called()


def test_tool_error_is_visible_and_does_not_write(store, monkeypatch):
    monkeypatch.setattr(service, 'clock_for_uid', lambda *_: None)
    result = service.create_action_item_text('owner', 'Buy milk', conversation_id='foreign-only')
    assert 'Error' in result and 'unavailable' in result
    store[2].assert_not_called()


def test_langchain_tool_uses_the_same_source_boundary(store, monkeypatch):
    monkeypatch.setattr(tools, 'clock_for_config', lambda *_: None)
    result = tools.create_action_item_tool.invoke(
        {'description': 'Buy milk', 'conversation_id': 'foreign-only'},
        config={'configurable': {'user_id': 'owner'}},
    )
    assert 'Error' in result and 'unavailable' in result
    store[2].assert_not_called()


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_automatic_missing_source_raises_before_replacement_or_capture(store, monkeypatch, mode):
    monkeypatch.setenv('ACTION_ITEMS_V2_MODE', mode)
    conv = SimpleNamespace(id=None, structured=SimpleNamespace(action_items=[]))
    with pytest.raises(ValueError, match='provenance'):
        extraction.action_items_for_write('owner', conv, datetime.now(timezone.utc), lambda *_: {})
    with pytest.raises(ValueError, match='provenance'):
        capture.process_conversation_before_legacy('owner', conv)
    store[2].assert_not_called()
    store[3].assert_not_called()


def test_conversion_keeps_only_existing_cited_segments():
    item = SimpleNamespace(completed=False, capture_owner='user', due_at=None, source_segment_ids=['s1', 'invented'])
    ref = capture.canonical_fields(item, 'valid', [SimpleNamespace(id='s1', start=1, end=2)])['provenance'][0]
    assert ref['id'] == 'valid'
    assert ref['transcript_segment_ids'] == ['s1']


def test_missing_automatic_source_preserves_existing_tasks(store, monkeypatch):
    delete = MagicMock()
    refresh = MagicMock()
    monkeypatch.setattr(pc.action_items_db, 'delete_action_items_for_conversation', delete)
    monkeypatch.setattr(pc, 'preserve_refresh_tasks', refresh)
    conv = SimpleNamespace(id=None, structured=SimpleNamespace(action_items=[]))
    with pytest.raises(ValueError, match='provenance'):
        pc._write_action_items('owner', conv)
    refresh.assert_not_called()
    delete.assert_not_called()
    store[2].assert_not_called()
    store[3].assert_not_called()

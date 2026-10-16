from contextlib import contextmanager
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')

import utils.mcp_action_items as mcp_action_items
from utils.mcp_server.handlers import action_items as mcp_action_item_handlers

BACKEND_DIR = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


@contextmanager
def _isolated_developer_router():
    saved = dict(sys.modules)
    try:
        stubs = [
            'ulid',
            'pinecone',
            'typesense',
            'opuslib',
            'pydub',
            'pusher',
            'modal',
            'database._client',
            'database.redis_db',
            'database.conversations',
            'database.memories',
            'database.action_items',
            'database.folders',
            'database.users',
            'database.user_usage',
            'database.vector_db',
            'database.chat',
            'database.apps',
            'database.goals',
            'database.notifications',
            'database.mem_db',
            'database.mcp_api_key',
            'database.daily_summaries',
            'database.fair_use',
            'database.auth',
            'database.knowledge_graph',
            'database.dev_api_key',
            'firebase_admin',
            'firebase_admin.messaging',
            'firebase_admin.auth',
            'firebase_admin.credentials',
            'firebase_admin.firestore',
            'google.cloud.firestore',
            'google.cloud.firestore_v1',
            'utils.other.storage',
            'utils.stt.pre_recorded',
            'utils.stt.vad',
            'utils.fair_use',
            'utils.subscription',
            'utils.conversations.process_conversation',
            'utils.conversations.location',
            'utils.notifications',
            'utils.apps',
            'utils.llm.memories',
            'utils.llm.chat',
            'utils.llm.knowledge_graph',
        ]
        for mod_name in stubs:
            if mod_name not in sys.modules:
                sys.modules[mod_name] = _AutoMockModule(mod_name)

        sys.modules['database._client'].document_id_from_seed = MagicMock(return_value='memory-id')
        sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
        sys.modules['utils.apps'].update_personas_async = MagicMock()

        endpoints = sys.modules.get('utils.other.endpoints')
        if endpoints is None:
            endpoints = ModuleType('utils.other.endpoints')
            sys.modules['utils.other.endpoints'] = endpoints
        endpoints.get_current_user_uid = lambda: 'u1'
        endpoints.with_rate_limit = lambda dependency, _policy: dependency
        endpoints.with_rate_limit_context = lambda dependency, _policy: dependency
        endpoints.check_api_key_rate_limit = MagicMock()
        endpoints.get_user = MagicMock()

        spec = importlib.util.spec_from_file_location('routers.developer', BACKEND_DIR / 'routers' / 'developer.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules['routers.developer'] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        for name in [k for k in sys.modules if k not in saved]:
            del sys.modules[name]
        for name, mod in saved.items():
            sys.modules[name] = mod


def test_developer_create_and_batch_create_action_items_index_vectors_and_skip_completed_reminders(monkeypatch):
    with _isolated_developer_router() as dev:
        upserts = []
        batch_upserts = []
        fcm_messages = []

        monkeypatch.setattr(
            dev.vector_db,
            'upsert_action_item_vector',
            lambda uid, aid, desc: upserts.append((uid, aid, desc)),
        )
        monkeypatch.setattr(
            dev.vector_db,
            'upsert_action_item_vectors_batch',
            lambda uid, items: batch_upserts.append((uid, items)),
        )
        monkeypatch.setattr(
            dev,
            'send_action_item_data_message',
            lambda **kw: fcm_messages.append(kw),
        )

        # 1. Single create with completed=True indexes vector but does NOT arm a reminder
        monkeypatch.setattr(dev.action_items_db, 'create_action_item', lambda uid, data: 'ai-1')
        monkeypatch.setattr(
            dev.action_items_db,
            'get_action_item',
            lambda uid, aid: {
                'id': aid,
                'description': 'Already done task',
                'completed': True,
                'due_at': NOW,
                'created_at': NOW,
            },
        )
        res = dev.create_action_item(
            dev.CreateActionItemRequest(description='  Already done task  ', completed=True, due_at=NOW),
            uid='u1',
        )
        assert res.id == 'ai-1'
        assert upserts == [('u1', 'ai-1', 'Already done task')]
        assert fcm_messages == []

        # 2. Batch create indexes all items in Pinecone and only sends reminders for open items with due_at
        monkeypatch.setattr(dev.action_items_db, 'create_action_items_batch', lambda uid, items: ['b1', 'b2'])
        monkeypatch.setattr(
            dev.action_items_db,
            'get_action_items_by_ids',
            lambda uid, ids: [
                {'id': 'b1', 'description': 'Open due task', 'completed': False, 'due_at': NOW},
                {'id': 'b2', 'description': 'Completed due task', 'completed': True, 'due_at': NOW},
            ],
        )
        batch_res = dev.create_action_items_batch(
            dev.BatchActionItemsRequest(
                action_items=[
                    dev.CreateActionItemRequest(description='Open due task', completed=False, due_at=NOW),
                    dev.CreateActionItemRequest(description='Completed due task', completed=True, due_at=NOW),
                ]
            ),
            uid='u1',
        )
        assert batch_res.created_count == 2
        assert batch_upserts == [
            (
                'u1',
                [
                    {'action_item_id': 'b1', 'description': 'Open due task'},
                    {'action_item_id': 'b2', 'description': 'Completed due task'},
                ],
            )
        ]
        assert len(fcm_messages) == 1
        assert fcm_messages[0]['action_item_id'] == 'b1'


def test_developer_update_action_item_reindexes_vector_and_rejects_soft_deleted_tombstone(monkeypatch):
    with _isolated_developer_router() as dev:
        upserts = []
        monkeypatch.setattr(
            dev.vector_db,
            'upsert_action_item_vector',
            lambda uid, aid, desc: upserts.append((uid, aid, desc)),
        )

        # 1. Soft-deleted tombstone returns 404 before attempting update
        monkeypatch.setattr(
            dev.action_items_db,
            'get_action_item',
            lambda uid, aid: {'id': aid, 'description': 'Deleted task', 'completed': False, 'deleted': True},
        )
        with pytest.raises(HTTPException) as exc_404:
            dev.update_action_item('ai-del', dev.UpdateActionItemRequest(description='New text'), uid='u1')
        assert exc_404.value.status_code == 404
        assert upserts == []

        # 2. Updating description re-indexes the action-item vector in Pinecone
        calls = {'count': 0}

        def _get_item(uid, aid):
            calls['count'] += 1
            if calls['count'] == 1:
                return {'id': aid, 'description': 'Old text', 'completed': False}
            return {'id': aid, 'description': 'Updated text', 'completed': False}

        monkeypatch.setattr(dev.action_items_db, 'get_action_item', _get_item)
        monkeypatch.setattr(dev.action_items_db, 'update_action_item', lambda uid, aid, data: True)

        updated = dev.update_action_item('ai-1', dev.UpdateActionItemRequest(description='  Updated text  '), uid='u1')
        assert updated['description'] == 'Updated text'
        assert upserts == [('u1', 'ai-1', 'Updated text')]


def test_developer_delete_action_item_purges_vector_and_rejects_soft_deleted_or_noop_delete(monkeypatch):
    with _isolated_developer_router() as dev:
        deleted_vectors = []
        reminder_syncs = []
        monkeypatch.setattr(
            dev.vector_db,
            'delete_action_item_vector',
            lambda uid, aid: deleted_vectors.append((uid, aid)),
        )
        monkeypatch.setattr(
            dev,
            'sync_action_item_reminder',
            lambda **kw: reminder_syncs.append(kw),
        )

        # 1. Soft-deleted tombstone is rejected with 404
        monkeypatch.setattr(
            dev.action_items_db,
            'get_action_item',
            lambda uid, aid: {'id': aid, 'description': 'Tombstone', 'completed': False, 'deleted': True},
        )
        with pytest.raises(HTTPException) as exc_tombstone:
            dev.delete_action_item('ai-del', uid='u1')
        assert exc_tombstone.value.status_code == 404
        assert deleted_vectors == []

        # 2. Concurrent delete where delete_action_item returns False raises 404
        monkeypatch.setattr(
            dev.action_items_db,
            'get_action_item',
            lambda uid, aid: {'id': aid, 'description': 'Live task', 'completed': False},
        )
        monkeypatch.setattr(dev.action_items_db, 'delete_action_item', lambda uid, aid: False)
        with pytest.raises(HTTPException) as exc_race:
            dev.delete_action_item('ai-race', uid='u1')
        assert exc_race.value.status_code == 404
        assert deleted_vectors == []

        # 3. Successful delete purges Pinecone vector and cancels reminder
        monkeypatch.setattr(dev.action_items_db, 'delete_action_item', lambda uid, aid: True)
        res = dev.delete_action_item('ai-live', uid='u1')
        assert res == {'success': True}
        assert deleted_vectors == [('u1', 'ai-live')]
        assert len(reminder_syncs) == 1


def test_create_conversation_request_rejects_offset_naive_timestamps_with_422():
    with _isolated_developer_router() as dev:
        with pytest.raises(ValidationError, match='timezone offset'):
            dev.CreateConversationRequest(
                text='Hello world',
                finished_at='2026-10-16T12:00:00',
            )
        with pytest.raises(ValidationError, match='timezone offset'):
            dev.CreateConversationRequest(
                text='Hello world',
                started_at='2026-10-16T12:00:00',
            )
        valid = dev.CreateConversationRequest(
            text='Hello world',
            started_at='2026-10-16T12:00:00Z',
            finished_at='2026-10-16T12:05:00Z',
        )
        assert valid.started_at.tzinfo is not None
        assert valid.finished_at.tzinfo is not None


def test_update_conversation_endpoint_redacts_transcript_populates_participants_and_404s_when_deleted(monkeypatch):
    with _isolated_developer_router() as dev:
        monkeypatch.setattr(dev, 'populate_folder_names', lambda uid, convs: None)
        monkeypatch.setattr(dev.conversations_db, 'update_conversation_title', lambda uid, cid, title: None)

        stored_conv = {
            'id': 'conv-1',
            'created_at': NOW,
            'started_at': NOW,
            'finished_at': NOW,
            'structured': {'title': 'New Title', 'overview': 'Summary', 'category': 'work'},
            'transcript_segments': [
                {
                    'id': 's1',
                    'text': 'Private transcript',
                    'speaker_id': 1,
                    'person_id': 'person-1',
                    'start': 0.0,
                    'end': 1.0,
                }
            ],
        }
        monkeypatch.setattr(dev.conversations_db, 'get_conversation', lambda uid, cid: dict(stored_conv))

        out = dev.update_conversation_endpoint(
            'conv-1',
            dev.UpdateConversationRequest(title='New Title'),
            uid='u1',
        )
        assert 'transcript_segments' not in out
        assert out['transcript_included'] is False
        assert out['participants_included'] is True
        assert out['person_ids'] == ['person-1']

        # Concurrent deletion between preflight check and reload raises 404 instead of returning None
        calls = {'count': 0}

        def _get_conv_vanished(uid, cid):
            calls['count'] += 1
            return dict(stored_conv) if calls['count'] == 1 else None

        monkeypatch.setattr(dev.conversations_db, 'get_conversation', _get_conv_vanished)
        with pytest.raises(HTTPException) as exc_404:
            dev.update_conversation_endpoint(
                'conv-1',
                dev.UpdateConversationRequest(title='New Title'),
                uid='u1',
            )
        assert exc_404.value.status_code == 404


def test_mcp_action_items_search_list_and_sync_exclude_locked_items(monkeypatch):
    # 1. mcp_action_items.search_action_items filters out is_locked items
    monkeypatch.setattr(
        mcp_action_items, 'search_action_items_by_vector', lambda uid, q, limit=10: ['a-locked', 'a-open']
    )
    monkeypatch.setattr(
        mcp_action_items.action_items_db,
        'get_action_items_by_ids',
        lambda uid, ids: [
            {'id': 'a-locked', 'description': 'Paywalled task', 'completed': False, 'is_locked': True},
            {'id': 'a-open', 'description': 'Accessible task', 'completed': False, 'is_locked': False},
        ],
    )
    search_hits = mcp_action_items.search_action_items('u1', 'task', limit=10)
    assert [item['id'] for item in search_hits] == ['a-open']

    # 2. action_items_list_page_core filters out is_locked items
    monkeypatch.setattr(
        mcp_action_item_handlers.action_items_db,
        'get_action_items',
        lambda uid, **kw: [
            {'id': 'a-locked', 'description': 'Paywalled task', 'completed': False, 'is_locked': True},
            {'id': 'a-open', 'description': 'Accessible task', 'completed': False, 'is_locked': False},
        ],
    )
    list_page, next_cursor = mcp_action_item_handlers.action_items_list_page_core(
        'u1',
        completed=None,
        due_start=None,
        due_end=None,
        limit=10,
        offset=0,
        cursor_token=None,
        cursor_kind='test_list',
    )
    assert [item['id'] for item in list_page] == ['a-open']
    assert next_cursor is None

    # 3. action_items_sync_page_core filters out is_locked items
    monkeypatch.setattr(
        mcp_action_item_handlers.action_item_sync_db,
        'get_action_items_sync_page',
        lambda uid, **kw: (
            [
                {
                    'id': 'a-locked',
                    'description': 'Paywalled task',
                    'completed': False,
                    'updated_at': NOW,
                    'is_locked': True,
                },
                {
                    'id': 'a-open',
                    'description': 'Accessible task',
                    'completed': False,
                    'updated_at': NOW,
                    'is_locked': False,
                },
            ],
            None,
        ),
    )
    sync_page, sync_cursor = mcp_action_item_handlers.action_items_sync_page_core(
        'u1',
        updated_since=NOW,
        limit=10,
        cursor_token=None,
        cursor_kind='test_sync',
    )
    assert [item['id'] for item in sync_page] == ['a-open']
    assert sync_cursor is None

"""Exact undo and owner receipts against loopback Firestore, no cloud IO."""

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import os

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from database import chat_edits
from database.messaging import MessagingStore
from utils.messaging.undo import UndoStore
from utils.messaging.projection import SurfaceRuntime, chat_write_runtime
from utils.messaging.contracts import Principal
from utils.messaging import undo
from utils.retrieval.tools.edit_tools import envelope


@pytest.fixture
def store(monkeypatch):
    host = os.getenv('MESSAGING_TEST_FIRESTORE_HOST')
    if not host:
        pytest.skip('Loopback Firestore not requested')
    assert host.startswith('127.0.0.1:')
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', host)
    client = firestore.Client(project='demo-chat-edits-' + uuid4().hex[:8], credentials=AnonymousCredentials())
    yield MessagingStore(firestore_client=client)
    client.close()


@pytest.mark.parametrize(
    'kind,collection,before,after',
    [
        (
            'conversation',
            'conversations',
            {'structured': {'title': 'Old', 'overview': 'Summary'}, 'transcript_segments': b'unchanged'},
            {
                'structured': {'title': 'New', 'overview': 'Summary'},
                'user_title': 'New',
                'user_corrections': [{'note': 'Film correction'}],
                'transcript_segments': b'unchanged',
            },
        ),
        (
            'person',
            'people',
            {'name': 'Old', 'aliases': ['Alias'], 'updated_at': datetime(2026, 10, 1, tzinfo=timezone.utc)},
            {'name': 'New', 'aliases': ['Alias', 'Old'], 'updated_at': datetime(2026, 10, 11, tzinfo=timezone.utc)},
        ),
        (
            'task',
            'action_items',
            {'description': 'Task', 'completed': False, 'due_at': datetime(2099, 10, 11, tzinfo=timezone.utc)},
            {
                'description': 'Task',
                'completed': True,
                'deleted': True,
                'deleted_at': datetime(2026, 10, 11, tzinfo=timezone.utc),
                'due_at': None,
            },
        ),
    ],
)
def test_exact_restore_including_missing_fields_and_timestamps(store, kind, collection, before, after):
    ref = store.user('owner').collection(collection).document('target')
    ref.set(before)
    prior = chat_edits.snapshot('owner', kind, 'target', firestore_client=store.db)
    ref.set(after)
    expected = chat_edits.snapshot('owner', kind, 'target', firestore_client=store.db)
    with pytest.raises(PermissionError):
        chat_edits.restore('foreign', kind, 'target', expected, prior, firestore_client=store.db)
    ref.update({'description' if kind == 'task' else 'name' if kind == 'person' else 'structured': 'concurrent'})
    with pytest.raises(PermissionError):
        chat_edits.restore('owner', kind, 'target', expected, prior, firestore_client=store.db)
    ref.set(after)
    chat_edits.restore('owner', kind, 'target', expected, prior, firestore_client=store.db)
    assert ref.get().to_dict() == before


def test_app_owner_undo_once_audit_and_reloaded_message(store, monkeypatch):
    store.user('owner').set({'name': 'Synthetic'})
    store.user('owner').collection('chat_sessions').document('session').set({'id': 'session'})
    manager = UndoStore(store)
    calls = []
    token = chat_write_runtime.set(SurfaceRuntime('app', '', Principal('owner'), session_id='session', turn_id='turn'))
    try:
        receipt = manager.record(
            'owner',
            'session',
            'person',
            'target',
            envelope({'name': 'Before'}, 'Before'),
            envelope({'name': 'After'}, 'After'),
        )
    finally:
        chat_write_runtime.reset(token)
    store.user('owner').collection('messages').document('message').set(
        {'content_blocks': [dict(receipt.content_block)]}
    )
    manager.bind_message('owner', receipt.id, 'message')
    monkeypatch.setattr(undo, 'apply_inverse', lambda uid, payload: calls.append((uid, payload)))
    with pytest.raises(LookupError):
        manager.undo_for_owner('foreign', receipt.id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: manager.undo_for_owner('owner', receipt.id), range(2)))
    assert len(calls) == 1
    assert any(result.status == 'undone' for result in results)
    replay = manager.undo_for_owner('owner', receipt.id)
    assert replay.status == 'already_undone' and replay.block.undoneAt and not replay.block.undoable
    audit = store.user('owner').collection('chat_edit_audit').document(receipt.id).get().to_dict()
    assert audit['uid'] == 'owner' and audit['tool'] == 'rename_person' and audit['surface'] == 'app'
    assert audit['before_hash'] != audit['after_hash']
    assert 'Before' not in str(audit) and 'After' not in str(audit)
    blocks = store.user('owner').collection('messages').document('message').get().to_dict()['content_blocks']
    assert blocks[0]['undoneAt'] and not blocks[0]['undoable']

"""Manual loopback proof of folder cleanup against real Firestore semantics.

FIRESTORE_EMULATOR_HOST=127.0.0.1:10279 PYTHONPATH=backend \
  backend/.venv/bin/pytest -q backend/tests/integration/test_folder_delete_concurrency_emulator.py
"""

import os
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import Aborted
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.query import Query
from google.cloud.firestore_v1.transaction import Transaction
import pytest

from database import _client
from routers import folders


@pytest.fixture
def deletion(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('This proof requires a loopback Firestore emulator')
    db = firestore.Client(project='demo-folder-deletion', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', db)
    uid = uuid4().hex
    user = db.collection('users').document(uid)
    now = datetime.now(timezone.utc)
    for order, folder_id in enumerate(('source', 'target', 'chosen')):
        user.collection('folders').document(folder_id).set(
            {'name': folder_id, 'is_system': False, 'order': order, 'created_at': now, 'updated_at': now}
        )
    for index in range(3):
        user.collection('conversations').document(f'conv-{index:04}').set(
            {'folder_id': 'source', 'discarded': False, 'folder_user_set': True, 'title': 'Synthetic conversation'}
        )
    app = FastAPI()
    app.include_router(folders.router)
    app.dependency_overrides[folders.auth.get_current_user_uid] = lambda: uid
    with TestClient(app) as client:
        yield client, db, user
    db.close()


def after_candidate_scan(monkeypatch, conversations, mutation):
    """Schedule an independent client edit after the cleanup's initial query."""
    original_stream = Query.stream
    fired = False

    def stream(query, *args, **kwargs):
        nonlocal fired
        if query._parent._path == conversations._path and not fired and kwargs.get('transaction') is None:
            snapshots = list(original_stream(query, *args, **kwargs))
            fired = True
            mutation()
            yield from snapshots
        else:
            yield from original_stream(query, *args, **kwargs)

    monkeypatch.setattr(Query, 'stream', stream)


@pytest.mark.parametrize('new_folder', ['chosen', None])
def test_cleanup_preserves_a_move_committed_after_its_query(deletion, monkeypatch, new_folder):
    client, _, user = deletion
    conversations = user.collection('conversations')
    edited = conversations.document('conv-0000')
    after_candidate_scan(
        monkeypatch, conversations, lambda: edited.update({'folder_id': new_folder, 'folder_user_set': True})
    )
    response = client.delete('/v1/folders/source?move_to_folder_id=target')
    assert response.status_code == 204, response.text
    assert edited.get().to_dict()['folder_id'] == new_folder
    assert conversations.document('conv-0001').get().to_dict()['folder_id'] == 'target'
    assert not user.collection('folders').document('source').get().exists


def test_cleanup_survives_a_conversation_deleted_after_its_query(deletion, monkeypatch):
    client, _, user = deletion
    conversations = user.collection('conversations')
    removed = conversations.document('conv-0001')
    after_candidate_scan(monkeypatch, conversations, removed.delete)
    response = client.delete('/v1/folders/source?move_to_folder_id=target')
    assert response.status_code == 204, response.text
    assert not removed.get().exists, 'cleanup must not resurrect a deleted conversation'
    assert {row.to_dict()['folder_id'] for row in conversations.stream()} == {'target'}
    assert user.collection('folders').document('target').get().to_dict()['conversation_count'] == 2
    assert not user.collection('folders').document('source').get().exists


@pytest.mark.parametrize('use_default', [False, True])
def test_cleanup_keeps_existing_default_and_unfiled_behavior(deletion, use_default):
    client, _, user = deletion
    if use_default:
        user.collection('folders').document('target').update({'is_default': True})
    response = client.delete('/v1/folders/source')
    assert response.status_code == 204, response.text
    expected = 'target' if use_default else None
    assert {row.to_dict()['folder_id'] for row in user.collection('conversations').stream()} == {expected}


def test_cleanup_does_not_overwrite_unrelated_conversation_edits(deletion, monkeypatch):
    client, _, user = deletion
    conversations = user.collection('conversations')
    edited = conversations.document('conv-0000')
    after_candidate_scan(monkeypatch, conversations, lambda: edited.update({'title': 'User edited title'}))
    response = client.delete('/v1/folders/source?move_to_folder_id=target')
    assert response.status_code == 204, response.text
    assert edited.get().to_dict()['title'] == 'User edited title'
    assert edited.get().to_dict()['folder_id'] == 'target'


def test_failed_later_chunk_keeps_source_folder_and_can_retry(deletion, monkeypatch):
    client, db, user = deletion
    conversations = user.collection('conversations')
    batch = db.batch()
    for index in range(3, 451):
        batch.set(conversations.document(f'conv-{index:04}'), {'folder_id': 'source', 'discarded': False})
    batch.commit()
    original_update = Transaction.update

    def fail_tail(transaction, reference, *args, **kwargs):
        if reference.path == conversations.document('conv-0450').path:
            raise RuntimeError('synthetic tail write rejection')
        return original_update(transaction, reference, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(Transaction, 'update', fail_tail)
        with pytest.raises(RuntimeError, match='synthetic tail write rejection'):
            client.delete('/v1/folders/source?move_to_folder_id=target')
    assert user.collection('folders').document('source').get().exists
    assert sum(row.to_dict()['folder_id'] == 'target' for row in conversations.stream()) == 450
    response = client.delete('/v1/folders/source?move_to_folder_id=target')
    assert response.status_code == 204, response.text
    assert {row.to_dict()['folder_id'] for row in conversations.stream()} == {'target'}
    assert user.collection('folders').document('target').get().to_dict()['conversation_count'] == 451


def test_read_contention_restarts_and_rechecks_membership(deletion, monkeypatch):
    client, db, user = deletion
    original_get_all = db.get_all
    attempts = 0
    edited = user.collection('conversations').document('conv-0000')

    def abort_first_read(references, *args, **kwargs):
        nonlocal attempts
        if kwargs.get('transaction') is not None:
            attempts += 1
            if attempts == 1:
                edited.update({'folder_id': 'chosen'})
                raise Aborted('synthetic read-time contention')
        return original_get_all(references, *args, **kwargs)

    monkeypatch.setattr(db, 'get_all', abort_first_read)
    response = client.delete('/v1/folders/source?move_to_folder_id=target')
    assert response.status_code == 204, response.text
    assert attempts == 2
    assert edited.get().to_dict()['folder_id'] == 'chosen'
    assert user.collection('conversations').document('conv-0001').get().to_dict()['folder_id'] == 'target'


def test_first_chunk_write_rejection_commits_nothing_and_can_retry(deletion, monkeypatch):
    client, _, user = deletion
    conversations = user.collection('conversations')
    original_update = Transaction.update
    staged = 0

    def fail_second_update(transaction, reference, *args, **kwargs):
        nonlocal staged
        staged += 1
        if staged == 2:
            raise RuntimeError('synthetic second write rejection')
        return original_update(transaction, reference, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(Transaction, 'update', fail_second_update)
        with pytest.raises(RuntimeError, match='synthetic second write rejection'):
            client.delete('/v1/folders/source?move_to_folder_id=target')
    assert staged == 2
    assert {row.to_dict()['folder_id'] for row in conversations.stream()} == {'source'}
    assert user.collection('folders').document('source').get().exists
    response = client.delete('/v1/folders/source?move_to_folder_id=target')
    assert response.status_code == 204, response.text
    assert {row.to_dict()['folder_id'] for row in conversations.stream()} == {'target'}

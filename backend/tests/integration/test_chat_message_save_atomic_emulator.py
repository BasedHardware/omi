"""Manual real-router/Firestore proof using synthetic accounts on a loopback emulator.

FIRESTORE_EMULATOR_HOST=127.0.0.1:10283 PYTHONPATH=backend \
  backend/.venv/bin/pytest -q backend/tests/integration/test_chat_message_save_atomic_emulator.py
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import Aborted, PermissionDenied
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.transaction import Transaction
import pytest

from database import _client
from routers import chat_sessions


@pytest.fixture
def chat(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('This proof requires a loopback Firestore emulator')
    store = firestore.Client(project='demo-chat-message-atomic', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', store)
    monkeypatch.setattr(chat_sessions, 'record_product_event', lambda *args, **kwargs: None)
    uid = uuid4().hex
    user = store.collection('users').document(uid)
    session = user.collection('chat_sessions').document('synthetic-session')
    now = datetime.now(timezone.utc)
    session.set({'id': session.id, 'created_at': now, 'updated_at': now, 'message_count': 0, 'preview': None})
    app = FastAPI()
    app.include_router(chat_sessions.router)
    app.dependency_overrides[chat_sessions.auth.get_current_user_uid] = lambda: uid
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, user.collection('messages'), session
    store.close()


def payload(client_id):
    result = {'text': 'synthetic message', 'sender': 'ai', 'session_id': 'synthetic-session'}
    if client_id:
        result['client_message_id'] = 'synthetic-turn'
    return result


def reject_session_write(monkeypatch, session):
    original_update = DocumentReference.update
    original_transaction_update = Transaction.update

    def update(reference, *args, **kwargs):
        if reference.path == session.path:
            raise RuntimeError('synthetic session write rejection')
        return original_update(reference, *args, **kwargs)

    def transaction_update(transaction, reference, *args, **kwargs):
        if reference.path == session.path:
            raise RuntimeError('synthetic session write rejection')
        return original_transaction_update(transaction, reference, *args, **kwargs)

    monkeypatch.setattr(DocumentReference, 'update', update)
    monkeypatch.setattr(Transaction, 'update', transaction_update)


@pytest.mark.parametrize('client_id', [False, True])
def test_rejected_session_write_does_not_partially_save_message(chat, monkeypatch, client_id):
    client, messages, session = chat
    reject_session_write(monkeypatch, session)
    response = client.post('/v2/desktop/messages', json=payload(client_id))
    assert response.status_code == 500
    assert list(messages.stream()) == []
    assert session.get().to_dict()['message_count'] == 0
    assert session.get().to_dict()['preview'] is None


@pytest.mark.parametrize('client_id', [False, True])
def test_retry_after_rejected_session_write_saves_one_row_and_one_count(chat, monkeypatch, client_id):
    client, messages, session = chat
    with monkeypatch.context() as fault:
        reject_session_write(fault, session)
        assert client.post('/v2/desktop/messages', json=payload(client_id)).status_code == 500
    retry = client.post('/v2/desktop/messages', json=payload(client_id))
    assert retry.status_code == 200, retry.text
    assert retry.json()['created'] is True
    assert len(list(messages.stream())) == 1
    stored_session = session.get().to_dict()
    assert stored_session['message_count'] == 1
    assert stored_session['preview'] == 'synthetic message'


def test_concurrently_deleted_session_is_not_resurrected_or_a_save_error(chat, monkeypatch):
    client, messages, session = chat
    original_get = DocumentReference.get
    fired = []

    def get(reference, *args, **kwargs):
        if reference.path != session.path or fired:
            return original_get(reference, *args, **kwargs)
        fired.append(True)
        if kwargs.get('transaction') is not None:
            session.delete()
            return original_get(reference, *args, **kwargs)
        snapshot = original_get(reference, *args, **kwargs)
        session.delete()
        return snapshot

    monkeypatch.setattr(DocumentReference, 'get', get)
    response = client.post('/v2/desktop/messages', json=payload(True))
    assert response.status_code == 200, response.text
    assert fired and not session.get().exists
    assert len(list(messages.stream())) == 1


@pytest.mark.parametrize('client_id', [False, True])
def test_normal_save_keeps_existing_wire_and_session_behavior(chat, client_id):
    client, messages, session = chat
    response = client.post('/v2/desktop/messages', json=payload(client_id))
    assert response.status_code == 200, response.text
    assert response.json()['created'] is True
    assert response.json()['session_id'] == session.id
    assert session.get().to_dict()['message_count'] == 1
    assert session.get().to_dict()['preview'] == 'synthetic message'
    saved = list(messages.stream())
    assert len(saved) == 1
    assert saved[0].to_dict()['chat_session_id'] == session.id


def test_simultaneous_same_key_saves_commit_one_message_and_one_increment(chat, monkeypatch):
    client, messages, session = chat
    barrier = Barrier(2)
    original_get = DocumentReference.get
    initial_reads = []
    message_path = messages.document('synthetic-turn').path

    def get(reference, *args, **kwargs):
        snapshot = original_get(reference, *args, **kwargs)
        if reference.path == message_path and kwargs.get('transaction') is None:
            assert not snapshot.exists
            initial_reads.append(True)
            barrier.wait(timeout=10)
        return snapshot

    monkeypatch.setattr(DocumentReference, 'get', get)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.post, '/v2/desktop/messages', json=payload(True)) for _ in range(2)]
        responses = [future.result(timeout=30) for future in futures]
    assert [response.status_code for response in responses] == [200, 200], [response.text for response in responses]
    assert initial_reads == [True, True]
    assert sorted(response.json()['created'] for response in responses) == [False, True]
    assert len(list(messages.stream())) == 1
    assert session.get().to_dict()['message_count'] == 1


def test_read_time_abort_retries_with_fresh_transaction_and_single_count(chat, monkeypatch):
    client, messages, session = chat
    original_get = DocumentReference.get
    attempts = []

    def get(reference, *args, **kwargs):
        if reference.path == session.path and kwargs.get('transaction') is not None:
            attempts.append(kwargs['transaction'])
            if len(attempts) < 3:
                raise Aborted('synthetic read contention')
        return original_get(reference, *args, **kwargs)

    monkeypatch.setattr(DocumentReference, 'get', get)
    response = client.post('/v2/desktop/messages', json=payload(True))
    assert response.status_code == 200, response.text
    assert len(attempts) == 3 and len({id(transaction) for transaction in attempts}) == 3
    assert len(list(messages.stream())) == 1
    assert session.get().to_dict()['message_count'] == 1


def test_exhausted_read_contention_is_bounded_and_commits_nothing(chat, monkeypatch):
    client, messages, session = chat
    original_get = DocumentReference.get
    attempts = []

    def get(reference, *args, **kwargs):
        if reference.path == session.path and kwargs.get('transaction') is not None:
            attempts.append(kwargs['transaction'])
            raise Aborted('synthetic sustained contention')
        return original_get(reference, *args, **kwargs)

    monkeypatch.setattr(DocumentReference, 'get', get)
    assert client.post('/v2/desktop/messages', json=payload(True)).status_code == 500
    assert len(attempts) == 5 and len({id(transaction) for transaction in attempts}) == 5
    assert list(messages.stream()) == []
    assert session.get().to_dict()['message_count'] == 0


@pytest.mark.parametrize('client_id', [False, True])
def test_unrelated_commit_failure_is_not_retried_or_partially_saved(chat, monkeypatch, client_id):
    client, messages, session = chat
    attempts = []

    def commit(transaction):
        attempts.append(transaction)
        raise PermissionDenied('synthetic commit rejection')

    monkeypatch.setattr(Transaction, '_commit', commit)
    assert client.post('/v2/desktop/messages', json=payload(client_id)).status_code == 500
    assert len(attempts) == 1
    assert list(messages.stream()) == []
    assert session.get().to_dict()['message_count'] == 0


def test_lost_commit_ack_is_not_auto_replayed_and_keyed_retry_converges(chat, monkeypatch):
    client, messages, session = chat
    original_commit = Transaction._commit
    attempts = []

    def commit(transaction):
        attempts.append(transaction)
        original_commit(transaction)
        raise RuntimeError('synthetic lost acknowledgment after successful commit')

    with monkeypatch.context() as fault:
        fault.setattr(Transaction, '_commit', commit)
        assert client.post('/v2/desktop/messages', json=payload(True)).status_code == 500
    assert len(attempts) == 1
    retry = client.post('/v2/desktop/messages', json=payload(True))
    assert retry.status_code == 200 and retry.json()['created'] is False
    assert len(list(messages.stream())) == 1
    assert session.get().to_dict()['message_count'] == 1


def test_changed_payload_key_collision_fails_without_changing_session(chat):
    client, messages, session = chat
    assert client.post('/v2/desktop/messages', json=payload(True)).status_code == 200
    before = session.get().to_dict()
    response = client.post('/v2/desktop/messages', json={**payload(True), 'text': 'different text'})
    assert response.status_code == 409
    assert session.get().to_dict() == before
    assert len(list(messages.stream())) == 1


def test_concurrent_distinct_messages_increment_without_losing_counts(chat):
    client, messages, session = chat
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(
                client.post, '/v2/desktop/messages', json={**payload(True), 'client_message_id': f'turn-{index}'}
            )
            for index in range(6)
        ]
        responses = [future.result(timeout=30) for future in futures]
    assert all(response.status_code == 200 and response.json()['created'] for response in responses)
    assert len(list(messages.stream())) == 6
    assert session.get().to_dict()['message_count'] == 6


def test_cross_session_same_key_race_does_not_increment_the_losing_session(chat, monkeypatch):
    client, messages, session = chat
    other_session = session.parent.document('synthetic-other-session')
    other_session.set({**session.get().to_dict(), 'id': other_session.id})
    barrier = Barrier(2)
    original_get = DocumentReference.get
    message_path = messages.document('synthetic-turn').path

    def get(reference, *args, **kwargs):
        snapshot = original_get(reference, *args, **kwargs)
        if reference.path == message_path and kwargs.get('transaction') is None:
            assert not snapshot.exists
            barrier.wait(timeout=10)
        return snapshot

    monkeypatch.setattr(DocumentReference, 'get', get)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(client.post, '/v2/desktop/messages', json={**payload(True), 'session_id': target.id})
            for target in (session, other_session)
        ]
        responses = [future.result(timeout=30) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.json()['session_id'] for response in responses if response.status_code == 200)
    saved = list(messages.stream())
    assert len(saved) == 1 and saved[0].to_dict()['session_id'] == winner
    assert session.get().to_dict()['message_count'] == int(winner == session.id)
    assert other_session.get().to_dict()['message_count'] == int(winner == other_session.id)


def test_newer_journal_revision_enriches_without_a_second_session_increment(chat):
    client, messages, session = chat
    assert client.post('/v2/desktop/messages', json={**payload(True), 'journal_revision': 1}).status_code == 200
    before = session.get().to_dict()
    response = client.post('/v2/desktop/messages', json={**payload(True), 'text': 'enriched', 'journal_revision': 2})
    assert response.status_code == 200, response.text
    assert response.json()['created'] is False and response.json()['updated'] is True
    assert messages.document('synthetic-turn').get().to_dict()['text'] == 'enriched'
    assert session.get().to_dict() == before

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.conversation_mutations as mutations_db
from routers import conversation_mutations as mutations_router
from utils.other import endpoints as auth

BASE_REVISION = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
COMMIT_REVISION = datetime(2026, 8, 30, 8, 1, tzinfo=timezone.utc)


def _resolve_server_timestamps(value: Any, commit_revision: datetime) -> Any:
    if value is mutations_db.firestore.SERVER_TIMESTAMP:
        return commit_revision
    if isinstance(value, dict):
        return {key: _resolve_server_timestamps(item, commit_revision) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_server_timestamps(item, commit_revision) for item in value]
    return deepcopy(value)


class _Snapshot:
    def __init__(self, data: dict[str, Any] | None, update_time: datetime | None):
        self._data = deepcopy(data)
        self.exists = data is not None
        self.update_time = update_time

    def to_dict(self):
        return deepcopy(self._data)


class _Document:
    def __init__(self, database: '_Firestore', path: tuple[str, ...]):
        self.database = database
        self.path = path

    def collection(self, name: str):
        return _Collection(self.database, (*self.path, name))

    def get(self, transaction: '_Transaction | None' = None):
        if transaction is not None:
            transaction.read(self)
        return _Snapshot(self.database.rows.get(self.path), self.database.update_times.get(self.path))


class _Collection:
    def __init__(self, database: '_Firestore', path: tuple[str, ...]):
        self.database = database
        self.path = path

    def document(self, name: str):
        return _Document(self.database, (*self.path, name))


class _Transaction:
    def __init__(self, database: '_Firestore'):
        self.database = database
        self.has_written = False
        self.read_paths: list[tuple[str, ...]] = []
        self.write_paths: list[tuple[str, ...]] = []

    def read(self, document: _Document):
        if self.has_written:
            raise AssertionError('Firestore transactions require all reads before writes')
        self.read_paths.append(document.path)

    def update(self, document: _Document, patch: dict[str, Any]):
        self.has_written = True
        if document.path not in self.database.rows:
            raise RuntimeError('missing document')
        row = self.database.rows[document.path]
        for key, value in patch.items():
            if '.' not in key:
                row[key] = deepcopy(value)
                continue
            outer, inner = key.split('.', 1)
            nested = row.setdefault(outer, {})
            nested[inner] = deepcopy(value)
        self.database.update_times[document.path] = self.database.commit_revision
        self.write_paths.append(document.path)

    def create(self, document: _Document, data: dict[str, Any]):
        self.has_written = True
        if document.path in self.database.rows:
            raise RuntimeError('document already exists')
        self.database.rows[document.path] = _resolve_server_timestamps(data, self.database.commit_revision)
        self.database.update_times[document.path] = self.database.commit_revision
        self.write_paths.append(document.path)


class _Firestore:
    def __init__(self, conversation: dict[str, Any], *, revision: datetime | None = BASE_REVISION):
        self.conversation_path: tuple[str, ...] = ('users', 'user-1', 'conversations', 'conversation-1')
        self.rows: dict[tuple[str, ...], dict[str, Any]] = {self.conversation_path: deepcopy(conversation)}
        self.update_times: dict[tuple[str, ...], datetime | None] = {self.conversation_path: revision}
        self.commit_revision = COMMIT_REVISION
        self.transactions: list[_Transaction] = []

    def collection(self, name: str):
        return _Collection(self, (name,))

    def transaction(self):
        transaction = _Transaction(self)
        self.transactions.append(transaction)
        return transaction


def _conversation(**overrides: Any) -> dict[str, Any]:
    conversation: dict[str, Any] = {
        'id': 'conversation-1',
        'structured': {'title': 'Generated title', 'overview': 'Summary'},
        'starred': False,
        'folder_id': 'folder-1',
        'visibility': 'private',
        'data_protection_level': 'standard',
    }
    conversation.update(overrides)
    return conversation


@pytest.fixture(autouse=True)
def transactional_decorator(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mutations_db.firestore, 'transactional', lambda function: function)


def _apply(
    database: _Firestore,
    *,
    mutation_id: str = 'mutation-1',
    base_revision: datetime = BASE_REVISION,
    operation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return mutations_db.apply_conversation_sync_mutation(
        'user-1',
        'conversation-1',
        client_mutation_id=mutation_id,
        base_revision=base_revision,
        operation=operation or {'type': 'set_title', 'title': 'My title'},
        firestore_client=database,
    )


def test_title_mutation_commits_compact_receipt_and_exact_canonical_revision():
    database = _Firestore(_conversation())

    response = _apply(database)

    assert response == {
        'status': 'ok',
        'client_mutation_id': 'mutation-1',
        'conversation_id': 'conversation-1',
        'conversation': {
            'revision': COMMIT_REVISION,
            'title': 'My title',
            'starred': False,
            'folder_id': 'folder-1',
            'visibility': 'private',
        },
    }
    assert database.rows[database.conversation_path]['structured']['title'] == 'My title'
    assert database.rows[database.conversation_path]['user_title'] == 'My title'
    receipt_paths = [path for path in database.rows if path[-2:-1] == ('mutation_receipts',)]
    assert len(receipt_paths) == 1
    assert 'transcript_segments' not in database.rows[receipt_paths[0]]
    assert database.transactions[0].read_paths == [receipt_paths[0], database.conversation_path]
    assert database.transactions[0].write_paths == [database.conversation_path, receipt_paths[0]]


def test_retry_replays_exact_response_after_processing_advances_conversation():
    database = _Firestore(_conversation())
    first = _apply(database)
    database.rows[database.conversation_path]['structured']['overview'] = 'Later processing result'
    database.update_times[database.conversation_path] = COMMIT_REVISION + timedelta(minutes=1)

    replay = _apply(database)

    assert replay == first
    assert len(database.transactions[1].write_paths) == 0


def test_retry_replays_before_rechecking_a_new_lock():
    database = _Firestore(_conversation())
    first = _apply(database)
    database.rows[database.conversation_path]['is_locked'] = True
    database.update_times[database.conversation_path] = COMMIT_REVISION + timedelta(minutes=1)

    replay = _apply(database)

    assert replay == first


def test_new_mutation_cannot_bypass_conversation_lock():
    database = _Firestore(_conversation(is_locked=True))

    with pytest.raises(mutations_db.ConversationMutationLockedError):
        _apply(database)

    assert len(database.rows) == 1


def test_new_mutation_returns_not_found_without_creating_orphan_receipt():
    database = _Firestore(_conversation())
    del database.rows[database.conversation_path]
    del database.update_times[database.conversation_path]

    with pytest.raises(mutations_db.ConversationMutationNotFoundError):
        _apply(database)

    assert database.rows == {}


def test_same_mutation_id_with_different_intent_is_rejected_without_second_write():
    database = _Firestore(_conversation())
    _apply(database)

    with pytest.raises(mutations_db.ConversationMutationConflictError) as raised:
        _apply(database, operation={'type': 'set_title', 'title': 'Different title'})

    assert raised.value.response['code'] == 'mutation_id_reused'
    assert database.rows[database.conversation_path]['user_title'] == 'My title'
    assert database.transactions[1].write_paths == []


def test_stale_base_revision_returns_and_replays_original_typed_conflict():
    database = _Firestore(_conversation())
    stale = BASE_REVISION - timedelta(seconds=1)

    with pytest.raises(mutations_db.ConversationMutationConflictError) as first_error:
        _apply(database, base_revision=stale)

    first = first_error.value.response
    assert first['code'] == 'base_revision_mismatch'
    assert first['conversation']['revision'] == BASE_REVISION
    assert database.rows[database.conversation_path].get('user_title') is None

    database.rows[database.conversation_path]['starred'] = True
    database.update_times[database.conversation_path] = BASE_REVISION + timedelta(minutes=5)
    with pytest.raises(mutations_db.ConversationMutationConflictError) as replay_error:
        _apply(database, base_revision=stale)

    assert replay_error.value.response == first
    assert replay_error.value.response['conversation']['starred'] is False


def test_missing_snapshot_revision_fails_closed_and_records_the_result():
    database = _Firestore(_conversation(), revision=None)

    with pytest.raises(mutations_db.ConversationMutationConflictError) as raised:
        _apply(database)

    assert raised.value.response['code'] == 'revision_unavailable'
    assert database.rows[database.conversation_path]['structured']['title'] == 'Generated title'


def test_starred_mutation_is_typed_and_does_not_touch_processing_fields():
    database = _Firestore(_conversation())

    response = _apply(database, operation={'type': 'set_starred', 'starred': True})

    assert response['conversation']['starred'] is True
    assert database.rows[database.conversation_path]['structured']['overview'] == 'Summary'


def test_noop_mutation_keeps_existing_conversation_revision():
    database = _Firestore(_conversation(starred=True))

    response = _apply(database, operation={'type': 'set_starred', 'starred': True})

    assert response['conversation']['revision'] == BASE_REVISION
    assert database.update_times[database.conversation_path] == BASE_REVISION
    assert database.transactions[0].write_paths[-1][-2] == 'mutation_receipts'


def test_http_contract_returns_top_level_typed_conflict(monkeypatch: pytest.MonkeyPatch):
    app = FastAPI()
    app.include_router(mutations_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'user-1'
    monkeypatch.setattr(
        mutations_db,
        'apply_conversation_sync_mutation',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            mutations_db.ConversationMutationConflictError(
                {
                    'status': 'conflict',
                    'code': 'base_revision_mismatch',
                    'client_mutation_id': 'mutation-1',
                    'conversation_id': 'conversation-1',
                    'conversation': {
                        'revision': BASE_REVISION,
                        'title': 'Canonical',
                        'starred': False,
                        'folder_id': None,
                        'visibility': 'private',
                    },
                }
            )
        ),
    )
    client = TestClient(app)

    response = client.post(
        '/v1/conversations/conversation-1/mutations',
        json={
            'client_mutation_id': 'mutation-1',
            'base_revision': BASE_REVISION.isoformat(),
            'operation': {'type': 'set_title', 'title': 'Updated'},
        },
    )

    assert response.status_code == 409
    assert response.json()['code'] == 'base_revision_mismatch'
    assert 'detail' not in response.json()


def test_http_contract_rejects_untyped_or_ambiguous_operations():
    app = FastAPI()
    app.include_router(mutations_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'user-1'
    client = TestClient(app)
    payload = {
        'client_mutation_id': 'mutation-1',
        'base_revision': BASE_REVISION.isoformat(),
        'operation': {'type': 'set_starred', 'starred': 'yes', 'title': 'smuggled'},
    }

    response = client.post('/v1/conversations/conversation-1/mutations', json=payload)

    assert response.status_code == 422

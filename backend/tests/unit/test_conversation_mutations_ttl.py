from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

import database.conversation_mutations as mutations_db

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


class _MockDocRef:
    def __init__(self, database: _MockFirestore, path: tuple[str, ...]):
        self.database = database
        self.path = path

    def delete(self):
        self.database.rows.pop(self.path, None)
        self.database.update_times.pop(self.path, None)


class _MockDocSnapshot:
    def __init__(self, database: _MockFirestore, path: tuple[str, ...], data: dict[str, Any] | None):
        self.database = database
        self.path = path
        self._data = deepcopy(data)
        self.exists = data is not None
        self.reference = _MockDocRef(database, path)

    def to_dict(self):
        return deepcopy(self._data)


class _MockQuery:
    def __init__(self, database: _MockFirestore, base_path: tuple[str, ...]):
        self.database = database
        self.base_path = base_path
        self._filters: list[tuple[str, str, Any]] = []
        self._limit_val: int | None = None

    def where(self, field: str, op: str, value: Any):
        new_q = _MockQuery(self.database, self.base_path)
        new_q._filters = list(self._filters) + [(field, op, value)]
        new_q._limit_val = self._limit_val
        return new_q

    def limit(self, count: int):
        new_q = _MockQuery(self.database, self.base_path)
        new_q._filters = list(self._filters)
        new_q._limit_val = count
        return new_q

    def stream(self):
        results = []
        for path, data in list(self.database.rows.items()):
            if path[: len(self.base_path)] != self.base_path or len(path) != len(self.base_path) + 1:
                continue
            matched = True
            for field, op, val in self._filters:
                doc_val = data.get(field)
                if op == '<=' and not (doc_val is not None and doc_val <= val):
                    matched = False
                    break
            if matched:
                results.append(_MockDocSnapshot(self.database, path, data))
        if self._limit_val is not None:
            results = results[: self._limit_val]
        return results

    def get(self):
        return self.stream()


class _Document:
    def __init__(self, database: _MockFirestore, path: tuple[str, ...]):
        self.database = database
        self.path = path

    def collection(self, name: str):
        return _Collection(self.database, (*self.path, name))

    def get(self, transaction: _Transaction | None = None):
        if transaction is not None:
            transaction.read(self)
        return _Snapshot(self.database.rows.get(self.path), self.database.update_times.get(self.path))

    def delete(self):
        self.database.rows.pop(self.path, None)
        self.database.update_times.pop(self.path, None)


class _Snapshot:
    def __init__(self, data: dict[str, Any] | None, update_time: datetime | None):
        self._data = deepcopy(data)
        self.exists = data is not None
        self.update_time = update_time

    def to_dict(self):
        return deepcopy(self._data)


class _Collection:
    def __init__(self, database: _MockFirestore, path: tuple[str, ...]):
        self.database = database
        self.path = path

    def document(self, name: str):
        return _Document(self.database, (*self.path, name))

    def where(self, field: str, op: str, value: Any):
        return _MockQuery(self.database, self.path).where(field, op, value)


class _Transaction:
    def __init__(self, database: _MockFirestore):
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

    def set(self, document: _Document, data: dict[str, Any]):
        self.has_written = True
        self.database.rows[document.path] = _resolve_server_timestamps(data, self.database.commit_revision)
        self.database.update_times[document.path] = self.database.commit_revision
        self.write_paths.append(document.path)


class _MockFirestore:
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


def test_mutation_receipt_stamps_created_at_and_expire_at():
    database = _MockFirestore(_conversation())
    now_before = datetime.now(timezone.utc)

    mutations_db.apply_conversation_sync_mutation(
        'user-1',
        'conversation-1',
        client_mutation_id='m-ttl-1',
        base_revision=BASE_REVISION,
        operation={'type': 'set_title', 'title': 'Title With TTL'},
        firestore_client=database,
    )
    now_after = datetime.now(timezone.utc)

    receipt_paths = [p for p in database.rows if p[-2:-1] == ('mutation_receipts',)]
    assert len(receipt_paths) == 1
    receipt = database.rows[receipt_paths[0]]

    assert receipt['schema_version'] == 1
    assert receipt['client_mutation_id'] == 'm-ttl-1'
    assert 'created_at' in receipt
    assert 'expire_at' in receipt
    assert isinstance(receipt['expire_at'], datetime)
    expected_min_expire = now_before + mutations_db.DEFAULT_RECEIPT_TTL
    expected_max_expire = now_after + mutations_db.DEFAULT_RECEIPT_TTL
    assert expected_min_expire <= receipt['expire_at'] <= expected_max_expire


def test_custom_ttl_is_respected():
    database = _MockFirestore(_conversation())
    custom_ttl = timedelta(days=3)
    now_before = datetime.now(timezone.utc)

    mutations_db.apply_conversation_sync_mutation(
        'user-1',
        'conversation-1',
        client_mutation_id='m-custom-ttl',
        base_revision=BASE_REVISION,
        operation={'type': 'set_starred', 'starred': True},
        ttl=custom_ttl,
        firestore_client=database,
    )

    receipt_paths = [p for p in database.rows if p[-2:-1] == ('mutation_receipts',)]
    receipt = database.rows[receipt_paths[0]]
    expected_expire = now_before + custom_ttl
    assert abs((receipt['expire_at'] - expected_expire).total_seconds()) < 5


def test_conflict_receipt_stamps_expire_at_to_bound_retry_loops():
    database = _MockFirestore(_conversation())
    stale_revision = BASE_REVISION - timedelta(seconds=10)

    with pytest.raises(mutations_db.ConversationMutationConflictError):
        mutations_db.apply_conversation_sync_mutation(
            'user-1',
            'conversation-1',
            client_mutation_id='m-conflict-loop',
            base_revision=stale_revision,
            operation={'type': 'set_title', 'title': 'Stale'},
            firestore_client=database,
        )

    receipt_paths = [p for p in database.rows if p[-2:-1] == ('mutation_receipts',)]
    assert len(receipt_paths) == 1
    receipt = database.rows[receipt_paths[0]]
    assert receipt['response']['code'] == 'base_revision_mismatch'
    assert 'expire_at' in receipt
    assert receipt['expire_at'] > datetime.now(timezone.utc)


def test_unexpired_receipt_replays_cleanly_without_reapplying():
    database = _MockFirestore(_conversation())

    res1, replayed1 = mutations_db.apply_conversation_sync_mutation(
        'user-1',
        'conversation-1',
        client_mutation_id='m-replay-check',
        base_revision=BASE_REVISION,
        operation={'type': 'set_title', 'title': 'Original'},
        firestore_client=database,
    )
    assert replayed1 is False

    res2, replayed2 = mutations_db.apply_conversation_sync_mutation(
        'user-1',
        'conversation-1',
        client_mutation_id='m-replay-check',
        base_revision=BASE_REVISION,
        operation={'type': 'set_title', 'title': 'Original'},
        firestore_client=database,
    )
    assert replayed2 is True
    assert res1 == res2


def test_expired_receipt_allows_reapplying_mutation():
    database = _MockFirestore(_conversation())

    # 1. Apply initial mutation
    mutations_db.apply_conversation_sync_mutation(
        'user-1',
        'conversation-1',
        client_mutation_id='m-reapply-expired',
        base_revision=BASE_REVISION,
        operation={'type': 'set_title', 'title': 'Old Title'},
        firestore_client=database,
    )

    receipt_paths = [p for p in database.rows if p[-2:-1] == ('mutation_receipts',)]
    assert len(receipt_paths) == 1
    receipt_path = receipt_paths[0]

    # 2. Simulate receipt expiration by setting expire_at in the past
    database.rows[receipt_path]['expire_at'] = datetime.now(timezone.utc) - timedelta(days=1)

    # 3. Simulate another valid update against the updated canonical revision
    res, replayed = mutations_db.apply_conversation_sync_mutation(
        'user-1',
        'conversation-1',
        client_mutation_id='m-reapply-expired',
        base_revision=COMMIT_REVISION,
        operation={'type': 'set_title', 'title': 'Renewed Title'},
        firestore_client=database,
    )

    assert replayed is False
    assert res['status'] == 'ok'
    assert database.rows[database.conversation_path]['user_title'] == 'Renewed Title'
    assert database.rows[receipt_path]['expire_at'] > datetime.now(timezone.utc)


def test_get_conversation_mutation_receipt_respects_expiration():
    database = _MockFirestore(_conversation())
    uid = 'user-1'
    cid = 'conversation-1'
    mid = 'm-get-receipt'

    mutations_db.apply_conversation_sync_mutation(
        uid,
        cid,
        client_mutation_id=mid,
        base_revision=BASE_REVISION,
        operation={'type': 'set_starred', 'starred': True},
        firestore_client=database,
    )

    # Valid receipt read
    receipt = mutations_db.get_conversation_mutation_receipt(uid, cid, mid, firestore_client=database)
    assert receipt is not None
    assert receipt['client_mutation_id'] == mid

    # Simulate expired
    receipt_paths = [p for p in database.rows if p[-2:-1] == ('mutation_receipts',)]
    database.rows[receipt_paths[0]]['expire_at'] = datetime.now(timezone.utc) - timedelta(hours=1)

    # Expired receipt returns None
    assert mutations_db.get_conversation_mutation_receipt(uid, cid, mid, firestore_client=database) is None

    # Non-existent returns None
    assert mutations_db.get_conversation_mutation_receipt(uid, cid, 'unknown', firestore_client=database) is None


def test_prune_expired_mutation_receipts():
    database = _MockFirestore(_conversation())
    uid = 'user-1'
    cid = 'conversation-1'

    now = datetime.now(timezone.utc)
    conv_base = ('users', uid, 'conversations', cid)

    # Add 2 expired and 1 unexpired receipt
    database.rows[(*conv_base, 'mutation_receipts', 'r1')] = {
        'client_mutation_id': 'm1',
        'expire_at': now - timedelta(days=2),
    }
    database.rows[(*conv_base, 'mutation_receipts', 'r2')] = {
        'client_mutation_id': 'm2',
        'expire_at': now - timedelta(days=1),
    }
    database.rows[(*conv_base, 'mutation_receipts', 'r3')] = {
        'client_mutation_id': 'm3',
        'expire_at': now + timedelta(days=7),
    }

    deleted = mutations_db.prune_expired_mutation_receipts(uid, cid, now=now, firestore_client=database)
    assert deleted == 2
    assert (*conv_base, 'mutation_receipts', 'r1') not in database.rows
    assert (*conv_base, 'mutation_receipts', 'r2') not in database.rows
    assert (*conv_base, 'mutation_receipts', 'r3') in database.rows

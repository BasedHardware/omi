"""One human, one Person document, even when two conversations finish at once.

Resolve-or-create by name used to be read-then-create: load the people, casefold
match, miss, coin a uuid4, write. Two concurrent passes inferring the same
previously unknown name both missed and both wrote, producing duplicate Person
records for one human and two voiceprint targets. These pin the closed race: the
name maps to one deterministic document, the transaction turns a concurrent
collision into a reuse, and existing uuid4-keyed people stay authoritative
including after a rename.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import uuid  # noqa: E402

import pytest  # noqa: E402

import database.users as users_db  # noqa: E402

UID = "u1"

_RESOLVE = users_db._resolve_person_by_name_transaction.to_wrap


class _Aborted(Exception):
    """Stands in for the contention error Firestore raises on a losing commit."""


class _Snapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _DocRef:
    def __init__(self, store, doc_id):
        self.store = store
        self.id = doc_id

    def get(self, transaction=None):
        return _Snapshot(self.id, self.store.get(self.id))

    def set(self, data):
        self.store[self.id] = dict(data)

    def collection(self, _name):
        return _CollectionRef(self.store)


class _CollectionRef:
    def __init__(self, store):
        self.store = store

    def document(self, doc_id):
        return _DocRef(self.store, doc_id)

    def stream(self):
        return [_Snapshot(doc_id, data) for doc_id, data in self.store.items()]


class _Client:
    def __init__(self, store):
        self.store = store

    def collection(self, _name):
        return _CollectionRef(self.store)

    def transaction(self):
        return _Transaction(self.store)


class _Transaction:
    """Buffers creates and rejects one whose document appeared meanwhile."""

    def __init__(self, store):
        self.store = store
        self.pending = []

    def create(self, ref, data):
        self.pending.append((ref, dict(data)))

    def commit(self):
        for ref, data in self.pending:
            if ref.id in self.store:
                raise _Aborted()
        for ref, data in self.pending:
            self.store[ref.id] = data


def _run_transaction(store, person_ref, name, name_key, attempts=5):
    """Emulate @transactional: run the body, retry the whole body on contention."""
    for _ in range(attempts):
        transaction = _Transaction(store)
        person, created = _RESOLVE(transaction, person_ref, name, name_key)
        try:
            transaction.commit()
        except _Aborted:
            continue
        return person, created
    raise AssertionError('transaction never committed')


class _ForbiddenGlobal:
    """Fails any use of the legacy `db` proxy, which resolution must no longer touch."""

    def __getattr__(self, attribute):
        raise AssertionError(f'legacy global db used for {attribute}')


@pytest.fixture
def store(monkeypatch):
    people = {}
    monkeypatch.setattr(users_db, 'db', _ForbiddenGlobal())
    monkeypatch.setattr(users_db, 'get_firestore_client', lambda: _Client(people))

    def _resolve(_transaction, person_ref, name, name_key):
        return _run_transaction(people, person_ref, name, name_key)

    monkeypatch.setattr(users_db, '_resolve_person_by_name_transaction', _resolve)
    return people


def _slot(name_key, probe=0):
    return users_db.person_name_document_id(UID, name_key, probe)


def test_identity_key_is_the_callers_matching_rule():
    assert users_db.person_name_identity_key('  Alice  ') == 'alice'
    assert users_db.person_name_identity_key('ALICE') == users_db.person_name_identity_key('alice')


def test_deterministic_id_is_stable_and_does_not_leak_the_name():
    doc_id = _slot('alice')

    assert doc_id == _slot(users_db.person_name_identity_key(' Alice '))
    assert doc_id != _slot('bob')
    assert doc_id != _slot('alice', probe=1)
    assert 'alice' not in doc_id.lower()
    assert uuid.UUID(doc_id).version == 4


def test_two_concurrent_resolvers_of_an_unseen_name_yield_one_person(store):
    """Both read an empty slot, both try to create; the loser retries into a reuse."""
    ref_a = _DocRef(store, _slot('alice'))
    ref_b = _DocRef(store, _slot('alice'))

    txn_a, txn_b = _Transaction(store), _Transaction(store)
    person_a, created_a = _RESOLVE(txn_a, ref_a, 'Alice', 'alice')
    person_b_first, _ = _RESOLVE(txn_b, ref_b, 'Alice', 'alice')

    assert person_b_first['id'] == person_a['id']
    txn_a.commit()
    with pytest.raises(_Aborted):
        txn_b.commit()

    person_b, created_b = _run_transaction(store, ref_b, 'Alice', 'alice')

    assert created_a and not created_b
    assert person_b['id'] == person_a['id']
    assert len(store) == 1


def test_concurrent_resolvers_reach_the_same_document(store):
    """The name, not a coin flip, chooses the document both passes contend over."""
    first, created_first = users_db.get_or_create_person_by_name(UID, 'Alice')
    second, created_second = users_db.get_or_create_person_by_name(UID, ' alice ')

    assert created_first and not created_second
    assert first['id'] == second['id'] == _slot('alice')
    assert len(store) == 1


def test_existing_uuid4_person_is_reused_not_duplicated(store):
    legacy_id = str(uuid.uuid4())
    store[legacy_id] = {'id': legacy_id, 'name': 'Alice'}

    person, created = users_db.get_or_create_person_by_name(UID, 'ALICE')

    assert not created
    assert person['id'] == legacy_id
    assert len(store) == 1


def test_renamed_person_is_reused_under_the_new_name(store):
    person, _ = users_db.get_or_create_person_by_name(UID, 'Alice')
    store[person['id']]['name'] = 'Alicia'

    resolved, created = users_db.get_or_create_person_by_name(UID, 'alicia')

    assert not created
    assert resolved['id'] == person['id']
    assert len(store) == 1


def test_a_slot_freed_by_a_rename_is_not_adopted_by_the_old_name(store):
    renamed, _ = users_db.get_or_create_person_by_name(UID, 'Alice')
    store[renamed['id']]['name'] = 'Alicia'

    other, created = users_db.get_or_create_person_by_name(UID, 'Alice')

    assert created
    assert other['id'] != renamed['id']
    assert other['id'] == _slot('alice', probe=1)
    assert store[renamed['id']]['name'] == 'Alicia'
    assert len(store) == 2


def test_blank_name_is_rejected(store):
    with pytest.raises(ValueError):
        users_db.get_or_create_person_by_name(UID, '   ')
    assert not store


def test_an_injected_client_serves_the_scan_the_transaction_and_the_creation(monkeypatch):
    """One client at the call boundary, so a fake can exercise resolve-or-create end to end."""
    people = {}
    client = _Client(people)
    monkeypatch.setattr(users_db, 'db', _ForbiddenGlobal())
    monkeypatch.setattr(
        users_db,
        'get_firestore_client',
        lambda: (_ for _ in ()).throw(AssertionError('injected client was ignored')),
    )
    monkeypatch.setattr(
        users_db,
        '_resolve_person_by_name_transaction',
        lambda _transaction, person_ref, name, name_key: _run_transaction(people, person_ref, name, name_key),
    )

    created_person, created = users_db.get_or_create_person_by_name(UID, 'Alice', firestore_client=client)
    reused, created_again = users_db.get_or_create_person_by_name(UID, 'Alice', firestore_client=client)

    assert created and not created_again
    assert reused['id'] == created_person['id'] == _slot('alice')
    assert len(people) == 1

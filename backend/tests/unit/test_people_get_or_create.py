"""Creating a person by name leaves one person, even when requests for that name race.

`POST /v1/users/people` looked the name up and then created the person in a separate
write, so two concurrent or retried requests for a new name could both miss the lookup
and each create a person. The create now re-checks the exact name in its own transaction.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from datetime import datetime, timezone

import routers.users as users_router
from database import people as people_db
from models.other import CreatePerson
from tests.unit.fixtures.strict_firestore_transaction import (
    ForeignTransactionError,
    StrictFirestore,
    StrictFirestoreCollection,
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
)

NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
PEOPLE = ('users', 'u1', 'people')


class PeopleFirestore(StrictFirestore):
    """StrictFirestore plus the equality query this path streams inside its transaction.

    The shared fixture models only id-projected, bounded queries. Its transaction still
    applies: a read after the first write fails.
    """

    def collection(self, name):
        return _Collection(self, (name,))


class _Collection(StrictFirestoreCollection):
    def document(self, name):
        return _Document(self._database, (*self._path, name))

    def where(self, *, filter):
        return _EqualityQuery(self._database, self._path, filter)


class _Document(StrictFirestoreDocument):
    def collection(self, name):
        return _Collection(self._database, (*self.path, name))


class _Snapshot(StrictFirestoreSnapshot):
    def __init__(self, path, data):
        super().__init__(data)
        self.id = path[-1]


class _EqualityQuery:
    """Every document in one collection whose field equals a value, read in a transaction."""

    def __init__(self, database, path, field_filter):
        assert field_filter.op_string == '=='
        self._database, self._path, self._filter = database, path, field_filter

    def stream(self, *, transaction):
        if transaction._database is not self._database:
            raise ForeignTransactionError('Firestore transaction and query must belong to the same store')
        transaction._assert_read_allowed()
        field, value = self._filter.field_path, self._filter.value
        rows = sorted(self._database.rows.items())
        return iter([_Snapshot(path, row) for path, row in rows if path[:-1] == self._path and row.get(field) == value])


def _person(person_id, name, **fields):
    return {'id': person_id, 'name': name, 'created_at': NOW, 'updated_at': NOW, **fields}


def _people(store):
    return {path[-1]: row for path, row in store.rows.items() if path[:-1] == PEOPLE}


def test_existing_active_person_is_returned_instead_of_a_second_one():
    # Dismissed namesakes sort first and must not hide the active person.
    dismissed = {(*PEOPLE, f'd{n:02d}'): _person(f'd{n:02d}', 'Alice', is_dismissed=True) for n in range(12)}
    store = PeopleFirestore({**dismissed, (*PEOPLE, 'p1'): _person('p1', 'Alice')})

    person = people_db.get_or_create_person_by_name('u1', _person('p2', 'Alice'), firestore_client=store)

    assert person['id'] == 'p1' and person['name'] == 'Alice'
    assert 'p2' not in _people(store)
    assert store.transactions[-1].sets == []


def test_person_is_created_when_only_a_dismissed_or_differently_named_person_exists():
    store = PeopleFirestore(
        {
            (*PEOPLE, 'p1'): _person('p1', 'Alice', is_dismissed=True),
            (*PEOPLE, 'p2'): _person('p2', 'Alicia'),
            ('users', 'u2', 'people', 'p3'): _person('p3', 'Alice'),
        }
    )

    person = people_db.get_or_create_person_by_name('u1', _person('p4', 'Alice'), firestore_client=store)

    assert person == _person('p4', 'Alice')
    assert store.rows[(*PEOPLE, 'p4')] == {**_person('p4', 'Alice'), 'is_user_created': True}
    assert [path for path, _ in store.transactions[-1].sets] == [(*PEOPLE, 'p4')]


def test_retried_create_returns_the_person_the_first_request_created():
    store = PeopleFirestore()

    first = people_db.get_or_create_person_by_name('u1', _person('p1', 'Alice'), firestore_client=store)
    retry = people_db.get_or_create_person_by_name('u1', _person('p2', 'Alice'), firestore_client=store)

    assert first['id'] == retry['id'] == 'p1'
    assert set(_people(store)) == {'p1'}


def test_endpoint_returns_the_person_a_racing_request_created(monkeypatch):
    store = PeopleFirestore()

    def lookup_misses_then_the_racing_create_lands(uid, name):
        # The other request's create commits after this request's lookup has missed.
        store.rows[('users', uid, 'people', 'p-race')] = {**_person('p-race', name), 'is_user_created': True}
        return None

    unchecked_creates = []
    monkeypatch.setattr(users_router, 'get_person_by_name', lookup_misses_then_the_racing_create_lands)
    monkeypatch.setattr(users_router, 'create_person', lambda uid, data: unchecked_creates.append(data) or data)
    monkeypatch.setattr(people_db, 'get_firestore_client', lambda: store)

    person = users_router.get_or_create_person(CreatePerson(name='Alice'), uid='u1')

    assert person['id'] == 'p-race'
    assert unchecked_creates == []
    assert set(_people(store)) == {'p-race'}

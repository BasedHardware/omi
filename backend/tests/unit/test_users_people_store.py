"""People CRUD in database.users, migrated to the WP2 storage port (ADR-0002).

Hermetic: injects the real Mongo adapter over a mongomock client (no server), so the migrated
path-based code paths run end to end without stubbing the Firestore SDK. The transactional
``update_person`` is covered by the live dual-backend contract test (mongomock has no replica-set
transactions); everything non-transactional is covered here.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import pytest

# pymongo + mongomock are on-prem (Mongo backend) deps, present in the offline test image but not in the
# upstream requirements/pyproject manifests. Skip the whole module where they are absent (a clean upstream
# CI checkout) instead of failing collection with ModuleNotFoundError (cubic PR 10887).
pytest.importorskip('pymongo')
mongomock = pytest.importorskip('mongomock')

import database.users as users
from database.store.adapters.mongo import MongoDocumentStore
from tests.store_fakes import install_fake_db_client


@pytest.fixture
def store(monkeypatch):
    # ADR-0044: users threads the raw db client; wire the neutral facade over the REAL Mongo adapter
    # (mongomock, no server) so the migrated path-based people CRUD runs end to end on Mongo (was the
    # retired _store seam). The transactional _add_sample path stays on the live contract test
    # (mongomock has no replica-set transactions).
    s = MongoDocumentStore(client=mongomock.MongoClient(), db_name='test')
    install_fake_db_client(monkeypatch, store=s)
    return s


def test_create_and_get_person(store):
    users.create_person('u1', {'id': 'p1', 'name': 'Alice'})
    assert users.get_person('u1', 'p1') == {'id': 'p1', 'name': 'Alice'}


def test_get_person_missing_returns_none(store):
    assert users.get_person('u1', 'nope') is None


def test_get_person_fills_id_from_document_key(store):
    store.set('users/u1/people/legacy', {'name': 'Bob'})  # no stored 'id'
    assert users.get_person('u1', 'legacy') == {'id': 'legacy', 'name': 'Bob'}


def test_get_people_lists_only_that_user(store):
    users.create_person('u1', {'id': 'p1', 'name': 'Alice'})
    users.create_person('u1', {'id': 'p2', 'name': 'Bob'})
    users.create_person('u2', {'id': 'p3', 'name': 'Carol'})  # different user
    people = users.get_people('u1')
    assert sorted(p['name'] for p in people) == ['Alice', 'Bob']
    assert all(p['id'] in {'p1', 'p2'} for p in people)


def test_get_person_by_name(store):
    users.create_person('u1', {'id': 'p1', 'name': 'Alice'})
    users.create_person('u1', {'id': 'p2', 'name': 'Bob'})
    assert users.get_person_by_name('u1', 'Bob')['id'] == 'p2'
    assert users.get_person_by_name('u1', 'Nobody') is None


def test_delete_person(store):
    users.create_person('u1', {'id': 'p1', 'name': 'Alice'})
    users.delete_person('u1', 'p1')
    assert users.get_person('u1', 'p1') is None

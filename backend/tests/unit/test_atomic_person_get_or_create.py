import os
import sys
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

if "deepgram" not in sys.modules:
    sys.modules["deepgram"] = MagicMock()

if "twilio" not in sys.modules:
    twilio_mock = types.ModuleType("twilio")
    twilio_jwt_mock = types.ModuleType("twilio.jwt")
    twilio_jwt_access_token_mock = types.ModuleType("twilio.jwt.access_token")
    twilio_jwt_access_token_mock.AccessToken = MagicMock()
    twilio_jwt_access_token_grants_mock = types.ModuleType("twilio.jwt.access_token.grants")
    twilio_jwt_access_token_grants_mock.VoiceGrant = MagicMock()
    twilio_request_validator_mock = types.ModuleType("twilio.request_validator")
    twilio_request_validator_mock.RequestValidator = MagicMock()
    twilio_rest_mock = types.ModuleType("twilio.rest")
    twilio_rest_mock.Client = MagicMock()

    sys.modules["twilio"] = twilio_mock
    sys.modules["twilio.jwt"] = twilio_jwt_mock
    sys.modules["twilio.jwt.access_token"] = twilio_jwt_access_token_mock
    sys.modules["twilio.jwt.access_token.grants"] = twilio_jwt_access_token_grants_mock
    sys.modules["twilio.request_validator"] = twilio_request_validator_mock
    sys.modules["twilio.rest"] = twilio_rest_mock

from google.api_core.exceptions import Aborted
import database.users as users_db
import database.person_aliases as person_aliases
from models.other import CreatePerson, Person


class FakeDocSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data else None


class FakeQuery:
    def __init__(self, store, filters):
        self.store = store
        self.filters = filters

    def stream(self, transaction=None):
        results = []
        for doc_id, doc in self.store.items():
            match = True
            for field, val in self.filters:
                if doc.get(field) != val:
                    match = False
                    break
            if match:
                results.append(FakeDocSnapshot(doc_id, doc))
        return iter(results)


class FakeDocRef:
    def __init__(self, store, doc_id):
        self.store = store
        self.id = doc_id

    def set(self, data):
        self.store[self.id] = dict(data)

    def get(self, transaction=None):
        return FakeDocSnapshot(self.id, self.store.get(self.id))


class FakePeopleCollection:
    def __init__(self, store):
        self.store = store

    def where(self, filter=None):
        field = filter.field_path if hasattr(filter, 'field_path') else 'name'
        val = filter.value if hasattr(filter, 'value') else ''
        return FakeQuery(self.store, [(field, val)])

    def document(self, doc_id=None):
        if not doc_id:
            doc_id = str(uuid.uuid4())
        return FakeDocRef(self.store, doc_id)

    def stream(self, transaction=None):
        results = [FakeDocSnapshot(doc_id, doc) for doc_id, doc in self.store.items()]
        return iter(results)


class FakeUserDoc:
    def __init__(self, people_store):
        self.people_store = people_store

    def collection(self, name):
        if name == 'people':
            return FakePeopleCollection(self.people_store)
        return MagicMock()


class FakeUsersCollection:
    def __init__(self, people_stores):
        self.people_stores = people_stores

    def document(self, uid):
        if uid not in self.people_stores:
            self.people_stores[uid] = {}
        return FakeUserDoc(self.people_stores[uid])


class FakeTransaction:
    def __init__(self, client):
        self.client = client
        self.sets = []
        self._read_only = False
        self._id = "fake-transaction-id"
        self._max_attempts = 5

    def _clean_up(self):
        pass

    def _begin(self, retry_id=None):
        pass

    def _commit(self):
        pass

    def _rollback(self):
        pass

    def set(self, doc_ref, data):
        self.sets.append((doc_ref.id, data))
        doc_ref.set(data)


class FakeClient:
    def __init__(self):
        self.people_stores = {}
        self.transactions = []

    def collection(self, name):
        if name == 'users':
            return FakeUsersCollection(self.people_stores)
        return MagicMock()

    def transaction(self):
        tx = FakeTransaction(self)
        self.transactions.append(tx)
        return tx


def test_get_or_create_person_creates_when_missing():
    client = FakeClient()
    uid = "test-uid-1"

    person = users_db.get_or_create_person(uid, "Alice", firestore_client=client)

    assert person is not None
    assert person["name"] == "Alice"
    assert person["is_user_created"] is True
    assert "id" in person
    assert client.people_stores[uid][person["id"]]["name"] == "Alice"


def test_get_or_create_person_idempotent_same_name():
    client = FakeClient()
    uid = "test-uid-1"

    person1 = users_db.get_or_create_person(uid, "Alice", firestore_client=client)
    person2 = users_db.get_or_create_person(uid, "Alice", firestore_client=client)

    assert person1["id"] == person2["id"]
    assert len(client.people_stores[uid]) == 1


def test_get_or_create_person_case_insensitive_match():
    client = FakeClient()
    uid = "test-uid-1"

    person1 = users_db.get_or_create_person(uid, "Alice", firestore_client=client)
    person2 = users_db.get_or_create_person(uid, "alice", firestore_client=client)

    assert person1["id"] == person2["id"]
    assert len(client.people_stores[uid]) == 1


def test_get_or_create_person_different_names():
    client = FakeClient()
    uid = "test-uid-1"

    person1 = users_db.get_or_create_person(uid, "Alice", firestore_client=client)
    person2 = users_db.get_or_create_person(uid, "Bob", firestore_client=client)

    assert person1["id"] != person2["id"]
    assert len(client.people_stores[uid]) == 2


def test_get_or_create_person_race_condition_retry():
    """Simulate two concurrent requests where request B experiences contention on attempt 1
    because request A wrote 'Alice' concurrently. On retry, request B must return request A's person."""
    client = FakeClient()
    uid = "test-uid-race"

    attempts = 0

    class ContendedTransaction(FakeTransaction):
        def _commit(self):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                # Concurrent request writes Alice
                concurrent_id = "concurrent-alice-id"
                client.people_stores[uid] = {
                    concurrent_id: {
                        "id": concurrent_id,
                        "name": "Alice",
                        "created_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                        "is_user_created": True,
                    }
                }
                raise Aborted("Contention: another transaction committed first")

    client.transaction = lambda: ContendedTransaction(client)

    person = users_db.get_or_create_person(uid, "Alice", firestore_client=client)
    # Must have recovered and returned the concurrently created person
    assert person["id"] == "concurrent-alice-id"
    assert len(client.people_stores[uid]) == 1


def test_router_get_or_create_person(monkeypatch):
    from routers import users as users_router

    client = FakeClient()
    uid = "router-user-1"

    monkeypatch.setattr(users_db, "get_firestore_client", lambda: client)

    req_data = CreatePerson(name="Charlie")
    res1 = users_router.get_or_create_person(req_data, uid=uid)

    assert res1["name"] == "Charlie"
    assert res1["id"] is not None

    # Call again - must return identical id
    res2 = users_router.get_or_create_person(req_data, uid=uid)
    assert res2["id"] == res1["id"]
    assert len(client.people_stores[uid]) == 1

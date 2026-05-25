import os
import sys
import types
import importlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _prefer_real_module(module_name):
    previous_module = sys.modules.get(module_name)
    sys.modules.pop(module_name, None)
    try:
        importlib.import_module(module_name)
    except Exception:
        if previous_module is not None:
            sys.modules[module_name] = previous_module


if "google" not in sys.modules:
    google_stub = types.ModuleType("google")
    sys.modules["google"] = google_stub
else:
    google_stub = sys.modules["google"]

api_core_stub = types.ModuleType("google.api_core")
api_core_exceptions_stub = types.ModuleType("google.api_core.exceptions")


class NotFound(Exception):
    pass


api_core_exceptions_stub.NotFound = NotFound
sys.modules.setdefault("google.api_core", api_core_stub)
sys.modules.setdefault("google.api_core.exceptions", api_core_exceptions_stub)

cloud_stub = types.ModuleType("google.cloud")
firestore_stub = types.ModuleType("google.cloud.firestore")
firestore_v1_stub = types.ModuleType("google.cloud.firestore_v1")


class Query:
    DESCENDING = "DESCENDING"


class FieldFilter:
    def __init__(self, field_path, op_string, value):
        self.field_path = field_path
        self.op_string = op_string
        self.value = value


class DeleteField:
    def __repr__(self):
        return "DELETE_FIELD"


firestore_stub.Query = Query
firestore_stub.DELETE_FIELD = DeleteField()
firestore_v1_stub.FieldFilter = FieldFilter
cloud_stub.firestore = firestore_stub
google_stub.cloud = cloud_stub
sys.modules.setdefault("google.cloud", cloud_stub)
sys.modules.setdefault("google.cloud.firestore", firestore_stub)
sys.modules.setdefault("google.cloud.firestore_v1", firestore_v1_stub)

audio_file_stub = types.ModuleType("models.audio_file")
audio_file_stub.AudioFile = type("AudioFile", (), {})
sys.modules["models.audio_file"] = audio_file_stub

conversation_enums_stub = types.ModuleType("models.conversation_enums")
conversation_enums_stub.ConversationStatus = type("ConversationStatus", (), {})
conversation_enums_stub.PostProcessingModel = type("PostProcessingModel", (), {"fal_whisperx": "fal_whisperx"})
conversation_enums_stub.PostProcessingStatus = type("PostProcessingStatus", (), {})
sys.modules["models.conversation_enums"] = conversation_enums_stub

conversation_photo_stub = types.ModuleType("models.conversation_photo")
conversation_photo_stub.ConversationPhoto = type("ConversationPhoto", (), {})
sys.modules["models.conversation_photo"] = conversation_photo_stub

transcript_segment_stub = types.ModuleType("models.transcript_segment")
transcript_segment_stub.TranscriptSegment = type("TranscriptSegment", (), {})
sys.modules["models.transcript_segment"] = transcript_segment_stub

for model_module_name in [
    "models.audio_file",
    "models.conversation_enums",
    "models.conversation_photo",
    "models.transcript_segment",
]:
    _prefer_real_module(model_module_name)


class FakeDocumentSnapshot:
    def __init__(self, doc_id, data, reference):
        self.id = doc_id
        self.exists = data is not None
        self._data = deepcopy(data) if data is not None else None
        self.reference = reference

    def to_dict(self):
        return deepcopy(self._data) if self._data is not None else None


class FakePhotosCollection:
    def stream(self):
        return []


class FakeConversationDocument:
    def __init__(self, db, uid, conversation_id):
        self._db = db
        self.uid = uid
        self.id = conversation_id

    def set(self, data):
        self._db.conversations.setdefault(self.uid, {})[self.id] = deepcopy(data)

    def get(self):
        data = self._db.conversations.get(self.uid, {}).get(self.id)
        return FakeDocumentSnapshot(self.id, data, self)

    def update(self, data):
        existing = self._db.conversations.setdefault(self.uid, {}).setdefault(self.id, {})
        for key, value in data.items():
            if value is firestore_stub.DELETE_FIELD or "DELETE_FIELD" in repr(value):
                existing.pop(key, None)
            else:
                existing[key] = value

    def delete(self):
        self._db.conversations.get(self.uid, {}).pop(self.id, None)

    def collection(self, name):
        if name != "photos":
            raise AssertionError(f"Unexpected subcollection {name}")
        return FakePhotosCollection()


class FakeConversationQuery:
    def __init__(self, db, uid, filters=None, order=None, limit_value=None, offset_value=0):
        self._db = db
        self.uid = uid
        self._filters = filters or []
        self._order = order
        self._limit = limit_value
        self._offset = offset_value

    def document(self, conversation_id):
        return FakeConversationDocument(self._db, self.uid, conversation_id)

    def where(self, filter=None):
        return FakeConversationQuery(
            self._db,
            self.uid,
            self._filters + [filter],
            self._order,
            self._limit,
            self._offset,
        )

    def order_by(self, field_path, direction=None):
        return FakeConversationQuery(
            self._db,
            self.uid,
            self._filters,
            (field_path, direction),
            self._limit,
            self._offset,
        )

    def limit(self, limit_value):
        return FakeConversationQuery(self._db, self.uid, self._filters, self._order, limit_value, self._offset)

    def offset(self, offset_value):
        return FakeConversationQuery(self._db, self.uid, self._filters, self._order, self._limit, offset_value)

    def stream(self):
        items = list(self._db.conversations.get(self.uid, {}).items())
        items = [(doc_id, data) for doc_id, data in items if self._matches(data)]

        if self._order:
            field_path, direction = self._order
            reverse = str(direction).upper().endswith("DESCENDING")
            items.sort(key=lambda item: self._field_value(item[1], field_path), reverse=reverse)

        if self._offset:
            items = items[self._offset :]
        if self._limit is not None:
            items = items[: self._limit]

        return [FakeDocumentSnapshot(doc_id, data, self.document(doc_id)) for doc_id, data in items]

    def _matches(self, data):
        for field_filter in self._filters:
            field_path = field_filter.field_path
            op = field_filter.op_string
            expected = field_filter.value
            actual = self._field_value(data, field_path)
            if op == "==" and actual != expected:
                return False
            if op == "!=" and actual == expected:
                return False
            if op == "in" and actual not in expected:
                return False
            if op == ">=" and actual < expected:
                return False
            if op == "<=" and actual > expected:
                return False
            if op == "<" and actual >= expected:
                return False
        return True

    @staticmethod
    def _field_value(data, field_path):
        value = data
        for part in field_path.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value


class FakeUserDocument:
    def __init__(self, db, uid):
        self._db = db
        self.id = uid

    def collection(self, name):
        if name != "conversations":
            raise AssertionError(f"Unexpected collection {name}")
        return FakeConversationQuery(self._db, self.id)


class FakeUsersCollection:
    def __init__(self, db):
        self._db = db

    def document(self, uid):
        return FakeUserDocument(self._db, uid)


class FakeFirestore:
    def __init__(self):
        self.conversations = {}

    def reset(self):
        self.conversations = {}

    def collection(self, name):
        if name != "users":
            raise AssertionError(f"Unexpected collection {name}")
        return FakeUsersCollection(self)

    def get_all(self, doc_refs):
        return [doc_ref.get() for doc_ref in doc_refs]


fake_db = FakeFirestore()

database_client_stub = types.ModuleType("database._client")
database_client_stub.db = fake_db
database_client_stub.document_id_from_seed = MagicMock(return_value="seed-id")
database_stub = sys.modules.setdefault("database", types.ModuleType("database"))
database_stub.__path__ = [str(BACKEND_DIR / "database")]
sys.modules["database._client"] = database_client_stub

redis_db_stub = sys.modules.get("database.redis_db") or types.ModuleType("database.redis_db")
if "r" not in redis_db_stub.__dict__:
    redis_db_stub.r = MagicMock()
redis_db_stub.get_user_data_protection_level = MagicMock(return_value="standard")
redis_db_stub.set_user_data_protection_level = MagicMock()
redis_db_stub.remove_conversation_to_uid = MagicMock()
redis_db_stub.remove_public_conversation = MagicMock()
sys.modules["database.redis_db"] = redis_db_stub

users_db_stub = sys.modules.get("database.users") or types.ModuleType("database.users")
users_db_stub.get_user_profile = MagicMock(return_value={"data_protection_level": "standard"})
sys.modules["database.users"] = users_db_stub

utils_other_stub = types.ModuleType("utils.other")
utils_other_stub.__path__ = [str(BACKEND_DIR / "utils" / "other")]
utils_stub = sys.modules.setdefault("utils", types.ModuleType("utils"))
utils_stub.__path__ = [str(BACKEND_DIR / "utils")]
utils_conversations_stub = sys.modules.setdefault("utils.conversations", types.ModuleType("utils.conversations"))
utils_conversations_stub.__path__ = [str(BACKEND_DIR / "utils" / "conversations")]
sys.modules["utils.other"] = utils_other_stub

hume_stub = sys.modules.get("utils.other.hume") or types.ModuleType("utils.other.hume")
if "HumeJobModelPredictionResponseModel" not in hume_stub.__dict__:
    hume_stub.HumeJobModelPredictionResponseModel = type("HumeJobModelPredictionResponseModel", (), {})
sys.modules["utils.other.hume"] = hume_stub
utils_other_stub.hume = hume_stub

storage_stub = sys.modules.get("utils.other.storage") or types.ModuleType("utils.other.storage")
if "list_audio_chunks" not in storage_stub.__dict__:
    storage_stub.list_audio_chunks = MagicMock(return_value=[])
if "delete_conversation_audio_files" not in storage_stub.__dict__:
    storage_stub.delete_conversation_audio_files = MagicMock()
sys.modules["utils.other.storage"] = storage_stub
utils_other_stub.storage = storage_stub

typesense_stub = types.ModuleType("typesense")
typesense_stub.Client = MagicMock(return_value=MagicMock())
sys.modules.setdefault("typesense", typesense_stub)

existing_conversations_module = sys.modules.get("database.conversations")
if existing_conversations_module and "upsert_conversation" not in existing_conversations_module.__dict__:
    del sys.modules["database.conversations"]

import database.conversations as conversations_db
import utils.conversations.search as search

REAL_CONVERSATION_DB_FUNCS = {
    name: getattr(conversations_db, name)
    for name in [
        "filter_visible_conversation_ids",
        "get_conversations",
        "get_conversations_without_photos",
        "get_trashed_conversations",
        "restore_conversation",
        "set_conversation_visibility",
        "trash_conversation",
        "upsert_conversation",
    ]
}


@pytest.fixture(scope="session", autouse=True)
def initialize_firebase():
    yield


@pytest.fixture(autouse=True)
def reset_fake_db():
    for name, func in REAL_CONVERSATION_DB_FUNCS.items():
        setattr(conversations_db, name, func)
    fake_db.reset()
    redis_db_stub.remove_conversation_to_uid.reset_mock()
    redis_db_stub.remove_public_conversation.reset_mock()
    yield
    fake_db.reset()


def _conversation(conversation_id, created_at=None, discarded=False, title="Conversation"):
    created_at = created_at or datetime.now(timezone.utc)
    return {
        "id": conversation_id,
        "created_at": created_at,
        "started_at": created_at,
        "finished_at": created_at,
        "discarded": discarded,
        "status": "completed",
        "structured": {"title": title, "overview": title},
        "data_protection_level": "standard",
    }


def _upsert(uid, conversation_id, **overrides):
    data = _conversation(conversation_id, **overrides)
    conversations_db.upsert_conversation(uid, data)
    return data


def test_trash_then_restore():
    uid = "uid-trash-restore"
    _upsert(uid, "conv-1")

    trashed = conversations_db.trash_conversation(uid, "conv-1")
    assert trashed["id"] == "conv-1"
    assert isinstance(trashed["trashed_at"], datetime)

    restored = conversations_db.restore_conversation(uid, "conv-1")
    assert restored["id"] == "conv-1"
    assert "trashed_at" not in restored


@pytest.mark.parametrize("visibility", ["shared", "public"])
def test_trash_revokes_shared_access(visibility):
    uid = "uid-trash-shared"
    _upsert(uid, "conv-1")
    conversations_db.set_conversation_visibility(uid, "conv-1", visibility)

    trashed = conversations_db.trash_conversation(uid, "conv-1")

    assert trashed["visibility"] == "private"
    assert isinstance(trashed["trashed_at"], datetime)
    redis_db_stub.remove_conversation_to_uid.assert_called_once_with("conv-1")
    redis_db_stub.remove_public_conversation.assert_called_once_with("conv-1")


def test_get_trashed_conversations():
    uid = "uid-trashed-list"
    _upsert(uid, "older")
    _upsert(uid, "newer")

    conversations_db.trash_conversation(uid, "older")
    conversations_db.trash_conversation(uid, "newer")

    trashed = conversations_db.get_trashed_conversations(uid)
    assert [conversation["id"] for conversation in trashed] == ["newer", "older"]
    assert trashed[0]["trashed_at"] >= trashed[1]["trashed_at"]


def test_default_list_excludes_trashed():
    uid = "uid-list"
    _upsert(uid, "visible")
    _upsert(uid, "trashed")
    conversations_db.trash_conversation(uid, "trashed")

    visible = conversations_db.get_conversations(uid)
    with_trashed = conversations_db.get_conversations(uid, include_trashed=True)

    assert [conversation["id"] for conversation in visible] == ["visible"]
    assert {conversation["id"] for conversation in with_trashed} == {"visible", "trashed"}


def test_default_list_fetches_past_recent_trashed_conversations():
    uid = "uid-list-pagination"
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(4):
        _upsert(uid, f"visible-{index}", created_at=base.replace(day=index + 1))
    for index in range(2):
        _upsert(uid, f"trashed-{index}", created_at=base.replace(day=index + 10))
        conversations_db.trash_conversation(uid, f"trashed-{index}")

    visible = conversations_db.get_conversations(uid, limit=3)
    visible_without_photos = conversations_db.get_conversations_without_photos(uid, limit=3)

    assert [conversation["id"] for conversation in visible] == ["visible-3", "visible-2", "visible-1"]
    assert [conversation["id"] for conversation in visible_without_photos] == [
        "visible-3",
        "visible-2",
        "visible-1",
    ]


def test_trash_404_when_missing():
    assert conversations_db.trash_conversation("uid-missing", "does-not-exist") is None


def test_filter_visible_conversation_ids():
    uid = "uid-visible"
    _upsert(uid, "trashed")
    _upsert(uid, "discarded", discarded=True)
    _upsert(uid, "visible")
    conversations_db.trash_conversation(uid, "trashed")

    visible_ids = conversations_db.filter_visible_conversation_ids(uid, ["trashed", "discarded", "visible"])

    assert visible_ids == ["visible"]


def test_search_excludes_trashed():
    uid = "uid-search"
    now_timestamp = int(datetime.now(timezone.utc).timestamp())
    _upsert(uid, "visible")
    _upsert(uid, "trashed")
    conversations_db.trash_conversation(uid, "trashed")

    search.client = MagicMock()
    search.client.collections.__getitem__.return_value.documents.search.return_value = {
        "hits": [
            {
                "document": {
                    "id": "trashed",
                    "created_at": now_timestamp,
                    "started_at": now_timestamp,
                    "finished_at": now_timestamp,
                    "structured": {"title": "match", "overview": "match"},
                    "userId": uid,
                }
            },
            {
                "document": {
                    "id": "visible",
                    "created_at": now_timestamp,
                    "started_at": now_timestamp,
                    "finished_at": now_timestamp,
                    "structured": {"title": "match", "overview": "match"},
                    "userId": uid,
                }
            },
        ]
    }

    results = search.search_conversations(uid, "match", per_page=10)

    assert [item["id"] for item in results["items"]] == ["visible"]

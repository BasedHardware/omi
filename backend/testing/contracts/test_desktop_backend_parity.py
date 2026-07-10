import base64
import json
import os
import sys
import types
import zlib
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "omi-contract-tests")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8787")

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

storage_stub = types.ModuleType("utils.other.storage")
storage_stub.list_audio_chunks = lambda *_args, **_kwargs: []
sys.modules.setdefault("utils.other.storage", storage_stub)

from database import conversations as conversations_db
from database import memories as memories_db
from models.memories import MemoryCategory, MemoryDB


def fixture(name: str) -> dict:
    return json.loads((REPO_DIR / "contract_tests" / "fixtures" / name).read_text())


class FakeDoc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class FakeQuery:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.filters = []
        self.orders = []
        self.limit_value = None
        self.offset_value = None
        self.collections = []

    def collection(self, name):
        self.collections.append(name)
        return self

    def document(self, _name):
        return self

    def where(self, *, filter):
        self.filters.append(filter)
        return self

    def order_by(self, field_path, direction=None):
        self.orders.append((field_path, direction))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def offset(self, value):
        self.offset_value = value
        return self

    def stream(self):
        return [FakeDoc(doc) for doc in self.docs]


def filter_parts(field_filter):
    return (
        getattr(field_filter, "field_path", getattr(field_filter, "_field_path", None)),
        getattr(field_filter, "op_string", getattr(field_filter, "_op_string", None)),
        getattr(field_filter, "value", getattr(field_filter, "_value", None)),
    )


def test_python_conversation_codec_reads_shared_standard_and_enhanced_fixtures():
    data = fixture("conversations.json")
    standard = conversations_db._prepare_conversation_for_read(
        {
            "data_protection_level": "standard",
            "transcript_segments": base64.b64decode(data["standard_compressed_transcript_b64"]),
            "transcript_segments_compressed": True,
        },
        data["uid"],
    )
    enhanced = conversations_db._prepare_conversation_for_read(
        {
            "data_protection_level": "enhanced",
            "transcript_segments": data["enhanced_encrypted_transcript"],
            "transcript_segments_compressed": True,
        },
        data["uid"],
    )

    assert standard["transcript_segments"] == data["segments"]
    assert enhanced["transcript_segments"] == data["segments"]


def test_python_conversation_codec_writes_normalized_segments():
    data = fixture("conversations.json")
    written = conversations_db._prepare_conversation_for_write(
        {"transcript_segments": data["segments"]},
        data["uid"],
        "standard",
    )

    assert written["transcript_segments_compressed"] is True
    assert zlib.decompress(written["transcript_segments"]).decode("utf-8")
    assert json.loads(zlib.decompress(written["transcript_segments"]).decode("utf-8")) == data["segments"]


def test_python_conversation_query_semantics(monkeypatch):
    data = fixture("conversations.json")["query"]
    fake_db = FakeQuery()
    monkeypatch.setattr(conversations_db, "db", fake_db)

    conversations_db.get_conversations(
        "contract-user-8547",
        limit=data["limit"],
        offset=data["offset"],
        statuses=["completed", "in_progress"],
        starred=True,
        folder_id="folder-1",
        start_date=datetime.fromisoformat(data["start_date"]),
        end_date=datetime.fromisoformat(data["end_date"]),
        date_field=data["date_field"],
    )

    filters = [filter_parts(f) for f in fake_db.filters]
    assert ("discarded", "==", False) in filters
    assert ("status", "in", ["completed", "in_progress"]) in filters
    assert ("starred", "==", True) in filters
    assert ("folder_id", "==", "folder-1") in filters
    assert (data["date_field"], ">=", datetime.fromisoformat(data["start_date"])) in filters
    assert (data["date_field"], "<=", datetime.fromisoformat(data["end_date"])) in filters
    assert fake_db.orders == [(data["date_field"], "DESCENDING")]
    assert fake_db.limit_value == data["limit"]
    assert fake_db.offset_value == data["offset"]


def test_python_conversation_query_defaults_to_created_at(monkeypatch):
    fake_db = FakeQuery()
    monkeypatch.setattr(conversations_db, "db", fake_db)

    conversations_db.get_conversations("contract-user-8547", limit=2, offset=1)

    assert fake_db.orders == [("created_at", "DESCENDING")]
    assert fake_db.limit_value == 2
    assert fake_db.offset_value == 1


def test_python_memory_codec_reads_shared_enhanced_fixture():
    data = fixture("memories.json")
    memory = memories_db._prepare_memory_for_read(
        {
            "data_protection_level": "enhanced",
            "content": data["enhanced_encrypted_content"],
        },
        data["uid"],
    )

    assert memory["content"] == data["enhanced_plain_content"]


def test_python_memory_scoring_matches_shared_fixture():
    data = fixture("memories.json")
    created_at = datetime.fromisoformat(data["created_at"])

    for category, expected in data["scoring"].items():
        if category == "manual_added_interesting":
            continue
        memory = MemoryDB(
            id=f"memory-{category}",
            uid=data["uid"],
            content="contract",
            category=MemoryCategory(category),
            created_at=created_at,
            updated_at=created_at,
        )
        assert MemoryDB.calculate_score(memory) == expected

    manual_memory = MemoryDB(
        id="manual-added",
        uid=data["uid"],
        content="contract",
        category=MemoryCategory.interesting,
        created_at=created_at,
        updated_at=created_at,
        manually_added=True,
    )
    assert MemoryDB.calculate_score(manual_memory) == data["scoring"]["manual_added_interesting"]


def test_python_memory_query_and_filter_semantics():
    data = fixture("memories.json")["query"]
    active = {"id": "active", "content": "active", "user_review": None, "invalid_at": None}
    rejected = {"id": "rejected", "content": "rejected", "user_review": False, "invalid_at": None}
    invalidated = {"id": "invalidated", "content": "invalidated", "user_review": None, "invalid_at": "2026-01-03"}
    fake_db = FakeQuery([active, rejected, invalidated])

    result = memories_db.get_memories(
        "contract-user-8547",
        limit=data["limit"],
        offset=data["offset"],
        categories=data["categories"],
        start_date=datetime.fromisoformat(data["start_date"]),
        end_date=datetime.fromisoformat(data["end_date"]),
        firestore_client=fake_db,
    )

    filters = [filter_parts(f) for f in fake_db.filters]
    assert ("category", "in", data["categories"]) in filters
    assert ("created_at", ">=", datetime.fromisoformat(data["start_date"])) in filters
    assert ("created_at", "<=", datetime.fromisoformat(data["end_date"])) in filters
    assert fake_db.orders == [("scoring", "DESCENDING"), ("created_at", "DESCENDING")]
    assert fake_db.limit_value == data["limit"]
    assert fake_db.offset_value == data["offset"]
    assert [memory["id"] for memory in result] == ["active"]

    fake_db = FakeQuery([active, rejected, invalidated])
    result = memories_db.get_memories("contract-user-8547", include_invalidated=True, firestore_client=fake_db)
    assert [memory["id"] for memory in result] == ["active", "invalidated"]


def test_python_public_memories_treat_missing_visibility_as_public():
    fake_db = FakeQuery(
        [
            {"id": "missing-visibility", "content": "legacy public"},
            {"id": "public", "content": "public", "visibility": "public"},
            {"id": "private", "content": "private", "visibility": "private"},
        ]
    )

    result = memories_db.get_user_public_memories("contract-user-8547", limit=5, offset=2, firestore_client=fake_db)

    assert [memory["id"] for memory in result] == ["missing-visibility", "public"]
    assert fake_db.orders == [("scoring", "DESCENDING"), ("created_at", "DESCENDING")]
    assert fake_db.limit_value == 5
    assert fake_db.offset_value == 2

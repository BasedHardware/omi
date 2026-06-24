import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone

from database.memory_vector_metadata import (
    MEMORY_VECTOR_SCHEMA_VERSION,
    build_archive_memory_vector_filter,
    build_default_memory_vector_filter,
    build_memory_vector_metadata,
    parse_memory_search_vector_hit,
)
from database.v17_vector_metadata import build_v17_memory_vector_metadata
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_memory_search_gateway import SearchDecision, SearchMode
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem


def _item(
    memory_id="mem_abc123",
    *,
    tier=MemoryTier.short_term,
    status=MemoryItemStatus.active,
    processing_state=ProcessingState.processed,
    source_state=SourceState.active,
    sensitive=False,
):
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    return V17MemoryItem(
        memory_id=memory_id,
        uid="uid-canonical",
        version=2,
        tier=tier,
        status=status,
        processing_state=processing_state,
        content=f"content for {memory_id}",
        evidence=[
            MemoryEvidence(
                evidence_id=f"ev_{memory_id}",
                source_id="conv-1",
                source_type="conversation",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=source_state,
        sensitivity_labels=["credential"] if sensitive else [],
        visibility="private",
        user_asserted=False,
        captured_at=now - timedelta(days=1),
        updated_at=now,
        expires_at=now + timedelta(days=30) if tier == MemoryTier.short_term else None,
        ledger_commit_id="commit-ledger",
        ledger_sequence=7,
        item_revision=3,
        source_commit_id="source-commit-1",
        content_hash="hash-1",
        account_generation=11,
    )


class _FakeEmbeddings:
    def embed_query(self, text):
        return [0.1, 0.2, 0.3]

    def embed_documents(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class _RecordingIndex:
    def __init__(self):
        self.upserts = []
        self.queries = []

    def upsert(self, *, vectors, namespace):
        self.upserts.append({"vectors": vectors, "namespace": namespace})
        return {"upserted_count": len(vectors)}

    def query(self, **kwargs):
        self.queries.append(kwargs)
        layer_value = "archive" if "archive" in str(kwargs.get("filter")) else "long_term"
        return {
            "matches": [
                {
                    "id": "mem_abc123",
                    "score": 0.92,
                    "metadata": {
                        "memory_schema_version": MEMORY_VECTOR_SCHEMA_VERSION,
                        "uid": "uid-canonical",
                        "memory_id": "mem_abc123",
                        "memory_layer": layer_value,
                        "status": "active",
                        "source_state": "active",
                        "restricted_sensitivity": False,
                        "projection_commit_id": "commit-ledger",
                        "vector_updated_at": "2026-06-24T12:05:00+00:00",
                    },
                }
            ]
        }


def _load_vector_db_with_stubs():
    pinecone_module = types.ModuleType("pinecone")
    setattr(pinecone_module, "Pinecone", lambda api_key: None)
    sys.modules["pinecone"] = pinecone_module
    clients_module = types.ModuleType("utils.llm.clients")
    setattr(clients_module, "embeddings", _FakeEmbeddings())
    sys.modules["utils.llm.clients"] = clients_module
    projection_repair_module = types.ModuleType("database.projection_repair")
    setattr(projection_repair_module, "projection_metadata_for_fact", lambda memory, source_commit_id=None: {})
    sys.modules["database.projection_repair"] = projection_repair_module
    vector_db_path = os.path.join(os.path.dirname(__file__), "..", "..", "database", "vector_db.py")
    spec = importlib.util.spec_from_file_location("canonical_vector_vector_db", vector_db_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_memory_vector_metadata_uses_neutral_keys_not_v17():
    item = _item(tier=MemoryTier.long_term)
    metadata = build_memory_vector_metadata(
        item,
        projection_commit_id="commit-ledger",
        vector_updated_at=datetime(2026, 6, 24, 12, 5, tzinfo=timezone.utc),
    )

    assert metadata["memory_schema_version"] == MEMORY_VECTOR_SCHEMA_VERSION
    assert metadata["memory_layer"] == "long_term"
    assert "v17_schema_version" not in metadata
    assert "memory_tier" not in metadata
    assert metadata["memory_id"] == "mem_abc123"
    assert metadata["uid"] == "uid-canonical"


def test_neutral_filters_use_memory_layer_and_schema_version():
    default_filter = build_default_memory_vector_filter("uid-canonical")
    archive_filter = build_archive_memory_vector_filter("uid-canonical")

    assert {"memory_layer": {"$in": ["short_term", "long_term"]}} in default_filter["$and"]
    assert {"memory_layer": {"$eq": "archive"}} in archive_filter["$and"]
    for pinecone_filter in (default_filter, archive_filter):
        assert {"memory_schema_version": {"$eq": MEMORY_VECTOR_SCHEMA_VERSION}} in pinecone_filter["$and"]
        assert {"v17_schema_version": {"$eq": 1}} not in pinecone_filter["$and"]


def test_parse_memory_search_vector_hit_rejects_v17_metadata():
    v17_metadata = build_v17_memory_vector_metadata(
        _item(),
        projection_commit_id="commit-ledger",
        vector_updated_at=datetime(2026, 6, 24, 12, 5, tzinfo=timezone.utc),
    )
    parsed = parse_memory_search_vector_hit({"score": 0.9, "metadata": v17_metadata})
    assert parsed.hit is None
    assert parsed.decision == SearchDecision.stale_vector


def test_upsert_canonical_memory_vector_writes_neutral_id_and_metadata(monkeypatch):
    vector_db = _load_vector_db_with_stubs()
    fake_index = _RecordingIndex()
    monkeypatch.setattr(vector_db, "index", fake_index)
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())

    item = _item(memory_id="mem_hash001", tier=MemoryTier.short_term)
    vector_db.upsert_canonical_memory_vector(item)

    assert len(fake_index.upserts) == 1
    payload = fake_index.upserts[0]["vectors"][0]
    assert payload["id"] == "mem_hash001"
    assert not payload["id"].startswith("v17mem:")
    assert payload["metadata"]["memory_schema_version"] == MEMORY_VECTOR_SCHEMA_VERSION
    assert payload["metadata"]["memory_layer"] == "short_term"
    assert fake_index.upserts[0]["namespace"] == "ns2"


def test_query_memory_vector_candidates_matches_neutral_metadata(monkeypatch):
    vector_db = _load_vector_db_with_stubs()
    fake_index = _RecordingIndex()
    monkeypatch.setattr(vector_db, "index", fake_index)
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())

    result = vector_db.query_memory_vector_candidates("uid-canonical", "find content", limit=5)

    assert [hit.memory_id for hit in result.hits] == ["mem_abc123"]
    assert result.rejected_count == 0
    assert {"memory_layer": {"$in": ["short_term", "long_term"]}} in fake_index.queries[0]["filter"]["$and"]
    assert {"memory_schema_version": {"$eq": MEMORY_VECTOR_SCHEMA_VERSION}} in fake_index.queries[0]["filter"]["$and"]


def test_query_memory_vector_candidates_archive_mode(monkeypatch):
    vector_db = _load_vector_db_with_stubs()
    fake_index = _RecordingIndex()
    monkeypatch.setattr(vector_db, "index", fake_index)
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())

    vector_db.query_memory_vector_candidates("uid-canonical", "archive query", mode=SearchMode.archive_explicit)

    assert {"memory_layer": {"$eq": "archive"}} in fake_index.queries[0]["filter"]["$and"]


def test_legacy_upsert_memory_vector_unchanged(monkeypatch):
    vector_db = _load_vector_db_with_stubs()
    fake_index = _RecordingIndex()
    monkeypatch.setattr(vector_db, "index", fake_index)
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())

    vector_db.upsert_memory_vector("legacy-uid", "legacy-mem-1", "hello legacy", "system")

    payload = fake_index.upserts[0]["vectors"][0]
    assert payload["id"] == "legacy-uid-legacy-mem-1"
    assert payload["metadata"]["uid"] == "legacy-uid"
    assert payload["metadata"]["memory_id"] == "legacy-mem-1"
    assert "memory_schema_version" not in payload["metadata"]
    assert "v17_schema_version" not in payload["metadata"]


def test_canonical_write_search_round_trip_short_term_and_long_term(monkeypatch):
    vector_db = _load_vector_db_with_stubs()
    fake_index = _RecordingIndex()
    monkeypatch.setattr(vector_db, "index", fake_index)
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())

    short_item = _item(memory_id="mem_short", tier=MemoryTier.short_term)
    long_item = _item(memory_id="mem_long", tier=MemoryTier.long_term)

    vector_db.upsert_canonical_memory_vector(short_item)
    vector_db.upsert_canonical_memory_vector(long_item)

    layers_written = {u["vectors"][0]["metadata"]["memory_layer"] for u in fake_index.upserts}
    assert layers_written == {"short_term", "long_term"}

    default_result = vector_db.query_memory_vector_candidates("uid-canonical", "content")
    assert default_result.hits


def test_canonical_archive_layer_round_trip(monkeypatch):
    vector_db = _load_vector_db_with_stubs()
    fake_index = _RecordingIndex()
    monkeypatch.setattr(vector_db, "index", fake_index)
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())

    archive_item = _item(memory_id="mem_archive", tier=MemoryTier.archive)
    vector_db.upsert_canonical_memory_vector(archive_item)

    assert fake_index.upserts[0]["vectors"][0]["metadata"]["memory_layer"] == "archive"
    archive_result = vector_db.query_memory_vector_candidates(
        "uid-canonical", "archive", mode=SearchMode.archive_explicit
    )
    assert archive_result.hits[0].memory_id == "mem_abc123"

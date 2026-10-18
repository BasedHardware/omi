"""Hermetic unit tests for defensive memory vector hydration and null-metadata handling.

Verifies:
1. When vector search or metadata parser receives unexpected null, missing, or malformed metadata,
   it fails closed gracefully without unhandled NoneType / KeyError / TypeError crashes.
2. Stale, deleted, and tombstoned memory vectors in vector stores fail closed and are not hydrated.
3. Memory search formatting handles string/None categories and None scores gracefully.
4. FastAPI endpoints (/v1/tools/memories/search, /v1/dev/user/memories/vector/search) do not crash
   with unhandled exceptions when encountering null metadata or stale hydrated records.
5. All external database calls (Pinecone, Firestore, Auth) are strictly mocked.
"""

# pyright: reportUnusedFunction=false, reportPrivateUsage=false
from datetime import datetime, timezone
import types
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database.memory_vector_metadata import (
    ParsedMemoryVectorHit,
    ParsedVectorHit,
    parse_memory_search_vector_hit,
    parse_search_vector_hit,
)
import database.vector_db as vector_db
from models.memory_search_gateway import SearchDecision


@pytest.fixture(autouse=True)
def _isolate_test_environment(monkeypatch):
    import utils.memory.read_resilience as _rr
    from tests.unit.memory_import_isolation import snapshot_sys_modules, restore_sys_modules

    saved = snapshot_sys_modules([
        "utils.retrieval.tool_services.memories",
        "utils.retrieval.tool_services.conversations",
        "routers.tools",
        "routers.developer",
    ])
    yield
    restore_sys_modules(saved)
    monkeypatch.setattr(_rr, "_retry_allowance", _rr.RetryAllowance())


# ===========================================================================
# 1. vector_db.find_similar_memories defensive checks
# ===========================================================================
class TestVectorDbFindSimilarMemoriesDefensive:
    def setup_method(self):
        self.mock_index = MagicMock()
        self.mock_embeddings = MagicMock()
        self.mock_embeddings.embed_query.return_value = [0.1, 0.2, 0.3]

    def test_find_similar_memories_null_metadata_fails_closed(self, monkeypatch):
        """When Pinecone returns a match with metadata=None, it fails closed without AttributeError."""
        monkeypatch.setattr(vector_db, "index", self.mock_index)
        monkeypatch.setattr(vector_db, "embeddings", self.mock_embeddings)

        self.mock_index.query.return_value = {
            "matches": [
                {"id": "vec-1", "score": 0.95, "metadata": None},
                {"id": "vec-2", "score": 0.90, "metadata": {"memory_id": "valid-1", "category": "facts"}},
            ]
        }

        results = vector_db.find_similar_memories("uid-1", "query", threshold=0.8)
        assert len(results) == 1
        assert results[0]["memory_id"] == "valid-1"
        assert results[0]["score"] == 0.90

    def test_find_similar_memories_missing_metadata_key(self, monkeypatch):
        """When match is missing 'metadata' key entirely, it does not raise KeyError."""
        monkeypatch.setattr(vector_db, "index", self.mock_index)
        monkeypatch.setattr(vector_db, "embeddings", self.mock_embeddings)

        self.mock_index.query.return_value = {
            "matches": [
                {"id": "vec-1", "score": 0.95},
                {"id": "vec-2", "score": 0.85, "metadata": {"memory_id": "valid-2"}},
            ]
        }

        results = vector_db.find_similar_memories("uid-1", "query", threshold=0.8)
        assert len(results) == 1
        assert results[0]["memory_id"] == "valid-2"

    def test_find_similar_memories_null_score(self, monkeypatch):
        """When match has score=None, NaN, or Inf, it does not crash on >= threshold comparison and is skipped even at threshold=0.0."""
        monkeypatch.setattr(vector_db, "index", self.mock_index)
        monkeypatch.setattr(vector_db, "embeddings", self.mock_embeddings)

        self.mock_index.query.return_value = {
            "matches": [
                {"id": "vec-1", "score": None, "metadata": {"memory_id": "mem-null-score"}},
                {"id": "vec-nan", "score": float("nan"), "metadata": {"memory_id": "mem-nan-score"}},
                {"id": "vec-inf", "score": float("inf"), "metadata": {"memory_id": "mem-inf-score"}},
                {"id": "vec-2", "score": 0.92, "metadata": {"memory_id": "mem-valid"}},
            ]
        }

        results = vector_db.find_similar_memories("uid-1", "query", threshold=0.8)
        assert len(results) == 1
        assert results[0]["memory_id"] == "mem-valid"

        results_zero = vector_db.find_similar_memories("uid-1", "query", threshold=0.0)
        assert len(results_zero) == 1
        assert results_zero[0]["memory_id"] == "mem-valid"

    def test_find_similar_memories_non_dict_match(self, monkeypatch):
        """When matches contains None, non-dict, failing to_dict, or ScoredVector objects, it handles them gracefully."""
        monkeypatch.setattr(vector_db, "index", self.mock_index)
        monkeypatch.setattr(vector_db, "embeddings", self.mock_embeddings)

        class MockScoredVector:
            def __init__(self, id, score, metadata):
                self.id = id
                self.score = score
                self.metadata = metadata

        class MockBrokenToDict:
            def to_dict(self):
                raise RuntimeError("failing to_dict")

        class MockPineconeResponse:
            def __init__(self, matches):
                self.matches = matches

        self.mock_index.query.return_value = MockPineconeResponse([
            None,
            "not-a-dict",
            MockBrokenToDict(),
            {"id": "vec-ok", "score": 0.95, "metadata": {"memory_id": "mem-ok"}},
            MockScoredVector("vec-obj", 0.91, {"memory_id": "mem-obj"}),
            MockScoredVector("vec-ns", 0.89, types.SimpleNamespace(memory_id="mem-ns")),
        ])

        results = vector_db.find_similar_memories("uid-1", "query", threshold=0.8)
        assert len(results) == 3
        assert {r["memory_id"] for r in results} == {"mem-ok", "mem-obj", "mem-ns"}

    def test_find_similar_memories_skips_tombstoned_and_deleted_vectors(self, monkeypatch):
        """Matches marked as tombstoned, deleted, redacted, or Enum status in vector metadata are skipped."""
        from models.memory_domain import MemoryRecordStatus
        monkeypatch.setattr(vector_db, "index", self.mock_index)
        monkeypatch.setattr(vector_db, "embeddings", self.mock_embeddings)

        self.mock_index.query.return_value = {
            "matches": [
                {"id": "vec-tomb-1", "score": 0.99, "metadata": {"memory_id": "m-tomb-1", "status": "tombstoned"}},
                {"id": "vec-tomb-2", "score": 0.98, "metadata": {"memory_id": "m-tomb-2", "status": "deleted"}},
                {"id": "vec-tomb-3", "score": 0.97, "metadata": {"memory_id": "m-tomb-3", "tombstoned": True}},
                {"id": "vec-tomb-4", "score": 0.96, "metadata": {"memory_id": "m-tomb-4", "deleted": True}},
                {"id": "vec-tomb-5", "score": 0.96, "metadata": {"memory_id": "m-tomb-5", "redaction_status": "tombstoned"}},
                {"id": "vec-tomb-enum", "score": 0.96, "metadata": {"memory_id": "m-tomb-enum", "status": MemoryRecordStatus.TOMBSTONED}},
                {"id": "vec-tomb-upper", "score": 0.96, "metadata": {"memory_id": "m-tomb-upper", "deleted": "TRUE"}},
                {"id": "vec-tomb-num", "score": 0.96, "metadata": {"memory_id": "m-tomb-num", "tombstoned": "1"}},
                {"id": "vec-tomb-redact", "score": 0.96, "metadata": {"memory_id": "m-tomb-redact", "redaction_status": "redacted"}},
                {"id": "vec-tomb-bytes", "score": 0.96, "metadata": {"memory_id": "m-tomb-bytes", "deleted": b"true"}},
                {"id": "vec-tomb-source", "score": 0.96, "metadata": {"memory_id": "m-tomb-source", "source_state": "tombstoned"}},
                {"id": "vec-tomb-purged", "score": 0.96, "metadata": {"memory_id": "m-tomb-purged", "purged": True}},
                {"id": "vec-active", "score": 0.95, "metadata": {"memory_id": "m-active", "status": "active"}},
            ]
        }

        results = vector_db.find_similar_memories("uid-1", "query", threshold=0.8)
        assert len(results) == 1
        assert results[0]["memory_id"] == "m-active"

    def test_find_similar_memories_empty_or_whitespace_memory_id(self, monkeypatch):
        """Matches with empty or missing memory_id fail closed."""
        monkeypatch.setattr(vector_db, "index", self.mock_index)
        monkeypatch.setattr(vector_db, "embeddings", self.mock_embeddings)

        self.mock_index.query.return_value = {
            "matches": [
                {"id": "vec-1", "score": 0.95, "metadata": {"memory_id": ""}},
                {"id": "vec-2", "score": 0.95, "metadata": {"memory_id": "   "}},
                {"id": "vec-3", "score": 0.95, "metadata": {}},
            ]
        }

        results = vector_db.find_similar_memories("uid-1", "query", threshold=0.8)
        assert results == []


# ===========================================================================
# 2. memory_vector_metadata defensive parsing
# ===========================================================================
class TestMemoryVectorMetadataDefensive:
    def test_parse_search_vector_hit_none_or_non_dict(self):
        """None or non-dict match fails closed to stale_vector returning ParsedVectorHit without AttributeError."""
        res_none = parse_search_vector_hit(None)  # type: ignore[arg-type]
        assert isinstance(res_none, ParsedVectorHit)
        assert res_none.decision == SearchDecision.stale_vector
        assert res_none.hit is None

        res_str = parse_search_vector_hit("invalid")  # type: ignore[arg-type]
        assert isinstance(res_str, ParsedVectorHit)
        assert res_str.decision == SearchDecision.stale_vector
        assert res_str.hit is None

    def test_parse_memory_search_vector_hit_none_or_non_dict(self):
        """None or non-dict match fails closed to stale_vector returning ParsedMemoryVectorHit without AttributeError."""
        res_none = parse_memory_search_vector_hit(None)  # type: ignore[arg-type]
        assert isinstance(res_none, ParsedMemoryVectorHit)
        assert res_none.decision == SearchDecision.stale_vector
        assert res_none.hit is None

        metadata_tomb = {
            "memory_schema_version": 1,
            "memory_id": "m1",
            "projection_commit_id": "p1",
            "vector_updated_at": "2026-06-19T12:05:00+00:00",
            "redaction_status": "tombstoned",
        }
        res_tomb = parse_memory_search_vector_hit({"score": 0.9, "metadata": metadata_tomb})
        assert isinstance(res_tomb, ParsedMemoryVectorHit)
        assert res_tomb.decision == SearchDecision.stale_vector
        assert res_tomb.hit is None

    def test_parse_search_vector_hit_tombstone_metadata_fails_closed(self):
        """Vectors carrying tombstone, deletion, redacted markers, or NaN scores fail closed."""
        from models.memory_domain import MemoryRecordStatus
        metadata = {
            "memory_schema_version": 1,
            "memory_id": "m1",
            "projection_commit_id": "p1",
            "vector_updated_at": "2026-06-19T12:05:00+00:00",
            "status": "TOMBSTONED",
        }
        res = parse_search_vector_hit({"score": 0.9, "metadata": metadata})
        assert isinstance(res, ParsedVectorHit)
        assert res.decision == SearchDecision.stale_vector
        assert res.hit is None

        metadata_del = dict(metadata, status="deleted")
        res_del = parse_search_vector_hit({"score": 0.9, "metadata": metadata_del})
        assert isinstance(res_del, ParsedVectorHit)
        assert res_del.decision == SearchDecision.stale_vector
        assert res_del.hit is None

        metadata_flag = dict(metadata, status="active", tombstoned="true")
        res_flag = parse_search_vector_hit({"score": 0.9, "metadata": metadata_flag})
        assert isinstance(res_flag, ParsedVectorHit)
        assert res_flag.decision == SearchDecision.stale_vector
        assert res_flag.hit is None

        metadata_redact = dict(metadata, status="active", redaction_status="soft_deleted")
        res_redact = parse_search_vector_hit({"score": 0.9, "metadata": metadata_redact})
        assert isinstance(res_redact, ParsedVectorHit)
        assert res_redact.decision == SearchDecision.stale_vector
        assert res_redact.hit is None

        metadata_enum = dict(metadata, status=MemoryRecordStatus.TOMBSTONED)
        res_enum = parse_search_vector_hit({"score": 0.9, "metadata": metadata_enum})
        assert isinstance(res_enum, ParsedVectorHit)
        assert res_enum.decision == SearchDecision.stale_vector
        assert res_enum.hit is None

        metadata_redacted_val = dict(metadata, status="active", redaction_status="redacted")
        res_redacted = parse_search_vector_hit({"score": 0.9, "metadata": metadata_redacted_val})
        assert isinstance(res_redacted, ParsedVectorHit)
        assert res_redacted.decision == SearchDecision.stale_vector
        assert res_redacted.hit is None

        # Verify bytes flag and source_state in parse_search_vector_hit
        metadata_bytes = dict(metadata, status="active", deleted=b"true")
        res_bytes = parse_search_vector_hit({"score": 0.9, "metadata": metadata_bytes})
        assert isinstance(res_bytes, ParsedVectorHit)
        assert res_bytes.decision == SearchDecision.stale_vector
        assert res_bytes.hit is None

        metadata_source = dict(metadata, status="active", source_state="tombstoned")
        res_source = parse_search_vector_hit({"score": 0.9, "metadata": metadata_source})
        assert isinstance(res_source, ParsedVectorHit)
        assert res_source.decision == SearchDecision.stale_vector
        assert res_source.hit is None

        metadata_purged = dict(metadata, status="active", purged=True)
        res_purged = parse_search_vector_hit({"score": 0.9, "metadata": metadata_purged})
        assert isinstance(res_purged, ParsedVectorHit)
        assert res_purged.decision == SearchDecision.stale_vector
        assert res_purged.hit is None

        # Verify NaN score in parse_search_vector_hit fails closed to stale_vector
        metadata_active = dict(metadata, status="active")
        res_nan = parse_search_vector_hit({"score": float("nan"), "metadata": metadata_active})
        assert isinstance(res_nan, ParsedVectorHit)
        assert res_nan.decision == SearchDecision.stale_vector
        assert res_nan.hit is None


# ===========================================================================
# 3. _legacy_search_memories defensive hydration
# ===========================================================================
class TestLegacySearchMemoriesDefensive:
    def test_legacy_search_filters_none_and_tombstoned_firestore_docs(self, monkeypatch):
        """When Firestore returns None or tombstoned dicts for stale IDs, fail closed gracefully."""
        from models.memory_domain import MemoryRecordStatus
        from utils.memory.memory_service import _memory_ids_and_scores
        # Verify _memory_ids_and_scores handles None and non-iterable gracefully
        assert _memory_ids_and_scores(None) == ([], {})  # type: ignore[arg-type]
        assert _memory_ids_and_scores("invalid") == ([], {})  # type: ignore[arg-type]

        mock_vdb = MagicMock()
        mock_vdb.find_similar_memories.return_value = [
            {"memory_id": "mem-stale", "score": 0.95},
            {"memory_id": "mem-tombstoned", "score": 0.90},
            {"memory_id": "mem-redacted", "score": 0.88},
            {"memory_id": "mem-enum", "score": 0.87},
            {"memory_id": "mem-upper-del", "score": 0.86},
            {"memory_id": "mem-bytes-del", "score": 0.86},
            {"memory_id": "mem-source-state", "score": 0.86},
            {"memory_id": "mem-purged", "score": 0.86},
            {"memory_id": "mem-active", "score": 0.85},
        ]
        monkeypatch.setattr("utils.memory.memory_service.vector_db", mock_vdb)

        # Mock Firestore get_memories_by_ids returning None for stale, tombstoned dict for tombstoned
        def fake_get_memories_by_ids(uid, ids, **kwargs):
            return [
                None,  # stale ID read miss
                {"id": "mem-tombstoned", "status": "tombstoned", "content": "dead", "is_locked": False},
                {"id": "mem-redacted", "redaction_status": "redacted", "content": "dead", "is_locked": False},
                {"id": "mem-enum", "status": MemoryRecordStatus.TOMBSTONED, "content": "dead", "is_locked": False},
                {"id": "mem-upper-del", "status": "active", "deleted": "TRUE", "content": "dead", "is_locked": False},
                {"id": "mem-bytes-del", "status": "active", "deleted": b"true", "content": "dead", "is_locked": False},
                {"id": "mem-source-state", "status": "active", "source_state": "tombstoned", "content": "dead", "is_locked": False},
                {"id": "mem-purged", "status": "active", "purged": True, "content": "dead", "is_locked": False},
                {
                    "id": "mem-active",
                    "uid": "uid-1",
                    "status": "active",
                    "content": "alive",
                    "is_locked": False,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "category": "interesting",
                },
            ]

        monkeypatch.setattr("utils.memory.memory_service.memories_db.get_memories_by_ids", fake_get_memories_by_ids)

        from utils.memory.memory_service import _legacy_search_memories
        results = _legacy_search_memories("uid-1", "query", limit=5)
        assert len(results) == 1
        assert results[0].memory.id == "mem-active"
        assert results[0].score == 0.85


# ===========================================================================
# 4. tool_services.memories search_memories_text defensive formatting
# ===========================================================================
class TestSearchMemoriesTextDefensive:
    def test_search_memories_text_handles_string_category(self, monkeypatch):
        """String category does not crash with AttributeError: 'str' object has no attribute 'value'."""
        import utils.retrieval.tool_services.memories as tool_memories_svc
        mock_service_cls = MagicMock()
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        from models.memories import MemoryCategory

        match = types.SimpleNamespace(
            memory=types.SimpleNamespace(
                id=None,
                memory_id="m1",
                is_locked=False,
                content="favorite coffee is espresso",
                category="beverages",  # raw string, NOT Enum
                created_at=datetime.now(timezone.utc),
                user_review=True,
                invalid_at=None,
            ),
            score=0.92,
        )
        match_enum = types.SimpleNamespace(
            memory=types.SimpleNamespace(
                id="m1-enum",
                memory_id="m1-enum",
                is_locked=False,
                content="prefers dark chocolate",
                category=MemoryCategory.interesting,  # Enum category
                created_at=datetime.now(timezone.utc),
                user_review=True,
                invalid_at=None,
            ),
            score=0.85,
        )
        mock_service.search.return_value = [match, match_enum]
        monkeypatch.setattr(tool_memories_svc, "MemoryService", mock_service_cls)

        sink: list = []
        output = tool_memories_svc.search_memories_text("uid-1", "coffee", source_sink=sink)
        assert "favorite coffee is espresso" in output
        assert "category: beverages" in output
        assert "relevance: 0.92" in output
        assert "prefers dark chocolate" in output
        assert "category: interesting" in output
        assert len(sink) == 2
        assert sink[0]["source_id"] == "m1"
        assert sink[1]["source_id"] == "m1-enum"

    def test_search_memories_text_handles_none_category_and_none_score(self, monkeypatch):
        """None category, whitespace category, and None or NaN score do not crash formatting."""
        import utils.retrieval.tool_services.memories as tool_memories_svc
        mock_service_cls = MagicMock()
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        match1 = types.SimpleNamespace(
            memory=types.SimpleNamespace(
                id="m2",
                memory_id="m2",
                is_locked=False,
                content="prefers morning workouts",
                category=None,
                created_at=datetime.now(timezone.utc),
                user_review=True,
                invalid_at=None,
            ),
            score=None,
        )
        match2 = types.SimpleNamespace(
            memory=types.SimpleNamespace(
                id="m2-nan",
                memory_id="m2-nan",
                is_locked=False,
                content="enjoys hiking",
                category="   ",  # whitespace category
                created_at=datetime.now(timezone.utc),
                user_review=True,
                invalid_at=None,
            ),
            score=float("nan"),  # NaN score
        )
        mock_service.search.return_value = [match1, match2]
        monkeypatch.setattr(tool_memories_svc, "MemoryService", mock_service_cls)

        output = tool_memories_svc.search_memories_text("uid-1", "workout")
        assert "prefers morning workouts" in output
        assert "enjoys hiking" in output
        assert "relevance: 0.00, category: other" in output

    def test_search_memories_text_handles_none_match_or_memory(self, monkeypatch):
        """Matches that are None or have None memory fail closed gracefully."""
        import utils.retrieval.tool_services.memories as tool_memories_svc
        mock_service_cls = MagicMock()
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        valid_match = types.SimpleNamespace(
            memory=types.SimpleNamespace(
                id="m3",
                memory_id="m3",
                is_locked=False,
                content="plays piano",
                category="music",
                created_at=datetime.now(timezone.utc),
                user_review=True,
                invalid_at=None,
            ),
            score=0.88,
        )
        mock_service.search.return_value = [
            None,
            types.SimpleNamespace(memory=None, score=0.9),
            valid_match,
        ]
        monkeypatch.setattr(tool_memories_svc, "MemoryService", mock_service_cls)

        output = tool_memories_svc.search_memories_text("uid-1", "piano")
        assert "plays piano" in output


# ===========================================================================
# 5. FastAPI Endpoints — No unhandled exceptions crash endpoints
# ===========================================================================
class TestFastApiEndpointDefensive:
    def test_tools_memories_search_endpoint_with_null_and_malformed_vector_data(self, monkeypatch):
        """FastAPI POST /v1/tools/memories/search fails closed with HTTP 200 on null metadata."""
        import routers.tools as tools_router

        app = FastAPI()
        app.include_router(tools_router.router)

        # Robustly override all route dependencies on the app
        for route in app.routes:
            dependant = getattr(route, "dependant", None)
            if dependant is not None:
                for dep in getattr(dependant, "dependencies", []):
                    app.dependency_overrides[dep.call] = lambda: "test-uid"

        # Mock MemoryService to return a match with string category and None score
        mock_service_cls = MagicMock()
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        match = types.SimpleNamespace(
            memory=types.SimpleNamespace(
                id="m-api",
                memory_id="m-api",
                is_locked=False,
                content="Likes black tea",
                category="diet",
                created_at=datetime.now(timezone.utc),
                user_review=True,
                invalid_at=None,
            ),
            score=None,
        )
        mock_service.search.return_value = [match]
        import utils.retrieval.tool_services.memories as tool_memories_svc
        monkeypatch.setattr(tool_memories_svc, "MemoryService", mock_service_cls)

        client = TestClient(app)
        response = client.post("/v1/tools/memories/search", json={"query": "tea"})

        assert response.status_code == 200
        data = response.json()
        assert data["tool_name"] == "search_memories"
        assert data["is_error"] is False
        assert "Likes black tea" in data["result_text"]

    def test_developer_vector_search_endpoint_with_none_score_and_string_category(self, monkeypatch):
        """FastAPI GET /v1/dev/user/memories/vector/search does not crash on None score."""
        import routers.developer as dev_router
        from routers.developer import get_developer_memory_default_memory_read_context
        from utils.memory.product_authorization import ProductAuthorizationContext

        app = FastAPI()
        app.include_router(dev_router.router)

        # Mock developer auth context
        dummy_context = ProductAuthorizationContext(
            uid="dev-user-uid",
            consumer="developer_api",
            surface="vector_search",
            app_id="app-1",
            key_id="key-1",
            scopes=("memories.read",),
        )
        app.dependency_overrides[get_developer_memory_default_memory_read_context] = lambda: dummy_context

        # Mock app_key_grant
        mock_grant = types.SimpleNamespace(allowed=True, status_code=200, reason=None)
        monkeypatch.setattr(dev_router, "authorize_memory_external_default_memory_read", lambda *a, **k: mock_grant)

        # Mock MemoryService
        mock_service_cls = MagicMock()
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        from models.memories import MemoryCategory

        match_none = types.SimpleNamespace(
            memory=types.SimpleNamespace(
                id="mem-dev-1",
                content="Works at Acme Corp",
                category="employment",
            ),
            score=None,  # Previously caused TypeError: type NoneType doesn't define __round__ method
        )
        match_nan = types.SimpleNamespace(
            memory=types.SimpleNamespace(
                id="mem-dev-2",
                content="Likes apples",
                category="   ",  # whitespace category fallback
            ),
            score=float("nan"),  # Previously caused ValueError: Out of range float values are not JSON compliant
        )
        match_enum = types.SimpleNamespace(
            memory=types.SimpleNamespace(
                id=None,
                memory_id="mem-dev-3",
                content="Reads books",
                category=MemoryCategory.interesting,  # Enum category
            ),
            score=0.75,
        )
        mock_service.search.return_value = [match_none, match_nan, match_enum]
        monkeypatch.setattr(dev_router, "MemoryService", mock_service_cls)

        client = TestClient(app)
        response = client.get("/v1/dev/user/memories/vector/search?query=work")

        assert response.status_code == 200
        data = response.json()
        assert data["returned_count"] == 3
        assert data["items"][0]["id"] == "mem-dev-1"
        assert data["items"][0]["relevance_score"] == 0.0
        assert data["items"][1]["id"] == "mem-dev-2"
        assert data["items"][1]["relevance_score"] == 0.0
        assert data["items"][1]["category"] == "other"
        assert data["items"][2]["id"] == "mem-dev-3"
        assert data["items"][2]["category"] == "interesting"
        assert data["items"][2]["relevance_score"] == 0.75


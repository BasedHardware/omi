"""WS-M atom keyword index — Typesense exact-recall for canonical long-term atoms."""

from __future__ import annotations

import os
import sys
import types
import importlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("TYPESENSE_HOST", "localhost")
os.environ.setdefault("TYPESENSE_HOST_PORT", "8108")
os.environ.setdefault("TYPESENSE_API_KEY", "test-key-not-real")

import hashlib
import uuid

_db_client_mod = types.ModuleType("database._client")
_db_client_mod.db = MagicMock()


def _document_id_from_seed(seed: str) -> str:
    seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=seed_hash[:16], version=4))


_db_client_mod.document_id_from_seed = _document_id_from_seed


from tests.unit.memory_import_isolation import (
    ensure_utils_memory_packages_importable,
    install_database_client_stub,
    install_ws_m_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


@dataclass
class _EmptyVectorResult:
    hits: list | None = None
    rejected_count: int = 0

    def __post_init__(self):
        if self.hits is None:
            self.hits = []


def _empty_vector_query(*args, **kwargs):
    return _EmptyVectorResult()


@pytest.fixture(scope="module", autouse=True)
def _ws_m_import_isolation():
    saved = snapshot_sys_modules(["database._client"])
    install_database_client_stub()
    touched = install_ws_m_heavy_import_stubs()
    saved.update(snapshot_sys_modules(touched))
    from utils.memory.memory_service import MemoryService

    globals()["MemoryService"] = MemoryService
    yield
    restore_sys_modules(saved)


ensure_utils_memory_packages_importable(str(BACKEND_DIR))
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.atom_keyword_index import (
    AtomKeywordRebuildReport,
    build_atom_keyword_document,
    is_indexable_long_term_atom,
    keyword_search_memory_ids,
    memories_collection_name,
    merge_memory_search_ids,
    purge_user_atom_keyword_index,
    rebuild_atom_keyword_index,
    sync_atom_keyword_index_for_item,
    upsert_atom_keyword_doc,
)
from utils.memory.canonical_memory_adapter import (
    purge_canonical_derived_user_data,
    retract_conversation_sourced_memories,
    search_canonical_memories,
)
from utils.memory.canonical_vector_sync import sync_canonical_memory_vector
from utils.memory.memory_system import MemorySystem

CANONICAL_UID = "uid-canonical-ws-m"
LEGACY_UID = "uid-legacy-ws-m"
NEEDLE = "CONFIRM-XYZZY-99182"


def _evidence(*, source_id: str = "conv-1") -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id="ev_ws_m",
        source_id=source_id,
        source_type="conversation",
        source_version="v1",
        conversation_id=source_id,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _long_term_item(
    *,
    uid: str = CANONICAL_UID,
    memory_id: str = "mem_lt_needle",
    content: str = f"Hotel reservation {NEEDLE}",
    tier: MemoryTier = MemoryTier.long_term,
    status: MemoryItemStatus = MemoryItemStatus.active,
    processing_state: ProcessingState = ProcessingState.processed,
) -> MemoryItem:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    expires_at = now + timedelta(days=30) if tier == MemoryTier.short_term else None
    ledger_commit_id = "commit_ws_m" if tier == MemoryTier.long_term and status == MemoryItemStatus.active else None
    return MemoryItem(
        memory_id=memory_id,
        uid=uid,
        version=1,
        tier=tier,
        status=status,
        processing_state=processing_state,
        content=content,
        evidence=[_evidence()],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=now,
        updated_at=now,
        expires_at=expires_at,
        ledger_commit_id=ledger_commit_id,
        ledger_sequence=1 if ledger_commit_id else None,
    )


def _data_protection_db(level: str = "enhanced") -> MagicMock:
    user_doc = MagicMock(exists=True, to_dict=lambda: {"data_protection_level": level})
    db_client = MagicMock()
    db_client.document.return_value = MagicMock(get=lambda: user_doc)
    return db_client


def test_user_rejected_long_term_item_is_not_rebuild_or_vector_eligible():
    rejected = _long_term_item().model_copy(update={"promotion": {"user_review": False}})

    assert is_indexable_long_term_atom(rejected) is False
    assert sync_canonical_memory_vector(rejected) is False


@pytest.fixture(autouse=True)
def _canonical_cohort(monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort

    atom_index = importlib.import_module("utils.memory.atom_keyword_index")
    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    memory_system = importlib.import_module("utils.memory.memory_system")
    globals().update(
        {
            "AtomKeywordRebuildReport": atom_index.AtomKeywordRebuildReport,
            "build_atom_keyword_document": atom_index.build_atom_keyword_document,
            "is_indexable_long_term_atom": atom_index.is_indexable_long_term_atom,
            "keyword_search_memory_ids": atom_index.keyword_search_memory_ids,
            "memories_collection_name": atom_index.memories_collection_name,
            "merge_memory_search_ids": atom_index.merge_memory_search_ids,
            "rebuild_atom_keyword_index": atom_index.rebuild_atom_keyword_index,
            "sync_atom_keyword_index_for_item": atom_index.sync_atom_keyword_index_for_item,
            "upsert_atom_keyword_doc": atom_index.upsert_atom_keyword_doc,
            "purge_canonical_derived_user_data": canonical_adapter.purge_canonical_derived_user_data,
            "retract_conversation_sourced_memories": canonical_adapter.retract_conversation_sourced_memories,
            "search_canonical_memories": canonical_adapter.search_canonical_memories,
            "MemorySystem": memory_system.MemorySystem,
        }
    )
    set_canonical_cohort(monkeypatch, CANONICAL_UID)
    cohort = frozenset({CANONICAL_UID})
    for resolve_func in (
        upsert_atom_keyword_doc.__globals__["resolve_memory_system"],
        search_canonical_memories.__globals__["resolve_memory_system"],
    ):
        monkeypatch.setitem(resolve_func.__globals__, "CANONICAL_MEMORY_USERS", cohort)


@pytest.fixture
def mock_typesense():
    docs_store: dict = {}
    typesense_client = MagicMock()

    def _upsert(doc):
        docs_store[doc["id"]] = doc
        return doc

    def _delete_filter(params):
        filter_by = params.get("filter_by", "")
        if f"userId:={CANONICAL_UID}" in filter_by:
            to_delete = [doc_id for doc_id, doc in docs_store.items() if doc.get("userId") == CANONICAL_UID]
            for doc_id in to_delete:
                docs_store.pop(doc_id, None)
            return {"num_deleted": len(to_delete)}
        return {"num_deleted": 0}

    def _search(params):
        query = (params.get("q") or "").lower()
        hits = []
        for doc in docs_store.values():
            haystack = " ".join(
                [
                    doc.get("content", ""),
                    doc.get("entity_terms", ""),
                    doc.get("predicate", ""),
                ]
            ).lower()
            if query and query in haystack:
                hits.append({"document": doc})
        return {"hits": hits}

    documents = MagicMock()
    documents.upsert.side_effect = _upsert
    documents.delete.side_effect = _delete_filter
    documents.__getitem__.side_effect = lambda doc_id: MagicMock(delete=lambda: docs_store.pop(doc_id, None))
    documents.search.side_effect = _search

    memories_collection = MagicMock()
    memories_collection.documents = documents
    memories_collection.retrieve.side_effect = Exception("missing")

    typesense_client.collections.__getitem__.return_value = memories_collection
    typesense_client.collections.create.return_value = None

    with (
        patch("utils.memory.atom_keyword_index._typesense_client", return_value=typesense_client),
        patch("utils.memory.atom_keyword_index.default_db_client", _data_protection_db()),
    ):
        yield typesense_client, docs_store


class TestIndexability:
    def test_long_term_active_processed_is_indexable(self):
        assert is_indexable_long_term_atom(_long_term_item()) is True

    def test_short_term_excluded(self):
        item = _long_term_item(tier=MemoryTier.short_term, memory_id="mem_st")
        assert is_indexable_long_term_atom(item) is False

    def test_archive_excluded(self):
        item = _long_term_item(tier=MemoryTier.archive, memory_id="mem_ar")
        assert is_indexable_long_term_atom(item) is False

    def test_tombstoned_excluded(self):
        item = _long_term_item(status=MemoryItemStatus.tombstoned, memory_id="mem_tomb")
        assert is_indexable_long_term_atom(item) is False


class TestMergeMemorySearchIds:
    def test_keyword_first_deduplicated(self):
        assert merge_memory_search_ids(["k1", "k2"], ["v1", "k2"]) == ["k1", "k2", "v1"]


class TestKeywordSearchAndHybrid:
    def test_canonical_atoms_use_isolated_collection_by_default(self, mock_typesense):
        typesense_client, _ = mock_typesense
        upsert_atom_keyword_doc(_long_term_item())
        assert memories_collection_name() == "canonical_memory_atoms"
        assert typesense_client.collections.__getitem__.call_args_list[-1].args[0] == "canonical_memory_atoms"

    def test_e2ee_user_skips_index_using_explicit_db_client(self, mock_typesense):
        _, docs_store = mock_typesense
        db_client = _data_protection_db("e2ee")

        assert upsert_atom_keyword_doc(_long_term_item(), db_client=db_client) is False
        assert docs_store == {}
        db_client.document.assert_called_with(f"users/{CANONICAL_UID}")

    def test_existing_wrong_typesense_schema_does_not_index(self, mock_typesense):
        typesense_client, docs_store = mock_typesense
        collection = typesense_client.collections.__getitem__.return_value
        collection.retrieve.side_effect = None
        collection.retrieve.return_value = {
            "fields": [
                {"name": "userId"},
                {"name": "transcript_segments"},
            ]
        }

        assert upsert_atom_keyword_doc(_long_term_item()) is False
        assert docs_store == {}
        typesense_client.collections.create.assert_not_called()

    def test_canonical_keyword_search_returns_exact_needle(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        item = _long_term_item()
        upsert_atom_keyword_doc(item)
        assert item.memory_id in docs_store

        ids = keyword_search_memory_ids(CANONICAL_UID, NEEDLE, limit=5)
        assert ids == [item.memory_id]

    def test_legacy_user_indexes_nothing(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        item = _long_term_item(uid=LEGACY_UID, memory_id="mem_legacy")
        from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

        clear_canonical_cohort(monkeypatch)
        assert upsert_atom_keyword_doc(item) is False
        assert docs_store == {}

    def test_literal_needle_found_with_vector_disabled(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        item = _long_term_item()
        upsert_atom_keyword_doc(item)

        def _empty_vector(*args, **kwargs):
            return _EmptyVectorResult()

        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: [item],
        )
        results = search_canonical_memories(
            CANONICAL_UID,
            NEEDLE,
            limit=5,
            vector_query=_empty_vector,
            db_client=_data_protection_db(),
        )
        assert len(results) == 1
        assert results[0]["memory_id"] == item.memory_id
        assert NEEDLE in results[0]["content"]

    def test_search_excludes_superseded_long_term_items(self, mock_typesense, monkeypatch):
        active = _long_term_item(memory_id="mem_active", content=f"Active {NEEDLE}")
        superseded = _long_term_item(
            memory_id="mem_superseded",
            content=f"Superseded {NEEDLE}",
            status=MemoryItemStatus.superseded,
        )

        def _empty_vector(*args, **kwargs):
            return _EmptyVectorResult()

        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.keyword_search_memory_ids",
            lambda uid, query, limit=5, db_client=None: ["mem_active", "mem_superseded"],
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: [active, superseded],
        )
        results = search_canonical_memories(
            CANONICAL_UID,
            NEEDLE,
            limit=5,
            vector_query=_empty_vector,
            db_client=_data_protection_db(),
        )
        assert [row["memory_id"] for row in results] == ["mem_active"]

    def test_memory_service_search_hybrid_for_canonical(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        item = _long_term_item()
        upsert_atom_keyword_doc(item)

        monkeypatch.setattr(
            "utils.memory.memory_service.canonical_read_enabled",
            lambda uid, db_client=None: True,
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: [item],
        )
        monkeypatch.setattr(
            "utils.memory.memory_service.search_canonical_memories",
            lambda uid, query, limit=5, db_client=None, device_scope_request=None: [
                {
                    "memory_id": item.memory_id,
                    "content": item.content,
                    "tier": item.tier.value,
                    "date": item.updated_at.isoformat(),
                    "visibility": item.visibility,
                }
            ],
        )

        def _empty_vector(*args, **kwargs):
            return _EmptyVectorResult()

        with patch("database.vector_db.query_memory_vector_candidates", side_effect=_empty_vector):
            matches = MemoryService().search(CANONICAL_UID, NEEDLE, limit=5)

        assert len(matches) == 1
        assert matches[0].memory.id == item.memory_id

    def test_legacy_memory_service_search_unchanged(self, monkeypatch):
        from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

        clear_canonical_cohort(monkeypatch)
        import utils.memory.memory_service as service_mod

        vector_matches = [{"memory_id": "mem-legacy-1", "score": 0.9}]
        memories = [
            {
                "id": "mem-legacy-1",
                "uid": LEGACY_UID,
                "content": "legacy content",
                "category": "interesting",
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "is_locked": False,
            }
        ]
        keyword_called = {"count": 0}

        def _keyword_guard(*args, **kwargs):
            keyword_called["count"] += 1
            return []

        monkeypatch.setattr(service_mod.memories_db, "get_memories_by_ids", lambda *a, **k: memories)
        monkeypatch.setattr(service_mod.vector_db, "find_similar_memories", lambda *a, **k: vector_matches)
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.keyword_search_memory_ids",
            _keyword_guard,
        )

        matches = MemoryService().search(LEGACY_UID, "legacy", limit=5)
        assert keyword_called["count"] == 0
        assert len(matches) == 1
        assert matches[0].memory.id == "mem-legacy-1"


class TestPurgeAndRebuild:
    def test_strict_keyword_purge_raises_on_typesense_failure(self, monkeypatch):
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index._typesense_client",
            MagicMock(side_effect=RuntimeError("typesense down")),
        )

        with pytest.raises(RuntimeError, match="typesense down"):
            purge_user_atom_keyword_index(CANONICAL_UID, force=True, raise_on_failure=True)

    def test_account_delete_purges_keyword_index(self, mock_typesense, monkeypatch):
        collections, docs_store = mock_typesense
        item = _long_term_item()
        upsert_atom_keyword_doc(item)
        assert item.memory_id in docs_store

        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.resolve_memory_system",
            lambda uid, **_: MemorySystem.CANONICAL,
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: [item],
        )
        monkeypatch.setattr(
            "database.vector_db.delete_pinecone_memory_vectors_by_id",
            lambda ids: len(ids),
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
            lambda **_: types.SimpleNamespace(account_generation=1, head_commit_id="head0", read_error_reason=None),
        )
        delete_kg = MagicMock()
        monkeypatch.setattr("utils.memory.canonical_memory_adapter.kg_db.delete_knowledge_graph", delete_kg)

        db_client = MagicMock()
        result = purge_canonical_derived_user_data(CANONICAL_UID, db_client=db_client)
        assert result["purged"] is True
        assert result["keyword_docs_deleted"] >= 0
        assert item.memory_id not in docs_store
        delete_kg.assert_called_once_with(CANONICAL_UID, db_client=db_client)

    def test_conversation_cascade_deletes_keyword_doc(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        item = _long_term_item(memory_id="mem_cascade")
        item = item.model_copy(update={"evidence": [_evidence(source_id="conv-1")]})
        upsert_atom_keyword_doc(item)
        assert item.memory_id in docs_store

        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: [item],
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
            lambda **_: types.SimpleNamespace(account_generation=1, head_commit_id="head0", read_error_reason=None),
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.atomic_bump_source_generation",
            lambda uid, db_client=None: types.SimpleNamespace(source_generation=2),
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.kg_db.prune_memory_citations_from_kg",
            lambda uid, memory_ids, db_client=None: 0,
        )

        retract_conversation_sourced_memories(CANONICAL_UID, "conv-1", db_client=MagicMock())
        assert item.memory_id not in docs_store

    def test_rebuild_reconstructs_index_count_verified(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        items = [
            _long_term_item(memory_id="mem_a", content="alpha token"),
            _long_term_item(memory_id="mem_b", content="beta token"),
            _long_term_item(memory_id="mem_st", tier=MemoryTier.short_term, content="short"),
        ]
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: items,
        )

        report = rebuild_atom_keyword_index(CANONICAL_UID)
        assert isinstance(report, AtomKeywordRebuildReport)
        assert report.expected_count == 2
        assert report.indexed_count == 2
        assert report.verified is True
        assert set(docs_store.keys()) == {"mem_a", "mem_b"}

    def test_sync_removes_short_term_from_index(self, mock_typesense):
        _, docs_store = mock_typesense
        long_item = _long_term_item(memory_id="mem_lt")
        upsert_atom_keyword_doc(long_item)
        assert "mem_lt" in docs_store

        short_item = _long_term_item(memory_id="mem_lt", tier=MemoryTier.short_term, content="gone")
        sync_atom_keyword_index_for_item(short_item)
        assert "mem_lt" not in docs_store


class TestDocumentShape:
    def test_build_document_uses_long_term_layer(self):
        doc = build_atom_keyword_document(_long_term_item())
        assert doc["layer"] == MemoryTier.long_term.value
        assert doc["status"] == MemoryItemStatus.active.value
        assert doc["schema_version"] == 1
        assert doc["userId"] == CANONICAL_UID
        assert NEEDLE in doc["content"]

    def test_build_document_indexes_flat_subject_predicate_arguments(self):
        item = _long_term_item().model_copy(
            update={
                "subject_entity_id": "ent_user",
                "predicate": "works_at",
                "arguments": {"company": "Omi"},
            }
        )
        doc = build_atom_keyword_document(item)
        assert doc["predicate"] == "works_at"
        assert "ent_user" in doc["entity_terms"]
        assert "Omi" in doc["entity_terms"]

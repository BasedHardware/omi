"""WS-M atom keyword index — Typesense exact-recall for canonical long-term atoms."""

from __future__ import annotations

import os
import re
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


@dataclass(frozen=True)
class _VectorHit:
    memory_id: str
    score: float


@dataclass
class _VectorResult:
    hits: list[_VectorHit]
    rejected_count: int = 0


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
from database.memory_vector_metadata import canonical_memory_provider_id
from models.memory_apply import MemoryControlState
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.atom_keyword_index import (
    AtomKeywordRebuildReport,
    build_atom_keyword_document,
    delete_atom_keyword_doc,
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


def _provider_id(item: MemoryItem) -> str:
    return canonical_memory_provider_id(item.uid, item.memory_id)


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
    canonical_memory_id: str | None = None,
    observed_at: datetime | None = None,
) -> MemoryItem:
    now = observed_at or datetime(2026, 6, 1, tzinfo=timezone.utc)
    expires_at = now + timedelta(days=30) if tier == MemoryTier.short_term else None
    ledger_commit_id = "commit_ws_m" if tier == MemoryTier.long_term and status == MemoryItemStatus.active else None
    return MemoryItem(
        memory_id=memory_id,
        uid=uid,
        canonical_memory_id=canonical_memory_id,
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
def _universal_memory(monkeypatch):
    from tests.unit.universal_memory_test_helpers import configure_universal_memory

    atom_index = importlib.import_module("utils.memory.atom_keyword_index")
    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    memory_system = importlib.import_module("utils.memory.memory_system")
    globals().update(
        {
            "AtomKeywordRebuildReport": atom_index.AtomKeywordRebuildReport,
            "build_atom_keyword_document": atom_index.build_atom_keyword_document,
            "delete_atom_keyword_doc": atom_index.delete_atom_keyword_doc,
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
    configure_universal_memory(monkeypatch, CANONICAL_UID)
    monkeypatch.setattr(atom_index, "ensure_canonical_apply_control_state", lambda *args, **kwargs: None)


@pytest.fixture
def mock_typesense():
    docs_store: dict = {}
    typesense_client = MagicMock()

    def _quoted_filter_values(filter_by):
        values = re.findall(r"`((?:\\.|[^`])*)`", filter_by)
        return [re.sub(r"\\(.)", r"\1", value) for value in values]

    def _upsert(doc):
        docs_store[doc["id"]] = doc
        return doc

    def _delete_filter(params):
        filter_by = params.get("filter_by", "")
        quoted_values = _quoted_filter_values(filter_by)
        user_id = quoted_values[0] if quoted_values else None
        identity_ids = set(quoted_values[1:]) if "id:=[" in filter_by else None
        to_delete = [
            doc_id
            for doc_id, doc in docs_store.items()
            if doc.get("userId") == user_id and (identity_ids is None or doc_id in identity_ids)
        ]
        for doc_id in to_delete:
            docs_store.pop(doc_id, None)
        return {"num_deleted": len(to_delete)}

    def _search(params):
        query = (params.get("q") or "").lower()
        filter_by = params.get("filter_by", "")
        quoted_values = _quoted_filter_values(filter_by)
        user_id = quoted_values[0] if quoted_values else None
        hits = []
        for doc in docs_store.values():
            if user_id is not None and doc.get("userId") != user_id:
                continue
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

    def test_restricted_sensitivity_excluded(self):
        item = _long_term_item(memory_id="mem_financial").model_copy(update={"sensitivity_labels": ["financial"]})
        assert is_indexable_long_term_atom(item) is False

    def test_inactive_source_excluded(self):
        item = _long_term_item(memory_id="mem_missing_source").model_copy(update={"source_state": SourceState.missing})
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

    def test_upsert_fails_closed_when_legacy_identity_cleanup_fails(self, mock_typesense):
        typesense_client, docs_store = mock_typesense
        documents = typesense_client.collections.__getitem__.return_value.documents
        documents.delete.side_effect = RuntimeError("typesense cleanup unavailable")
        documents.upsert.reset_mock()

        assert upsert_atom_keyword_doc(_long_term_item(memory_id="mem-cleanup-failed")) is False

        assert docs_store == {}
        documents.upsert.assert_not_called()

    def test_canonical_keyword_search_returns_exact_needle(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        item = _long_term_item()
        upsert_atom_keyword_doc(item)
        assert _provider_id(item) in docs_store

        ids = keyword_search_memory_ids(CANONICAL_UID, NEEDLE, limit=5)
        assert ids == [item.memory_id]

    def test_same_memory_id_isolated_by_uid_across_typesense_upsert_search_and_delete(
        self,
        mock_typesense,
        monkeypatch,
    ):
        _, docs_store = mock_typesense
        memory_id = "content-derived-shared-id"
        first = _long_term_item(uid="uid-first", memory_id=memory_id)
        second = _long_term_item(uid="uid-second", memory_id=memory_id)
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.user_allows_atom_keyword_index",
            lambda *args, **kwargs: True,
        )

        legacy_doc = build_atom_keyword_document(first)
        docs_store[memory_id] = {**legacy_doc, "id": memory_id}
        assert upsert_atom_keyword_doc(first) is True
        assert memory_id not in docs_store
        assert upsert_atom_keyword_doc(second) is True

        first_provider_id = _provider_id(first)
        second_provider_id = _provider_id(second)
        assert first_provider_id != second_provider_id
        assert set(docs_store) == {first_provider_id, second_provider_id}
        assert docs_store[first_provider_id]["memory_id"] == memory_id
        assert docs_store[second_provider_id]["memory_id"] == memory_id
        assert keyword_search_memory_ids(first.uid, NEEDLE) == [memory_id]
        assert keyword_search_memory_ids(second.uid, NEEDLE) == [memory_id]

        docs_store[memory_id] = {**legacy_doc, "id": memory_id}
        assert delete_atom_keyword_doc(first.uid, memory_id) is True
        assert set(docs_store) == {second_provider_id}
        assert keyword_search_memory_ids(first.uid, NEEDLE) == []
        assert keyword_search_memory_ids(second.uid, NEEDLE) == [memory_id]

    def test_arbitrary_user_uses_the_same_keyword_index(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        item = _long_term_item(uid=LEGACY_UID, memory_id="mem_legacy")
        assert upsert_atom_keyword_doc(item) is True
        assert set(docs_store) == {_provider_id(item)}

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
            "utils.memory.atom_keyword_index.keyword_search_memory_ids",
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

    def test_search_includes_processed_visible_short_term_and_long_term(self, mock_typesense, monkeypatch):
        now = datetime.now(timezone.utc)
        short_term = _long_term_item(
            memory_id="mem_fresh_st",
            content="Fresh coffee preference evidence",
            tier=MemoryTier.short_term,
            observed_at=now,
        )
        long_term = _long_term_item(
            memory_id="mem_stable_lt",
            content="Stable coffee preference",
            observed_at=now - timedelta(days=2),
        )
        pending = _long_term_item(
            memory_id="mem_pending_st",
            content="Pending coffee submission",
            tier=MemoryTier.short_term,
            processing_state=ProcessingState.pending,
            observed_at=now,
        )

        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.keyword_search_memory_ids",
            lambda *args, **kwargs: [],
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: [pending, long_term, short_term],
        )

        def _vector_query(*args, **kwargs):
            return _VectorResult(
                hits=[
                    _VectorHit(memory_id=short_term.memory_id, score=0.95),
                    _VectorHit(memory_id=pending.memory_id, score=0.92),
                    _VectorHit(memory_id=long_term.memory_id, score=0.85),
                ]
            )

        results = search_canonical_memories(
            CANONICAL_UID,
            "coffee",
            limit=5,
            vector_query=_vector_query,
            db_client=_data_protection_db(),
        )

        assert [row["memory_id"] for row in results] == [short_term.memory_id, long_term.memory_id]
        assert [row["tier"] for row in results] == [MemoryTier.short_term.value, MemoryTier.long_term.value]

    def test_search_prefers_long_term_canonical_survivor_and_keeps_unique_short_term(self, mock_typesense, monkeypatch):
        now = datetime.now(timezone.utc)
        survivor = _long_term_item(
            memory_id="mem_canonical_survivor",
            content="Project Beacon uses weekly planning",
            canonical_memory_id="mem_canonical_survivor",
            observed_at=now - timedelta(days=5),
        )
        duplicate_short_term = _long_term_item(
            memory_id="mem_duplicate_st",
            content="Fresh duplicate: Project Beacon uses weekly planning",
            tier=MemoryTier.short_term,
            canonical_memory_id=survivor.memory_id,
            observed_at=now,
        )
        unique_short_term = _long_term_item(
            memory_id="mem_unique_st",
            content="Project Beacon launch review is tomorrow",
            tier=MemoryTier.short_term,
            observed_at=now,
        )

        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.keyword_search_memory_ids",
            lambda *args, **kwargs: [],
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: [unique_short_term, duplicate_short_term, survivor],
        )

        def _vector_query(*args, **kwargs):
            return _VectorResult(
                hits=[
                    _VectorHit(memory_id=duplicate_short_term.memory_id, score=0.99),
                    _VectorHit(memory_id=unique_short_term.memory_id, score=0.9),
                ]
            )

        first = search_canonical_memories(
            CANONICAL_UID,
            "Project Beacon",
            limit=5,
            vector_query=_vector_query,
            db_client=_data_protection_db(),
        )
        second = search_canonical_memories(
            CANONICAL_UID,
            "Project Beacon",
            limit=5,
            vector_query=_vector_query,
            db_client=_data_protection_db(),
        )
        default_list = search_canonical_memories(
            CANONICAL_UID,
            "",
            limit=5,
            vector_query=_vector_query,
            db_client=_data_protection_db(),
        )

        assert [row["memory_id"] for row in first] == [survivor.memory_id, unique_short_term.memory_id]
        assert [row["memory_id"] for row in second] == [survivor.memory_id, unique_short_term.memory_id]
        assert [row["memory_id"] for row in default_list] == [survivor.memory_id, unique_short_term.memory_id]
        assert duplicate_short_term.memory_id not in {row["memory_id"] for row in first}
        assert first[1]["tier"] == MemoryTier.short_term.value

    def test_memory_service_search_hybrid_for_canonical(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        item = _long_term_item()
        upsert_atom_keyword_doc(item)

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


class TestPurgeAndRebuild:
    def test_sync_deletes_existing_keyword_doc_when_user_policy_is_revoked(
        self,
        mock_typesense,
        monkeypatch,
    ):
        _, docs_store = mock_typesense
        item = _long_term_item(memory_id="mem-policy-revoked")
        assert upsert_atom_keyword_doc(item) is True
        assert _provider_id(item) in docs_store
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.user_allows_atom_keyword_index",
            lambda *args, **kwargs: False,
        )

        assert sync_atom_keyword_index_for_item(item) is True
        assert _provider_id(item) not in docs_store

    def test_sync_does_not_acknowledge_revocation_when_exact_delete_fails(self, monkeypatch):
        item = _long_term_item(memory_id="mem-policy-delete-failed")
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.user_allows_atom_keyword_index",
            lambda *args, **kwargs: False,
        )
        delete = MagicMock(return_value=False)
        monkeypatch.setattr("utils.memory.atom_keyword_index.delete_atom_keyword_doc", delete)

        assert sync_atom_keyword_index_for_item(item) is False
        delete.assert_called_once_with(item.uid, item.memory_id, db_client=None)

    def test_delete_attempts_exact_remote_removal_even_after_index_eligibility_is_revoked(
        self,
        mock_typesense,
        monkeypatch,
    ):
        typesense_client, _ = mock_typesense
        documents = typesense_client.collections.__getitem__.return_value.documents
        documents.delete.reset_mock()
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.user_allows_atom_keyword_index",
            lambda *args, **kwargs: False,
        )

        assert delete_atom_keyword_doc(CANONICAL_UID, "mem-previously-indexed") is True
        documents.delete.assert_called_once()
        delete_filter = documents.delete.call_args.args[0]["filter_by"]
        assert f"`{CANONICAL_UID}`" in delete_filter
        assert "`mem-previously-indexed`" in delete_filter
        assert f"`{canonical_memory_provider_id(CANONICAL_UID, 'mem-previously-indexed')}`" in delete_filter

    def test_delete_missing_keyword_doc_is_idempotent_success(self, mock_typesense):
        typesense_client, _ = mock_typesense
        documents = typesense_client.collections.__getitem__.return_value.documents
        documents.delete.reset_mock()

        assert delete_atom_keyword_doc(CANONICAL_UID, "mem-already-absent") is True
        documents.delete.assert_called_once()

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
        assert _provider_id(item) in docs_store
        legacy_doc = build_atom_keyword_document(item)
        docs_store[item.memory_id] = {**legacy_doc, "id": item.memory_id}
        other_user = _long_term_item(uid="uid-other", memory_id=item.memory_id)
        other_doc = build_atom_keyword_document(other_user)
        docs_store[other_doc["id"]] = other_doc

        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: [item],
        )
        monkeypatch.setattr(
            "database.vector_db.delete_canonical_memory_vectors",
            lambda uid, memory_id=None: True,
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
            lambda **_: types.SimpleNamespace(account_generation=1, head_commit_id="head0", read_error_reason=None),
        )
        delete_kg = MagicMock()
        monkeypatch.setattr("utils.memory.canonical_memory_adapter.kg_db.delete_knowledge_graph", delete_kg)
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.read_account_deletion_projection_fence",
            lambda *args, **kwargs: types.SimpleNamespace(blocks_projection_writes=True),
        )

        db_client = MagicMock()
        db_client.collection.return_value.where.return_value.limit.return_value.stream.return_value = []
        result = purge_canonical_derived_user_data(CANONICAL_UID, db_client=db_client)
        assert result["purged"] is True
        assert result["keyword_docs_deleted"] >= 0
        assert set(docs_store) == {other_doc["id"]}
        delete_kg.assert_called_once_with(CANONICAL_UID, db_client=db_client)

    def test_conversation_cascade_deletes_keyword_doc(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        item = _long_term_item(memory_id="mem_cascade")
        item = item.model_copy(update={"evidence": [_evidence(source_id="conv-1")]})
        upsert_atom_keyword_doc(item)
        assert _provider_id(item) in docs_store
        control = MemoryControlState(
            uid=CANONICAL_UID,
            head_commit_id="head0",
            account_generation=1,
            source_generation=1,
        )
        committed_control = control.model_copy(
            update={
                "head_commit_id": "head1",
                "source_generation": 2,
                "commit_sequence": 1,
            }
        )

        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items_for_source",
            lambda uid, source_id, db_client=None: [item],
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.fetch_authoritative_superseded_memory_items_for_targets",
            lambda uid, target_memory_ids, db_client=None: [],
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter._read_replacement_control",
            lambda uid, db_client=None: control,
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.replace_conversation_source_firestore",
            lambda **_: types.SimpleNamespace(
                control_state=committed_control,
                retracted_memory_ids=[item.memory_id],
                committed_memory_ids=[],
                reactivated_memory_ids=[],
                tombstoned_evidence_ids=[item.evidence[0].evidence_id],
            ),
        )
        monkeypatch.setattr(
            "utils.memory.canonical_memory_adapter.kg_db.prune_memory_citations_from_kg",
            lambda uid, memory_ids, db_client=None: 0,
        )

        retract_conversation_sourced_memories(CANONICAL_UID, "conv-1", db_client=MagicMock())
        assert _provider_id(item) not in docs_store

    def test_rebuild_reconstructs_index_count_verified(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        items = [
            _long_term_item(memory_id="mem_a", content="alpha token"),
            _long_term_item(memory_id="mem_b", content="beta token"),
            _long_term_item(memory_id="mem_st", tier=MemoryTier.short_term, content="short"),
        ]
        legacy_doc = build_atom_keyword_document(items[0])
        docs_store[items[0].memory_id] = {**legacy_doc, "id": items[0].memory_id}
        other_user = _long_term_item(uid="uid-other", memory_id="mem_other", content="other")
        other_doc = build_atom_keyword_document(other_user)
        docs_store[other_doc["id"]] = other_doc
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: items,
        )

        report = rebuild_atom_keyword_index(CANONICAL_UID)
        assert isinstance(report, AtomKeywordRebuildReport)
        assert report.expected_count == 2
        assert report.indexed_count == 2
        assert report.verified is True
        assert set(docs_store) == {
            *(_provider_id(item) for item in items[:2]),
            other_doc["id"],
        }

    def test_rebuild_never_sends_restricted_or_inactive_source_content(self, mock_typesense, monkeypatch):
        _, docs_store = mock_typesense
        safe = _long_term_item(memory_id="mem_safe", content="safe token")
        restricted = _long_term_item(memory_id="mem_restricted", content="Bank routing number 012345678").model_copy(
            update={"sensitivity_labels": ["financial"]}
        )
        missing_source = _long_term_item(
            memory_id="mem_missing_source",
            content="Provider must not retain missing-source text",
        ).model_copy(update={"source_state": SourceState.missing})
        assert upsert_atom_keyword_doc(restricted.model_copy(update={"sensitivity_labels": []}))
        assert _provider_id(restricted) in docs_store
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.fetch_authoritative_product_memory_items",
            lambda uid, db_client=None: [restricted, missing_source, safe],
        )

        report = rebuild_atom_keyword_index(CANONICAL_UID)

        assert report.expected_count == 1
        assert report.indexed_count == 1
        assert report.verified is True
        assert set(docs_store) == {_provider_id(safe)}

    def test_rebuild_fails_closed_when_provider_purge_fails(self, monkeypatch):
        purge = MagicMock(side_effect=RuntimeError("typesense unavailable"))
        fetch = MagicMock()
        upsert = MagicMock()
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.user_allows_atom_keyword_index",
            lambda *args, **kwargs: True,
        )
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.purge_user_atom_keyword_index",
            purge,
        )
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.fetch_authoritative_product_memory_items",
            fetch,
        )
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.upsert_atom_keyword_doc",
            upsert,
        )

        report = rebuild_atom_keyword_index(CANONICAL_UID)

        assert report.verified is False
        assert report.failure_reason == "purge_failed"
        purge.assert_called_once()
        purge_args, purge_kwargs = purge.call_args
        assert purge_args == (CANONICAL_UID,)
        assert purge_kwargs["force"] is True
        assert purge_kwargs["raise_on_failure"] is True
        fetch.assert_not_called()
        upsert.assert_not_called()

    def test_rebuild_purges_prior_docs_after_user_becomes_ineligible(
        self,
        mock_typesense,
        monkeypatch,
    ):
        _, docs_store = mock_typesense
        prior = _long_term_item(memory_id="mem_prior")
        assert upsert_atom_keyword_doc(prior)
        assert _provider_id(prior) in docs_store
        monkeypatch.setattr(
            "utils.memory.atom_keyword_index.user_allows_atom_keyword_index",
            lambda *args, **kwargs: False,
        )

        report = rebuild_atom_keyword_index(CANONICAL_UID)

        assert report.skipped_reason == "not_indexable_user"
        assert report.verified is True
        assert docs_store == {}

    def test_sync_removes_short_term_from_index(self, mock_typesense):
        _, docs_store = mock_typesense
        long_item = _long_term_item(memory_id="mem_lt")
        upsert_atom_keyword_doc(long_item)
        assert _provider_id(long_item) in docs_store

        short_item = _long_term_item(memory_id="mem_lt", tier=MemoryTier.short_term, content="gone")
        sync_atom_keyword_index_for_item(short_item)
        assert _provider_id(long_item) not in docs_store


class TestDocumentShape:
    def test_build_document_uses_long_term_layer(self):
        doc = build_atom_keyword_document(_long_term_item())
        assert doc["layer"] == MemoryTier.long_term.value
        assert doc["status"] == MemoryItemStatus.active.value
        assert doc["schema_version"] == 1
        assert doc["userId"] == CANONICAL_UID
        assert doc["id"] == canonical_memory_provider_id(CANONICAL_UID, doc["memory_id"])
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

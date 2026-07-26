import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort
from tests.unit.memory_import_isolation import (
    WS_I_HEAVY_STUB_MODULE_NAMES,
    restore_sys_modules,
    snapshot_sys_modules,
)

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_VECTOR_DB_STUB_MODULE_NAMES = (
    "pinecone",
    "utils.llm.clients",
    "database.projection_repair",
    "database.vector_db",
    "canonical_vector_vector_db",
)

_CANONICAL_VECTOR_TEST_STUB_MODULE_NAMES = tuple(
    dict.fromkeys([*_VECTOR_DB_STUB_MODULE_NAMES, *WS_I_HEAVY_STUB_MODULE_NAMES])
)


@pytest.fixture(autouse=True)
def _vector_db_stub_isolation():
    saved = snapshot_sys_modules(_CANONICAL_VECTOR_TEST_STUB_MODULE_NAMES)
    yield
    restore_sys_modules(saved)


from database.memory_vector_metadata import (
    MEMORY_VECTOR_SCHEMA_VERSION,
    build_archive_memory_vector_filter,
    build_default_memory_vector_filter,
    build_memory_vector_metadata,
    parse_memory_search_vector_hit,
)
from database.memory_vector_metadata import build_memory_vector_metadata
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_search_gateway import SearchDecision, SearchMode, SearchVectorHit, hydrate_and_filter_vector_hits
from models.product_memory import MemoryAccessPolicy, MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.canonical_kg_promotion import CanonicalKgPromotionResult

_FIXTURE_NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


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
    return MemoryItem(
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


def _metadata_matches_clause(metadata, clause):
    for field, condition in clause.items():
        value = metadata.get(field)
        if "$eq" in condition:
            if value != condition["$eq"]:
                return False
        elif "$in" in condition:
            if value not in condition["$in"]:
                return False
        else:
            return False
    return True


def _metadata_matches_filter(metadata, pinecone_filter):
    and_clauses = pinecone_filter.get("$and") or []
    return all(_metadata_matches_clause(metadata, clause) for clause in and_clauses)


class _RecordingIndex:
    def __init__(self):
        self.upserts = []
        self.queries = []
        self._vectors = {}

    def upsert(self, *, vectors, namespace):
        self.upserts.append({"vectors": vectors, "namespace": namespace})
        for vector in vectors:
            self._vectors[vector["id"]] = {
                "id": vector["id"],
                "values": vector.get("values"),
                "metadata": dict(vector.get("metadata") or {}),
            }
        return {"upserted_count": len(vectors)}

    def query(self, **kwargs):
        self.queries.append(kwargs)
        pinecone_filter = kwargs.get("filter") or {}
        top_k = kwargs.get("top_k", 10)
        matches = []
        for vector_id, stored in self._vectors.items():
            metadata = stored["metadata"]
            if _metadata_matches_filter(metadata, pinecone_filter):
                matches.append(
                    {
                        "id": vector_id,
                        "score": 0.92,
                        "metadata": metadata,
                    }
                )
        matches.sort(key=lambda match: match["id"])
        return {"matches": matches[:top_k]}


class _FailingIndex:
    def upsert(self, **kwargs):
        raise RuntimeError("pinecone unavailable")


def _load_vector_db_with_stubs():
    pinecone_module = types.ModuleType("pinecone")
    setattr(pinecone_module, "Pinecone", lambda api_key: None)
    sys.modules.setdefault("pinecone", pinecone_module)
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
    # dataclasses with postponed annotations inspect sys.modules[__module__]
    # while the class body is processed, so register the synthetic module
    # before executing it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _install_recording_vector_db(monkeypatch):
    vector_db = _load_vector_db_with_stubs()
    fake_index = _RecordingIndex()
    monkeypatch.setattr(vector_db, "index", fake_index)
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())
    sys.modules["database.vector_db"] = vector_db
    return vector_db, fake_index


def test_build_memory_vector_metadata_uses_neutral_keys_not_memory():
    item = _item(tier=MemoryTier.long_term)
    metadata = build_memory_vector_metadata(
        item,
        projection_commit_id="commit-ledger",
        vector_updated_at=datetime(2026, 6, 24, 12, 5, tzinfo=timezone.utc),
    )

    assert metadata["memory_schema_version"] == MEMORY_VECTOR_SCHEMA_VERSION
    assert metadata["memory_layer"] == "long_term"
    assert "memory" not in metadata
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
        assert not any("memory_tier" in clause for clause in pinecone_filter["$and"])


def test_parse_memory_search_vector_hit_rejects_legacy_memory_tier_metadata():
    legacy_metadata = {
        "uid": "uid-canonical",
        "memory_id": "mem_abc123",
        "memory_tier": "short_term",
        "projection_commit_id": "commit-ledger",
        "vector_updated_at": datetime(2026, 6, 24, 12, 5, tzinfo=timezone.utc).isoformat(),
    }
    parsed = parse_memory_search_vector_hit({"score": 0.9, "metadata": legacy_metadata})
    assert parsed.hit is None
    assert parsed.decision == SearchDecision.stale_vector


def test_upsert_canonical_memory_vector_writes_neutral_id_and_metadata(monkeypatch):
    vector_db, fake_index = _install_recording_vector_db(monkeypatch)

    item = _item(memory_id="mem_hash001", tier=MemoryTier.short_term)
    vector_db.upsert_canonical_memory_vector(item)

    assert len(fake_index.upserts) == 1
    payload = fake_index.upserts[0]["vectors"][0]
    assert payload["id"] == "mem_hash001"
    assert not payload["id"].startswith("memvec:")
    assert payload["metadata"]["memory_schema_version"] == MEMORY_VECTOR_SCHEMA_VERSION
    assert payload["metadata"]["memory_layer"] == "short_term"
    assert fake_index.upserts[0]["namespace"] == "ns2"


def test_upsert_canonical_memory_vector_strips_null_optional_metadata(monkeypatch):
    vector_db, fake_index = _install_recording_vector_db(monkeypatch)

    item = _item(memory_id="mem_hash001", tier=MemoryTier.short_term).model_copy(
        update={"source_commit_id": None, "content_hash": None}
    )
    vector_db.upsert_canonical_memory_vector(item)

    metadata = fake_index.upserts[0]["vectors"][0]["metadata"]
    assert "source_commit_id" not in metadata
    assert "content_hash" not in metadata
    assert metadata["projection_commit_id"] == "commit-ledger"


def test_hydration_allows_missing_vector_source_freshness_when_authoritative_item_is_null():
    item = _item(memory_id="mem_null_freshness", tier=MemoryTier.short_term).model_copy(
        update={"source_commit_id": None, "content_hash": None}
    )
    hit = SearchVectorHit(
        vector_id="mem_null_freshness",
        memory_id=item.memory_id,
        score=0.9,
        projection_commit_id="commit-ledger",
        vector_updated_at=datetime(2026, 6, 24, 12, 5, tzinfo=timezone.utc),
        uid=item.uid,
        account_generation=item.account_generation,
        item_revision=item.item_revision,
    )

    result = hydrate_and_filter_vector_hits(
        hits=[hit],
        authoritative_items={item.memory_id: item},
        policy=MemoryAccessPolicy.for_omi_chat(),
        mode=SearchMode.default,
        required_projection_commit_id="commit-ledger",
        required_account_generation=item.account_generation,
        now=_FIXTURE_NOW,
    )

    assert result.decisions[item.memory_id] == SearchDecision.allowed
    assert [search_result.item.memory_id for search_result in result.results] == [item.memory_id]
    assert result.repair_purge_candidates == []


def test_hydration_rejects_missing_vector_source_freshness_when_authoritative_item_has_values():
    item = _item(memory_id="mem_required_freshness", tier=MemoryTier.short_term)
    hit = SearchVectorHit(
        vector_id="mem_required_freshness",
        memory_id=item.memory_id,
        score=0.9,
        projection_commit_id="commit-ledger",
        vector_updated_at=datetime(2026, 6, 24, 12, 5, tzinfo=timezone.utc),
        uid=item.uid,
        account_generation=item.account_generation,
        item_revision=item.item_revision,
    )

    result = hydrate_and_filter_vector_hits(
        hits=[hit],
        authoritative_items={item.memory_id: item},
        policy=MemoryAccessPolicy.for_omi_chat(),
        mode=SearchMode.default,
        required_projection_commit_id="commit-ledger",
        required_account_generation=item.account_generation,
        now=_FIXTURE_NOW,
    )

    assert result.decisions[item.memory_id] == SearchDecision.stale_vector
    assert result.results == []
    assert result.repair_purge_candidates[0]["reason"] == "missing_vector_freshness_metadata"


def test_query_memory_vector_candidates_matches_neutral_metadata(monkeypatch):
    vector_db, fake_index = _install_recording_vector_db(monkeypatch)

    vector_db.upsert_canonical_memory_vector(_item(memory_id="mem_abc123", tier=MemoryTier.long_term))
    result = vector_db.query_memory_vector_candidates("uid-canonical", "find content", limit=5)

    assert [hit.memory_id for hit in result.hits] == ["mem_abc123"]
    assert result.rejected_count == 0
    assert {"memory_layer": {"$in": ["short_term", "long_term"]}} in fake_index.queries[0]["filter"]["$and"]
    assert {"memory_schema_version": {"$eq": MEMORY_VECTOR_SCHEMA_VERSION}} in fake_index.queries[0]["filter"]["$and"]


def test_query_memory_vector_candidates_archive_mode(monkeypatch):
    vector_db, fake_index = _install_recording_vector_db(monkeypatch)

    vector_db.query_memory_vector_candidates("uid-canonical", "archive query", mode=SearchMode.archive_explicit)

    assert {"memory_layer": {"$eq": "archive"}} in fake_index.queries[0]["filter"]["$and"]


def test_legacy_upsert_memory_vector_unchanged(monkeypatch):
    vector_db, fake_index = _install_recording_vector_db(monkeypatch)

    vector_db.upsert_memory_vector("legacy-uid", "legacy-mem-1", "hello legacy", "system")

    payload = fake_index.upserts[0]["vectors"][0]
    assert payload["id"] == "legacy-uid-legacy-mem-1"
    assert payload["metadata"]["uid"] == "legacy-uid"
    assert payload["metadata"]["memory_id"] == "legacy-mem-1"
    assert "memory_schema_version" not in payload["metadata"]
    assert "memory_schema_version" not in payload["metadata"]


def test_canonical_write_search_round_trip_short_term_and_long_term(monkeypatch):
    vector_db, fake_index = _install_recording_vector_db(monkeypatch)

    short_item = _item(memory_id="mem_short", tier=MemoryTier.short_term)
    long_item = _item(memory_id="mem_long", tier=MemoryTier.long_term)
    archive_item = _item(memory_id="mem_archive", tier=MemoryTier.archive)

    vector_db.upsert_canonical_memory_vector(short_item)
    vector_db.upsert_canonical_memory_vector(long_item)
    vector_db.upsert_canonical_memory_vector(archive_item)

    layers_written = {upsert["vectors"][0]["metadata"]["memory_layer"] for upsert in fake_index.upserts}
    assert layers_written == {"short_term", "long_term", "archive"}

    default_result = vector_db.query_memory_vector_candidates("uid-canonical", "content")
    default_ids = {hit.memory_id for hit in default_result.hits}
    assert default_ids == {"mem_short", "mem_long"}
    assert "mem_archive" not in default_ids


def test_canonical_archive_layer_round_trip(monkeypatch):
    vector_db, fake_index = _install_recording_vector_db(monkeypatch)

    short_item = _item(memory_id="mem_short", tier=MemoryTier.short_term)
    archive_item = _item(memory_id="mem_archive", tier=MemoryTier.archive)
    vector_db.upsert_canonical_memory_vector(short_item)
    vector_db.upsert_canonical_memory_vector(archive_item)

    archive_result = vector_db.query_memory_vector_candidates(
        "uid-canonical", "archive", mode=SearchMode.archive_explicit
    )
    archive_ids = {hit.memory_id for hit in archive_result.hits}
    assert archive_ids == {"mem_archive"}
    assert fake_index.upserts[1]["vectors"][0]["metadata"]["memory_layer"] == "archive"


def test_sync_canonical_memory_vector_swallows_pinecone_failure(monkeypatch):
    vector_db = _load_vector_db_with_stubs()
    monkeypatch.setattr(vector_db, "index", _FailingIndex())
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())
    sys.modules["database.vector_db"] = vector_db

    from utils.memory.canonical_vector_sync import sync_canonical_memory_vector

    hard_failures = []
    synced = sync_canonical_memory_vector(_item(), on_hard_failure=lambda: hard_failures.append(1))
    assert synced is False
    assert hard_failures == [1]


def test_write_path_syncs_vector_on_idempotent_skip(monkeypatch):
    from tests.unit.test_ws_i_write_convergence import (
        _FakeDb,
        _fresh_short_term_item,
        _sample_memory_payload,
        _stored_item,
        _trusted_account_generation,
        extraction_memory_id,
        write_canonical_extraction_memory,
    )

    vector_db, fake_index = _install_recording_vector_db(monkeypatch)
    uid = "uid-canonical"
    conversation_id = "conv-1"
    content = "User enjoys hiking"
    memory_id = extraction_memory_id(uid=uid, source_id=conversation_id, content=content)
    committed_item = _fresh_short_term_item(
        uid=uid,
        memory_id=memory_id,
        conversation_id=conversation_id,
        content=content,
    )
    db = _FakeDb(
        {
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
                uid=uid, head_commit_id="head0", account_generation=1, source_generation=1
            ).model_dump(mode="json"),
            f"users/{uid}/memory_evidence/ev_ws_i_1": MemoryEvidence(
                evidence_id="ev_ws_i_1",
                source_type="conversation",
                source_id=conversation_id,
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            ).model_dump(mode="json"),
            f"users/{uid}/memory_items/{memory_id}": _stored_item(committed_item),
        }
    )
    apply_result = SimpleNamespace(
        status=ApplyStatus.idempotent_skip,
        memory_items=[],
        operation=SimpleNamespace(committed_memory_item_ids=[memory_id]),
        reason=None,
        control_state=MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1),
    )

    with patch(
        "utils.memory.canonical_memory_adapter.apply_long_term_patch_firestore",
        return_value=apply_result,
    ), patch(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        return_value=_trusted_account_generation(),
    ), patch(
        "utils.memory.canonical_memory_adapter.sync_atom_keyword_index_for_item",
        return_value=None,
    ):
        returned_id = write_canonical_extraction_memory(
            uid, _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content), db_client=db
        )

    assert returned_id == memory_id
    assert len(fake_index.upserts) == 1
    assert fake_index.upserts[0]["vectors"][0]["id"] == memory_id
    assert fake_index.upserts[0]["vectors"][0]["metadata"]["memory_layer"] == "short_term"


def test_backfill_path_syncs_vector_on_idempotent_skip(monkeypatch):
    from tests.unit.test_ws_i_write_convergence import _install_heavy_import_stubs

    _install_heavy_import_stubs()
    vector_db, fake_index = _install_recording_vector_db(monkeypatch)
    from utils.memory.legacy_backfill import _apply_one_legacy_row

    uid = "uid-canonical"
    legacy_id = "leg-1"
    content = "legacy memory content"
    canonical_memory_id = "mem_backfill_test"
    committed_item = _item(memory_id=canonical_memory_id, tier=MemoryTier.long_term)
    committed_item = committed_item.model_copy(update={"content": content, "uid": uid})

    class _BackfillDb:
        def __init__(self):
            self._get_calls_by_path = {}

        def document(self, path):
            return _BackfillDocRef(self, path)

    class _BackfillDocRef:
        def __init__(self, db, path):
            self._db = db
            self.path = path

        def get(self):
            calls = self._db._get_calls_by_path.get(self.path, 0) + 1
            self._db._get_calls_by_path[self.path] = calls
            if self.path.endswith(canonical_memory_id) and calls == 1:
                return SimpleNamespace(exists=False, to_dict=lambda: {})
            if self.path.endswith(canonical_memory_id):
                return SimpleNamespace(
                    exists=True,
                    to_dict=lambda: committed_item.model_dump(mode="json"),
                )
            return SimpleNamespace(exists=False, to_dict=lambda: {})

        def set(self, *args, **kwargs):
            return None

    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    apply_result = SimpleNamespace(
        status=ApplyStatus.idempotent_skip,
        memory_items=[],
        operation=SimpleNamespace(committed_memory_item_ids=[canonical_memory_id]),
        control_state=control,
    )

    with patch(
        "utils.memory.legacy_backfill.apply_long_term_patch_firestore",
        return_value=apply_result,
    ), patch(
        "utils.memory.legacy_backfill._ensure_backfill_operation",
        return_value=SimpleNamespace(operation_id="op-1"),
    ), patch(
        "utils.memory.legacy_backfill._persist_evidence",
        return_value=None,
    ), patch(
        "utils.memory.legacy_backfill._build_backfill_evidence",
        return_value=committed_item.evidence[0],
    ), patch(
        "utils.memory.legacy_backfill.legacy_backfill_memory_id",
        return_value=canonical_memory_id,
    ), patch(
        "utils.memory.legacy_backfill.sync_atom_keyword_index_for_item",
        return_value=True,
    ):
        row_result = _apply_one_legacy_row(
            uid=uid,
            legacy_row={"id": legacy_id, "content": content},
            index=0,
            control=control,
            run_id="run-1",
            db_client=_BackfillDb(),
        )

    assert row_result.written is False
    assert row_result.skip_reason == "idempotent_skip"
    assert row_result.vector_sync_failed is False
    assert row_result.keyword_sync_succeeded is True
    assert len(fake_index.upserts) == 1
    assert fake_index.upserts[0]["vectors"][0]["id"] == canonical_memory_id
    assert fake_index.upserts[0]["vectors"][0]["metadata"]["memory_layer"] == "long_term"


def test_promotion_path_updates_same_vector_id_layer(monkeypatch):
    from utils.memory.short_term_promotion import promote_short_term_item_via_apply

    vector_db, fake_index = _install_recording_vector_db(monkeypatch)
    uid = "uid-canonical"
    set_canonical_cohort(monkeypatch, uid)
    memory_id = "mem_promote"
    short_item = _item(memory_id=memory_id, tier=MemoryTier.short_term).model_copy(update={"uid": uid})
    long_item = short_item.model_copy(update={"tier": MemoryTier.long_term})

    vector_db.upsert_canonical_memory_vector(short_item)

    class _PromotionDb:
        def document(self, path):
            return SimpleNamespace(
                get=lambda: SimpleNamespace(exists=False),
                set=lambda *args, **kwargs: None,
            )

    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)

    committed_apply = SimpleNamespace(
        status=ApplyStatus.committed,
        memory_items=[long_item],
        operation=SimpleNamespace(committed_memory_item_ids=[memory_id]),
    )
    with patch(
        "utils.memory.short_term_promotion.apply_long_term_patch_firestore",
        return_value=committed_apply,
    ), patch(
        "utils.memory.short_term_promotion._ensure_promotion_operation",
        return_value=SimpleNamespace(operation_id="op-promo"),
    ), patch(
        "utils.memory.short_term_promotion.sync_atom_keyword_index_for_item",
        return_value=True,
    ), patch(
        "utils.memory.short_term_promotion.extract_kg_for_promoted_memory",
        return_value=CanonicalKgPromotionResult(attempted=True, success=True),
    ):
        promoted, _, _, keyword_sync_succeeded = promote_short_term_item_via_apply(
            uid,
            short_item,
            control=control,
            run_id="promo-run",
            trigger_reason="batch_threshold",
            now=now,
            db_client=_PromotionDb(),
        )
    assert keyword_sync_succeeded is True

    idempotent_apply = SimpleNamespace(
        status=ApplyStatus.idempotent_skip,
        memory_items=[],
        operation=SimpleNamespace(committed_memory_item_ids=[memory_id]),
    )

    class _PromotionDbWithItem:
        def document(self, path):
            if path.endswith(memory_id):
                return SimpleNamespace(
                    get=lambda: SimpleNamespace(
                        exists=True,
                        to_dict=lambda: long_item.model_dump(mode="json"),
                    ),
                )
            return SimpleNamespace(get=lambda: SimpleNamespace(exists=False), set=lambda *a, **k: None)

    with patch(
        "utils.memory.short_term_promotion.apply_long_term_patch_firestore",
        return_value=idempotent_apply,
    ), patch(
        "utils.memory.short_term_promotion._ensure_promotion_operation",
        return_value=SimpleNamespace(operation_id="op-promo-2"),
    ), patch(
        "utils.memory.short_term_promotion.sync_atom_keyword_index_for_item",
        return_value=True,
    ), patch(
        "utils.memory.short_term_promotion.extract_kg_for_promoted_memory",
        return_value=CanonicalKgPromotionResult(attempted=True, success=True),
    ):
        promoted, _, _, keyword_sync_succeeded = promote_short_term_item_via_apply(
            uid,
            short_item,
            control=control,
            run_id="promo-run-2",
            trigger_reason="batch_threshold",
            now=now,
            db_client=_PromotionDbWithItem(),
        )
    assert keyword_sync_succeeded is True

    vector_ids = [upsert["vectors"][0]["id"] for upsert in fake_index.upserts]
    assert vector_ids == [memory_id, memory_id, memory_id]
    assert fake_index.upserts[0]["vectors"][0]["metadata"]["memory_layer"] == "short_term"
    assert fake_index.upserts[1]["vectors"][0]["metadata"]["memory_layer"] == "long_term"
    assert fake_index.upserts[2]["vectors"][0]["metadata"]["memory_layer"] == "long_term"
    assert len(fake_index._vectors) == 1
    assert fake_index._vectors[memory_id]["metadata"]["memory_layer"] == "long_term"


def test_promotion_vector_sync_failure_increments_report(monkeypatch):
    from datetime import datetime, timezone

    from utils.memory.short_term_promotion import run_canonical_short_term_promotion

    vector_db = _load_vector_db_with_stubs()
    monkeypatch.setattr(vector_db, "index", _FailingIndex())
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())
    sys.modules["database.vector_db"] = vector_db

    from tests.unit.test_ws_b_short_term_lifecycle import (
        _canonical_db_with_control,
        _seed_canonical_short_term,
        _set_canonical_cohort,
    )

    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    uid = "uid-canonical-vector-fail"
    _set_canonical_cohort(monkeypatch, uid)
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.sync_atom_keyword_index_for_item",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "utils.memory.short_term_promotion.sync_atom_keyword_index_for_item",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "utils.memory.short_term_promotion.extract_kg_for_promoted_memory",
        lambda *_args, **_kwargs: CanonicalKgPromotionResult(attempted=True, success=True),
    )
    db = _canonical_db_with_control(uid)
    threshold = 25
    for index in range(threshold):
        _seed_canonical_short_term(
            db,
            uid=uid,
            conversation_id=f"conv-vector-fail-{index}",
            content=f"Fact {index}",
            monkeypatch=monkeypatch,
        )

    report = run_canonical_short_term_promotion(uid, db_client=db, now=now, run_id="promo-vector-fail")

    assert report.trigger_reason == "batch_threshold"
    assert report.promoted_count == threshold
    assert report.vector_sync_failures == threshold
    for memory_id in report.promoted_memory_ids:
        stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
        assert stored["tier"] == MemoryTier.long_term.value

"""WS-J delete/privacy matrix tests — vectors, account delete, cascade characterization."""

from __future__ import annotations

import ast
import hashlib
import importlib
import os
import re
import sys
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONVERSATIONS_ROUTER_PATH = BACKEND_DIR / "routers" / "conversations.py"

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_db_client_mod = types.ModuleType("database._client")
_db_client_mod.db = MagicMock()


def _document_id_from_seed(seed: str) -> str:
    seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=seed_hash[:16], version=4))


_db_client_mod.document_id_from_seed = _document_id_from_seed

from tests.unit.memory_import_isolation import (
    ensure_utils_memory_packages_importable,
    install_database_client_stub,
    install_ws_j_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _ws_j_import_isolation():
    saved = snapshot_sys_modules(["database._client"])
    install_database_client_stub()
    touched = install_ws_j_heavy_import_stubs()
    saved.update(snapshot_sys_modules(touched))
    from utils.memory.memory_service import MemoryService

    globals()["MemoryService"] = MemoryService
    yield
    restore_sys_modules(saved)


def _install_heavy_import_stubs():
    install_ws_j_heavy_import_stubs()


ensure_utils_memory_packages_importable(str(BACKEND_DIR))
from models.memories import MemoryCategory
from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItemStatus
from utils.memory.canonical_memory_adapter import (
    delete_all_canonical_memories,
    delete_canonical_memory,
    extraction_memory_id,
    neutral_vector_id_for_memory,
    purge_canonical_derived_user_data,
    retract_conversation_sourced_memories,
    update_canonical_memory_content,
    update_canonical_memory_visibility,
    write_canonical_extraction_memory,
)
from utils.memory.memory_system import MemorySystem, resolve_memory_system


def _refresh_canonical_memory_adapter_runtime() -> None:
    canonical_adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    globals().update(
        {
            "delete_all_canonical_memories": canonical_adapter.delete_all_canonical_memories,
            "delete_canonical_memory": canonical_adapter.delete_canonical_memory,
            "extraction_memory_id": canonical_adapter.extraction_memory_id,
            "neutral_vector_id_for_memory": canonical_adapter.neutral_vector_id_for_memory,
            "purge_canonical_derived_user_data": canonical_adapter.purge_canonical_derived_user_data,
            "retract_conversation_sourced_memories": canonical_adapter.retract_conversation_sourced_memories,
            "update_canonical_memory_content": canonical_adapter.update_canonical_memory_content,
            "update_canonical_memory_visibility": canonical_adapter.update_canonical_memory_visibility,
            "write_canonical_extraction_memory": canonical_adapter.write_canonical_extraction_memory,
        }
    )


@pytest.fixture(autouse=True)
def _clear_canonical_env(monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    _refresh_canonical_memory_adapter_runtime()
    clear_canonical_cohort(monkeypatch)


@pytest.fixture(autouse=True)
def _ensure_vector_db_delete_by_id_stub():
    """Re-apply stub attrs when other test modules replace ``database.vector_db`` at collection time."""
    _install_heavy_import_stubs()


LEGACY_UID = "uid-legacy-ws-j"


def _legacy_db_with_control(uid: str = LEGACY_UID) -> "_FakeDb":
    """Default memory_control/state with no ``memory_system=canonical`` — real resolver → LEGACY."""
    return _FakeDb(
        {
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json"),
        }
    )


def _canonical_doc_paths(db: "_FakeDb", uid: str) -> set[str]:
    prefixes = (
        f"users/{uid}/memory_items/",
        f"users/{uid}/memory_evidence/",
        f"users/{uid}/memory_outbox/",
        f"users/{uid}/memory_operations/",
    )
    return {path for path in db.docs if any(path.startswith(prefix) for prefix in prefixes)}


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeTransaction:
    def __init__(self, db):
        self._db = db
        self.sets = []
        self._read_only = False
        self._max_attempts = 1
        self._id = None

    def set(self, ref, data):
        self.sets.append((ref.path, data))

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self.sets = []
        self._id = retry_id or "txn-1"

    def _commit(self):
        for path, data in self.sets:
            self._db.docs[path] = data

    def _rollback(self):
        self._id = None


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def get(self, transaction=None):
        if self.path not in self._db.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db.docs[self.path], exists=True)

    def set(self, data, merge=False):
        if merge and isinstance(self._db.docs.get(self.path), dict):
            self._db.docs[self.path].update(data)
            return
        self._db.docs[self.path] = data


class _CollectionRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def stream(self):
        prefix = f"{self.path}/"
        for path, data in sorted(self._db.docs.items()):
            if path.startswith(prefix):
                yield _Snapshot(data, exists=True)


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.transaction_obj = _FakeTransaction(self)

    def transaction(self):
        return self.transaction_obj

    def document(self, path):
        return _DocRef(self, path)

    def collection(self, path):
        return _CollectionRef(self, path)


def _trusted_account_generation():
    return SimpleNamespace(
        account_generation=1,
        head_commit_id="head0",
        read_error_reason=None,
    )


def _sample_memory_payload(*, uid: str, conversation_id: str, content: str) -> dict:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    evidence_id = "ev_ws_j_1"
    memory_id = extraction_memory_id(uid=uid, source_id=conversation_id, content=content)
    return {
        "id": memory_id,
        "uid": uid,
        "content": content,
        "conversation_id": conversation_id,
        "category": MemoryCategory.interesting.value,
        "created_at": now,
        "updated_at": now,
        "tags": [],
        "manually_added": False,
        "reviewed": False,
        "visibility": "private",
        "evidence": [
            {
                "evidence_id": evidence_id,
                "source_id": conversation_id,
                "source_type": "conversation",
                "source_signal": "transcription",
                "extractor_id": "new_memories_extractor",
                "extractor_version": "v1",
                "artifact_ref": {},
                "capture_confidence": 0.5,
                "independence_group": conversation_id,
                "redaction_status": "active",
                "created_at": now,
            }
        ],
    }


@pytest.fixture
def canonical_db():
    uid = "uid-canonical-ws-j"
    return _FakeDb(
        {
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
                uid=uid,
                head_commit_id="head0",
                account_generation=1,
                source_generation=1,
            ).model_dump(mode="json"),
        }
    )


def test_neutral_vector_id_is_deterministic_and_distinct_from_legacy_and_memory():
    from database.memory_vector_metadata import deterministic_memory_vector_id
    from models.product_memory import MemoryTier

    uid = "uid-1"
    conversation_id = "conv-1"
    content = "User likes hiking"
    memory_id = extraction_memory_id(uid=uid, source_id=conversation_id, content=content)

    neutral_once = neutral_vector_id_for_memory(memory_id)
    neutral_twice = neutral_vector_id_for_memory(memory_id)
    assert neutral_once == neutral_twice
    assert neutral_once == memory_id
    assert memory_id.startswith("mem_")
    assert not neutral_once.startswith("memvec:")

    legacy_vector_id = f"{uid}-{memory_id}"
    memory_vector_id = deterministic_memory_vector_id(uid, memory_id, MemoryTier.long_term, 1)
    assert neutral_once != legacy_vector_id
    assert neutral_once != memory_vector_id
    assert memory_vector_id.startswith("memvec:")


def test_canonical_account_delete_purge_emits_neutral_vector_outbox(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-acct"
    content = "Canonical fact for account delete"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.resolve_memory_system",
        lambda uid, **_: MemorySystem.CANONICAL,
    )

    deleted_vector_ids = []

    def _fake_delete_by_id(vector_ids):
        deleted_vector_ids.extend(vector_ids)
        return len(vector_ids)

    monkeypatch.setattr(
        "database.vector_db.delete_pinecone_memory_vectors_by_id",
        _fake_delete_by_id,
        raising=False,
    )
    delete_graph = MagicMock()
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.kg_db.delete_knowledge_graph",
        delete_graph,
    )

    write_canonical_extraction_memory(uid, payload, db_client=canonical_db)
    memory_id = payload["id"]
    item_path = f"users/{uid}/memory_items/{memory_id}"
    assert canonical_db.docs[item_path]["status"] == MemoryItemStatus.active.value

    result = purge_canonical_derived_user_data(uid, db_client=canonical_db)
    assert result["purged"] is True
    assert memory_id in result["memory_ids"]
    expected_vector_id = neutral_vector_id_for_memory(memory_id)
    assert expected_vector_id in result["vector_ids"]
    assert expected_vector_id in deleted_vector_ids
    delete_graph.assert_called_once_with(uid, db_client=canonical_db)

    outbox_paths = [path for path in canonical_db.docs if f"users/{uid}/memory_outbox/" in path]
    assert outbox_paths, "account delete should enqueue durable vector purge outbox records"
    purge_record = next(
        canonical_db.docs[path]
        for path in outbox_paths
        if canonical_db.docs[path].get("reason") == "account_delete_canonical_purge"
    )
    assert purge_record["vector_id"] == expected_vector_id


def test_canonical_account_delete_purge_raises_on_partial_vector_delete(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-acct-partial"
    content = "Canonical fact for partial account delete"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.resolve_memory_system",
        lambda uid, **_: MemorySystem.CANONICAL,
    )
    monkeypatch.setattr(
        "database.vector_db.delete_pinecone_memory_vectors_by_id",
        lambda vector_ids: 0,
        raising=False,
    )

    write_canonical_extraction_memory(uid, payload, db_client=canonical_db)

    with pytest.raises(RuntimeError, match="canonical vector purge only deleted 0/1 vectors"):
        purge_canonical_derived_user_data(uid, db_client=canonical_db)


def test_legacy_account_delete_purge_skips_canonical_path(monkeypatch):
    db = _legacy_db_with_control()
    assert resolve_memory_system(LEGACY_UID, db_client=db) == MemorySystem.LEGACY

    delete_by_id = MagicMock()
    monkeypatch.setattr(
        "database.vector_db.delete_pinecone_memory_vectors_by_id",
        delete_by_id,
        raising=False,
    )
    before = set(db.docs.keys())

    result = purge_canonical_derived_user_data(LEGACY_UID, db_client=db)

    assert result["purged"] is False
    assert result["reason"] == "not_canonical_cohort"
    delete_by_id.assert_not_called()
    assert set(db.docs.keys()) == before
    assert not _canonical_doc_paths(db, LEGACY_UID)


def test_legacy_purge_derived_user_data_still_purges_legacy_vectors(monkeypatch):
    """Canonical neutral-id purge is inert for a real legacy uid; legacy batch path stays separate."""
    db = _legacy_db_with_control()
    assert resolve_memory_system(LEGACY_UID, db_client=db) == MemorySystem.LEGACY

    delete_by_id = MagicMock()
    legacy_batch = MagicMock()
    monkeypatch.setattr(
        "database.vector_db.delete_pinecone_memory_vectors_by_id",
        delete_by_id,
        raising=False,
    )
    monkeypatch.setattr(
        "database.vector_db.delete_memory_vectors_batch",
        legacy_batch,
        raising=False,
    )
    before = set(db.docs.keys())

    purge_canonical_derived_user_data(LEGACY_UID, db_client=db)

    delete_by_id.assert_not_called()
    assert set(db.docs.keys()) == before

    import database.vector_db as vector_db

    vector_db.delete_memory_vectors_batch(LEGACY_UID, ["legacy-m1"])
    legacy_batch.assert_called_once_with(LEGACY_UID, ["legacy-m1"])


def test_memory_service_retract_conversation_memories_is_noop_for_legacy():
    db = _legacy_db_with_control()
    assert resolve_memory_system(LEGACY_UID, db_client=db) == MemorySystem.LEGACY
    before = set(db.docs.keys())

    result = MemoryService(db_client=db).retract_conversation_memories(LEGACY_UID, "conv-x")

    assert result is None
    assert set(db.docs.keys()) == before
    assert not _canonical_doc_paths(db, LEGACY_UID)


def test_conversation_delete_cascade_tombstones_canonical_and_emits_vector_purge(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-cascade"
    content = "Fact sourced from conversation"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload, db_client=canonical_db)
    retract_result = retract_conversation_sourced_memories(uid, conversation_id, db_client=canonical_db)

    assert retract_result["retracted_memory_ids"] == [memory_id]
    tombstoned = canonical_db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert tombstoned["status"] == MemoryItemStatus.tombstoned.value
    assert tombstoned["evidence"][0]["source_state"] == "tombstoned"

    outbox_paths = [path for path in canonical_db.docs if "memory_outbox" in path]
    assert outbox_paths
    purge_record = next(
        record
        for path, record in ((p, canonical_db.docs[p]) for p in outbox_paths)
        if record.get("reason") == "conversation_reprocess_retract"
    )
    assert purge_record["vector_id"] == neutral_vector_id_for_memory(memory_id)


def test_conversation_delete_cascade_deletes_canonical_vector_immediately(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-cascade-vector"
    content = "Fact sourced from conversation with vector"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    deleted_vectors = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.delete_canonical_memory_vector",
        lambda u, mid: deleted_vectors.append((u, mid)),
    )

    write_canonical_extraction_memory(uid, payload, db_client=canonical_db)
    retract_conversation_sourced_memories(uid, conversation_id, db_client=canonical_db)

    assert deleted_vectors == [(uid, memory_id)]


def test_retract_calls_kg_invalidation_hook(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-kg"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content="KG defer hook")

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    kg_calls = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction",
        lambda u, ids, **kwargs: kg_calls.append((u, list(ids), kwargs.get("db_client"))),
    )

    write_canonical_extraction_memory(uid, payload, db_client=canonical_db)
    retract_conversation_sourced_memories(uid, conversation_id, db_client=canonical_db)
    assert kg_calls
    assert kg_calls[0][0] == uid
    assert payload["id"] in kg_calls[0][1]
    assert kg_calls[0][2] is canonical_db


def test_delete_canonical_memory_calls_kg_invalidation_hook(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-delete-kg"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content="Delete KG hook")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    kg_calls = []
    deleted_vectors = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction",
        lambda u, ids, **kwargs: kg_calls.append((u, list(ids))),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.delete_canonical_memory_vector",
        lambda u, mid: deleted_vectors.append((u, mid)),
    )

    write_canonical_extraction_memory(uid, payload, db_client=canonical_db)
    delete_canonical_memory(uid, memory_id, db_client=canonical_db)

    assert kg_calls == [(uid, [memory_id])]
    assert deleted_vectors == [(uid, memory_id)]
    tombstoned = canonical_db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert tombstoned["status"] == MemoryItemStatus.tombstoned.value


def test_update_canonical_visibility_validates_before_persisting(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(uid=uid, conversation_id="conv-invalid-visibility", content="Visibility invariant")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload, db_client=canonical_db)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    before = dict(canonical_db.docs[item_path])

    with pytest.raises(ValueError, match="visibility"):
        update_canonical_memory_visibility(uid, memory_id, "friends", db_client=canonical_db)

    assert canonical_db.docs[item_path] == before


def test_update_canonical_visibility_resyncs_keyword_and_vector_side_effects(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    conversation_id = "conv-visibility"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content="Visibility side effect")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload, db_client=canonical_db)

    keyword_syncs = []
    vector_syncs = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.sync_atom_keyword_index_for_item",
        lambda item, **kwargs: keyword_syncs.append((item.memory_id, item.visibility)) or True,
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.sync_canonical_memory_vector",
        lambda item, **kwargs: vector_syncs.append((item.memory_id, item.visibility)) or True,
    )

    updated = update_canonical_memory_visibility(uid, memory_id, "public", db_client=canonical_db)

    assert updated.visibility == "public"
    assert canonical_db.docs[f"users/{uid}/memory_items/{memory_id}"]["visibility"] == "public"
    assert keyword_syncs == [(memory_id, "public")]
    assert vector_syncs == [(memory_id, "public")]


def test_update_canonical_content_fails_on_document_memory_id_mismatch(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(uid=uid, conversation_id="conv-id-mismatch", content="Original fact")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload, db_client=canonical_db)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    canonical_db.docs[item_path] = {**canonical_db.docs[item_path], "memory_id": "different-memory-id"}

    with pytest.raises(ValueError, match="memory id mismatch"):
        update_canonical_memory_content(uid, memory_id, "Updated fact", db_client=canonical_db)

    assert canonical_db.docs[item_path]["content"] == "Original fact"


def test_update_canonical_content_kg_invalidation_uses_merge_update(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payload = _sample_memory_payload(uid=uid, conversation_id="conv-kg-merge", content="Original KG fact")
    memory_id = payload["id"]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.resolve_memory_system", lambda *_, **__: MemorySystem.CANONICAL
    )
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction", lambda *_, **__: None
    )
    monkeypatch.setattr(
        "utils.memory.canonical_kg_promotion.extract_kg_for_promoted_memory",
        lambda *_, **__: SimpleNamespace(success=False),
    )

    write_canonical_extraction_memory(uid, payload, db_client=canonical_db)
    item_path = f"users/{uid}/memory_items/{memory_id}"
    canonical_db.docs[item_path].update(
        {
            "tier": "long_term",
            "processing_state": "processed",
            "expires_at": None,
            "ledger_commit_id": "commit1",
            "ledger_sequence": 1,
            "kg_extracted": True,
            "promotion": {"reviewed": False},
        }
    )

    original_set = _DocRef.set

    def concurrent_visibility_change_on_kg_merge(ref, data, merge=False):
        if ref.path == item_path and merge and set(data) == {"kg_extracted", "updated_at"}:
            canonical_db.docs[item_path]["visibility"] = "shared"
        return original_set(ref, data, merge=merge)

    monkeypatch.setattr(_DocRef, "set", concurrent_visibility_change_on_kg_merge)

    updated = update_canonical_memory_content(uid, memory_id, "Updated KG fact", db_client=canonical_db)

    assert updated.kg_extracted is False
    assert canonical_db.docs[item_path]["content"] == "Updated KG fact"
    assert canonical_db.docs[item_path]["kg_extracted"] is False
    assert canonical_db.docs[item_path]["visibility"] == "shared"


def test_delete_all_canonical_memories_batches_kg_invalidation(monkeypatch, canonical_db):
    uid = "uid-canonical-ws-j"
    payloads = [
        _sample_memory_payload(uid=uid, conversation_id="conv-del-all-1", content="First fact"),
        _sample_memory_payload(uid=uid, conversation_id="conv-del-all-2", content="Second fact"),
    ]

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )
    kg_calls = []
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.invalidate_kg_for_memory_retraction",
        lambda u, ids, **kwargs: kg_calls.append((u, list(ids))),
    )

    memory_ids = []
    for payload in payloads:
        write_canonical_extraction_memory(uid, payload, db_client=canonical_db)
        memory_ids.append(payload["id"])

    delete_all_canonical_memories(uid, db_client=canonical_db)

    assert len(kg_calls) == 1
    assert kg_calls[0][0] == uid
    assert set(kg_calls[0][1]) == set(memory_ids)


def test_conversation_delete_cascade_default_is_false():
    """Q8 gated: production default must stay cascade=false until owner sign-off."""
    source = CONVERSATIONS_ROUTER_PATH.read_text(encoding="utf-8")
    assert re.search(r"cascade:\s*bool\s*=\s*Query\(False\)", source)
    assert "Q8-gated" in source


def test_conversation_delete_cascade_branches_memory_delete_by_cohort():
    """Cascade delete must branch legacy delete vs canonical retract."""
    source = CONVERSATIONS_ROUTER_PATH.read_text(encoding="utf-8")
    cascade_start = source.index("if cascade:")
    cascade_block = source[cascade_start : source.index("return {\"status\": \"Ok\"}", cascade_start)]
    assert "memory_system = pin_memory_system(uid" in cascade_block
    assert "memory_system == MemorySystem.CANONICAL" in cascade_block
    assert ".retract_conversation_memories(uid, conversation_id)" in cascade_block
    assert "memories_db.delete_memories_for_conversation(uid, conversation_id)" in cascade_block
    canonical_branch_start = cascade_block.index("memory_system == MemorySystem.CANONICAL")
    legacy_delete_idx = cascade_block.index("memories_db.delete_memories_for_conversation")
    assert legacy_delete_idx > canonical_branch_start


def test_purge_derived_user_data_wires_canonical_purge_helper():
    users_source = (BACKEND_DIR / "services" / "users" / "account_deletion.py").read_text(encoding="utf-8")
    tree = ast.parse(users_source)
    purge_fn = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "purge_derived_user_data"
    )
    call_names = {
        node.func.id for node in ast.walk(purge_fn) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "purge_canonical_derived_user_data" in call_names

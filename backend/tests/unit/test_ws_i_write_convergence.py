"""WS-I write/read convergence tests."""

from __future__ import annotations

import ast
import hashlib
import importlib
import uuid
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROCESS_CONVERSATION_PATH = BACKEND_DIR / "utils" / "conversations" / "process_conversation.py"

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
    AutoMockModule as _AutoMockModule,
    ensure_utils_memory_packages_importable,
    install_database_client_stub,
    install_ws_i_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _ws_i_import_isolation():
    saved = snapshot_sys_modules(["database._client"])
    install_database_client_stub()
    touched = install_ws_i_heavy_import_stubs()
    saved.update(snapshot_sys_modules(touched))
    yield
    restore_sys_modules(saved)


def _install_heavy_import_stubs():
    install_ws_i_heavy_import_stubs()


def _load_process_conversation(monkeypatch):
    _install_heavy_import_stubs()
    for name in list(sys.modules):
        if name == "utils.conversations.process_conversation" or name.startswith(
            "utils.conversations.process_conversation."
        ):
            del sys.modules[name]
    return importlib.import_module("utils.conversations.process_conversation")


def _load_memories_router(monkeypatch):
    _install_heavy_import_stubs()
    for name in list(sys.modules):
        if name == "routers.memories" or name.startswith("routers.memories."):
            del sys.modules[name]
    return importlib.import_module("routers.memories")


ensure_utils_memory_packages_importable(str(BACKEND_DIR))
from models.memory_domain import MemoryLayer, MemoryProcessingState, MemoryRecordStatus
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memories import Memory, MemoryDB, MemoryCategory
from models.v17_memory_apply import ApplyStatus, MemoryControlState
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.canonical_memory_adapter import (
    extraction_memory_id,
    read_canonical_memories,
    retract_conversation_sourced_memories,
    write_canonical_extraction_memory,
)
from utils.memory.memory_system import MemorySystem, resolve_memory_system


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
    evidence_id = "ev_ws_i_1"
    return {
        "id": extraction_memory_id(uid=uid, source_id=conversation_id, content=content),
        "uid": uid,
        "content": content,
        "category": MemoryCategory.interesting.value,
        "conversation_id": conversation_id,
        "created_at": now,
        "updated_at": now,
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


def _stored_item(item: V17MemoryItem) -> dict:
    return item.model_dump(mode="json")


def _fresh_short_term_item(*, uid: str, memory_id: str, conversation_id: str, content: str) -> V17MemoryItem:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    evidence = MemoryEvidence(
        evidence_id="ev1",
        source_type="conversation",
        source_id=conversation_id,
        source_version="v1",
        conversation_id=conversation_id,
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    return V17MemoryItem(
        memory_id=memory_id,
        uid=uid,
        version=1,
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[evidence],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=30),
        ledger_commit_id="commit_1",
        ledger_sequence=1,
        source_commit_id="commit_1",
        source_commit_sequence=1,
        content_hash="hash1",
        account_generation=1,
    )


@pytest.fixture(autouse=True)
def _clear_canonical_env(monkeypatch):
    monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)
    from utils.memory.memory_system_pin import clear_memory_system_pin

    clear_memory_system_pin()
    yield
    clear_memory_system_pin()


def _patch_cohort_resolver(monkeypatch, system: MemorySystem):
    """Pin tests to a cohort via the real request-scope resolver seam."""
    monkeypatch.setattr(
        "utils.memory.memory_system_pin.resolve_memory_system",
        lambda uid, **_: system,
    )


def test_arbitrary_uid_defaults_to_legacy():
    assert resolve_memory_system("uid-random", db_client=_FakeDb()) == MemorySystem.LEGACY


def test_canonical_write_uses_apply_and_not_legacy_save(monkeypatch):
    uid = "uid-canonical"
    conversation_id = "conv-1"
    content = "User enjoys hiking"
    db = _FakeDb(
        {
            f"users/{uid}/memory_control/state": MemoryControlState(
                uid=uid, head_commit_id="head0", account_generation=1, source_generation=1
            ).model_dump(mode="json"),
            f"users/{uid}/memory_evidence/ev_ws_i_1": MemoryEvidence(
                evidence_id="ev_ws_i_1",
                source_type="conversation",
                source_id=conversation_id,
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            ).model_dump(mode="json"),
        }
    )

    committed_item = _fresh_short_term_item(
        uid=uid,
        memory_id=extraction_memory_id(uid=uid, source_id=conversation_id, content=content),
        conversation_id=conversation_id,
        content=content,
    )
    apply_result = SimpleNamespace(
        status=ApplyStatus.committed,
        memory_items=[committed_item],
        operation=SimpleNamespace(committed_memory_item_ids=[committed_item.memory_id]),
        reason=None,
    )

    _install_heavy_import_stubs()
    legacy_save = sys.modules["database.memories"].save_memories
    legacy_save.reset_mock()

    with patch(
        "utils.memory.canonical_memory_adapter.apply_long_term_patch_firestore", return_value=apply_result
    ) as apply_mock:
        memory_id = write_canonical_extraction_memory(
            uid, _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content), db_client=db
        )

    assert memory_id == committed_item.memory_id
    apply_mock.assert_called_once()
    legacy_save.assert_not_called()
    assert committed_item.tier == MemoryTier.short_term
    assert committed_item.status == MemoryItemStatus.active
    assert committed_item.processing_state == ProcessingState.processed


def test_canonical_read_returns_default_visible_items():
    uid = "uid-canonical"
    conversation_id = "conv-1"
    content = "User enjoys hiking"
    memory_id = extraction_memory_id(uid=uid, source_id=conversation_id, content=content)
    item = _fresh_short_term_item(uid=uid, memory_id=memory_id, conversation_id=conversation_id, content=content)
    db = _FakeDb({f"users/{uid}/memory_items/{memory_id}": _stored_item(item)})

    memories = read_canonical_memories(uid, db_client=db)
    assert len(memories) == 1
    assert memories[0].id == memory_id
    assert memories[0].content == content
    assert memories[0].memory_tier == MemoryTier.short_term


def test_canonical_read_hides_restricted_sensitivity():
    uid = "uid-canonical"
    conversation_id = "conv-1"
    content = "password is secret123"
    memory_id = extraction_memory_id(uid=uid, source_id=conversation_id, content=content)
    item = _fresh_short_term_item(uid=uid, memory_id=memory_id, conversation_id=conversation_id, content=content)
    restricted = item.model_copy(update={"sensitivity_labels": ["credential"]})
    db = _FakeDb({f"users/{uid}/memory_items/{memory_id}": _stored_item(restricted)})

    assert read_canonical_memories(uid, db_client=db) == []


def test_legacy_extract_path_unchanged_for_non_canonical():
    source = PROCESS_CONVERSATION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    inner_fn = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_extract_memories_inner"
    )
    first_stmt = inner_fn.body[0]
    assert isinstance(first_stmt, ast.With)
    assert any(
        isinstance(node, ast.Call)
        and isinstance(getattr(node.func, "id", None), str)
        and node.func.id == "memory_system_request_scope"
        for node in ast.walk(first_stmt)
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(getattr(node.func, "id", None), str)
        and node.func.id == "_extract_memories_canonical"
        for node in ast.walk(inner_fn)
    )
    assert "_extract_memories_legacy(uid, conversation)" in source
    canonical_fn_idx = source.index("def _extract_memories_canonical")
    legacy_fn_idx = source.index("def _extract_memories_legacy")
    assert canonical_fn_idx < legacy_fn_idx
    assert "deletion_result = memories_db.delete_memories_for_conversation" in source
    assert "memories_db.save_memories(uid, [fact.dict() for fact in parsed_memories])" in source


def test_canonical_extract_uses_memory_service_not_legacy_save():
    source = PROCESS_CONVERSATION_PATH.read_text(encoding="utf-8")
    start = source.index("def _extract_memories_canonical")
    end = source.index("\ndef _extract_memories_inner", start)
    canonical_body = source[start:end]
    assert "MemoryService()" in canonical_body
    assert "retract_conversation_memories" in canonical_body
    assert "memory_service.write" in canonical_body
    assert "memories_db.delete_memories_for_conversation" not in canonical_body
    assert "memories_db.save_memories" not in canonical_body
    assert "short_term_db.save_short_term_memories" not in canonical_body


def test_reprocess_retract_then_rewrite_restores_active_memory(monkeypatch):
    """Integration: real apply path must recreate an active item after retract (Blocker 2)."""
    uid = "uid-canonical"
    conversation_id = "conv-reprocess"
    content = "User enjoys hiking"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    memory_id = payload["id"]
    db = _FakeDb(
        {
            f"users/{uid}/memory_control/state": MemoryControlState(
                uid=uid, head_commit_id="head0", account_generation=1, source_generation=1
            ).model_dump(mode="json"),
        }
    )

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.read_v17_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
    )

    write_canonical_extraction_memory(uid, payload, db_client=db)
    first_read = read_canonical_memories(uid, db_client=db)
    assert len(first_read) == 1
    assert first_read[0].id == memory_id
    assert first_read[0].content == content

    retract_result = retract_conversation_sourced_memories(uid, conversation_id, db_client=db)
    assert retract_result["retracted_memory_ids"] == [memory_id]
    assert retract_result["source_generation"] == 2
    tombstoned = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert tombstoned["status"] == MemoryItemStatus.tombstoned.value

    mid_read = read_canonical_memories(uid, db_client=db)
    assert mid_read == []

    write_canonical_extraction_memory(uid, payload, db_client=db)
    restored = read_canonical_memories(uid, db_client=db)
    assert len(restored) == 1
    assert restored[0].id == memory_id
    assert restored[0].content == content
    assert db.docs[f"users/{uid}/memory_items/{memory_id}"]["status"] == MemoryItemStatus.active.value

    # Second rewrite with identical content must not duplicate.
    write_canonical_extraction_memory(uid, payload, db_client=db)
    assert len(read_canonical_memories(uid, db_client=db)) == 1


def test_extract_memories_inner_legacy_calls_save_memories(monkeypatch):
    pc = _load_process_conversation(monkeypatch)
    legacy_save = sys.modules["database.memories"].save_memories
    legacy_save.reset_mock()
    legacy_delete = sys.modules["database.memories"].delete_memories_for_conversation
    legacy_delete.reset_mock(return_value={"vector_delete_ids": []})

    memory = Memory(content="User likes coffee", category=MemoryCategory.interesting)
    _patch_cohort_resolver(monkeypatch, MemorySystem.LEGACY)
    monkeypatch.setattr(pc, "new_memories_extractor", lambda *args, **kwargs: [memory])
    monkeypatch.setattr(pc, "record_usage", lambda *args, **kwargs: None)

    conversation = SimpleNamespace(
        id="conv-legacy",
        source=pc.ConversationSource.omi,
        transcript_segments=[],
        external_data={},
        is_locked=False,
    )
    pc._extract_memories_inner("uid-legacy", conversation)

    legacy_delete.assert_called_once_with("uid-legacy", "conv-legacy")
    legacy_save.assert_called_once()
    assert legacy_save.call_args[0][0] == "uid-legacy"


def test_extract_memories_inner_canonical_uses_memory_service(monkeypatch):
    pc = _load_process_conversation(monkeypatch)
    legacy_save = sys.modules["database.memories"].save_memories
    legacy_save.reset_mock()
    legacy_delete = sys.modules["database.memories"].delete_memories_for_conversation
    legacy_delete.reset_mock()

    memory = Memory(content="User likes coffee", category=MemoryCategory.interesting)
    write_mock = MagicMock()
    retract_mock = MagicMock()
    service = MagicMock()
    service.write = write_mock
    service.retract_conversation_memories = retract_mock

    _patch_cohort_resolver(monkeypatch, MemorySystem.CANONICAL)
    monkeypatch.setattr(pc, "new_memories_extractor", lambda *args, **kwargs: [memory])
    monkeypatch.setattr(pc, "record_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr(pc, "MemoryService", lambda **_: service)

    conversation = SimpleNamespace(
        id="conv-canonical",
        source=pc.ConversationSource.omi,
        transcript_segments=[],
        external_data={},
        is_locked=False,
    )
    pc._extract_memories_inner("uid-canonical", conversation)

    retract_mock.assert_called_once_with("uid-canonical", "conv-canonical")
    legacy_delete.assert_not_called()
    legacy_save.assert_not_called()
    assert write_mock.call_count == 1


def test_v3_get_routes_canonical_user_to_memory_service(monkeypatch):
    memories_router = _load_memories_router(monkeypatch)

    canonical_memories = [
        MemoryDB(
            id="mem-1",
            uid="uid-canonical",
            content="hello",
            category=MemoryCategory.interesting,
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
    ]
    legacy_get = MagicMock(return_value=[])
    service_read = MagicMock(return_value=canonical_memories)

    monkeypatch.setattr(
        memories_router,
        "pin_memory_system",
        lambda uid, **_: MemorySystem.CANONICAL if uid == "uid-canonical" else MemorySystem.LEGACY,
    )
    monkeypatch.setattr(memories_router, "MemoryService", lambda **_: SimpleNamespace(read=service_read))
    monkeypatch.setattr(memories_router, "_legacy_get_memories", legacy_get)

    runtime = memories_router.V17V3GetRuntime(enabled=True, source_decision="v17_read")
    result = memories_router.get_memories(
        response=MagicMock(),
        limit=10,
        offset=0,
        cursor=None,
        uid="uid-canonical",
        v17_runtime=runtime,
    )

    assert result == canonical_memories
    service_read.assert_called_once_with("uid-canonical", limit=10, offset=0)
    legacy_get.assert_not_called()


def test_v3_get_keeps_legacy_path_for_non_canonical(monkeypatch):
    memories_router = _load_memories_router(monkeypatch)

    legacy_memories = [
        MemoryDB(
            id="mem-legacy",
            uid="uid-legacy",
            content="legacy",
            category=MemoryCategory.interesting,
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
    ]
    legacy_get = MagicMock(return_value=legacy_memories)
    service_read = MagicMock()

    monkeypatch.setattr(memories_router, "pin_memory_system", lambda uid, **_: MemorySystem.LEGACY)
    monkeypatch.setattr(memories_router, "MemoryService", lambda **_: SimpleNamespace(read=service_read))
    monkeypatch.setattr(memories_router, "_legacy_get_memories", legacy_get)

    runtime = memories_router.V17V3GetRuntime(enabled=False, source_decision="disabled")
    result = memories_router.get_memories(
        response=MagicMock(),
        limit=10,
        offset=0,
        cursor=None,
        uid="uid-legacy",
        v17_runtime=runtime,
    )

    assert result == legacy_memories
    legacy_get.assert_called_once_with("uid-legacy", 10, 0)
    service_read.assert_not_called()


def test_legal_state_short_term_active_processed():
    from models.memory_domain import assert_legal_state

    assert_legal_state(MemoryLayer.SHORT_TERM, MemoryRecordStatus.ACTIVE, MemoryProcessingState.PROCESSED)

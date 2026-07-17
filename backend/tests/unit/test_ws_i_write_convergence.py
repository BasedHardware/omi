"""WS-I write/read convergence tests."""

from __future__ import annotations

import ast
import asyncio
import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROCESS_CONVERSATION_PATH = BACKEND_DIR / "utils" / "conversations" / "process_conversation.py"

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

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
from models.memory_apply import ApplyStatus, MemoryControlState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from database.memory_apply_store import apply_long_term_patch_firestore
import utils.memory.canonical_memory_adapter as canonical_memory_adapter_module
from utils.memory.canonical_memory_adapter import (
    extraction_memory_id,
    memory_item_to_memorydb,
    read_canonical_memories,
    retract_conversation_sourced_memories,
    write_canonical_extraction_memory,
    write_canonical_external_memory,
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
        if merge and self.path in self._db.docs:
            self._db.docs[self.path] = self._db.docs[self.path] | data
            return
        self._db.docs[self.path] = data

    def update(self, data):
        if self.path not in self._db.docs:
            raise NotFound(f"Document {self.path} not found")
        self._db.docs[self.path] = self._db.docs[self.path] | data


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


def _stored_item(item: MemoryItem) -> dict:
    return item.model_dump(mode="json")


def _fresh_short_term_item(*, uid: str, memory_id: str, conversation_id: str, content: str) -> MemoryItem:
    now = datetime.now(timezone.utc)
    evidence = MemoryEvidence(
        evidence_id="ev1",
        source_type="conversation",
        source_id=conversation_id,
        source_version="v1",
        conversation_id=conversation_id,
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    return MemoryItem(
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
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    clear_canonical_cohort(monkeypatch)
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
    """Routing + real apply: memory_items doc is written via apply, not legacy save."""
    uid = "uid-canonical"
    conversation_id = "conv-1"
    content = "User enjoys hiking"
    payload = _sample_memory_payload(uid=uid, conversation_id=conversation_id, content=content)
    memory_id = payload["id"]
    evidence_id = payload["evidence"][0]["evidence_id"]
    db = _FakeDb(
        {
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
                uid=uid, head_commit_id="head0", account_generation=1, source_generation=1
            ).model_dump(mode="json"),
        }
    )

    monkeypatch.setattr(
        canonical_memory_adapter_module,
        "read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
        raising=False,
    )
    _install_heavy_import_stubs()
    legacy_save = sys.modules["database.memories"].save_memories
    legacy_save.reset_mock()

    with patch(
        "utils.memory.canonical_memory_adapter.apply_long_term_patch_firestore",
        wraps=apply_long_term_patch_firestore,
    ) as apply_mock:
        returned_id = write_canonical_extraction_memory(uid, payload, db_client=db)

    assert returned_id == memory_id
    apply_mock.assert_called_once()
    legacy_save.assert_not_called()

    stored_path = f"users/{uid}/memory_items/{memory_id}"
    assert stored_path in db.docs
    stored = db.docs[stored_path]
    assert stored["content"] == content
    assert stored["tier"] == MemoryTier.short_term.value
    assert stored["status"] == MemoryItemStatus.active.value
    assert stored["processing_state"] == ProcessingState.processed.value
    assert stored["evidence"][0]["evidence_id"] == evidence_id
    assert stored["evidence"][0]["source_id"] == conversation_id

    evidence_path = f"users/{uid}/memory_evidence/{evidence_id}"
    assert evidence_path in db.docs
    assert db.docs[evidence_path]["source_id"] == conversation_id

    memories = read_canonical_memories(uid, db_client=db)
    assert len(memories) == 1
    assert memories[0].id == memory_id
    assert memories[0].content == content


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
    assert (
        "memories_db.save_memories(uid, [memory_write_payload(fact, MemoryApiExposure.LEGACY) "
        "for fact in parsed_memories])"
    ) in source


def test_canonical_extract_uses_memory_service_not_legacy_save():
    source = PROCESS_CONVERSATION_PATH.read_text(encoding="utf-8")
    start = source.index("def _extract_memories_canonical")
    end = source.index("\ndef _extract_memories_inner", start)
    canonical_body = source[start:end]
    assert "MemoryService(db_client=db_client)" in canonical_body
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
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
                uid=uid, head_commit_id="head0", account_generation=1, source_generation=1
            ).model_dump(mode="json"),
        }
    )

    monkeypatch.setattr(
        canonical_memory_adapter_module,
        "read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
        raising=False,
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
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")
    kg_module = ModuleType("utils.llm.knowledge_graph")
    kg_module.extract_knowledge_from_memory = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "utils.llm.knowledge_graph", kg_module)

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

    memories = [
        Memory(content="User likes coffee", category=MemoryCategory.interesting),
        Memory(content="User changed the launch date", category=MemoryCategory.interesting),
    ]
    write_mock = MagicMock()
    retract_mock = MagicMock()
    readiness_mock = MagicMock()
    service = MagicMock()
    service.write = write_mock
    service.retract_conversation_memories = retract_mock
    service.ensure_canonical_mutation_ready = readiness_mock

    _patch_cohort_resolver(monkeypatch, MemorySystem.CANONICAL)
    monkeypatch.setattr(pc, "new_memories_extractor", lambda *args, **kwargs: memories)
    monkeypatch.setattr(pc, "record_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")
    monkeypatch.setattr(pc, "MemoryService", lambda **_: service)
    association_mock = MagicMock()
    monkeypatch.setattr(pc, "associate_canonical_evidence", association_mock)

    conversation = SimpleNamespace(
        id="conv-canonical",
        source=pc.ConversationSource.omi,
        transcript_segments=[],
        external_data={},
        is_locked=False,
    )
    pc._extract_memories_inner("uid-canonical", conversation)

    retract_mock.assert_called_once_with("uid-canonical", "conv-canonical")
    readiness_mock.assert_called_once_with("uid-canonical")
    legacy_delete.assert_not_called()
    legacy_save.assert_not_called()
    assert write_mock.call_count == 2
    association_mock.assert_called_once()
    evidence = association_mock.call_args.args[1]
    assert evidence.evidence_id == "conv-canonical"
    assert len(evidence.evidence_refs) == 3

    association_mock.reset_mock()
    conversation.is_locked = True
    pc._extract_memories_inner("uid-canonical", conversation)
    assert write_mock.call_count == 4
    assert readiness_mock.call_count == 2
    association_mock.assert_not_called()


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
        "canonical_read_enabled",
        lambda uid, **_: uid == "uid-canonical",
    )
    monkeypatch.setattr(memories_router, "MemoryService", lambda **_: SimpleNamespace(read=service_read))
    monkeypatch.setattr(memories_router, "_legacy_get_memories", legacy_get)

    runtime = memories_router.V3GetRuntime(enabled=True, source_decision="memory_read")
    result = memories_router.get_memories(
        response=MagicMock(),
        limit=10,
        offset=0,
        cursor=None,
        device_scope="explicit",
        client_device_id="device-1",
        uid="uid-canonical",
        memory_runtime=runtime,
        x_app_platform=None,
        x_device_id_hash=None,
    )

    assert result == canonical_memories
    from utils.client_device import DeviceScopeRequest

    service_read.assert_called_once_with(
        "uid-canonical",
        limit=5000,
        offset=0,
        device_scope_request=DeviceScopeRequest(device_scope="explicit", client_device_id="device-1"),
        include_pending_processing=True,
    )
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

    monkeypatch.setattr(memories_router, "canonical_read_enabled", lambda uid, **_: False)
    monkeypatch.setattr(memories_router, "MemoryService", lambda **_: SimpleNamespace(read=service_read))
    monkeypatch.setattr(memories_router, "_legacy_get_memories", legacy_get)

    runtime = memories_router.V3GetRuntime(enabled=False, source_decision="disabled")
    result = memories_router.get_memories(
        response=MagicMock(),
        limit=10,
        offset=0,
        cursor=None,
        device_scope="all",
        client_device_id=None,
        uid="uid-legacy",
        memory_runtime=runtime,
        x_app_platform=None,
        x_device_id_hash=None,
    )

    body = json.loads(result.body)
    assert body[0]["id"] == "mem-legacy"
    assert body[0]["content"] == "legacy"
    assert "memory_tier" not in body[0]
    assert "layer" not in body[0]
    assert "tier" not in body[0]
    assert result.headers["x-omi-memory-device-scope-supported"] == "false"
    legacy_get.assert_called_once_with("uid-legacy", 10, 0)
    service_read.assert_not_called()


def test_v3_memory_creates_forward_request_device_provenance(monkeypatch):
    memories_router = _load_memories_router(monkeypatch)
    device_context = SimpleNamespace(client_device_id="macos_a1b2c3d4")
    forwarded_device_ids = []

    class ProvenanceCaptured(Exception):
        pass

    async def skip_import_guard(*args, **kwargs):
        return None

    def capture_from_memory(*args, **kwargs):
        forwarded_device_ids.append(kwargs["client_device_id"])
        raise ProvenanceCaptured

    monkeypatch.setattr(memories_router, "resolve_client_device_from_request", lambda request: device_context)
    monkeypatch.setattr(memories_router, "_guard_import_memory_write", skip_import_guard)
    monkeypatch.setattr(memories_router.MemoryDB, "from_memory", staticmethod(capture_from_memory))

    memory = SimpleNamespace(category=MemoryCategory.manual, visibility="private", tags=[])
    with pytest.raises(ProvenanceCaptured):
        asyncio.run(memories_router.create_memory(MagicMock(), memory, "uid-device-provenance"))
    with pytest.raises(ProvenanceCaptured):
        asyncio.run(
            memories_router.create_memories_batch(
                MagicMock(),
                SimpleNamespace(memories=[memory]),
                "uid-device-provenance",
            )
        )

    assert forwarded_device_ids == ["macos_a1b2c3d4", "macos_a1b2c3d4"]


def test_legal_state_short_term_active_processed():
    from models.memory_domain import assert_legal_state

    assert_legal_state(MemoryLayer.SHORT_TERM, MemoryRecordStatus.ACTIVE, MemoryProcessingState.PROCESSED)


@pytest.fixture
def _clear_canonical_env_ws_i2(monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    clear_canonical_cohort(monkeypatch)
    from utils.memory.memory_system_pin import clear_memory_system_pin

    clear_memory_system_pin()
    yield
    clear_memory_system_pin()


def test_canonical_external_write_preserves_public_visibility_and_manual_flag(monkeypatch, _clear_canonical_env_ws_i2):
    uid = "uid-canonical-meta"
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    payload = {
        "id": "mem_public_manual",
        "uid": uid,
        "content": "I prefer tea over coffee",
        "category": MemoryCategory.manual.value,
        "visibility": "public",
        "manually_added": True,
        "tags": ["user-note"],
        "created_at": now,
        "updated_at": now,
    }
    db = _FakeDb(
        {
            f"users/{uid}/memory_state/apply_control": MemoryControlState(
                uid=uid, head_commit_id="head0", account_generation=1, source_generation=1
            ).model_dump(mode="json"),
        }
    )
    monkeypatch.setattr(
        canonical_memory_adapter_module,
        "read_memory_v3_trusted_account_generation",
        lambda **_: _trusted_account_generation(),
        raising=False,
    )

    with patch(
        "utils.memory.canonical_memory_adapter.apply_long_term_patch_firestore",
        wraps=apply_long_term_patch_firestore,
    ) as apply_mock:
        memory_id = write_canonical_external_memory(uid, payload, db_client=db)

    assert memory_id == "mem_public_manual"
    apply_mock.assert_called_once()
    patch_payload = apply_mock.call_args.kwargs["patch_payload"]
    assert patch_payload["visibility"] == "public"
    assert patch_payload["user_asserted"] is True
    assert patch_payload["initial_tier"] == MemoryTier.short_term.value

    stored = db.docs[f"users/{uid}/memory_items/{memory_id}"]
    assert stored["visibility"] == "public"
    assert stored["user_asserted"] is True
    assert stored["tier"] == MemoryTier.short_term.value
    assert stored["promotion"]["category"] == MemoryCategory.manual.value
    assert stored["promotion"]["tags"] == ["user-note"]

    item = MemoryItem(**stored)
    mapped = memory_item_to_memorydb(item)
    assert mapped.visibility == "public"
    assert mapped.manually_added is True
    assert mapped.category == MemoryCategory.manual
    assert mapped.tags == ["user-note"]
    assert mapped.memory_tier == MemoryTier.short_term

    memories = read_canonical_memories(uid, db_client=db)
    assert len(memories) == 1
    assert memories[0].visibility == "public"
    assert memories[0].manually_added is True


def test_mcp_validate_memory_uses_canonical_store_for_canonical_cohort():
    source = (BACKEND_DIR / "routers" / "mcp.py").read_text(encoding="utf-8")
    section = source.split("def _validate_mcp_memory", 1)[1].split("@router.delete", 1)[0]
    assert "fetch_memory_dict" in section
    memory_service_source = (BACKEND_DIR / "utils" / "memory" / "memory_service.py").read_text(encoding="utf-8")
    assert "MemorySystem.CANONICAL" in memory_service_source
    assert "read_canonical_memory_item" in memory_service_source


_WRITER_FILES = [
    BACKEND_DIR / "routers" / "memories.py",
    BACKEND_DIR / "routers" / "mcp.py",
    BACKEND_DIR / "routers" / "mcp_sse.py",
    BACKEND_DIR / "routers" / "developer.py",
    BACKEND_DIR / "utils" / "conversations" / "memories.py",
    BACKEND_DIR / "utils" / "x_connector.py",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "preference_tools.py",
]

_EXCLUDED_OFFLINE_WRITER_FILES = [
    BACKEND_DIR / "scripts" / "rag" / "memories.py",
]

_LEGACY_WRITE_CALLS = frozenset(
    {
        "memories_db.create_memory",
        "memories_db.save_memories",
        "memories_db.review_memory",
        "memories_db.refine_memory",
        "memories_db.merge_contradict_memory",
    }
)

_ALLOWLISTED_LEGACY_WRITES = frozenset()

_COHORT_GATE_MARKERS = (
    "pin_memory_system",
    "resolve_memory_system",
    "MemorySystem.CANONICAL",
    "canonical_write_enabled",
)


def _legacy_write_allowed(source_lines: list[str], lineno: int, *, rel_path: str, call_name: str) -> bool:
    if (rel_path, call_name) in _ALLOWLISTED_LEGACY_WRITES:
        return True

    window = source_lines[max(0, lineno - 150) : lineno]
    gate_indices = [idx for idx, line in enumerate(window) if any(marker in line for marker in _COHORT_GATE_MARKERS)]
    if not gate_indices:
        return False

    last_gate = gate_indices[-1]
    after_gate = window[last_gate:]
    if any("return" in line for line in after_gate):
        return True
    if any(line.strip().startswith("else:") for line in window[last_gate:]):
        return True
    return False


def _canonical_guarded_legacy_writes(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    rel_path = str(path.relative_to(BACKEND_DIR))
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = None
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                call_name = f"{node.func.value.id}.{node.func.attr}"
        if call_name not in _LEGACY_WRITE_CALLS:
            continue
        if _legacy_write_allowed(source_lines, node.lineno, rel_path=rel_path, call_name=call_name):
            continue
        line = source_lines[node.lineno - 1]
        violations.append(f"{rel_path}:{node.lineno}: {line.strip()}")

    return violations


def test_canonical_writer_files_do_not_call_legacy_writes_without_cohort_gate():
    all_violations: list[str] = []
    for path in _WRITER_FILES:
        assert path.exists(), f"missing writer file: {path}"
        all_violations.extend(_canonical_guarded_legacy_writes(path))

    assert not all_violations, "ungated legacy memory writes in canonical writer surfaces:\n" + "\n".join(
        all_violations
    )


def test_offline_rag_script_excluded_from_live_writer_guard():
    for path in _EXCLUDED_OFFLINE_WRITER_FILES:
        assert path.exists(), f"missing excluded offline writer: {path}"
    assert all(path not in _WRITER_FILES for path in _EXCLUDED_OFFLINE_WRITER_FILES)


def test_memories_router_routes_canonical_create_through_memory_service():
    source = (BACKEND_DIR / "routers" / "memories.py").read_text(encoding="utf-8")
    assert "_canonical_write_enabled_or_fail_closed(uid, db_client=db_client)" in source
    assert "memory_service.create_external_memory" in source
    assert "require_canonical_promotion=True" in source
    create_section = source.split("async def create_memory", 1)[1].split("@router.post", 1)[0]
    canonical_pos = create_section.find("_canonical_write_enabled_or_fail_closed")
    legacy_pos = create_section.find("memories_db.create_memory")
    assert canonical_pos != -1 and legacy_pos != -1
    assert canonical_pos < legacy_pos


def test_review_memory_routes_canonical_cohort_through_memory_service():
    source = (BACKEND_DIR / "routers" / "memories.py").read_text(encoding="utf-8")
    section = source.split("def review_memory", 1)[1].split("@router.patch", 1)[0]
    assert "_canonical_write_enabled_or_fail_closed(uid, db_client=db_client)" in section
    assert ".review(uid, memory_id, value)" in section
    canonical_pos = section.find("_canonical_write_enabled_or_fail_closed")
    legacy_pos = section.find("memories_db.review_memory")
    assert canonical_pos != -1 and legacy_pos != -1
    assert canonical_pos < legacy_pos


def test_preference_tools_routes_canonical_cohort_through_memory_service():
    source = (BACKEND_DIR / "utils" / "retrieval" / "tools" / "preference_tools.py").read_text(encoding="utf-8")
    assert "resolve_memory_system(uid, db_client=db) == MemorySystem.CANONICAL" in source
    assert "MemoryService(db_client=db).create_external_memory(" in source
    assert "require_canonical_promotion=True" in source
    canonical_pos = source.find("MemorySystem.CANONICAL")
    legacy_pos = source.find("memory_db.create_memory")
    assert canonical_pos != -1 and legacy_pos != -1
    assert canonical_pos < legacy_pos

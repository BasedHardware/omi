"""Regressions for verified backend atomicity/lifecycle fixes.

Covers: preference scoreless-hit suppression, merge target compensation on
source retraction failure, explicit integration required-processing, review
reject idempotency after tombstone, and deletion-fenced apply control.
"""

from __future__ import annotations

import os
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from models.memory_apply import MemoryControlState, WriterMode
from models.product_memory import MemoryItemStatus
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from utils.memory.memory_system import (
    CanonicalApplyStateUnavailable,
    ensure_canonical_apply_control_state,
)

_BACKEND = Path(__file__).resolve().parents[2]


def _preference_tools_module():
    """Load preference_tools without tools/__init__ side effects."""
    tools_pkg = types.ModuleType("utils.retrieval.tools")
    tools_pkg.__path__ = [os.path.join(str(_BACKEND), "utils", "retrieval", "tools")]  # type: ignore[attr-defined]
    fakes = {
        "utils.retrieval.tools": tools_pkg,
        "database._client": AutoMockModule("database._client"),
        "utils.memory.canonical_memory_adapter": AutoMockModule("utils.memory.canonical_memory_adapter"),
        "utils.memory.knowledge_ledger": AutoMockModule("utils.memory.knowledge_ledger"),
        "utils.memory.memory_service": AutoMockModule("utils.memory.memory_service"),
        "utils.memory.memory_system": AutoMockModule("utils.memory.memory_system"),
        "testing.parity_pack_v0.live_capture": AutoMockModule("testing.parity_pack_v0.live_capture"),
        "langchain_core.tools": AutoMockModule("langchain_core.tools"),
        "langchain_core.runnables": AutoMockModule("langchain_core.runnables"),
        "models.memories": AutoMockModule("models.memories"),
    }
    with stub_modules(fakes):
        import langchain_core.tools as lc_tools

        def _tool(fn=None, **_kwargs):
            if fn is None:
                return lambda real_fn: real_fn
            return fn

        lc_tools.tool = _tool
        module = load_module_fresh(
            "utils.retrieval.tools.preference_tools",
            os.path.join(str(_BACKEND), "utils", "retrieval", "tools", "preference_tools.py"),
        )
        return module


@pytest.fixture(scope="module")
def preference_tools_module():
    """Amortize the intentionally isolated module load across focused tests."""

    return _preference_tools_module()


def test_preference_tool_ignores_scoreless_unrelated_hits(preference_tools_module):
    """Scoreless/synthetic search hits must not suppress unrelated preferences."""
    message = preference_tools_module.preference_duplicate_message(
        "Prefers Google Calendar over Outlook",
        [{"memory_id": "other", "content": "Prefers Outlook calendar"}],
    )
    assert message is None


def test_preference_tool_blocks_exact_normalized_duplicate(preference_tools_module):
    message = preference_tools_module.preference_duplicate_message(
        "Prefers Google Calendar over Outlook",
        [{"memory_id": "dup", "content": "  Prefers Google Calendar over Outlook "}],
    )
    assert message is not None
    assert message.startswith("Similar preference already exists:")


def test_preference_tool_honors_real_relevance_score(preference_tools_module):
    message = preference_tools_module.preference_duplicate_message(
        "Prefers Google Calendar over Outlook",
        [{"memory_id": "near", "content": "Uses Google Calendar", "score": 0.95}],
    )
    assert message is not None
    assert "Uses Google Calendar" in message


def test_preference_tool_writes_retry_stable_agent_conclusion_to_ledger(preference_tools_module, monkeypatch):
    module = preference_tools_module

    class Provenance:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    save_fact = MagicMock(return_value="mem_ledger")
    capture_memory_write = MagicMock()
    firestore_client = object()
    monkeypatch.setattr(module, "LedgerProvenance", Provenance)
    monkeypatch.setattr(module, "save_fact", save_fact)
    monkeypatch.setattr(module, "capture_memory_write", capture_memory_write)
    monkeypatch.setattr(module, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))
    monkeypatch.setattr(
        module,
        "ensure_canonical_apply_control_state",
        lambda *_args, **_kwargs: types.SimpleNamespace(writer_mode=WriterMode.ledger),
    )
    config = {
        "configurable": {
            "user_id": "user-1",
            "chat_session_id": "chat-1",
            "thread_id": "thread-ignored",
        }
    }

    first = module.save_user_preference_tool("Prefers metric units", config=config)
    second = module.save_user_preference_tool("Prefers metric units", config=config)

    assert first == second == "Preference saved: Prefers metric units"
    assert save_fact.call_count == 2
    first_call = save_fact.call_args_list[0]
    second_call = save_fact.call_args_list[1]
    assert first_call.kwargs["write_reason"].value == "agent_reusable_conclusion"
    assert first_call.kwargs["provenance"].source_id == "chat-1"
    assert first_call.kwargs["provenance"].source_type == "agent_chat"
    assert first_call.kwargs["provenance"].action_id == second_call.kwargs["provenance"].action_id
    assert first_call.kwargs["provenance"].artifact_ref == {"chat_session_id": "chat-1"}
    assert first_call.kwargs["db_client"] is firestore_client
    capture_memory_write.assert_called_with(
        principal_id="user-1",
        source="agent_preference_ledger_write",
        session_id="chat-1",
        memories=[
            {
                "id": "mem_ledger",
                "content": "Prefers metric units",
                "ledger_schema_version": "knowledge_ledger.v1",
                "write_reason": "agent_reusable_conclusion",
            }
        ],
    )


def test_preference_tool_persists_canonical_slot_and_drops_unknown_names(preference_tools_module, monkeypatch):
    module = preference_tools_module
    save_fact = MagicMock(return_value="mem_ledger")
    firestore_client = object()
    monkeypatch.setattr(module, "save_fact", save_fact)
    monkeypatch.setattr(module, "capture_memory_write", MagicMock())
    monkeypatch.setattr(module, "search_canonical_memories", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(module, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))
    monkeypatch.setattr(
        module,
        "ensure_canonical_apply_control_state",
        lambda *_args, **_kwargs: types.SimpleNamespace(writer_mode=WriterMode.ledger),
    )
    config = {"configurable": {"user_id": "user-1", "chat_session_id": "chat-1"}}

    known = module.save_user_preference_tool("Lives in Brooklyn", slot=" Home-Location ", config=config)
    unknown = module.save_user_preference_tool("Prefers dark mode", slot="invented_slot", config=config)

    assert known == "Preference saved: Lives in Brooklyn"
    assert unknown == "Preference saved: Prefers dark mode"
    assert save_fact.call_args_list[0].kwargs["slot"] == "home_city"
    assert save_fact.call_args_list[1].kwargs["slot"] is None


def test_preference_tool_uses_strict_compatibility_writer_in_default_mode(preference_tools_module, monkeypatch):
    """The default writer mode retains the released MemoryService contract."""
    module = preference_tools_module
    firestore_client = object()
    capture_memory_write = MagicMock()
    save_fact = MagicMock(side_effect=AssertionError("ledger writer must stay gated"))

    class StrictMemory:
        def __init__(self, payload):
            self.payload = payload
            self.id = "mem-compat"

    class StrictMemoryDB:
        @classmethod
        def model_validate(cls, payload):
            assert payload["category"] == "system"
            assert payload["manually_added"] is False
            assert payload["visibility"] == "private"
            assert payload["tags"] == ["agent-learned"]
            assert "ledger_schema_version" not in payload
            return StrictMemory(payload)

        @staticmethod
        def calculate_score(memory):
            assert memory.payload["content"] == "Prefers metric units"
            return "00_999_0000000000"

    class StrictMemoryService:
        def __init__(self, *, db_client):
            assert db_client is firestore_client

        def create_external_memory(
            self,
            uid,
            memory_db,
            *,
            memory_system,
            consumer,
            operation,
            upsert_vector,
            require_canonical_promotion,
        ):
            assert uid == "user-compat"
            assert memory_db.payload["content"] == "Prefers metric units"
            assert memory_system is module.MemorySystem.CANONICAL
            assert consumer == "agent_preference"
            assert operation == "save_user_preference"
            assert upsert_vector is False
            assert require_canonical_promotion is True
            return types.SimpleNamespace(id="adapter-returned-id")

    monkeypatch.setattr(module, "MemoryDB", StrictMemoryDB)
    monkeypatch.setattr(module, "MemoryService", StrictMemoryService)
    monkeypatch.setattr(module.uuid, "uuid4", lambda: "mem-compat")
    monkeypatch.setattr(module, "save_fact", save_fact)
    monkeypatch.setattr(module, "capture_memory_write", capture_memory_write)
    monkeypatch.setattr(module, "get_data_plane_firestore_client", MagicMock(return_value=firestore_client))
    monkeypatch.setattr(
        module,
        "ensure_canonical_apply_control_state",
        lambda *_args, **_kwargs: types.SimpleNamespace(writer_mode=WriterMode.compatibility),
    )
    config = {"configurable": {"user_id": "user-compat", "chat_session_id": "chat-compat"}}

    result = module.save_user_preference_tool("Prefers metric units", config=config)

    assert result == "Preference saved: Prefers metric units"
    save_fact.assert_not_called()
    capture_memory_write.assert_called_once()
    capture = capture_memory_write.call_args.kwargs
    assert capture["principal_id"] == "user-compat"
    assert capture["source"] == "agent_preference_memory_create"
    assert capture["session_id"] == "mem-compat"
    captured_memory = capture["memories"][0]
    assert captured_memory["id"] == "mem-compat"
    assert captured_memory["content"] == "Prefers metric units"
    assert captured_memory["category"] == "system"
    assert captured_memory["tags"] == ["agent-learned"]
    assert captured_memory["scoring"] == "00_999_0000000000"
    assert "ledger_schema_version" not in captured_memory


def test_preference_tool_fails_closed_during_writer_transition(preference_tools_module, monkeypatch):
    """A transition fence may not silently choose either writer."""
    module = preference_tools_module
    save_fact = MagicMock()
    compatibility_service = MagicMock()
    monkeypatch.setattr(module, "save_fact", save_fact)
    monkeypatch.setattr(module, "MemoryService", compatibility_service)
    monkeypatch.setattr(module, "get_data_plane_firestore_client", MagicMock(return_value=object()))
    monkeypatch.setattr(
        module,
        "ensure_canonical_apply_control_state",
        lambda *_args, **_kwargs: types.SimpleNamespace(writer_mode=WriterMode.transitioning_to_ledger),
    )

    result = module.save_user_preference_tool(
        "Prefers metric units",
        config={"configurable": {"user_id": "user-transition"}},
    )

    assert result == "Error saving preference"
    save_fact.assert_not_called()
    compatibility_service.assert_not_called()


def test_preference_tool_does_not_write_without_user_authority(preference_tools_module, monkeypatch):
    module = preference_tools_module
    save_fact = MagicMock()
    monkeypatch.setattr(module, "save_fact", save_fact)

    result = module.save_user_preference_tool("Prefers metric units", config={"configurable": {}})

    assert result == "Error: Could not determine user ID"
    save_fact.assert_not_called()


def test_preference_tool_fails_closed_when_storage_authority_is_unavailable(preference_tools_module, monkeypatch):
    module = preference_tools_module
    save_fact = MagicMock()
    monkeypatch.setattr(
        module, "get_data_plane_firestore_client", MagicMock(side_effect=RuntimeError("credential detail"))
    )
    monkeypatch.setattr(module, "save_fact", save_fact)

    result = module.save_user_preference_tool(
        "Prefers metric units",
        config={"configurable": {"user_id": "user-1"}},
    )

    assert result == "Error saving preference"
    save_fact.assert_not_called()


def test_explicit_integration_memories_keep_required_processing_contract():
    """Explicit integration writes must wrap required_processing_payload."""
    src = (_BACKEND / "utils" / "conversations" / "memories.py").read_text(encoding="utf-8")
    assert "required_processing_payload" in src
    assert 'extractor_id="external_integration_explicit"' in src
    assert 'consumer=f"integration:{app_id}"' in src


def test_merge_failure_tombstones_merged_target_contract():
    """Source retraction failure must compensate the already-admitted merge target."""
    src = (_BACKEND / "utils" / "conversations" / "merge_conversations.py").read_text(encoding="utf-8")
    assert "merged_conversation_id: Optional[str] = None" in src
    assert "MergeFailurePhase" in src
    assert "SOURCE_DELETION_STARTED" in src
    compact = "".join(src.split())
    assert "retract_conversation_memories(uid,merged_conversation_id)" in compact
    assert "failure_phase=failure_phase" in compact


@pytest.fixture
def review_queue_module():
    fakes = {
        "database._client": AutoMockModule("database._client"),
        "database.memories": AutoMockModule("database.memories"),
        "database.memory_ledger": AutoMockModule("database.memory_ledger"),
        "database.short_term_memories": AutoMockModule("database.short_term_memories"),
        "google.cloud.firestore_v1": AutoMockModule("google.cloud.firestore_v1"),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.review_queue",
            os.path.join(str(_BACKEND), "database", "review_queue.py"),
        )
        yield module


def test_review_reject_is_idempotent_after_tombstone(review_queue_module):
    memory_service = MagicMock()
    memory_service._canonical_status = MagicMock(return_value=MemoryItemStatus.tombstoned)
    memory_service.delete = MagicMock(side_effect=AssertionError("direct delete must not run"))
    memory_service.delete_batch = MagicMock(side_effect=AssertionError("no live ids to delete"))

    memory_service_module = types.ModuleType("utils.memory.memory_service")
    memory_service_module.MemoryService = lambda db_client=None: memory_service
    canonical_adapter_module = AutoMockModule("utils.memory.canonical_memory_adapter")
    with stub_modules(
        {
            "utils.memory.memory_service": memory_service_module,
            "utils.memory.canonical_memory_adapter": canonical_adapter_module,
        }
    ):
        result = review_queue_module.append_resolution_commit(
            "u1",
            {
                "review_id": "review_1",
                "fact_id": "fact_1",
                "candidate": {},
                "conflict_with": [],
            },
            "reject",
            None,
            [{"op": "reject"}],
        )

    assert result is not None
    memory_service.delete.assert_not_called()
    memory_service.delete_batch.assert_not_called()


class _Snapshot:
    def __init__(self, payload=None, *, exists=True):
        self._payload = payload
        self.exists = exists

    def to_dict(self):
        return dict(self._payload or {})


class _Ref:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self):
        if self.path not in self.db.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self.db.docs[self.path])

    def create(self, payload):
        if self.path in self.db.docs:
            from google.api_core.exceptions import AlreadyExists

            raise AlreadyExists("exists")
        self.db.docs[self.path] = dict(payload)

    def set(self, payload, **_kwargs):
        self.db.docs[self.path] = dict(payload)


class _Db:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def document(self, path):
        return _Ref(self, path)


def test_ensure_canonical_apply_control_refuses_deleting_account():
    uid = "uid-deleting"
    db = _Db({f"account_deletions/{uid}": {"wipe_status": "running"}})
    with pytest.raises(CanonicalApplyStateUnavailable, match="account deletion"):
        ensure_canonical_apply_control_state(uid, db_client=db)
    from database.memory_collections import MemoryCollections

    assert MemoryCollections(uid=uid).memory_apply_control_state not in db.docs
    assert f"canonical_memory_maintenance_registry/{uid}" not in db.docs


def test_ensure_canonical_apply_control_refuses_completed_wipe_reenrollment():
    uid = "uid-wiped"
    db = _Db({f"account_deletions/{uid}": {"wipe_status": "completed"}})
    with pytest.raises(CanonicalApplyStateUnavailable, match="account deletion"):
        ensure_canonical_apply_control_state(uid, db_client=db)


def test_ensure_canonical_apply_control_still_provisions_live_accounts():
    db = _Db()
    control = ensure_canonical_apply_control_state("uid-live", db_client=db)
    assert isinstance(control, MemoryControlState)
    assert control.account_generation == 1

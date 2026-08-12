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

from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItemStatus
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from utils.memory.memory_system import (
    CanonicalApplyStateUnavailable,
    ensure_canonical_apply_control_state,
)

_BACKEND = Path(__file__).resolve().parents[2]


def _preference_duplicate_message():
    """Load preference_duplicate_message without tools/__init__ side effects."""
    tools_pkg = types.ModuleType("utils.retrieval.tools")
    tools_pkg.__path__ = [os.path.join(str(_BACKEND), "utils", "retrieval", "tools")]  # type: ignore[attr-defined]
    fakes = {
        "utils.retrieval.tools": tools_pkg,
        "database._client": AutoMockModule("database._client"),
        "utils.memory.canonical_memory_adapter": AutoMockModule("utils.memory.canonical_memory_adapter"),
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
        return module.preference_duplicate_message


def test_preference_tool_ignores_scoreless_unrelated_hits():
    """Scoreless/synthetic search hits must not suppress unrelated preferences."""
    preference_duplicate_message = _preference_duplicate_message()
    message = preference_duplicate_message(
        "Prefers Google Calendar over Outlook",
        [{"memory_id": "other", "content": "Prefers Outlook calendar"}],
    )
    assert message is None


def test_preference_tool_blocks_exact_normalized_duplicate():
    preference_duplicate_message = _preference_duplicate_message()
    message = preference_duplicate_message(
        "Prefers Google Calendar over Outlook",
        [{"memory_id": "dup", "content": "  Prefers Google Calendar over Outlook "}],
    )
    assert message is not None
    assert message.startswith("Similar preference already exists:")


def test_preference_tool_honors_real_relevance_score():
    preference_duplicate_message = _preference_duplicate_message()
    message = preference_duplicate_message(
        "Prefers Google Calendar over Outlook",
        [{"memory_id": "near", "content": "Uses Google Calendar", "score": 0.95}],
    )
    assert message is not None
    assert "Uses Google Calendar" in message


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
    with stub_modules({"utils.memory.memory_service": memory_service_module}):
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

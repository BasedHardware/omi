"""Regression tests for the action-items mirror in PATCH /v1/conversations/{id}/action-items.

``set_action_item_status`` mirrors each patched summary row onto the standalone
action_items collection. Rows that carry a durable ``target_task_id`` link must
mirror exactly that one task: two standalone tasks can share a description with
different due dates or evidence, and the legacy description-wide mirror flipped
every sibling when one row was toggled. Rows without the link keep the legacy
description mirror for released clients.

This suite reuses the hermetic router harness from test_conversation_events_bounds:
the router constructs clients at import time, so the fakes must precede the
import, and the real ``utils.manual_speaker_assignments`` chain (which needs the
real ``database.read_boundary``) must be loaded before the ``database`` package
is stubbed.
"""

import enum
import importlib.util as _importlib_util
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Pre-import the real manual-assignment policy the router binds at import time;
# its transitive imports need the real database.read_boundary, so this must run
# before the stubbed ``database`` package exists.
from utils.manual_speaker_assignments import manual_assignment  # noqa: F401

from testing.import_isolation import (
    AutoMockModule,
    load_module_fresh,
    package_submodule_stubs,
    stub_modules,
)

_BACKEND = Path(__file__).resolve().parents[2]

# The router imports the list-read budget seam at module level (#11831); load
# the real stdlib-only module under a private name for the same reason.
_list_budget_path = _BACKEND / "utils" / "other" / "list_budget.py"
_list_budget_spec = _importlib_util.spec_from_file_location("_omi_real_list_budget", str(_list_budget_path))
list_budget_real = _importlib_util.module_from_spec(_list_budget_spec)
_list_budget_spec.loader.exec_module(list_budget_real)


def _pkg(name):
    mod = AutoMockModule(name)
    mod.__path__ = []
    return mod


@pytest.fixture(scope="module")
def router():
    client_mod = ModuleType("database._client")
    client_mod.db = MagicMock(name="db")
    client_mod.get_firestore_client = lambda: client_mod.db

    fa_auth = _pkg("firebase_admin.auth")
    fa_auth.InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})

    endpoints = ModuleType("utils.other.endpoints")
    endpoints.get_current_user_uid = lambda: "test-uid"
    endpoints.with_rate_limit = lambda dependency, _policy: dependency
    endpoints.get_user = MagicMock()

    class _MemorySystem(str, enum.Enum):
        LEGACY = "legacy"
        CANONICAL = "canonical"

    memory_system = ModuleType("utils.memory.memory_system")
    setattr(memory_system, "MemorySystem", _MemorySystem)

    canonical_activation = ModuleType("utils.memory.canonical_activation")
    setattr(canonical_activation, "canonical_write_enabled", MagicMock(return_value=False))

    memory_service = ModuleType("utils.memory.memory_service")
    memory_service.MemoryService = MagicMock()

    retraction_scope = ModuleType("utils.memory.retraction_scope")
    setattr(retraction_scope, "retraction_can_be_skipped", MagicMock(return_value=False))

    canonical_adapter = ModuleType("utils.memory.canonical_memory_adapter")

    class _ConversationReplacementConflictError(RuntimeError):
        pass

    setattr(canonical_adapter, "ConversationReplacementConflictError", _ConversationReplacementConflictError)

    request_validation = ModuleType("utils.request_validation")
    setattr(request_validation, "NonNegativeOffset", int)
    setattr(request_validation, "PositiveLimit", int)

    fakes = {
        "ulid": _pkg("ulid"),
        "pinecone": _pkg("pinecone"),
        "typesense": _pkg("typesense"),
        "database": _pkg("database"),
        "database._client": client_mod,
        "database.conversations": _pkg("database.conversations"),
        "database.conversation_scan": _pkg("database.conversation_scan"),
        "database.screen_frames": _pkg("database.screen_frames"),
        "database.action_items": _pkg("database.action_items"),
        "database.memories": _pkg("database.memories"),
        "database.redis_db": _pkg("database.redis_db"),
        "database.cache": _pkg("database.cache"),
        "database.apps": _pkg("database.apps"),
        "database.folders": _pkg("database.folders"),
        "database.trends": _pkg("database.trends"),
        "database.calendar_meetings": _pkg("database.calendar_meetings"),
        "database.tasks": _pkg("database.tasks"),
        "database.goals": _pkg("database.goals"),
        "database.llm_usage": _pkg("database.llm_usage"),
        "database.chat": _pkg("database.chat"),
        "database.notifications": _pkg("database.notifications"),
        "database.fair_use": _pkg("database.fair_use"),
        "database.webhook_health": _pkg("database.webhook_health"),
        "database.mem_db": _pkg("database.mem_db"),
        "database.firestore_read_metrics": _pkg("database.firestore_read_metrics"),
        "utils.apps": _pkg("utils.apps"),
        "utils.product_metrics": _pkg("utils.product_metrics"),
        "database.users": _pkg("database.users"),
        "database.vector_db": _pkg("database.vector_db"),
        "services.conversation_frame_evidence": _pkg("services.conversation_frame_evidence"),
        "firebase_admin": _pkg("firebase_admin"),
        "firebase_admin.messaging": _pkg("firebase_admin.messaging"),
        "firebase_admin.auth": fa_auth,
        "firebase_admin.credentials": _pkg("firebase_admin.credentials"),
        "firebase_admin.firestore": _pkg("firebase_admin.firestore"),
        "google": _pkg("google"),
        "google.cloud": _pkg("google.cloud"),
        "google.cloud.firestore": _pkg("google.cloud.firestore"),
        "google.cloud.firestore_v1": _pkg("google.cloud.firestore_v1"),
        "utils.other": _pkg("utils.other"),
        "utils.other.endpoints": endpoints,
        "utils.other.list_budget": list_budget_real,
        "utils.other.storage": _pkg("utils.other.storage"),
        **package_submodule_stubs("utils.conversations"),
        "utils.llm": _pkg("utils.llm"),
        "utils.llm.conversation_processing": _pkg("utils.llm.conversation_processing"),
        "utils.speaker_identification": _pkg("utils.speaker_identification"),
        "utils.speaker_tag_prompts.service": _pkg("utils.speaker_tag_prompts.service"),
        "utils.subscription": _pkg("utils.subscription"),
        "utils.app_integrations": _pkg("utils.app_integrations"),
        "utils.memory": _pkg("utils.memory"),
        "utils.memory.memory_service": memory_service,
        "utils.memory.memory_system": memory_system,
        "utils.memory.canonical_activation": canonical_activation,
        "utils.memory.retraction_scope": retraction_scope,
        "utils.memory.canonical_memory_adapter": canonical_adapter,
        "utils.retrieval": _pkg("utils.retrieval"),
        "utils.retrieval.tools": _pkg("utils.retrieval.tools"),
        "utils.retrieval.tools.calendar_tools": _pkg("utils.retrieval.tools.calendar_tools"),
        "utils.retrieval.tools.google_utils": _pkg("utils.retrieval.tools.google_utils"),
        "utils.request_validation": request_validation,
    }

    with stub_modules(fakes):
        conv = load_module_fresh(
            "routers.conversations",
            os.path.join(str(_BACKEND), "routers", "conversations.py"),
        )
        from models.conversation import SetConversationActionItemsStateRequest

        yield SimpleNamespace(conv=conv, request=SetConversationActionItemsStateRequest)


class _FakeActionItem:
    """Minimal structured action item: tracks .completed and is .model_dump()-able."""

    def __init__(self, description, completed=False, target_task_id=None):
        self.description = description
        self.completed = completed
        self.created_at = None
        self.completed_at = None
        self.target_task_id = target_task_id

    def model_dump(self):
        return {
            "description": self.description,
            "completed": self.completed,
            "target_task_id": self.target_task_id,
        }


@pytest.fixture()
def mirror(router, monkeypatch):
    """Installs fakes around the endpoint's mirror step and records calls.

    The handler imports ``sync_action_item_reminder`` from utils.notifications
    inside the function body, so the fake module must be planted in sys.modules
    for the ``from ... import`` to bind it. The stubbed ``deserialize_conversation``
    must return the fake conversation unchanged, as the real one does for
    non-Mapping inputs.
    """
    marked = []
    synced = []
    fetched = []
    conversations_updated = []

    conversation_holder = {}

    def _get_valid_conversation_by_id(uid, cid):
        return conversation_holder["conversation"]

    monkeypatch.setattr(router.conv, "_get_valid_conversation_by_id", _get_valid_conversation_by_id, raising=False)
    monkeypatch.setattr(router.conv, "deserialize_conversation", lambda data: data, raising=False)
    monkeypatch.setattr(
        router.conv.conversations_db,
        "update_conversation_action_items",
        lambda uid, cid, items: conversations_updated.append((cid, items)),
    )
    ai_db = router.conv.action_items_db
    monkeypatch.setattr(
        ai_db,
        "get_action_items_by_conversation",
        lambda uid, cid: conversation_holder["standalone"],
    )
    monkeypatch.setattr(ai_db, "mark_action_item_completed", lambda uid, ai_id, value: marked.append((ai_id, value)))

    def _get_action_item(uid, ai_id):
        fetched.append(ai_id)
        return {"id": ai_id, "description": "Send the plan", "due_at": None}

    monkeypatch.setattr(ai_db, "get_action_item", _get_action_item)

    notifications = ModuleType("utils.notifications")

    def _sync(*, user_id, action_item_id, description, completed, due_at):
        synced.append((action_item_id, completed))

    notifications.sync_action_item_reminder = _sync
    monkeypatch.setitem(sys.modules, "utils.notifications", notifications)

    def _run(structured_items, standalone_items, values):
        conversation_holder["conversation"] = SimpleNamespace(
            structured=SimpleNamespace(action_items=structured_items),
            created_at=None,
        )
        conversation_holder["standalone"] = standalone_items
        return router.conv.set_action_item_status(
            router.request(items_idx=list(range(len(structured_items))), values=values),
            "conversation-1",
            uid="test-uid",
        )

    return SimpleNamespace(run=_run, marked=marked, synced=synced, fetched=fetched, updated=conversations_updated)


def test_linked_row_mirrors_exactly_its_task_not_description_siblings(mirror):
    result = mirror.run(
        [_FakeActionItem("Send the plan", target_task_id="task-linked")],
        [
            {"id": "task-linked", "description": "Send the plan", "due_at": "2026-10-05T16:00:00Z"},
            # Same description, different task: the mirror must not flip it.
            {"id": "task-manual", "description": "Send the plan", "due_at": None},
        ],
        [True],
    )

    assert result == {"status": "Ok"}
    assert mirror.marked == [("task-linked", True)]
    assert mirror.synced == [("task-linked", True)]
    assert mirror.fetched == [], "the linked task was in the conversation list; no direct fetch needed"


def test_unlinked_row_keeps_the_legacy_description_mirror(mirror):
    mirror.run(
        [_FakeActionItem("Send the plan")],
        [
            {"id": "task-a", "description": "Send the plan", "due_at": None},
            {"id": "task-b", "description": "Send the plan", "due_at": None},
        ],
        [True],
    )

    assert sorted(mirror.marked) == [("task-a", True), ("task-b", True)]
    assert mirror.fetched == []


def test_linked_task_outside_the_conversation_list_is_fetched_directly(mirror):
    mirror.run(
        [_FakeActionItem("Send the plan", target_task_id="task-orphan")],
        [],
        [True],
    )

    assert mirror.fetched == ["task-orphan"]
    assert mirror.marked == [("task-orphan", True)]

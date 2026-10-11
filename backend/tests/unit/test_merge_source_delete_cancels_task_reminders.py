"""Merge cleanup must cancel the deleted source tasks' client-scheduled reminders.

`_delete_conversation_and_related_data` removes each source conversation's action
items, but a deleted row can still own a local notification the mobile client
scheduled from the reminder data message. The client cancels it only when the
backend sends the deletion data message, so a merge left a reminder armed for every
open dated task in the sources while the merged conversation's own tasks scheduled
fresh ones. The cleanup now sends the cancel for each open dated row it removes,
the same way the conversation delete path does (#15041, #5085).
"""

from __future__ import annotations

import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (
    AutoMockModule,
    install_database_client_stub,
    install_ws_i_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

_ORIGINAL_ATTRS: dict[tuple[str, str], object] = {}


def _remember(module_name: str, attr: str) -> None:
    key = (module_name, attr)
    if key in _ORIGINAL_ATTRS:
        return
    module = sys.modules.get(module_name)
    if module is not None and hasattr(module, attr):
        _ORIGINAL_ATTRS[key] = getattr(module, attr)


def _install_merge_conversations_stubs() -> list[str]:
    touched = install_ws_i_heavy_import_stubs()
    for _mod, _attr in (
        ("database.conversations", "delete_conversation"),
        ("database.conversations", "delete_conversation_photos"),
        ("database.action_items", "delete_action_items_for_conversation"),
        ("database.action_items", "get_action_items_by_conversation"),
    ):
        _remember(_mod, _attr)
    conversations_mod = sys.modules["database.conversations"]
    conversations_mod.delete_conversation = MagicMock()
    conversations_mod.delete_conversation_photos = MagicMock()
    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.delete_action_items_for_conversation = MagicMock()
    action_items_mod.get_action_items_by_conversation = MagicMock(return_value=[])

    sys.modules["utils.other.storage"] = AutoMockModule("utils.other.storage")
    touched.append("utils.other.storage")

    for _modname in ["utils.conversations", "utils.conversations.merge_conversations"]:
        _existing = sys.modules.get(_modname)
        if _existing is not None and not getattr(_existing, "__file__", None):
            del sys.modules[_modname]
    return list(dict.fromkeys(touched))


@pytest.fixture(scope="module", autouse=True)
def _merge_conversations_import_isolation():
    saved = snapshot_sys_modules(["database._client", "utils.memory.retraction_scope", "database.conversations"])
    install_database_client_stub()
    touched = _install_merge_conversations_stubs()
    saved.update(snapshot_sys_modules(touched))
    from utils.conversations.merge_conversations import _delete_conversation_and_related_data

    globals()["_delete_conversation_and_related_data"] = _delete_conversation_and_related_data
    yield
    # Attribute patches on real modules are not undone by restore_sys_modules; put
    # them back explicitly so a later suite still sees the real helpers.
    for module_name, attr in (
        ("database.conversations", "delete_conversation"),
        ("database.conversations", "delete_conversation_photos"),
        ("database.action_items", "delete_action_items_for_conversation"),
        ("database.action_items", "get_action_items_by_conversation"),
    ):
        module = sys.modules.get(module_name)
        original = _ORIGINAL_ATTRS.get((module_name, attr))
        if module is not None and original is not None:
            setattr(module, attr, original)
    restore_sys_modules(saved)
    # Drop the freshly imported merge modules too: a later file that imports them
    # would otherwise bind this process's copy with this file's patched seams gone.
    for _modname in ["utils.conversations.merge_conversations", "utils.conversations"]:
        _existing = sys.modules.get(_modname)
        if _existing is not None and getattr(_existing, "__file__", None):
            del sys.modules[_modname]


@pytest.fixture(autouse=True)
def _reinstall_stubs():
    _install_merge_conversations_stubs()


def _delete_source_with_tasks(tasks):
    """Run the source cleanup over one source's stored tasks."""
    notifications = ModuleType("utils.notifications")
    notifications.sync_action_item_reminder = MagicMock()
    service = MagicMock()

    with patch("utils.conversations.merge_conversations.retraction_can_be_skipped", return_value=True), patch(
        "utils.conversations.merge_conversations.MemoryService", return_value=service
    ), patch.object(
        sys.modules["database.action_items"], "get_action_items_by_conversation", return_value=list(tasks)
    ), patch.dict(
        "sys.modules", {"utils.notifications": notifications}
    ):
        _delete_conversation_and_related_data("uid-any", "conv-1")

    return notifications.sync_action_item_reminder


def test_a_deleted_source_task_cancels_its_reminder():
    due = "2026-09-21T09:00:00+00:00"
    cancel = _delete_source_with_tasks(
        [
            {"id": "task-open", "description": "Send the budget", "due_at": due, "completed": False},
            {"id": "task-done", "description": "Old item", "due_at": due, "completed": True},
            {"id": "task-undated", "description": "No deadline", "due_at": None, "completed": False},
        ]
    )

    cancel.assert_called_once_with(
        user_id="uid-any", action_item_id="task-open", description="", completed=True, due_at=None
    )


def test_a_source_without_open_dated_tasks_sends_nothing():
    cancel = _delete_source_with_tasks([{"id": "task-undated", "description": "No deadline", "due_at": None}])

    cancel.assert_not_called()

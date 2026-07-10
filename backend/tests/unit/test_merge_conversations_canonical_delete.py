"""Canonical vs legacy memory delete routing in merge conversation cleanup."""

from __future__ import annotations

import os
import sys
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


def _install_merge_conversations_stubs() -> list[str]:
    touched = install_ws_i_heavy_import_stubs()
    conversations_mod = sys.modules["database.conversations"]
    conversations_mod.delete_conversation = MagicMock()
    conversations_mod.delete_conversation_photos = MagicMock()
    memories_mod = sys.modules["database.memories"]
    memories_mod.delete_memories_for_conversation = MagicMock()
    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.delete_action_items_for_conversation = MagicMock()

    sys.modules["utils.other.storage"] = AutoMockModule("utils.other.storage")
    touched.append("utils.other.storage")

    for _modname in ["utils.conversations", "utils.conversations.merge_conversations"]:
        _existing = sys.modules.get(_modname)
        if _existing is not None and not getattr(_existing, "__file__", None):
            del sys.modules[_modname]
    return list(dict.fromkeys(touched))


@pytest.fixture(scope="module", autouse=True)
def _merge_conversations_import_isolation():
    saved = snapshot_sys_modules(["database._client"])
    install_database_client_stub()
    touched = _install_merge_conversations_stubs()
    saved.update(snapshot_sys_modules(touched))
    from utils.conversations.merge_conversations import _delete_conversation_and_related_data
    from utils.memory.memory_system import MemorySystem

    globals()["_delete_conversation_and_related_data"] = _delete_conversation_and_related_data
    globals()["MemorySystem"] = MemorySystem
    yield
    restore_sys_modules(saved)


@pytest.fixture(autouse=True)
def _reinstall_merge_conversations_stubs():
    _install_merge_conversations_stubs()


def test_delete_conversation_related_data_routes_canonical_to_retract():
    service = MagicMock()
    legacy_delete = sys.modules["database.memories"].delete_memories_for_conversation
    legacy_delete.reset_mock()

    with patch(
        "utils.conversations.merge_conversations.pin_memory_system",
        return_value=MemorySystem.CANONICAL,
    ):
        with patch("utils.conversations.merge_conversations.canonical_write_enabled", return_value=True):
            with patch("utils.conversations.merge_conversations.MemoryService", return_value=service):
                _delete_conversation_and_related_data("uid-canonical", "conv-1")

    service.retract_conversation_memories.assert_called_once_with("uid-canonical", "conv-1")
    legacy_delete.assert_not_called()


def test_delete_conversation_related_data_routes_legacy_to_memories_db():
    service = MagicMock()
    legacy_delete = sys.modules["database.memories"].delete_memories_for_conversation
    legacy_delete.reset_mock()

    with patch(
        "utils.conversations.merge_conversations.pin_memory_system",
        return_value=MemorySystem.LEGACY,
    ):
        with patch("utils.conversations.merge_conversations.MemoryService", return_value=service):
            _delete_conversation_and_related_data("uid-legacy", "conv-1")

    legacy_delete.assert_called_once_with("uid-legacy", "conv-1")
    service.retract_conversation_memories.assert_not_called()

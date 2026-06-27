"""Canonical vs legacy memory delete routing in merge conversation cleanup."""

import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _ensure_stub(name):
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None):
        return existing
    if existing is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


_ensure_stub("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], "__path__", [])
for _sub in ["_client", "conversations", "vector_db", "memories", "action_items"]:
    _ensure_stub(f"database.{_sub}")
sys.modules["database._client"].db = MagicMock()
sys.modules["database.conversations"].delete_conversation = MagicMock()
sys.modules["database.conversations"].delete_conversation_photos = MagicMock()
sys.modules["database.vector_db"].delete_vector = MagicMock()
sys.modules["database.memories"].delete_memories_for_conversation = MagicMock()
sys.modules["database.action_items"].delete_action_items_for_conversation = MagicMock()

import utils  # noqa: F401, E402
import utils.other  # noqa: F401, E402

_fake_storage = types.ModuleType("utils.other.storage")
for _name in [
    "delete_conversation_audio_files",
    "list_audio_chunks",
    "storage_client",
    "private_cloud_sync_bucket",
    "_get_extension_for_path",
]:
    setattr(_fake_storage, _name, MagicMock())
sys.modules["utils.other.storage"] = _fake_storage

for _modname in ["utils.conversations", "utils.conversations.merge_conversations"]:
    _existing = sys.modules.get(_modname)
    if _existing is not None and not getattr(_existing, "__file__", None):
        del sys.modules[_modname]

from utils.conversations.merge_conversations import _delete_conversation_and_related_data  # noqa: E402
from utils.memory.memory_system import MemorySystem  # noqa: E402


def test_delete_conversation_related_data_routes_canonical_to_retract():
    service = MagicMock()
    legacy_delete = sys.modules["database.memories"].delete_memories_for_conversation
    legacy_delete.reset_mock()

    with patch(
        "utils.conversations.merge_conversations.pin_memory_system",
        return_value=MemorySystem.CANONICAL,
    ):
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

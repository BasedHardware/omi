import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is None:
            parent = types.ModuleType(parent_name)
            parent.__path__ = []
            sys.modules[parent_name] = parent
        setattr(parent, attr_name, mod)
    return mod


conversations_db_stub = _stub_module("database.conversations")
conversations_db_stub.list_expired_trashed = MagicMock(return_value=[])
conversations_db_stub.delete_conversation = MagicMock()

memories_db_stub = _stub_module("database.memories")
memories_db_stub.get_memory_ids_for_conversation = MagicMock(return_value=[])
memories_db_stub.delete_memories_for_conversation = MagicMock()

action_items_db_stub = _stub_module("database.action_items")
action_items_db_stub.delete_action_items_for_conversation = MagicMock()

vector_db_stub = _stub_module("database.vector_db")
vector_db_stub.delete_vector = MagicMock()
vector_db_stub.delete_memory_vector = MagicMock()

log_sanitizer_stub = _stub_module("utils.log_sanitizer")
log_sanitizer_stub.sanitize_pii = MagicMock(side_effect=lambda value: value)

utils_other_stub = _stub_module("utils.other")
utils_other_stub.__path__ = [str(BACKEND_DIR / "utils" / "other")]

storage_stub = _stub_module("utils.other.storage")
storage_stub.delete_conversation_audio_files = MagicMock()
utils_other_stub.storage = storage_stub

sys.modules.pop("utils.other.purge_trashed", None)
import utils.other.purge_trashed as purge_trashed


@pytest.fixture(autouse=True)
def reset_mocks():
    conversations_db_stub.list_expired_trashed.reset_mock(return_value=True, side_effect=True)
    conversations_db_stub.list_expired_trashed.return_value = []
    conversations_db_stub.delete_conversation.reset_mock(side_effect=True)
    memories_db_stub.get_memory_ids_for_conversation.reset_mock(return_value=True, side_effect=True)
    memories_db_stub.get_memory_ids_for_conversation.return_value = []
    memories_db_stub.delete_memories_for_conversation.reset_mock(side_effect=True)
    action_items_db_stub.delete_action_items_for_conversation.reset_mock(side_effect=True)
    vector_db_stub.delete_vector.reset_mock(side_effect=True)
    vector_db_stub.delete_memory_vector.reset_mock(side_effect=True)
    log_sanitizer_stub.sanitize_pii.reset_mock(side_effect=True)
    log_sanitizer_stub.sanitize_pii.side_effect = lambda value: value
    storage_stub.delete_conversation_audio_files.reset_mock(side_effect=True)
    purge_trashed.logger = MagicMock()
    yield


def test_should_run_purge_trashed_job_at_3am():
    assert purge_trashed.should_run_purge_trashed_job(datetime(2026, 5, 6, 3, tzinfo=timezone.utc)) is True

    for hour in [0, 1, 2, 4, 12, 23]:
        assert purge_trashed.should_run_purge_trashed_job(datetime(2026, 5, 6, hour, tzinfo=timezone.utc)) is False


def test_purge_does_not_touch_recent():
    now = datetime(2026, 5, 6, 12, tzinfo=timezone.utc)
    recent_trashed_at = now - timedelta(days=29)

    def list_expired(cutoff):
        assert recent_trashed_at >= cutoff
        return []

    conversations_db_stub.list_expired_trashed.side_effect = list_expired

    purged_count = purge_trashed.purge_expired_trashed_conversations(now)

    assert purged_count == 0
    conversations_db_stub.delete_conversation.assert_not_called()
    vector_db_stub.delete_vector.assert_not_called()
    storage_stub.delete_conversation_audio_files.assert_not_called()
    memories_db_stub.delete_memories_for_conversation.assert_not_called()
    action_items_db_stub.delete_action_items_for_conversation.assert_not_called()


def test_purge_removes_expired():
    now = datetime(2026, 5, 6, 12, tzinfo=timezone.utc)
    conversations_db_stub.list_expired_trashed.return_value = [("uid-1", "conv-1")]
    memories_db_stub.get_memory_ids_for_conversation.return_value = ["mem-1", "mem-2"]

    purged_count = purge_trashed.purge_expired_trashed_conversations(now)

    assert purged_count == 1
    conversations_db_stub.list_expired_trashed.assert_called_once_with(now - timedelta(days=30))
    conversations_db_stub.delete_conversation.assert_called_once_with("uid-1", "conv-1")
    vector_db_stub.delete_vector.assert_called_once_with("uid-1", "conv-1")
    storage_stub.delete_conversation_audio_files.assert_called_once_with("uid-1", "conv-1")
    memories_db_stub.get_memory_ids_for_conversation.assert_called_once_with("uid-1", "conv-1")
    memories_db_stub.delete_memories_for_conversation.assert_called_once_with("uid-1", "conv-1")
    vector_db_stub.delete_memory_vector.assert_has_calls([call("uid-1", "mem-1"), call("uid-1", "mem-2")])
    action_items_db_stub.delete_action_items_for_conversation.assert_called_once_with("uid-1", "conv-1")


def test_purge_continues_on_error():
    now = datetime(2026, 5, 6, 12, tzinfo=timezone.utc)
    conversations_db_stub.list_expired_trashed.return_value = [("uid-bad", "conv-bad"), ("uid-good", "conv-good")]
    conversations_db_stub.delete_conversation.side_effect = [RuntimeError("delete failed"), None]

    purged_count = purge_trashed.purge_expired_trashed_conversations(now)

    assert purged_count == 1
    conversations_db_stub.delete_conversation.assert_has_calls(
        [call("uid-bad", "conv-bad"), call("uid-good", "conv-good")]
    )
    vector_db_stub.delete_vector.assert_called_once_with("uid-good", "conv-good")
    purge_trashed.logger.exception.assert_called_once()
    purge_trashed.logger.info.assert_called_once()

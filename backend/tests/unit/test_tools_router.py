"""Tests for /v1/tools/* REST router and shared service functions.

Covers:
1. get_conversations_text — date parsing, limit caps, empty results
2. search_conversations_text — query routing, date conversion to timestamps
3. get_memories_text — date parsing, locked memory filtering
4. search_memories_text — vector search delegation
5. get_action_items_text — date parsing, status filtering
6. create_action_item_text — validation, default due date, past-date rejection
7. update_action_item_text — exists check, field updates
8. Router _ok envelope — is_error flag detection
"""

import importlib
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


def _load_module_from_file(module_name, file_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing anything from backend
# ---------------------------------------------------------------------------
for mod_name in [
    "firebase_admin",
    "firebase_admin.firestore",
    "firebase_admin.auth",
    "firebase_admin.messaging",
    "firebase_admin.credentials",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.cloud.storage",
    "opuslib",
    "sentry_sdk",
    "database._client",
    "database.redis_db",
    "database.auth",
]:
    if mod_name not in sys.modules:
        _stub_module(mod_name)

# Stub database packages
_stub_package("database")

# Stub database.conversations
conversations_db = _stub_module("database.conversations")
conversations_db.get_conversations = MagicMock(return_value=[])
conversations_db.get_conversations_by_id = MagicMock(return_value=[])

# Stub database.users
users_db = _stub_module("database.users")
users_db.get_people_by_ids = MagicMock(return_value=[])

# Stub database.memories
memories_db = _stub_module("database.memories")
memories_db.get_memories = MagicMock(return_value=[])
memories_db.get_memories_by_ids = MagicMock(return_value=[])

# Stub database.vector_db
vector_db = _stub_module("database.vector_db")
vector_db.query_vectors = MagicMock(return_value=[])
vector_db.find_similar_memories = MagicMock(return_value=[])

# Stub database.action_items
action_items_db = _stub_module("database.action_items")
action_items_db.get_action_items = MagicMock(return_value=[])
action_items_db.get_action_item = MagicMock(return_value=None)
action_items_db.create_action_item = MagicMock(return_value="test-item-id")
action_items_db.update_action_item = MagicMock(return_value=True)

# Stub notifications
notif_mod = _stub_module("utils.notifications")
notif_mod.send_action_item_completed_notification = MagicMock()
notif_mod.send_action_item_created_notification = MagicMock()
notif_mod.send_action_item_data_message = MagicMock()

# Stub utils packages
_stub_package("utils")
_stub_package("utils.retrieval")
_stub_package("utils.retrieval.tool_services")
_stub_package("utils.other")
endpoints_mod = _stub_module("utils.other.endpoints")
endpoints_mod.get_current_user_uid = MagicMock()

# Stub routers package
_stub_package("routers")

# Stub models
_stub_package("models")

# Stub Conversation model
conversation_mod = _stub_module("models.conversation")


class FakeConversation:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 'test-conv-id')
        self.transcript_segments = kwargs.get('transcript_segments', [])

    def dict(self):
        return {'id': self.id}

    @staticmethod
    def conversations_to_string(convs, use_transcript=True, include_timestamps=False, people=None):
        return f"[{len(convs)} conversations formatted]"


conversation_mod.Conversation = FakeConversation

# Stub Person model
other_mod = _stub_module("models.other")


class FakePerson:
    def __init__(self, **kwargs):
        pass


other_mod.Person = FakePerson

# Stub MemoryDB model
from enum import Enum


class FakeCategory(Enum):
    other = "other"


memories_model_mod = _stub_module("models.memories")


class FakeMemoryDB:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 'test-mem-id')
        self.content = kwargs.get('content', 'test memory')
        self.category = FakeCategory.other
        self.created_at = kwargs.get('created_at', datetime.now(timezone.utc))

    @staticmethod
    def get_memories_as_str(memories):
        return '\n'.join(f"- {m.content}" for m in memories)


memories_model_mod.MemoryDB = FakeMemoryDB

# ---------------------------------------------------------------------------
# Add backend to path and load service modules
# ---------------------------------------------------------------------------
sys.path.insert(0, str(BACKEND_DIR))

# Now load the shared service modules
conversations_svc = _load_module_from_file(
    "utils.retrieval.tool_services.conversations",
    BACKEND_DIR / "utils" / "retrieval" / "tool_services" / "conversations.py",
)
memories_svc = _load_module_from_file(
    "utils.retrieval.tool_services.memories",
    BACKEND_DIR / "utils" / "retrieval" / "tool_services" / "memories.py",
)
action_items_svc = _load_module_from_file(
    "utils.retrieval.tool_services.action_items",
    BACKEND_DIR / "utils" / "retrieval" / "tool_services" / "action_items.py",
)


# ===========================================================================
# Tests: parse_iso_date
# ===========================================================================
class TestParseIsoDate:
    def test_valid_utc(self):
        dt = conversations_svc.parse_iso_date("2024-06-15T10:00:00Z", "test")
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.tzinfo is not None

    def test_valid_offset(self):
        dt = conversations_svc.parse_iso_date("2024-06-15T10:00:00-08:00", "test")
        assert dt.year == 2024
        assert dt.tzinfo is not None

    def test_missing_timezone_raises(self):
        with pytest.raises(ValueError, match="must include timezone"):
            conversations_svc.parse_iso_date("2024-06-15T10:00:00", "test")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            conversations_svc.parse_iso_date("not-a-date", "test")


# ===========================================================================
# Tests: get_conversations_text
# ===========================================================================
class TestGetConversationsText:
    def setup_method(self):
        conversations_db.get_conversations.reset_mock()
        conversations_db.get_conversations.return_value = []

    def test_empty_result(self):
        result = conversations_svc.get_conversations_text(uid="test-uid")
        assert "No conversations found" in result

    def test_empty_with_date_range(self):
        result = conversations_svc.get_conversations_text(
            uid="test-uid",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-31T23:59:59Z",
        )
        assert "No conversations found" in result
        assert "2024-01" in result

    def test_invalid_start_date(self):
        result = conversations_svc.get_conversations_text(uid="test-uid", start_date="bad-date")
        assert "Error" in result

    def test_limit_cap(self):
        conversations_svc.get_conversations_text(uid="test-uid", limit=99999)
        call_kwargs = conversations_db.get_conversations.call_args
        assert call_kwargs[1]['limit'] <= 5000

    def test_with_conversations(self):
        conversations_db.get_conversations.return_value = [
            {'id': 'conv-1', 'transcript_segments': [], 'title': 'Test'},
        ]
        result = conversations_svc.get_conversations_text(uid="test-uid")
        assert "1 conversations formatted" in result


# ===========================================================================
# Tests: search_conversations_text
# ===========================================================================
class TestSearchConversationsText:
    def setup_method(self):
        vector_db.query_vectors.reset_mock()
        vector_db.query_vectors.return_value = []
        conversations_db.get_conversations_by_id.reset_mock()
        conversations_db.get_conversations_by_id.return_value = []

    def test_no_results(self):
        result = conversations_svc.search_conversations_text(uid="test-uid", query="test query")
        assert "No conversations found" in result
        assert "test query" in result

    def test_invalid_date(self):
        result = conversations_svc.search_conversations_text(uid="test-uid", query="test", start_date="bad")
        assert "Error" in result

    def test_with_results(self):
        vector_db.query_vectors.return_value = ["conv-1"]
        conversations_db.get_conversations_by_id.return_value = [
            {'id': 'conv-1', 'transcript_segments': []},
        ]
        result = conversations_svc.search_conversations_text(uid="test-uid", query="test query")
        assert "Found" in result
        assert "1 conversations formatted" in result


# ===========================================================================
# Tests: get_memories_text
# ===========================================================================
class TestGetMemoriesText:
    def setup_method(self):
        memories_db.get_memories.reset_mock()
        memories_db.get_memories.return_value = []

    def test_empty_result(self):
        result = memories_svc.get_memories_text(uid="test-uid")
        assert "No memories found" in result

    def test_filters_locked(self):
        memories_db.get_memories.return_value = [
            {'id': 'mem-1', 'content': 'visible', 'is_locked': False, 'created_at': datetime.now(timezone.utc)},
            {'id': 'mem-2', 'content': 'locked', 'is_locked': True, 'created_at': datetime.now(timezone.utc)},
        ]
        result = memories_svc.get_memories_text(uid="test-uid")
        assert "1 total" in result

    def test_limit_cap(self):
        memories_svc.get_memories_text(uid="test-uid", limit=99999)
        call_kwargs = memories_db.get_memories.call_args
        assert call_kwargs[1]['limit'] <= 5000


# ===========================================================================
# Tests: search_memories_text
# ===========================================================================
class TestSearchMemoriesText:
    def setup_method(self):
        vector_db.find_similar_memories.reset_mock()
        vector_db.find_similar_memories.return_value = []
        memories_db.get_memories_by_ids.reset_mock()
        memories_db.get_memories_by_ids.return_value = []

    def test_no_results(self):
        result = memories_svc.search_memories_text(uid="test-uid", query="cooking")
        assert "No memories found" in result
        assert "cooking" in result

    def test_with_results(self):
        vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.95},
        ]
        memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'likes pasta', 'is_locked': False, 'created_at': datetime.now(timezone.utc)},
        ]
        result = memories_svc.search_memories_text(uid="test-uid", query="food")
        assert "likes pasta" in result
        assert "0.95" in result


# ===========================================================================
# Tests: get_action_items_text
# ===========================================================================
class TestGetActionItemsText:
    def setup_method(self):
        action_items_db.get_action_items.reset_mock()
        action_items_db.get_action_items.return_value = []

    def test_empty_result(self):
        result = action_items_svc.get_action_items_text(uid="test-uid")
        assert "No" in result and "action items found" in result

    def test_empty_with_completed_filter(self):
        result = action_items_svc.get_action_items_text(uid="test-uid", completed=False)
        assert "pending" in result

    def test_with_items(self):
        action_items_db.get_action_items.return_value = [
            {
                'id': 'ai-1',
                'description': 'Buy groceries',
                'completed': False,
                'created_at': datetime.now(timezone.utc),
                'due_at': datetime.now(timezone.utc) + timedelta(hours=24),
            },
        ]
        result = action_items_svc.get_action_items_text(uid="test-uid")
        assert "Buy groceries" in result
        assert "Pending" in result
        assert "ai-1" in result


# ===========================================================================
# Tests: create_action_item_text
# ===========================================================================
class TestCreateActionItemText:
    def setup_method(self):
        action_items_db.create_action_item.reset_mock()
        action_items_db.create_action_item.return_value = "test-item-id"
        action_items_db.get_action_item.reset_mock()
        action_items_db.get_action_item.return_value = {
            'id': 'test-item-id',
            'description': 'Test task',
            'completed': False,
            'due_at': datetime.now(timezone.utc) + timedelta(hours=24),
        }
        notif_mod.send_action_item_data_message.reset_mock()
        notif_mod.send_action_item_created_notification.reset_mock()

    def test_empty_description_rejected(self):
        result = action_items_svc.create_action_item_text(uid="test-uid", description="")
        assert "Error" in result

    def test_whitespace_description_rejected(self):
        result = action_items_svc.create_action_item_text(uid="test-uid", description="   ")
        assert "Error" in result

    def test_past_due_date_rejected(self):
        past = (datetime.now(timezone.utc) - timedelta(days=5)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = action_items_svc.create_action_item_text(uid="test-uid", description="Test", due_at=past)
        assert "Error" in result
        assert "past" in result.lower()

    def test_success(self):
        result = action_items_svc.create_action_item_text(uid="test-uid", description="Ship feature")
        assert "Added" in result
        assert "Ship feature" in result or "Test task" in result

    def test_invalid_due_format(self):
        result = action_items_svc.create_action_item_text(uid="test-uid", description="Test", due_at="bad-date")
        assert "Error" in result


# ===========================================================================
# Tests: update_action_item_text
# ===========================================================================
class TestUpdateActionItemText:
    def setup_method(self):
        action_items_db.get_action_item.reset_mock()
        action_items_db.update_action_item.reset_mock()
        action_items_db.update_action_item.return_value = True
        notif_mod.send_action_item_completed_notification.reset_mock()

    def test_empty_id_rejected(self):
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="")
        assert "Error" in result

    def test_nonexistent_item(self):
        action_items_db.get_action_item.return_value = None
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="bad-id")
        assert "not found" in result.lower()

    def test_no_changes(self):
        action_items_db.get_action_item.return_value = {'id': 'ai-1', 'description': 'Test'}
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="ai-1")
        assert "No changes" in result

    def test_mark_completed(self):
        action_items_db.get_action_item.return_value = {'id': 'ai-1', 'description': 'Test'}
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="ai-1", completed=True)
        assert "completed" in result.lower()

    def test_update_description(self):
        action_items_db.get_action_item.return_value = {'id': 'ai-1', 'description': 'Old'}
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="ai-1", description="New desc")
        assert "New desc" in result


# ===========================================================================
# Tests: Router envelope
# ===========================================================================
class TestRouterEnvelope:
    """Test the _ok helper in the router module."""

    def test_ok_normal(self):
        # Import the router module
        router_mod = _load_module_from_file(
            "routers.tools",
            BACKEND_DIR / "routers" / "tools.py",
        )
        result = router_mod._ok("test_tool", "All good")
        assert result["tool_name"] == "test_tool"
        assert result["result_text"] == "All good"
        assert result["is_error"] is False

    def test_ok_error(self):
        router_mod = sys.modules["routers.tools"]
        result = router_mod._ok("test_tool", "Error: something went wrong")
        assert result["is_error"] is True

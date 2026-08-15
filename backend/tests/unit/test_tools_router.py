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
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit.memory_import_isolation import restore_sys_modules, snapshot_sys_modules

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
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, mod)
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
#
# Snapshot touched modules first so the stubs installed below do not leak into
# other test files during bulk ``pytest tests/unit/`` collection (issue #8661).
# They are restored right after the modules under test are imported.
# ---------------------------------------------------------------------------
_SYS_MODULE_NAMES = [
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
    "database",
    "database._client",
    "database.redis_db",
    "database.auth",
    "database.conversations",
    "database.users",
    "database.memories",
    "database.vector_db",
    "database.action_items",
    "database.notifications",
    "utils",
    "utils.notifications",
    "utils.conversations",
    "utils.conversations.render",
    "utils.conversations.factory",
    "utils.conversations.search",
    "utils.conversations.transcript_chunks",
    "utils.retrieval",
    "utils.retrieval.tools",
    "utils.retrieval.tools.calendar_tools",
    "utils.retrieval.safety",
    "utils.retrieval.tool_services",
    "utils.retrieval.tool_services.conversations",
    "utils.retrieval.tool_services.memories",
    "utils.retrieval.tool_services.action_items",
    "utils.retrieval.tool_result_boundaries",
    "utils.other",
    "utils.other.endpoints",
    "utils.memory",
    "utils.memory.chat_memory_adapter",
    "utils.memory.default_read_rollout",
    "utils.memory.memory_system",
    "utils.memory.memory_service",
    "utils.rate_limit_config",
    "routers",
    "routers.tools",
    "models",
    "models.conversation",
    "models.other",
    "models.memories",
]
_SYS_MODULES_SNAPSHOT = snapshot_sys_modules(_SYS_MODULE_NAMES)

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
sys.modules["database._client"].db = MagicMock()

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
vector_db.search_transcript_chunks = MagicMock(return_value=[])

# Stub database.action_items
action_items_db = _stub_module("database.action_items")
action_items_db.get_action_items = MagicMock(return_value=[])
action_items_db.get_action_item = MagicMock(return_value=None)
action_items_db.create_action_item = MagicMock(return_value="test-item-id")
action_items_db.update_action_item = MagicMock(return_value=True)

# Stub database.notifications
notifications_db = _stub_module("database.notifications")
notifications_db.get_user_time_zone = MagicMock(return_value="UTC")

# Stub notifications
notif_mod = _stub_module("utils.notifications")
notif_mod.send_action_item_completed_notification = MagicMock()
notif_mod.send_action_item_created_notification = MagicMock()
notif_mod.send_action_item_data_message = MagicMock()
notif_mod.sync_action_item_reminder = MagicMock()

# Stub utils packages
_stub_package("utils")
_stub_package("utils.conversations")
_stub_package("utils.retrieval")
_stub_package("utils.retrieval.tools")
_stub_package("utils.retrieval.tool_services")
_stub_package("utils.other")
_stub_package("utils.memory")

memory_service_stub = _stub_module("utils.memory.memory_service")


class FakeMemoryService:
    """Exercise the universal service contract while keeping this router suite hermetic."""

    def __init__(self, *, db_client=None):
        self.db_client = db_client

    def read(self, uid, *, limit=100, offset=0, now=None):
        del now
        return [FakeMemoryDB(**row) for row in memories_db.get_memories(uid, limit=limit, offset=offset)]

    def search(self, uid, query, *, limit=5):
        rows = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=limit)
        ids = [row["memory_id"] for row in rows]
        scores = {row["memory_id"]: float(row.get("score", 0.0)) for row in rows}
        hydrated = {
            row["id"]: FakeMemoryDB(**row)
            for row in memories_db.get_memories_by_ids(uid, ids)
            if not row.get("is_locked", False)
        }
        return [
            types.SimpleNamespace(memory=hydrated[memory_id], score=scores[memory_id])
            for memory_id in ids
            if memory_id in hydrated
        ]


memory_service_stub.MemoryService = FakeMemoryService
boundary_stub = _stub_module("utils.retrieval.tool_result_boundaries")
boundary_stub.preserve_chat_memory_tool_result_boundary = MagicMock(side_effect=lambda _tool_name, result: result)


class FakeCalendarEventTool:
    def __init__(self):
        self.calls = []
        self.next_result = None

    async def ainvoke(self, tool_input, config=None):
        self.calls.append((tool_input, config))
        if self.next_result is not None:
            result = self.next_result
            self.next_result = None
            return result
        return f"✅ Successfully created calendar event: {tool_input['title']}"


calendar_tools_mod = _stub_module("utils.retrieval.tools.calendar_tools")
calendar_tools_mod.create_calendar_event_tool = FakeCalendarEventTool()

# Stub render and factory modules
render_mod = _stub_module("utils.conversations.render")


def _stub_resolve_display_tz(tz):
    if tz:
        try:
            return ZoneInfo(tz), tz
        except Exception:
            pass
    return timezone.utc, "UTC"


def _stub_format_local_time(dt, display_tz, tz_label):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return f"{dt.astimezone(display_tz).strftime('%Y-%m-%d %H:%M:%S')} {tz_label}"


def _stub_format_local_date(dt, display_tz):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(display_tz).strftime('%Y-%m-%d')


render_mod.resolve_display_tz = _stub_resolve_display_tz
render_mod.format_local_time = _stub_format_local_time
render_mod.format_local_date = _stub_format_local_date
render_mod.conversations_to_string = MagicMock(
    side_effect=lambda convs, **kw: f"[{len(convs)} conversations formatted]"
)
factory_mod = _stub_module("utils.conversations.factory")
factory_mod.deserialize_conversation = MagicMock(
    side_effect=lambda d: d if not isinstance(d, dict) else type('FakeConv', (), d)()
)
search_mod = _stub_module("utils.conversations.search")
search_mod.keyword_search_conversation_ids = MagicMock(return_value=[])
search_mod.parse_exact_conversation_reference = MagicMock(return_value=None)
search_mod.conversation_matches_date_range = MagicMock(return_value=True)


def _merge_conversation_search_ids(keyword_ids, vector_ids):
    return list(keyword_ids) + [cid for cid in vector_ids if cid not in keyword_ids]


search_mod.merge_conversation_search_ids = MagicMock(side_effect=_merge_conversation_search_ids)
transcript_chunks_mod = _stub_module("utils.conversations.transcript_chunks")


def _hydrate_chunk_texts(_uid, conversations):
    return conversations


transcript_chunks_mod.hydrate_chunk_texts = MagicMock(side_effect=_hydrate_chunk_texts)


@pytest.fixture(autouse=True)
def reset_conversation_search_stubs():
    search_mod.keyword_search_conversation_ids.reset_mock()
    search_mod.keyword_search_conversation_ids.return_value = []
    search_mod.parse_exact_conversation_reference.reset_mock()
    search_mod.parse_exact_conversation_reference.return_value = None
    search_mod.conversation_matches_date_range.reset_mock()
    search_mod.conversation_matches_date_range.return_value = True
    search_mod.merge_conversation_search_ids.reset_mock()
    search_mod.merge_conversation_search_ids.side_effect = _merge_conversation_search_ids
    transcript_chunks_mod.hydrate_chunk_texts.reset_mock()
    transcript_chunks_mod.hydrate_chunk_texts.side_effect = _hydrate_chunk_texts
    vector_db.search_transcript_chunks.reset_mock()
    vector_db.search_transcript_chunks.return_value = []


endpoints_mod = _stub_module("utils.other.endpoints")
endpoints_mod.get_current_user_uid = MagicMock()
endpoints_mod.with_rate_limit = MagicMock(return_value=MagicMock())

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
        self.memory_id = kwargs.get('memory_id', self.id)
        self.content = kwargs.get('content', 'test memory')
        self.category = FakeCategory.other
        self.created_at = kwargs.get('created_at', datetime.now(timezone.utc))
        self.is_locked = kwargs.get('is_locked', False)

    @staticmethod
    def get_memories_as_str(memories):
        return '\n'.join(f"- {m.content}" for m in memories)


memories_model_mod.MemoryDB = FakeMemoryDB

# ---------------------------------------------------------------------------
# Add backend to path and load service modules
# ---------------------------------------------------------------------------
sys.path.insert(0, str(BACKEND_DIR))

# Now load the shared service modules
retrieval_safety = _load_module_from_file(
    "utils.retrieval.safety",
    BACKEND_DIR / "utils" / "retrieval" / "safety.py",
)
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
router_mod = _load_module_from_file(
    "routers.tools",
    BACKEND_DIR / "routers" / "tools.py",
)
rate_limit_config_mod = _load_module_from_file(
    "utils.rate_limit_config",
    BACKEND_DIR / "utils" / "rate_limit_config.py",
)

# Restore sys.modules now that the modules under test are imported and bound to
# their stubbed dependencies. Tests below patch those module objects directly.
restore_sys_modules(_SYS_MODULES_SNAPSHOT)
del _SYS_MODULES_SNAPSHOT, _SYS_MODULE_NAMES


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

    def test_space_to_plus_recovery_positive_offset(self):
        """URL decoding converts + to space; parse_iso_date should recover it."""
        dt = conversations_svc.parse_iso_date("2026-02-01T00:00:00 07:00", "test")
        assert dt.year == 2026
        assert dt.utcoffset().total_seconds() == 7 * 3600

    def test_space_to_plus_recovery_utc(self):
        """Space before 00:00 at end should be recovered to +00:00."""
        dt = conversations_svc.parse_iso_date("2026-02-01T00:00:00 00:00", "test")
        assert dt.utcoffset().total_seconds() == 0

    def test_negative_offset_unchanged(self):
        """Negative offsets (-07:00) should not be affected by recovery."""
        dt = conversations_svc.parse_iso_date("2026-02-01T00:00:00-07:00", "test")
        assert dt.utcoffset().total_seconds() == -7 * 3600

    def test_valid_plus_still_works(self):
        """Normal +07:00 (not URL-corrupted) should still parse fine."""
        dt = conversations_svc.parse_iso_date("2026-02-01T00:00:00+07:00", "test")
        assert dt.utcoffset().total_seconds() == 7 * 3600

    def test_z_suffix_still_works(self):
        """Z suffix should still parse as UTC."""
        dt = conversations_svc.parse_iso_date("2026-02-01T00:00:00Z", "test")
        assert dt.utcoffset().total_seconds() == 0

    def test_malformed_still_raises(self):
        """Truly malformed dates should still raise ValueError."""
        with pytest.raises(ValueError):
            conversations_svc.parse_iso_date("2026-13-01T00:00:00+07:00", "test")

    def test_double_space_date_time_and_tz(self):
        """Date with space separator AND URL-corrupted tz: '2026-02-01 00:00:00 07:00'.
        Regex only replaces trailing ' HH:MM', so result is '2026-02-01 00:00:00+07:00'
        which is valid ISO (space between date and time is allowed)."""
        dt = conversations_svc.parse_iso_date("2026-02-01 00:00:00 07:00", "test")
        assert dt.year == 2026
        assert dt.utcoffset().total_seconds() == 7 * 3600

    def test_space_before_plus_accepted_by_python(self):
        """'2026-02-01T00:00:00 +07:00' — Python 3.11+ fromisoformat accepts space before offset.
        Regex does NOT match (ends with +07:00 not ' HH:MM'), but fromisoformat handles it natively."""
        dt = conversations_svc.parse_iso_date("2026-02-01T00:00:00 +07:00", "test")
        assert dt.utcoffset().total_seconds() == 7 * 3600

    def test_trailing_whitespace_not_recovered(self):
        """Trailing whitespace after offset should not be recovered."""
        with pytest.raises(ValueError):
            conversations_svc.parse_iso_date("2026-02-01T00:00:00 07:00 ", "test")

    def test_source_has_encode_query_date(self):
        """Verify desktop tool routes preserve plus-sign timezone offsets."""
        source_root = BACKEND_DIR.parent / "desktop" / "macos" / "Desktop" / "Sources"
        paths = sorted(source_root.rglob("APIClient*.swift"))
        if not paths:
            pytest.skip("APIClient sources not found (backend-only test environment)")
        source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        assert 'func encodeQueryDate' in source, "encodeQueryDate helper must exist in the APIClient extension set"
        # 8 call sites + 1 definition = at least 9 occurrences
        count = source.count('encodeQueryDate(')
        assert count >= 9, f"Expected >= 9 encodeQueryDate( occurrences (1 def + 8 calls), got {count}"


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

    def test_source_mapping_matches_search_results(self):
        conversation = {
            'id': 'conv-1',
            'transcript_segments': [],
            'structured': types.SimpleNamespace(title='Shared title', overview='Shared overview'),
            'created_at': datetime(2026, 8, 13, tzinfo=timezone.utc),
        }
        conversations_db.get_conversations.return_value = [conversation]
        list_sources = []
        conversations_svc.get_conversations_text(uid="test-uid", source_sink=list_sources)

        vector_db.query_vectors.return_value = ['conv-1']
        conversations_db.get_conversations_by_id.return_value = [conversation]
        search_sources = []
        conversations_svc.search_conversations_text(uid="test-uid", query="shared", source_sink=search_sources)

        assert (
            list_sources
            == search_sources
            == [
                {
                    'kind': 'conversation',
                    'source_id': 'conv-1',
                    'title': 'Shared title',
                    'preview': 'Shared overview',
                    'created_at': '2026-08-13T00:00:00+00:00',
                }
            ]
        )


class TestGetConversationsTextMalformedPerson:
    def setup_method(self):
        conversations_db.get_conversations.reset_mock()
        conversations_db.get_conversations.return_value = []
        users_db.get_people_by_ids.reset_mock()
        users_db.get_people_by_ids.return_value = []
        render_mod.conversations_to_string.reset_mock()

    def test_malformed_person_is_skipped_not_500(self):
        """A legacy person doc missing the required name must be skipped, not 500 the whole list.

        Before the fix, Person(**p) raised out of the unguarded people list-comp and, via the
        unguarded GET /v1/tools/conversations handler, surfaced as HTTP 500 for the entire response.
        Now the bad person is skipped (and logged) and the conversations still return with the good
        speaker resolved.
        """
        conversations_db.get_conversations.return_value = [
            {'id': 'conv-1', 'transcript_segments': [{'person_id': 'p-good'}, {'person_id': 'p-bad'}], 'title': 'T'},
        ]
        users_db.get_people_by_ids.return_value = [
            {'id': 'p-good', 'name': 'Alice'},
            {'id': 'p-bad'},  # legacy doc missing the required 'name'
        ]

        def fake_person(**kwargs):
            if 'name' not in kwargs:
                raise ValueError("Person requires name")  # stand-in for pydantic ValidationError
            return types.SimpleNamespace(**kwargs)

        with patch.object(conversations_svc, 'Person', side_effect=fake_person):
            result = conversations_svc.get_conversations_text(uid="test-uid")

        assert "1 conversations formatted" in result  # completed without raising -> no 500
        people_arg = render_mod.conversations_to_string.call_args.kwargs['people']
        assert [pp.name for pp in people_arg] == ['Alice']  # malformed person skipped, good one kept


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

    def test_exact_reference_bypasses_keyword_and_vector_search(self):
        conversation_id = "e8c05000-52f0-4a95-951c-ccd715523429"
        search_mod.parse_exact_conversation_reference.return_value = conversation_id
        conversations_db.get_conversations_by_id.return_value = [
            {'id': conversation_id, 'transcript_segments': [], 'is_locked': False},
        ]

        result = conversations_svc.search_conversations_text(
            uid="test-uid", query=f"https://h.omi.me/conversations/{conversation_id}"
        )

        assert "matching exactly" in result
        assert "1 conversations formatted" in result
        search_mod.keyword_search_conversation_ids.assert_not_called()
        vector_db.query_vectors.assert_not_called()
        conversations_db.get_conversations_by_id.assert_called_once_with("test-uid", [conversation_id])

    def test_exact_reference_respects_date_filter(self):
        conversation_id = "e8c05000-52f0-4a95-951c-ccd715523429"
        search_mod.parse_exact_conversation_reference.return_value = conversation_id
        search_mod.conversation_matches_date_range.return_value = False
        conversations_db.get_conversations_by_id.return_value = [
            {'id': conversation_id, 'transcript_segments': [], 'is_locked': False},
        ]

        result = conversations_svc.search_conversations_text(
            uid="test-uid", query=conversation_id, start_date="2026-01-01T00:00:00Z"
        )

        assert "No conversations found" in result
        search_mod.keyword_search_conversation_ids.assert_not_called()
        vector_db.query_vectors.assert_not_called()

    def test_start_date_only_sets_ends_at(self):
        """One-sided date: start_date only should set ends_at to avoid $lte: None."""
        conversations_svc.search_conversations_text(uid="test-uid", query="test", start_date="2024-06-01T00:00:00Z")
        call_kwargs = vector_db.query_vectors.call_args
        assert call_kwargs[1]['starts_at'] is not None
        assert call_kwargs[1]['ends_at'] is not None

    def test_end_date_only_sets_starts_at(self):
        """One-sided date: end_date only should set starts_at to 0."""
        conversations_svc.search_conversations_text(uid="test-uid", query="test", end_date="2024-12-31T23:59:59Z")
        call_kwargs = vector_db.query_vectors.call_args
        assert call_kwargs[1]['starts_at'] == 0
        assert call_kwargs[1]['ends_at'] is not None


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

    def test_filters_locked_items(self):
        action_items_db.get_action_items.return_value = [
            {'id': 'ai-1', 'description': 'Visible', 'completed': False, 'is_locked': False},
            {'id': 'ai-2', 'description': 'Locked', 'completed': False, 'is_locked': True},
        ]
        result = action_items_svc.get_action_items_text(uid="test-uid")
        assert "Visible" in result
        assert "Locked" not in result
        assert "1 total" in result


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
        calendar_tools_mod.create_calendar_event_tool.calls.clear()
        notif_mod.send_action_item_completed_notification.reset_mock()

    def test_empty_id_rejected(self):
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="")
        assert "Error" in result

    def test_nonexistent_item(self):
        action_items_db.get_action_item.return_value = None
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="bad-id")
        assert "not found" in result.lower()

    def test_locked_item_rejected(self):
        action_items_db.get_action_item.return_value = {'id': 'ai-1', 'description': 'Test', 'is_locked': True}
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="ai-1", completed=True)
        assert "paid plan" in result.lower()

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
        result = router_mod._ok("test_tool", "All good")
        assert result["tool_name"] == "test_tool"
        assert result["result_text"] == "All good"
        assert result["is_error"] is False

    def test_ok_preserves_typed_sources(self):
        source = {
            "kind": "memory",
            "source_id": "memory-1",
            "title": "Memory",
            "preview": "A bounded preview",
        }
        response = router_mod.ToolResponse.model_validate(router_mod._ok("get_memories", "result", [source]))

        assert response.sources == [router_mod.ToolSource(**source)]

    def test_ok_error(self):
        result = router_mod._ok(
            "test_tool",
            "Error: something went wrong",
            [{'kind': 'memory', 'source_id': 'memory-1'}],
        )
        assert result["is_error"] is True
        assert router_mod.ToolResponse.model_validate(result).sources == []

    @pytest.mark.parametrize('url', ['javascript:alert(1)', 'file:///tmp/source', 'example.com/source'])
    def test_tool_source_rejects_non_http_urls(self, url):
        with pytest.raises(ValueError, match=r'absolute HTTP\(S\) URL'):
            router_mod.ToolSource(kind='web', source_id='source-1', url=url)

    @pytest.mark.parametrize('url', ['http://example.com/source', 'https://example.com/source'])
    def test_tool_source_accepts_http_urls(self, url):
        assert router_mod.ToolSource(kind='web', source_id='source-1', url=url).url == url

    def test_shared_safe_isoformat_preserves_iso_and_string_values(self):
        assert (
            retrieval_safety.safe_isoformat(datetime(2026, 8, 13, tzinfo=timezone.utc)) == '2026-08-13T00:00:00+00:00'
        )
        assert retrieval_safety.safe_isoformat('raw-value') == 'raw-value'


# ===========================================================================
# Tests: Router endpoint integration via TestClient
# ===========================================================================
class TestRouterEndpoints:
    """Exercise all 7 REST endpoints through FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def setup_app(self):
        # Override auth dependency
        app = FastAPI()
        app.include_router(router_mod.router)

        # Override auth deps to return a fixed uid
        app.dependency_overrides[endpoints_mod.get_current_user_uid] = lambda: "test-uid"
        # Override rate-limited deps too — with_rate_limit returns a new dependency
        # so we need to override whatever it returned
        for route in app.routes:
            if hasattr(route, 'dependant'):
                for dep in getattr(route, 'dependant', type('', (), {'dependencies': []})()).dependencies:
                    pass
        # Simpler: just override all Depends that resolve to rate-limited uid
        # Since with_rate_limit is mocked to return MagicMock(), we override that mock
        rl_mock = endpoints_mod.with_rate_limit.return_value
        app.dependency_overrides[rl_mock] = lambda: "test-uid"

        self.client = TestClient(app)
        self.router_mod = router_mod

        # Reset mocks
        conversations_db.get_conversations.reset_mock()
        conversations_db.get_conversations.return_value = []
        conversations_db.get_conversations_by_id.reset_mock()
        conversations_db.get_conversations_by_id.return_value = []
        vector_db.query_vectors.reset_mock()
        vector_db.query_vectors.return_value = []
        memories_db.get_memories.reset_mock()
        memories_db.get_memories.return_value = []
        memories_db.get_memories_by_ids.reset_mock()
        memories_db.get_memories_by_ids.return_value = []
        vector_db.find_similar_memories.reset_mock()
        vector_db.find_similar_memories.return_value = []
        action_items_db.get_action_items.reset_mock()
        action_items_db.get_action_items.return_value = []
        action_items_db.get_action_item.reset_mock()
        action_items_db.get_action_item.return_value = None
        action_items_db.create_action_item.reset_mock()
        action_items_db.create_action_item.return_value = "test-item-id"
        action_items_db.update_action_item.reset_mock()
        action_items_db.update_action_item.return_value = True
        calendar_tools_mod.create_calendar_event_tool.calls.clear()
        calendar_tools_mod.create_calendar_event_tool.next_result = None

    def test_get_conversations_endpoint(self):
        resp = self.client.get("/v1/tools/conversations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_name"] == "get_conversations"
        assert "No conversations found" in body["result_text"]

    def test_search_conversations_endpoint(self):
        resp = self.client.post("/v1/tools/conversations/search", json={"query": "test"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_name"] == "search_conversations"

    def test_get_memories_endpoint(self):
        resp = self.client.get("/v1/tools/memories")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_name"] == "get_memories"

    def test_search_memories_endpoint(self):
        resp = self.client.post("/v1/tools/memories/search", json={"query": "food"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_name"] == "search_memories"

    def test_get_action_items_endpoint(self):
        resp = self.client.get("/v1/tools/action-items")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_name"] == "get_action_items"

    def test_create_action_item_endpoint(self):
        action_items_db.create_action_item.return_value = "new-id"
        action_items_db.get_action_item.return_value = {
            'id': 'new-id',
            'description': 'Test task',
            'completed': False,
            'due_at': datetime.now(timezone.utc) + timedelta(hours=24),
        }
        resp = self.client.post("/v1/tools/action-items", json={"description": "Test task"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_name"] == "create_action_item"
        assert "Added" in body["result_text"]

    def test_update_action_item_endpoint(self):
        action_items_db.get_action_item.return_value = {'id': 'ai-1', 'description': 'Task'}
        resp = self.client.patch("/v1/tools/action-items/ai-1", json={"completed": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_name"] == "update_action_item"
        assert "completed" in body["result_text"].lower()

    def test_create_calendar_event_endpoint(self):
        resp = self.client.post(
            "/v1/tools/calendar-events",
            json={
                "title": "Design review",
                "start_time": "2026-06-28T14:00:00-04:00",
                "end_time": "2026-06-28T15:00:00-04:00",
                "location": "Zoom",
                "attendees": "sam@example.com",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_name"] == "create_calendar_event"
        assert "Design review" in body["result_text"]
        assert body["is_error"] is False

        tool_input, config = calendar_tools_mod.create_calendar_event_tool.calls[-1]
        assert tool_input["title"] == "Design review"
        assert tool_input["start_time"] == "2026-06-28T14:00:00-04:00"
        assert tool_input["end_time"] == "2026-06-28T15:00:00-04:00"
        assert tool_input["location"] == "Zoom"
        assert tool_input["attendees"] == "sam@example.com"
        assert config == {"configurable": {"user_id": "test-uid"}}

    def test_create_calendar_event_rejects_malformed_datetimes(self):
        resp = self.client.post(
            "/v1/tools/calendar-events",
            json={
                "title": "Design review",
                "start_time": "tomorrow at 2",
                "end_time": "2026-06-28T15:00:00-04:00",
            },
        )
        assert resp.status_code == 422

    def test_create_calendar_event_requires_timezone(self):
        resp = self.client.post(
            "/v1/tools/calendar-events",
            json={
                "title": "Design review",
                "start_time": "2026-06-28T14:00:00",
                "end_time": "2026-06-28T15:00:00-04:00",
            },
        )
        assert resp.status_code == 422

    def test_create_calendar_event_marks_calendar_tool_failures_as_errors(self):
        calendar_tools_mod.create_calendar_event_tool.next_result = "Google Calendar is not connected."
        resp = self.client.post(
            "/v1/tools/calendar-events",
            json={
                "title": "Design review",
                "start_time": "2026-06-28T14:00:00-04:00",
                "end_time": "2026-06-28T15:00:00-04:00",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_name"] == "create_calendar_event"
        assert body["result_text"] == "Google Calendar is not connected."
        assert body["is_error"] is True

    def test_get_conversations_query_params(self):
        """Query params are forwarded correctly to the service."""
        resp = self.client.get("/v1/tools/conversations?limit=10&offset=5&include_transcript=false")
        assert resp.status_code == 200
        call_kwargs = conversations_db.get_conversations.call_args[1]
        assert call_kwargs['limit'] == 10
        assert call_kwargs['offset'] == 5

    def test_create_action_item_empty_body_rejected(self):
        """Missing required field returns 422."""
        resp = self.client.post("/v1/tools/action-items", json={})
        assert resp.status_code == 422

    def test_search_conversations_missing_query_rejected(self):
        """Missing required query field returns 422."""
        resp = self.client.post("/v1/tools/conversations/search", json={})
        assert resp.status_code == 422

    def test_is_error_propagated_in_envelope(self):
        """Service returning 'Error: ...' sets is_error=True in response envelope."""
        conversations_db.get_conversations.side_effect = None
        conversations_db.get_conversations.return_value = []
        resp = self.client.get("/v1/tools/conversations?start_date=bad-date")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_error"] is True
        assert "Error" in body["result_text"]

    def test_search_chunks_endpoint_returns_typed_sources(self):
        """Route wiring: /search-chunks serializes typed sources through the envelope."""
        vector_db.search_transcript_chunks.return_value = [
            {'conversation_id': 'conv-a', 'chunk_index': 0, 'created_at': 1722500000, 'score': 0.9},
        ]
        transcript_chunks_mod.hydrate_chunk_texts.side_effect = lambda _uid, rows: [
            {
                **r,
                'text': '[Conversation on 01 Aug 2024, 08:53]\nUser: the beta shipped',
                'conversation_title': 'Release chat',
                'conversation_started_at': datetime(2024, 8, 1, 8, 53, tzinfo=timezone.utc),
            }
            for r in rows
        ]
        resp = self.client.post("/v1/tools/conversations/search-chunks", json={"query": "beta"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool_name"] == "search_conversation_chunks"
        assert "User: the beta shipped" in body["result_text"]
        assert body["sources"] == [
            {
                "kind": "conversation",
                "source_id": "conv-a",
                "title": "Release chat",
                "preview": "[Conversation on 01 Aug 2024, 08:53] User: the beta shipped",
                "created_at": "2024-08-01T08:13:20+00:00",
                "moment_timestamp_ms": None,
                "app_name": None,
                "url": None,
            }
        ]


# ===========================================================================
# Tests: search-chunks typed sources (verbatim retrieval layer)
# ===========================================================================
class TestSearchConversationChunksSources:
    """The chunks endpoint must emit sources shaped exactly like its siblings:
    kind 'conversation' + PARENT conversation id (shared ref namespace, no client
    citation-validation changes), a single-line verbatim preview, and an ISO date."""

    def _call(self, query="beta release"):
        body = router_mod.SearchChunksRequest(query=query)
        result = router_mod.search_conversation_chunks(body, uid="test-uid")
        # Validate through the response model so field bounds (preview <= 600,
        # created_at <= 80) are enforced exactly as FastAPI serialization would.
        return router_mod.ToolResponse.model_validate(result)

    def _hydrate_with(self, **fields):
        transcript_chunks_mod.hydrate_chunk_texts.side_effect = lambda _uid, rows: [{**r, **fields} for r in rows]

    def test_sources_carry_parent_conversation_id_and_dedupe_by_conversation(self):
        vector_db.search_transcript_chunks.return_value = [
            {'conversation_id': 'conv-a', 'chunk_index': 2, 'created_at': 1722500000, 'score': 0.91},
            {'conversation_id': 'conv-a', 'chunk_index': 3, 'created_at': 1722500000, 'score': 0.88},
            {'conversation_id': 'conv-b', 'chunk_index': 0, 'created_at': 1722600000, 'score': 0.70},
        ]
        self._hydrate_with(text='User: verbatim evidence', conversation_title='Standup')
        response = self._call()
        assert not response.is_error
        # All three excerpts render, but sources dedupe to one per conversation,
        # best-scored chunk first.
        assert response.result_text.count("Excerpt") == 3
        assert [(s.kind, s.source_id) for s in response.sources] == [
            ("conversation", "conv-a"),
            ("conversation", "conv-b"),
        ]
        assert response.sources[0].title == "Standup"
        assert response.sources[0].created_at == "2024-08-01T08:13:20+00:00"

    def test_preview_is_single_line_and_capped_at_600(self):
        vector_db.search_transcript_chunks.return_value = [
            {'conversation_id': 'conv-a', 'chunk_index': 0, 'created_at': 1722500000, 'score': 0.9},
        ]
        self._hydrate_with(text="line one\nSpeaker 2: line two\n" + ("x" * 700))
        response = self._call()
        preview = response.sources[0].preview
        assert "\n" not in preview
        assert "line one Speaker 2: line two" in preview
        assert len(preview) == 600

    def test_created_at_falls_back_to_conversation_start_when_chunk_ts_missing(self):
        vector_db.search_transcript_chunks.return_value = [
            {'conversation_id': 'conv-a', 'chunk_index': 0, 'created_at': 0, 'score': 0.9},
        ]
        self._hydrate_with(
            text='User: hello',
            conversation_started_at=datetime(2026, 8, 14, 22, 0, tzinfo=timezone.utc),
        )
        response = self._call()
        assert response.sources[0].created_at == "2026-08-14T22:00:00+00:00"

    def test_missing_title_falls_back_without_error(self):
        vector_db.search_transcript_chunks.return_value = [
            {'conversation_id': 'conv-a', 'chunk_index': 0, 'created_at': None, 'score': 0.9},
        ]
        self._hydrate_with(text='User: hello')
        response = self._call()
        assert response.sources[0].title == "Conversation"
        assert response.sources[0].created_at is None

    def test_no_results_returns_empty_sources(self):
        vector_db.search_transcript_chunks.return_value = []
        response = self._call()
        assert response.sources == []
        assert "No transcript excerpts found" in response.result_text


# ===========================================================================
# Tests: Rate limiting policy verification
# ===========================================================================
class TestRateLimitPolicies:
    """Verify rate limit policies exist and are wired correctly."""

    def test_tools_search_policy_exists(self):
        rl_mod = rate_limit_config_mod
        assert "tools:search" in rl_mod.RATE_POLICIES
        max_req, window = rl_mod.RATE_POLICIES["tools:search"]
        assert max_req == 60
        assert window == 3600

    def test_tools_mutate_policy_exists(self):
        rl_mod = rate_limit_config_mod
        assert "tools:mutate" in rl_mod.RATE_POLICIES
        max_req, window = rl_mod.RATE_POLICIES["tools:mutate"]
        assert max_req == 60
        assert window == 3600

    def test_with_rate_limit_called_for_search(self):
        """with_rate_limit was called with 'tools:search' during router import."""
        calls = endpoints_mod.with_rate_limit.call_args_list
        search_calls = [c for c in calls if len(c[0]) >= 2 and c[0][1] == "tools:search"]
        assert len(search_calls) >= 1, "with_rate_limit not called with 'tools:search'"

    def test_with_rate_limit_called_for_mutate(self):
        """with_rate_limit was called with 'tools:mutate' during router import."""
        calls = endpoints_mod.with_rate_limit.call_args_list
        mutate_calls = [c for c in calls if len(c[0]) >= 2 and c[0][1] == "tools:mutate"]
        assert len(mutate_calls) >= 1, "with_rate_limit not called with 'tools:mutate'"


# ===========================================================================
# Tests: Conversation locked item filtering
# ===========================================================================
class TestConversationLockedFiltering:
    def setup_method(self):
        conversations_db.get_conversations.reset_mock()
        conversations_db.get_conversations_by_id.reset_mock()
        vector_db.query_vectors.reset_mock()

    def test_get_conversations_filters_locked(self):
        """Locked conversations are excluded from get results."""
        conversations_db.get_conversations.return_value = [
            {'id': 'conv-1', 'transcript_segments': [], 'is_locked': False},
            {'id': 'conv-2', 'transcript_segments': [], 'is_locked': True},
        ]
        result = conversations_svc.get_conversations_text(uid="test-uid")
        assert "1 conversations formatted" in result

    def test_get_conversations_all_locked_returns_empty(self):
        """All locked conversations returns 'no conversations' message."""
        conversations_db.get_conversations.return_value = [
            {'id': 'conv-1', 'transcript_segments': [], 'is_locked': True},
        ]
        result = conversations_svc.get_conversations_text(uid="test-uid")
        assert "No conversations found" in result

    def test_search_conversations_filters_locked(self):
        """Locked conversations are excluded from search results."""
        vector_db.query_vectors.return_value = ["conv-1", "conv-2"]
        conversations_db.get_conversations_by_id.return_value = [
            {'id': 'conv-1', 'transcript_segments': [], 'is_locked': False},
            {'id': 'conv-2', 'transcript_segments': [], 'is_locked': True},
        ]
        result = conversations_svc.search_conversations_text(uid="test-uid", query="test")
        assert "1 conversations formatted" in result

    def test_search_conversations_all_locked_returns_empty(self):
        """All locked conversations in search returns 'no conversations' message."""
        vector_db.query_vectors.return_value = ["conv-1"]
        conversations_db.get_conversations_by_id.return_value = [
            {'id': 'conv-1', 'transcript_segments': [], 'is_locked': True},
        ]
        result = conversations_svc.search_conversations_text(uid="test-uid", query="test")
        assert "No conversations found" in result


# ===========================================================================
# Tests: Search memories locked filtering
# ===========================================================================
class TestSearchMemoriesLockedFiltering:
    def setup_method(self):
        vector_db.find_similar_memories.reset_mock()
        memories_db.get_memories_by_ids.reset_mock()

    def test_search_memories_filters_locked(self):
        """Locked memories are excluded from search results."""
        vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
            {'memory_id': 'mem-2', 'score': 0.8},
        ]
        memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'visible', 'is_locked': False, 'created_at': datetime.now(timezone.utc)},
            {'id': 'mem-2', 'content': 'locked', 'is_locked': True, 'created_at': datetime.now(timezone.utc)},
        ]
        result = memories_svc.search_memories_text(uid="test-uid", query="test")
        assert "visible" in result
        assert "locked" not in result
        assert "1 memories" in result

    def test_search_memories_all_locked_returns_empty(self):
        """All locked memories in search returns 'no memories' message."""
        vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
        ]
        memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'locked', 'is_locked': True, 'created_at': datetime.now(timezone.utc)},
        ]
        result = memories_svc.search_memories_text(uid="test-uid", query="test")
        assert "No memories found" in result


# ===========================================================================
# Tests: Error handling — DB/vector failures
# ===========================================================================
class TestErrorHandling:
    def setup_method(self):
        conversations_db.get_conversations.reset_mock()
        conversations_db.get_conversations_by_id.reset_mock()
        vector_db.query_vectors.reset_mock()
        memories_db.get_memories.reset_mock()
        vector_db.find_similar_memories.reset_mock()
        action_items_db.get_action_items.reset_mock()
        action_items_db.create_action_item.reset_mock()
        action_items_db.get_action_item.reset_mock()
        action_items_db.update_action_item.reset_mock()

    def test_get_conversations_db_error(self):
        """DB failure in get_conversations returns error text."""
        conversations_db.get_conversations.side_effect = Exception("Firestore unavailable")
        result = conversations_svc.get_conversations_text(uid="test-uid")
        assert "Error" in result
        assert "Firestore unavailable" in result
        conversations_db.get_conversations.side_effect = None

    def test_search_conversations_vector_error(self):
        """Vector DB failure in search returns error text."""
        vector_db.query_vectors.side_effect = Exception("Pinecone timeout")
        result = conversations_svc.search_conversations_text(uid="test-uid", query="test")
        assert "Error" in result
        assert "Pinecone timeout" in result
        vector_db.query_vectors.side_effect = None

    def test_get_memories_db_error(self):
        """DB failure in get_memories returns error text."""
        memories_db.get_memories.side_effect = Exception("Firestore down")
        result = memories_svc.get_memories_text(uid="test-uid")
        assert "Error" in result
        assert "Firestore down" in result
        memories_db.get_memories.side_effect = None

    def test_search_memories_vector_error(self):
        """Vector DB failure in search_memories returns error text."""
        vector_db.find_similar_memories.side_effect = Exception("Vector timeout")
        result = memories_svc.search_memories_text(uid="test-uid", query="test")
        assert "Error" in result
        assert "Vector timeout" in result
        vector_db.find_similar_memories.side_effect = None

    def test_get_action_items_db_error(self):
        """DB failure in get_action_items returns error text."""
        action_items_db.get_action_items.side_effect = Exception("DB connection lost")
        result = action_items_svc.get_action_items_text(uid="test-uid")
        assert "Error" in result
        assert "DB connection lost" in result
        action_items_db.get_action_items.side_effect = None

    def test_create_action_item_db_returns_none(self):
        """create_action_item returning None (failure) returns error text."""
        action_items_db.create_action_item.return_value = None
        result = action_items_svc.create_action_item_text(uid="test-uid", description="Test")
        assert "Error" in result or "Failed" in result
        action_items_db.create_action_item.return_value = "test-item-id"

    def test_create_action_item_db_exception(self):
        """create_action_item raising exception returns error text."""
        action_items_db.create_action_item.side_effect = Exception("Write failed")
        result = action_items_svc.create_action_item_text(uid="test-uid", description="Test")
        assert "Error" in result
        assert "Write failed" in result
        action_items_db.create_action_item.side_effect = None

    def test_update_action_item_db_exception(self):
        """update_action_item raising exception returns error text."""
        action_items_db.get_action_item.return_value = {'id': 'ai-1', 'description': 'Task'}
        action_items_db.update_action_item.side_effect = Exception("Update failed")
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="ai-1", completed=True)
        assert "Error" in result
        assert "Update failed" in result
        action_items_db.update_action_item.side_effect = None

    def test_create_action_item_get_after_create_returns_none(self):
        """Created item can't be retrieved — partial success message."""
        action_items_db.create_action_item.return_value = "new-id"
        action_items_db.get_action_item.return_value = None
        result = action_items_svc.create_action_item_text(uid="test-uid", description="Test")
        assert "created" in result.lower() or "couldn't retrieve" in result.lower()


# ===========================================================================
# Tests: Boundary conditions — limit caps and edge values
# ===========================================================================
class TestBoundaryConditions:
    def setup_method(self):
        conversations_db.get_conversations.reset_mock()
        conversations_db.get_conversations.return_value = []
        vector_db.query_vectors.reset_mock()
        vector_db.query_vectors.return_value = []
        memories_db.get_memories.reset_mock()
        memories_db.get_memories.return_value = []
        vector_db.find_similar_memories.reset_mock()
        vector_db.find_similar_memories.return_value = []
        action_items_db.get_action_items.reset_mock()
        action_items_db.get_action_items.return_value = []

    def test_search_conversations_limit_cap(self):
        """search_conversations_text caps limit at 20."""
        conversations_svc.search_conversations_text(uid="test-uid", query="test", limit=100)
        call_kwargs = vector_db.query_vectors.call_args[1]
        assert call_kwargs['k'] <= 20

    def test_search_memories_limit_cap(self):
        """search_memories_text caps limit at 20."""
        memories_svc.search_memories_text(uid="test-uid", query="test", limit=100)
        call_kwargs = vector_db.find_similar_memories.call_args
        # limit is positional arg 3 or keyword
        assert call_kwargs[1].get('limit', call_kwargs[0][2] if len(call_kwargs[0]) > 2 else 20) <= 20

    def test_action_items_limit_cap(self):
        """get_action_items_text caps limit at 500."""
        action_items_svc.get_action_items_text(uid="test-uid", limit=99999)
        call_kwargs = action_items_db.get_action_items.call_args[1]
        assert call_kwargs['limit'] <= 500

    def test_update_action_item_mark_pending(self):
        """completed=False marks item as pending."""
        action_items_db.get_action_item.reset_mock()
        action_items_db.update_action_item.reset_mock()
        action_items_db.get_action_item.return_value = {'id': 'ai-1', 'description': 'Task', 'completed': True}
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="ai-1", completed=False)
        assert "pending" in result.lower()
        update_data = action_items_db.update_action_item.call_args[0][2]
        assert update_data['completed'] is False
        assert update_data['completed_at'] is None

    def test_update_action_item_due_date(self):
        """due_at update with valid future date succeeds."""
        action_items_db.get_action_item.reset_mock()
        action_items_db.update_action_item.reset_mock()
        action_items_db.get_action_item.return_value = {'id': 'ai-1', 'description': 'Task'}
        future = (datetime.now(timezone.utc) + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="ai-1", due_at=future)
        assert "due date" in result.lower()

    def test_update_action_item_invalid_due_date(self):
        """due_at update with invalid format returns error."""
        action_items_db.get_action_item.reset_mock()
        action_items_db.get_action_item.return_value = {'id': 'ai-1', 'description': 'Task'}
        result = action_items_svc.update_action_item_text(uid="test-uid", action_item_id="ai-1", due_at="not-a-date")
        assert "Error" in result

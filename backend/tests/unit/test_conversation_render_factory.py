"""Tests for the render and factory modules extracted from Conversation class."""

import ast
import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _ensure_stub(name):
    """Create a stub module only if one doesn't already exist with a real __file__."""
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None):
        return existing  # real module, keep it
    if existing is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# Stub database chain so render.py can import at module level without Firestore
_ensure_stub("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], "__path__", [])
for _sub in ["_client", "redis_db", "users", "folders"]:
    _ensure_stub(f"database.{_sub}")
sys.modules["database._client"].db = MagicMock()
sys.modules["database.users"].get_user_profile = MagicMock(return_value={"name": "TestUser"})
sys.modules["database.users"].get_people_by_ids = MagicMock(return_value=[])
sys.modules["database.folders"].get_folders = MagicMock(return_value=[])

# When run via `pytest tests/unit/`, earlier test files may have stubbed these
# packages with empty ModuleType objects. Force-reimport the real ones.
for _mod in [
    "models",
    "models.conversation",
    "models.conversation_enums",
    "models.structured",
    "utils",
    "utils.conversations",
    "utils.conversations.render",
    "utils.conversations.factory",
]:
    _existing = sys.modules.get(_mod)
    if _existing is not None and not getattr(_existing, "__file__", None):
        del sys.modules[_mod]

from models.conversation import AppResult, Conversation
from models.conversation_enums import CategoryEnum
from models.other import Person
from models.structured import ActionItem, Event, Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations.factory import deserialize_conversation, deserialize_conversations
from utils.conversations.render import conversations_to_string


def _make_conversation(**overrides):
    defaults = dict(
        id="test-id",
        created_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc),
        structured=Structured(title="Test Title", overview="Test overview", category=CategoryEnum.personal),
    )
    defaults.update(overrides)
    return Conversation(**defaults)


class TestFactory:
    def test_deserialize_from_dict(self):
        data = {
            "id": "abc",
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "started_at": None,
            "finished_at": None,
            "structured": {"title": "t", "overview": "o"},
        }
        conv = deserialize_conversation(data)
        assert isinstance(conv, Conversation)
        assert conv.id == "abc"

    def test_deserialize_passthrough(self):
        conv = _make_conversation()
        result = deserialize_conversation(conv)
        assert result is conv  # same object, no re-construction

    def test_deserialize_preserves_init_side_effects(self):
        data = {
            "id": "abc",
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "started_at": None,
            "finished_at": None,
            "structured": {"title": "t", "overview": "o"},
            "apps_results": [{"app_id": "app1", "content": "result"}],
            "processing_conversation_id": "proc-123",
        }
        conv = deserialize_conversation(data)
        # __init__ syncs plugins_results from apps_results
        assert len(conv.plugins_results) == 1
        assert conv.plugins_results[0].plugin_id == "app1"
        # __init__ syncs processing_memory_id from processing_conversation_id
        assert conv.processing_memory_id == "proc-123"

    def test_deserialize_conversations_batch(self):
        items = [
            {
                "id": f"id-{i}",
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "started_at": None,
                "finished_at": None,
                "structured": {"title": "t", "overview": "o"},
            }
            for i in range(3)
        ]
        result = deserialize_conversations(items)
        assert len(result) == 3
        assert all(isinstance(c, Conversation) for c in result)
        assert [c.id for c in result] == ["id-0", "id-1", "id-2"]

    def test_deserialize_conversations_mixed(self):
        conv = _make_conversation(id="existing")
        data = {
            "id": "new",
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "started_at": None,
            "finished_at": None,
            "structured": {"title": "t", "overview": "o"},
        }
        result = deserialize_conversations([conv, data])
        assert result[0] is conv
        assert result[1].id == "new"


class TestRender:
    def test_basic_render(self):
        conv = _make_conversation()
        result = conversations_to_string([conv])
        assert "Test title" in result  # .capitalize() lowercases after first char
        assert "Test overview" in result
        assert "15 Jan 2026" in result

    def test_apps_results_override_overview(self):
        conv = _make_conversation(apps_results=[AppResult(app_id="a", content="App output")])
        result = conversations_to_string([conv])
        assert "App output" in result
        assert "Test overview" not in result

    def test_action_items_rendered(self):
        conv = _make_conversation(
            structured=Structured(
                title="t",
                overview="o",
                category=CategoryEnum.personal,
                action_items=[ActionItem(description="Do the thing")],
            )
        )
        result = conversations_to_string([conv])
        assert "Do the thing" in result

    def test_multiple_conversations_separated(self):
        c1 = _make_conversation(id="1")
        c2 = _make_conversation(id="2")
        result = conversations_to_string([c1, c2])
        assert "Conversation #1" in result
        assert "Conversation #2" in result
        assert "---------------------" in result

    def test_empty_list(self):
        result = conversations_to_string([])
        assert result == ""

    def test_events_rendered(self):
        conv = _make_conversation(
            structured=Structured(
                title="t",
                overview="o",
                category=CategoryEnum.personal,
                events=[Event(title="Standup", start=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc), duration=30)],
            )
        )
        result = conversations_to_string([conv])
        assert "Standup" in result
        assert "30 minutes" in result

    def test_attendees_rendered(self):
        conv = _make_conversation(
            transcript_segments=[
                TranscriptSegment(text="hello", speaker_id=0, is_user=False, start=0.0, end=1.0, person_id="p1")
            ]
        )
        people = [Person(id="p1", name="Alice")]
        result = conversations_to_string([conv], people=people)
        assert "Attendees: Alice" in result

    def test_transcript_rendered(self):
        conv = _make_conversation(
            transcript_segments=[TranscriptSegment(text="hello world", speaker_id=0, is_user=True, start=0.0, end=1.0)]
        )
        result = conversations_to_string([conv], use_transcript=True)
        assert "Transcript:" in result
        assert "hello world" in result

    def test_started_finished_rendered(self):
        conv = _make_conversation()
        result = conversations_to_string([conv])
        assert "Started:" in result
        assert "Finished:" in result

    def test_no_started_finished_when_none(self):
        conv = _make_conversation(started_at=None, finished_at=None)
        result = conversations_to_string([conv])
        assert "Started:" not in result
        assert "Finished:" not in result


class TestConversationModelNoRenderMethod:
    """Verify conversations_to_string was removed from the Conversation class."""

    def test_no_conversations_to_string_on_class(self):
        assert not hasattr(Conversation, 'conversations_to_string')

    def test_render_module_not_imported_in_conversation_model(self):
        model_path = os.path.join(os.path.dirname(__file__), '../../models/conversation.py')
        with open(model_path) as f:
            tree = ast.parse(f.read())
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            and any('render' in (getattr(node, 'module', '') or '') for _ in [None])
        ]
        assert len(imports) == 0, "conversation.py should not import from render module"


class TestProductionCallSitesMigrated:
    """Verify production files use render/factory instead of Conversation.conversations_to_string."""

    RENDER_CONSUMERS = [
        'utils/llm/external_integrations.py',
        'utils/apps.py',
        'utils/app_integrations.py',
        'utils/retrieval/rag.py',
        'utils/retrieval/tool_services/conversations.py',
        'utils/retrieval/tools/conversation_tools.py',
    ]

    def test_no_class_method_calls_in_render_consumers(self):
        backend = os.path.join(os.path.dirname(__file__), '../..')
        for rel_path in self.RENDER_CONSUMERS:
            path = os.path.join(backend, rel_path)
            with open(path) as f:
                content = f.read()
            assert (
                'Conversation.conversations_to_string' not in content
            ), f"{rel_path} still uses Conversation.conversations_to_string"

    def test_render_consumers_import_from_render_module(self):
        backend = os.path.join(os.path.dirname(__file__), '../..')
        for rel_path in self.RENDER_CONSUMERS:
            path = os.path.join(backend, rel_path)
            with open(path) as f:
                content = f.read()
            assert 'from utils.conversations.render import' in content, f"{rel_path} does not import from render module"

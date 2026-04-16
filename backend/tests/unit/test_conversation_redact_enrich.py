"""Tests for the redact and render modules extracted from router inline logic."""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

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


# Stub database chain so render.py can import at module level without Firestore
_ensure_stub("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], "__path__", [])
for _sub in ["_client", "redis_db", "users", "folders"]:
    _ensure_stub(f"database.{_sub}")
sys.modules["database._client"].db = MagicMock()
sys.modules["database.users"].get_user_profile = MagicMock(return_value={"name": "TestUser"})
sys.modules["database.users"].get_people_by_ids = MagicMock(return_value=[])
sys.modules["database.folders"].get_folders = MagicMock(return_value=[])

# Stub-cleanup preamble: force-reimport real modules if earlier test files
# left empty ModuleType stubs in sys.modules.
for _mod in [
    "models",
    "models.conversation",
    "models.conversation_enums",
    "models.structured",
    "utils",
    "utils.conversations",
    "utils.conversations.render",
]:
    _existing = sys.modules.get(_mod)
    if _existing is not None and not getattr(_existing, "__file__", None):
        del sys.modules[_mod]

from utils.conversations.render import (
    redact_conversation_for_list,
    redact_conversation_for_integration,
    redact_conversations_for_list,
    redact_conversations_for_integration,
    serialize_datetimes,
    conversation_to_dict,
)
from models.conversation import Conversation
from models.conversation_enums import CategoryEnum
from models.structured import Structured


def _make_conv_dict(**overrides):
    defaults = dict(
        id="test-id",
        is_locked=False,
        structured=dict(
            title="Test Title",
            overview="Test overview",
            category="personal",
            action_items=[{"description": "Do thing"}],
            events=[{"title": "Standup", "start": "2026-01-15T10:00:00", "duration": 30}],
        ),
        apps_results=[{"app_id": "a1", "content": "result"}],
        plugins_results=[{"plugin_id": "a1", "content": "result"}],
        suggested_summarization_apps=["app1"],
        transcript_segments=[{"text": "hello", "speaker_id": 0, "is_user": True, "start": 0.0, "end": 1.0}],
    )
    defaults.update(overrides)
    return defaults


class TestRedactForList:
    def test_unlocked_passthrough(self):
        conv = _make_conv_dict(is_locked=False)
        result = redact_conversation_for_list(conv)
        assert result['structured']['action_items'] == [{"description": "Do thing"}]
        assert len(result['transcript_segments']) == 1

    def test_locked_strips_details_keeps_title(self):
        conv = _make_conv_dict(is_locked=True)
        result = redact_conversation_for_list(conv)
        assert result['structured']['title'] == "Test Title"
        assert result['structured']['overview'] == "Test overview"
        assert result['structured']['action_items'] == []
        assert result['structured']['events'] == []
        assert result['apps_results'] == []
        assert result['plugins_results'] == []
        assert result['suggested_summarization_apps'] == []
        assert result['transcript_segments'] == []

    def test_locked_no_structured_key(self):
        conv = {"id": "x", "is_locked": True}
        result = redact_conversation_for_list(conv)
        assert 'structured' not in result

    def test_locked_non_dict_structured_coerced(self):
        """structured can be a Pydantic model (non-dict); redact should coerce to dict."""

        class FakeStructured:
            def __init__(self):
                self.title = "Title"
                self.overview = "Overview"
                self.action_items = [{"desc": "x"}]
                self.events = [{"title": "y"}]

            def __iter__(self):
                return iter(
                    {
                        "title": self.title,
                        "overview": self.overview,
                        "action_items": self.action_items,
                        "events": self.events,
                    }.items()
                )

        conv = {
            "id": "x",
            "is_locked": True,
            "structured": FakeStructured(),
            "apps_results": [{"a": 1}],
            "plugins_results": [{"p": 1}],
            "suggested_summarization_apps": ["app1"],
            "transcript_segments": [{"text": "hi"}],
        }
        result = redact_conversation_for_list(conv)
        assert isinstance(result['structured'], dict)
        assert result['structured']['action_items'] == []
        assert result['structured']['events'] == []

    def test_batch_redact(self):
        convs = [_make_conv_dict(is_locked=True), _make_conv_dict(is_locked=False)]
        results = redact_conversations_for_list(convs)
        assert results[0]['transcript_segments'] == []
        assert len(results[1]['transcript_segments']) == 1


class TestRedactForIntegration:
    def test_unlocked_passthrough(self):
        conv = _make_conv_dict(is_locked=False)
        result = redact_conversation_for_integration(conv)
        assert result['structured']['title'] == "Test Title"

    def test_locked_strips_everything(self):
        conv = _make_conv_dict(is_locked=True)
        result = redact_conversation_for_integration(conv)
        assert result['structured']['title'] == ''
        assert result['structured']['overview'] == ''
        assert result['structured']['action_items'] == []
        assert result['structured']['events'] == []
        assert result['apps_results'] == []
        assert result['plugins_results'] == []
        assert result['suggested_summarization_apps'] == []
        assert result['transcript_segments'] == []

    def test_locked_non_dict_structured_coerced(self):
        """Integration redaction also handles non-dict structured (e.g. Pydantic)."""

        class FakeStructured:
            def __init__(self):
                self.title = "Title"
                self.overview = "Overview"
                self.action_items = [{"desc": "x"}]
                self.events = [{"title": "y"}]

            def __iter__(self):
                return iter(
                    {
                        "title": self.title,
                        "overview": self.overview,
                        "action_items": self.action_items,
                        "events": self.events,
                    }.items()
                )

        conv = {
            "id": "x",
            "is_locked": True,
            "structured": FakeStructured(),
            "apps_results": [{"a": 1}],
            "plugins_results": [{"p": 1}],
            "suggested_summarization_apps": ["app1"],
            "transcript_segments": [{"text": "hi"}],
        }
        result = redact_conversation_for_integration(conv)
        assert isinstance(result['structured'], dict)
        assert result['structured']['title'] == ''
        assert result['structured']['overview'] == ''
        assert result['structured']['action_items'] == []
        assert result['structured']['events'] == []

    def test_batch_redact(self):
        convs = [_make_conv_dict(is_locked=True), _make_conv_dict(is_locked=False)]
        results = redact_conversations_for_integration(convs)
        assert results[0]['structured']['title'] == ''
        assert results[1]['structured']['title'] == "Test Title"


class TestSerializeDatetimes:
    def test_datetime_to_iso(self):
        dt = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        result = serialize_datetimes(dt)
        assert result == "2026-01-15T10:00:00+00:00"

    def test_nested_dict(self):
        data = {"created": datetime(2026, 1, 1, tzinfo=timezone.utc), "name": "test"}
        result = serialize_datetimes(data)
        assert result["created"] == "2026-01-01T00:00:00+00:00"
        assert result["name"] == "test"

    def test_nested_list(self):
        data = [datetime(2026, 1, 1, tzinfo=timezone.utc), "text", 42]
        result = serialize_datetimes(data)
        assert result[0] == "2026-01-01T00:00:00+00:00"
        assert result[1] == "text"
        assert result[2] == 42

    def test_deep_nesting(self):
        data = {"items": [{"ts": datetime(2026, 6, 1, tzinfo=timezone.utc)}]}
        result = serialize_datetimes(data)
        assert result["items"][0]["ts"] == "2026-06-01T00:00:00+00:00"

    def test_non_datetime_passthrough(self):
        assert serialize_datetimes(42) == 42
        assert serialize_datetimes("hello") == "hello"
        assert serialize_datetimes(None) is None


class TestConversationToDict:
    def test_produces_json_safe_dict(self):
        conv = Conversation(
            id="abc",
            created_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            started_at=None,
            finished_at=None,
            structured=Structured(title="t", overview="o", category=CategoryEnum.personal),
        )
        result = conversation_to_dict(conv)
        assert isinstance(result, dict)
        assert result["id"] == "abc"
        assert result["created_at"] == "2026-01-15T10:00:00+00:00"

    def test_no_datetime_objects_remain(self):
        conv = Conversation(
            id="abc",
            created_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            started_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc),
            structured=Structured(title="t", overview="o", category=CategoryEnum.personal),
        )
        result = conversation_to_dict(conv)

        def _check_no_datetimes(obj, path=""):
            if isinstance(obj, datetime):
                raise AssertionError(f"datetime found at {path}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    _check_no_datetimes(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _check_no_datetimes(v, f"{path}[{i}]")

        _check_no_datetimes(result)


class TestCallSitesMigrated:
    """Verify production files use redact/enrich/render instead of inline logic."""

    REDACT_CONSUMERS = [
        'routers/conversations.py',
        'routers/mcp.py',
        'routers/mcp_sse.py',
        'routers/integration.py',
        'routers/folders.py',
    ]

    ENRICH_CONSUMERS = [
        'routers/developer.py',
    ]

    def test_no_inline_locked_redaction_in_routers(self):
        """Routers should not have inline is_locked field-stripping loops."""
        import os

        backend = os.path.join(os.path.dirname(__file__), '../..')
        for rel_path in self.REDACT_CONSUMERS:
            path = os.path.join(backend, rel_path)
            with open(path) as f:
                content = f.read()
            # Should not have the old inline pattern of stripping action_items inside an is_locked check
            assert (
                "conv['structured']['action_items'] = []" not in content
            ), f"{rel_path} still has inline locked redaction"

    def test_no_duplicate_speaker_enrichment(self):
        """Routers should not define their own _add_speaker_names_to_segments."""
        import os

        backend = os.path.join(os.path.dirname(__file__), '../..')
        for rel_path in ['routers/mcp.py', 'routers/developer.py']:
            path = os.path.join(backend, rel_path)
            with open(path) as f:
                content = f.read()
            assert (
                'def _add_speaker_names_to_segments' not in content
            ), f"{rel_path} still has duplicate speaker enrichment function"

    def test_no_duplicate_folder_enrichment(self):
        """Routers should not define their own _add_folder_names_to_conversations."""
        import os

        backend = os.path.join(os.path.dirname(__file__), '../..')
        for rel_path in ['routers/developer.py']:
            path = os.path.join(backend, rel_path)
            with open(path) as f:
                content = f.read()
            assert (
                'def _add_folder_names_to_conversations' not in content
            ), f"{rel_path} still has duplicate folder enrichment function"

    def test_no_duplicate_json_serialize_datetime(self):
        """Production files should use render.serialize_datetimes, not local copies."""
        import os

        backend = os.path.join(os.path.dirname(__file__), '../..')
        for rel_path in ['utils/webhooks.py', 'utils/app_integrations.py']:
            path = os.path.join(backend, rel_path)
            with open(path) as f:
                content = f.read()
            assert (
                'def _json_serialize_datetime' not in content
            ), f"{rel_path} still has duplicate _json_serialize_datetime"

    def test_no_as_dict_cleaned_dates_in_production_callers(self):
        """Production callers should use render.conversation_to_dict."""
        import os

        backend = os.path.join(os.path.dirname(__file__), '../..')
        for rel_path in ['utils/webhooks.py', 'utils/app_integrations.py', 'routers/conversations.py']:
            path = os.path.join(backend, rel_path)
            with open(path) as f:
                content = f.read()
            assert '.as_dict_cleaned_dates()' not in content, f"{rel_path} still uses .as_dict_cleaned_dates()"

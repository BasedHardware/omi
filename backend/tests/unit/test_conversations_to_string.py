import sys
from datetime import datetime, timezone

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
]:
    _existing = sys.modules.get(_mod)
    if _existing is not None and not getattr(_existing, "__file__", None):
        del sys.modules[_mod]

from models.conversation import AppResult, Conversation
from models.conversation_enums import CategoryEnum
from models.structured import Structured
from utils.conversations.render import conversations_to_string


def _make_conversation(overview="Test overview", apps_results=None, title="Test Title"):
    """Create a minimal Conversation for testing."""
    return Conversation(
        id="test-id",
        created_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc),
        structured=Structured(
            title=title,
            overview=overview,
            category=CategoryEnum.personal,
        ),
        apps_results=apps_results or [],
    )


class TestConversationsToStringDedup:
    """Test that conversations_to_string avoids double-summarization."""

    def test_no_apps_results_uses_overview(self):
        conv = _make_conversation(overview="My overview")
        result = conversations_to_string([conv])
        assert "My overview" in result

    def test_apps_results_uses_app_content(self):
        conv = _make_conversation(
            overview="My overview",
            apps_results=[AppResult(app_id="summarizer", content="App summary here")],
        )
        result = conversations_to_string([conv])
        assert "App summary here" in result

    def test_apps_results_excludes_overview(self):
        conv = _make_conversation(
            overview="My overview",
            apps_results=[AppResult(app_id="summarizer", content="App summary here")],
        )
        result = conversations_to_string([conv])
        assert "My overview" not in result

    def test_empty_apps_results_uses_overview(self):
        conv = _make_conversation(overview="Fallback overview", apps_results=[])
        result = conversations_to_string([conv])
        assert "Fallback overview" in result

    def test_empty_app_content_falls_back_to_overview(self):
        conv = _make_conversation(
            overview="Fallback overview",
            apps_results=[AppResult(app_id="summarizer", content="")],
        )
        result = conversations_to_string([conv])
        assert "Fallback overview" in result

    def test_whitespace_app_content_falls_back_to_overview(self):
        conv = _make_conversation(
            overview="Fallback overview",
            apps_results=[AppResult(app_id="summarizer", content="   ")],
        )
        result = conversations_to_string([conv])
        assert "Fallback overview" in result

    def test_no_duplicate_summarization_label(self):
        conv = _make_conversation(
            apps_results=[AppResult(app_id="summarizer", content="App summary")],
        )
        result = conversations_to_string([conv])
        assert "Summarization:" not in result

"""
Tests for issue #4655: Fix double-summarization in conversations_to_string.

conversations_to_string() previously included BOTH structured.overview AND
apps_results[0].content, feeding redundant content to downstream LLM calls.

Fix: When apps_results[0] has non-empty content, use it instead of overview.
"""

from datetime import datetime, timezone

from models.conversation import AppResult, Conversation, Structured


def _make_conversation(overview="Test overview", app_content=None, title="Test Title"):
    """Create a minimal Conversation for testing conversations_to_string."""
    apps_results = []
    if app_content is not None:
        apps_results = [AppResult(app_id="test-app", content=app_content)]

    return Conversation(
        id="conv-1",
        created_at=datetime(2026, 2, 7, 12, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 2, 7, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 2, 7, 12, 30, tzinfo=timezone.utc),
        structured=Structured(title=title, overview=overview),
        apps_results=apps_results,
    )


class TestConversationsToString:
    """Test Conversation.conversations_to_string summary selection logic."""

    def test_no_app_results_includes_overview(self):
        """Without app results, output includes title + overview."""
        conv = _make_conversation(overview="A productive meeting about goals")
        result = Conversation.conversations_to_string([conv])

        assert "Test title" in result
        assert "A productive meeting about goals" in result
        assert "Summarization" not in result

    def test_app_result_replaces_overview(self):
        """With non-empty app result, output uses app content instead of overview."""
        conv = _make_conversation(
            overview="Brief overview",
            app_content="Detailed app summary with key takeaways and action items.",
        )
        result = Conversation.conversations_to_string([conv])

        assert "Test title" in result
        assert "Detailed app summary with key takeaways and action items." in result
        assert "Brief overview" not in result

    def test_empty_app_result_falls_back_to_overview(self):
        """With empty app result, output falls back to overview."""
        conv = _make_conversation(overview="Fallback overview", app_content="")
        result = Conversation.conversations_to_string([conv])

        assert "Fallback overview" in result

    def test_whitespace_app_result_falls_back_to_overview(self):
        """With whitespace-only app result, output falls back to overview."""
        conv = _make_conversation(overview="Fallback overview", app_content="   \n  ")
        result = Conversation.conversations_to_string([conv])

        assert "Fallback overview" in result

    def test_no_double_summary(self):
        """Ensure overview and app result are never both included."""
        conv = _make_conversation(
            overview="Short overview",
            app_content="Rich app summary",
        )
        result = Conversation.conversations_to_string([conv])

        assert "Rich app summary" in result
        assert "Short overview" not in result
        # Old "Summarization:" label should not appear
        assert "Summarization:" not in result

    def test_title_always_included(self):
        """Title is always present regardless of app result."""
        conv_no_app = _make_conversation(title="Meeting Notes")
        conv_with_app = _make_conversation(title="Meeting Notes", app_content="App summary")

        result_no_app = Conversation.conversations_to_string([conv_no_app])
        result_with_app = Conversation.conversations_to_string([conv_with_app])

        assert "Meeting notes" in result_no_app
        assert "Meeting notes" in result_with_app

    def test_multiple_app_results_uses_first(self):
        """Only the first app result is used (existing behavior preserved)."""
        conv = _make_conversation(overview="Overview text")
        conv.apps_results = [
            AppResult(app_id="app1", content="First app result"),
            AppResult(app_id="app2", content="Second app result"),
        ]
        result = Conversation.conversations_to_string([conv])

        assert "First app result" in result
        assert "Second app result" not in result
        assert "Overview text" not in result

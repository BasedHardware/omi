from datetime import datetime, timezone

from omi_plugin_sdk.models import ActionItem, Conversation, Structured


def test_structured_parses_action_items_and_optional_lists():
    structured = Structured.model_validate(
        {
            "title": "Planning",
            "overview": "Discussed launch tasks",
            "category": "not-a-real-category",
            "action_items": [{"description": "Send recap", "completed": True}],
        }
    )

    assert structured.category.value == "other"
    assert structured.action_items == [ActionItem(description="Send recap", completed=True)]
    assert structured.events == []


def test_conversation_parses_legacy_payload_without_optional_lists():
    conversation = Conversation.model_validate(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "transcript_segments": [{"text": "hello", "speaker": "SPEAKER_03", "is_user": False, "start": 0, "end": 1}],
            "structured": {"title": "hello", "overview": "world"},
        }
    )

    assert conversation.discarded is False
    assert conversation.transcript_segments[0].speaker_id == 3
    assert conversation.structured.action_items == []


def test_dropbox_compatible_conversation_helpers():
    conversation = Conversation.model_validate(
        {
            "id": "conv-1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "transcript_segments": [
                {"text": "hello", "speaker": "SPEAKER_01", "is_user": False, "start": 0, "end": 2},
                {"text": "reply", "speaker": "SPEAKER_00", "is_user": True, "start": 3, "end": 5},
            ],
            "structured": {
                "title": "Dropbox",
                "overview": "Summary",
                "action_items": [{"description": "Share file"}],
            },
        }
    )

    assert conversation.id == "conv-1"
    assert conversation.get_duration() == "0:00:05"
    assert "[0:00:00 - 0:00:02] Speaker 1: hello" in conversation.get_transcript(include_timestamps=True)
    assert "User: reply" in conversation.get_transcript(user_name="User")


def test_conversation_preserves_apps_results_and_syncs_legacy_plugins_results():
    conversation = Conversation.model_validate(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "transcript_segments": [],
            "structured": {"title": "Apps", "overview": "Has app output"},
            "apps_results": [{"app_id": "summarizer", "content": "App summary"}],
        }
    )

    assert conversation.apps_results[0].app_id == "summarizer"
    assert conversation.apps_results[0].content == "App summary"
    assert conversation.plugins_results[0].plugin_id == "summarizer"
    assert conversation.plugins_results[0].content == "App summary"

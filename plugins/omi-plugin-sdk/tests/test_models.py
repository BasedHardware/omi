from datetime import datetime, timezone

import pytest

from omi_plugin_sdk.models import (
    ActionItem,
    ActionItemsExtraction,
    Conversation,
    EndpointResponse,
    Event,
    ExternalIntegrationConversationSource,
    ExternalIntegrationCreateConversation,
    Geolocation,
    Section,
    Structured,
    TranscriptSegment,
)


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


def test_geolocation_accepts_documented_boundaries():
    location = Geolocation(latitude=-90, longitude=180, address="Boundary")

    assert location.latitude == -90.0
    assert location.longitude == 180.0


@pytest.mark.parametrize(
    "field,value",
    [("latitude", -90.01), ("latitude", 90.01), ("longitude", -180.01), ("longitude", 180.01)],
)
def test_geolocation_rejects_out_of_bounds_coordinates(field, value):
    payload = {"latitude": 0, "longitude": 0}
    payload[field] = value
    with pytest.raises(ValueError):
        Geolocation(**payload)


def test_external_conversation_parses_nested_geolocation():
    conversation = ExternalIntegrationCreateConversation.model_validate(
        {
            "text": "Meet at the museum",
            "text_source": "other_text",
            "started_at": "2026-09-16T12:00:00Z",
            "geolocation": {"latitude": 19.4326, "longitude": -99.1332, "address": "Mexico City"},
        }
    )

    assert conversation.text_source is ExternalIntegrationConversationSource.other
    assert conversation.geolocation.latitude == pytest.approx(19.4326)
    assert conversation.geolocation.longitude == pytest.approx(-99.1332)


def test_action_items_to_string_formats_status_and_empty_list():
    item = ActionItem(
        description="Send recap",
        completed=True,
        created_at=datetime(2026, 9, 16, 12, 0, 0),
        due_at=datetime(2026, 9, 17, 13, 30, 0),
    )

    assert ActionItem.actions_to_string([]) == "None"
    assert ActionItem.actions_to_string([item]) == (
        "- Send recap (completed) [Created: 2026-09-16 12:00:00 UTC, Due: 2026-09-17 13:30:00 UTC]"
    )


def test_events_to_string_and_cleaned_dates():
    event = Event.model_validate(
        {"title": "Launch", "start": "2026-09-17T14:30:00+00:00", "duration": 45}
    )

    assert Event.events_to_string([event]) == "- Launch (Starts: 2026-09-17 14:30:00 UTC, Duration: 45 mins)"
    assert event.as_dict_cleaned_dates()["start"] == "2026-09-17T14:30:00+00:00"
    assert Event.events_to_string([]) == "None"


def test_transcript_segment_coerces_speaker_and_combines_adjacent_segments():
    first = TranscriptSegment(text="hello", speaker="SPEAKER_03", is_user=False, start=1, end=2)
    second = TranscriptSegment(text="world", speaker="SPEAKER_03", is_user=False, start=2, end=4)

    assert first.speaker_id == 3
    assert first.get_timestamp_string() == "0:00:01 - 0:00:02"
    combined = TranscriptSegment.combine_segments([], [first, second])

    assert len(combined) == 1
    assert combined[0].text == "hello world"
    assert combined[0].end == 4


def test_endpoint_response_defaults_and_custom_message():
    assert EndpointResponse().message == ""
    assert EndpointResponse(message="Done").message == "Done"


def test_section_and_action_items_extraction_preserve_fields():
    section = Section.model_validate(
        {"heading": "Summary", "body_markdown": "Details", "source_segment_ids": ["seg-1"]}
    )
    extraction = ActionItemsExtraction.model_validate({"action_items": [{"description": "Follow up"}]})

    assert section.heading == "Summary"
    assert section.source_segment_ids == ["seg-1"]
    assert extraction.action_items[0].description == "Follow up"

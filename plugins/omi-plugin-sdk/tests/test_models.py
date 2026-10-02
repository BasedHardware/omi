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

def test_geolocation_bounds_and_fields():
    import pytest
    from pydantic import ValidationError
    from omi_plugin_sdk.models import Geolocation

    geo = Geolocation(latitude=37.7749, longitude=-122.4194, address="San Francisco, CA")
    assert geo.latitude == 37.7749
    assert geo.longitude == -122.4194
    assert geo.address == "San Francisco, CA"

    # Test invalid bounds
    with pytest.raises(ValidationError):
        Geolocation(latitude=91.0, longitude=0.0)
    with pytest.raises(ValidationError):
        Geolocation(latitude=-91.0, longitude=0.0)
    with pytest.raises(ValidationError):
        Geolocation(latitude=0.0, longitude=181.0)
    with pytest.raises(ValidationError):
        Geolocation(latitude=0.0, longitude=-181.0)


def test_external_integration_create_conversation_full():
    from omi_plugin_sdk.models import (
        ExternalIntegrationCreateConversation,
        ExternalIntegrationConversationSource,
        Geolocation,
    )

    payload = {
        "text": "Discussion on Q3 deliverables",
        "text_source": "audio_transcript",
        "language": "en",
        "geolocation": {"latitude": 13.7563, "longitude": 100.5018, "address": "Bangkok, Thailand"},
    }
    conv = ExternalIntegrationCreateConversation.model_validate(payload)
    assert conv.text == "Discussion on Q3 deliverables"
    assert conv.text_source == ExternalIntegrationConversationSource.audio
    assert conv.geolocation.latitude == 13.7563
    assert conv.geolocation.longitude == 100.5018


def test_action_item_actions_to_string_and_empty():
    from omi_plugin_sdk.models import ActionItem

    now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
    item1 = ActionItem(description="Review PR", completed=False, created_at=now)
    item2 = ActionItem(description="Deploy app", completed=True, completed_at=now)

    output = ActionItem.actions_to_string([item1, item2])
    assert "- Review PR (pending)" in output
    assert "Created: 2026-09-17 12:00:00 UTC" in output
    assert "- Deploy app (completed)" in output
    assert "Completed: 2026-09-17 12:00:00 UTC" in output
    assert ActionItem.actions_to_string([]) == "None"


def test_event_to_string_and_cleaned_dates():
    from omi_plugin_sdk.models import Event

    now = datetime(2026, 9, 17, 14, 30, 0, tzinfo=timezone.utc)
    ev = Event(title="Architecture Review", start=now, duration=45)
    output = Event.events_to_string([ev])
    assert "- Architecture Review (Starts: 2026-09-17 14:30:00 UTC, Duration: 45 mins)" in output
    assert Event.events_to_string([]) == "None"

    cleaned = ev.as_dict_cleaned_dates()
    assert cleaned["start"] == now.isoformat()


def test_transcript_segment_helpers_and_speaker_id():
    from omi_plugin_sdk.models import TranscriptSegment

    seg1 = TranscriptSegment(text="Hello", speaker="SPEAKER_02", is_user=False, start=0.0, end=2.0)
    seg2 = TranscriptSegment(text="Hi there", speaker="SPEAKER_00", is_user=True, start=2.5, end=4.5)

    assert seg1.speaker_id == 2
    assert seg2.speaker_id == 0
    assert seg1.get_timestamp_string() == "0:00:00 - 0:00:02"

    rendered = TranscriptSegment.segments_as_string([seg1, seg2], include_timestamps=True, user_name="Pinyo")
    assert "Speaker 2: Hello" in rendered
    assert "Pinyo: Hi there" in rendered


def test_transcript_segment_combine():
    from omi_plugin_sdk.models import TranscriptSegment

    seg1 = TranscriptSegment(text="Part 1", speaker="SPEAKER_01", is_user=False, start=0.0, end=2.0)
    seg2 = TranscriptSegment(text="Part 2", speaker="SPEAKER_01", is_user=False, start=2.0, end=4.0)

    combined = TranscriptSegment.combine_segments([seg1], [seg2])
    assert len(combined) == 1
    assert combined[0].text == "Part 1 Part 2"
    assert combined[0].end == 4.0


def test_endpoint_response_default_and_custom():
    from omi_plugin_sdk.models import EndpointResponse

    resp_default = EndpointResponse()
    assert resp_default.message == ""

    resp_custom = EndpointResponse(message="Notification dispatched")
    assert resp_custom.message == "Notification dispatched"


def test_section_and_action_items_extraction():
    from omi_plugin_sdk.models import Section, ActionItemsExtraction, ActionItem

    sec = Section(heading="Executive Summary", body_markdown="Key takeaway points", source_segment_ids=["seg-1"])
    assert sec.heading == "Executive Summary"
    assert sec.body_markdown == "Key takeaway points"
    assert sec.source_segment_ids == ["seg-1"]

    extraction = ActionItemsExtraction(action_items=[ActionItem(description="Follow up")])
    assert len(extraction.action_items) == 1
    assert extraction.action_items[0].description == "Follow up"


def _canonical_punctuation_normalization(text):
    """The normalization backend/models/transcript_segment.py applies.

    Mirrors the canonical implementation's final pass verbatim so a future
    divergence fails here instead of silently corrupting plugin transcripts.
    """
    return text.strip().replace("  ", " ").replace(" ,", ",").replace(" .", ".").replace(" ?", "?")


def test_combine_segments_keeps_the_word_boundary_when_a_segment_is_space_padded():
    from omi_plugin_sdk.models import TranscriptSegment

    # combine_segments joins with f" {new_segment.text}", so a segment whose
    # text is already space-padded - routine in streaming STT output - produces
    # a double space that the normalization pass must not delete.
    seg1 = TranscriptSegment(text="Part 1 ", speaker="SPEAKER_01", is_user=False, start=0.0, end=2.0)
    seg2 = TranscriptSegment(text="Part 2", speaker="SPEAKER_01", is_user=False, start=2.0, end=4.0)

    combined = TranscriptSegment.combine_segments([seg1], [seg2])

    assert len(combined) == 1
    assert combined[0].text == "Part 1 Part 2"


def test_combine_segments_collapses_an_internal_double_space_instead_of_deleting_it():
    from omi_plugin_sdk.models import TranscriptSegment

    seg = TranscriptSegment(text="I said  hello", speaker="SPEAKER_00", is_user=False, start=0.0, end=1.0)

    combined = TranscriptSegment.combine_segments([], [seg])

    assert combined[0].text == "I said hello"


def test_combine_segments_normalization_matches_the_canonical_backend_pass():
    from omi_plugin_sdk.models import TranscriptSegment

    cases = [
        "I said  hello",
        "hello world",
        "trailing space ",
        " leading space",
        "spaced , comma",
        "spaced . period",
        "spaced ? question",
    ]

    for index, text in enumerate(cases):
        seg = TranscriptSegment(
            text=text, speaker="SPEAKER_00", is_user=False, start=float(index), end=float(index) + 0.5
        )
        combined = TranscriptSegment.combine_segments([], [seg])
        assert combined[0].text == _canonical_punctuation_normalization(text), text

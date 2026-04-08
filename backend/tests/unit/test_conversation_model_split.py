"""Tests for conversation model split (#6423).

Verifies that splitting models/conversation.py into separate files
maintains backward compatibility and correct behavior.
"""

from datetime import datetime, timezone

import pytest


class TestImportBackwardCompatibility:
    """All existing import patterns must continue to work via re-exports."""

    def test_enums_importable_from_conversation(self):
        from models.conversation import (
            CategoryEnum,
            ConversationSource,
            ConversationStatus,
            ConversationVisibility,
            ExternalIntegrationConversationSource,
            PostProcessingModel,
            PostProcessingStatus,
        )

        assert CategoryEnum.other.value == 'other'
        assert ConversationSource.omi.value == 'omi'
        assert ConversationStatus.completed.value == 'completed'
        assert ConversationVisibility.private.value == 'private'
        assert PostProcessingStatus.not_started.value == 'not_started'
        assert PostProcessingModel.fal_whisperx.value == 'fal_whisperx'
        assert ExternalIntegrationConversationSource.audio.value == 'audio_transcript'

    def test_structured_models_importable_from_conversation(self):
        from models.conversation import ActionItem, ActionItemsExtraction, Event, Structured

        assert ActionItem(description="test").description == "test"
        assert Event(title="test", start=datetime.now(timezone.utc)).title == "test"
        assert Structured().title == ''
        assert ActionItemsExtraction().action_items == []

    def test_domain_models_importable_from_conversation(self):
        from models.conversation import (
            AudioFile,
            CalendarMeetingContext,
            ConversationPhoto,
            Geolocation,
            MeetingParticipant,
        )

        assert Geolocation(latitude=0, longitude=0).latitude == 0
        assert MeetingParticipant().name is None
        assert ConversationPhoto(base64="abc").base64 == "abc"

    def test_core_models_importable_from_conversation(self):
        from models.conversation import (
            AppResult,
            Conversation,
            ConversationPostProcessing,
            CreateConversation,
            CreateConversationResponse,
            CreateMemoryResponse,
            ExternalIntegrationCreateConversation,
            PluginResult,
            UpdateConversation,
        )

        assert UpdateConversation().title is None
        assert PluginResult(plugin_id="p1", content="c").content == "c"
        assert AppResult(app_id="a1", content="c").app_id == "a1"

    def test_request_response_models_importable(self):
        from models.conversation import (
            BulkAssignSegmentsRequest,
            DeleteActionItemRequest,
            MergeConversationsRequest,
            MergeConversationsResponse,
            SearchRequest,
            SetConversationActionItemsStateRequest,
            SetConversationEventsStateRequest,
            TestPromptRequest,
            UpdateActionItemDescriptionRequest,
            UpdateSegmentTextRequest,
        )

        assert SearchRequest(query="test").query == "test"

    def test_star_import_covers_all_symbols(self):
        import importlib

        mod = importlib.import_module('models.conversation')
        for name in mod.__all__:
            assert hasattr(mod, name), f"__all__ lists '{name}' but it's not in the module"

    def test_identity_preserved_across_import_paths(self):
        """Re-exported classes must be the same object, not copies."""
        from models.conversation import CategoryEnum as CE_conv
        from models.conversation_enums import CategoryEnum as CE_enum

        assert CE_conv is CE_enum

        from models.conversation import Structured as S_conv
        from models.structured import Structured as S_struct

        assert S_conv is S_struct

        from models.conversation import Geolocation as G_conv
        from models.geolocation import Geolocation as G_geo

        assert G_conv is G_geo

        from models.conversation import AudioFile as AF_conv
        from models.audio_file import AudioFile as AF_audio

        assert AF_conv is AF_audio

        from models.conversation import ConversationPhoto as CP_conv
        from models.conversation_photo import ConversationPhoto as CP_photo

        assert CP_conv is CP_photo

        from models.conversation import CalendarMeetingContext as CMC_conv
        from models.calendar_context import CalendarMeetingContext as CMC_cal

        assert CMC_conv is CMC_cal


class TestDirectImportsFromNewModules:
    """New modules are independently importable."""

    def test_conversation_enums(self):
        from models.conversation_enums import CategoryEnum

        assert len(CategoryEnum) == 33  # 31 categories + architecture + environment from issue but counting actual

    def test_conversation_source_missing(self):
        from models.conversation_enums import ConversationSource

        # Unknown string values should map to 'unknown' via _missing_
        assert ConversationSource('nonexistent_source') == ConversationSource.unknown

    def test_structured_category_validator(self):
        from models.structured import Structured

        # Invalid category should default to 'other'
        s = Structured(category='invalid_category_value')
        from models.conversation_enums import CategoryEnum

        assert s.category == CategoryEnum.other

    def test_structured_str(self):
        from models.structured import Structured, ActionItem, Event
        from models.conversation_enums import CategoryEnum

        s = Structured(
            title="Test Meeting",
            overview="Discussion about testing",
            category=CategoryEnum.work,
            action_items=[ActionItem(description="Write tests")],
        )
        result = str(s)
        assert "Test meeting" in result
        assert "Work" in result
        assert "Write tests" in result


class TestSerializationRoundTrip:
    """Models must serialize and deserialize correctly after the split."""

    def test_conversation_round_trip(self):
        from models.conversation import Conversation
        from models.conversation_enums import CategoryEnum, ConversationSource
        from models.structured import Structured

        now = datetime.now(timezone.utc)
        conv = Conversation(
            id="test-123",
            created_at=now,
            started_at=now,
            finished_at=now,
            source=ConversationSource.omi,
            structured=Structured(
                title="Test",
                overview="Overview",
                category=CategoryEnum.work,
            ),
        )
        data = conv.dict()
        conv2 = Conversation(**data)
        assert conv2.id == "test-123"
        assert conv2.structured.title == "Test"
        assert conv2.structured.category == CategoryEnum.work
        assert conv2.source == ConversationSource.omi

    def test_create_conversation_round_trip(self):
        from models.conversation import CreateConversation
        from models.conversation_enums import ConversationSource
        from models.geolocation import Geolocation
        from models.transcript_segment import TranscriptSegment

        now = datetime.now(timezone.utc)
        cc = CreateConversation(
            started_at=now,
            finished_at=now,
            transcript_segments=[
                TranscriptSegment(text="hello", speaker="SPEAKER_00", start=0.0, end=1.0, is_user=False)
            ],
            geolocation=Geolocation(latitude=37.7749, longitude=-122.4194),
            source=ConversationSource.desktop,
        )
        data = cc.dict()
        cc2 = CreateConversation(**data)
        assert cc2.geolocation.latitude == 37.7749
        assert cc2.source == ConversationSource.desktop
        assert len(cc2.transcript_segments) == 1

    def test_external_integration_round_trip(self):
        from models.conversation import ExternalIntegrationCreateConversation
        from models.conversation_enums import ConversationSource, ExternalIntegrationConversationSource

        eic = ExternalIntegrationCreateConversation(
            text="test content",
            text_source=ExternalIntegrationConversationSource.message,
            source=ConversationSource.workflow,
        )
        data = eic.dict()
        eic2 = ExternalIntegrationCreateConversation(**data)
        assert eic2.text == "test content"
        assert eic2.text_source == ExternalIntegrationConversationSource.message


class TestHelperMethods:
    """Helper methods on moved models must work correctly."""

    def test_action_item_to_string(self):
        from models.structured import ActionItem

        items = [
            ActionItem(description="Do thing A", completed=False),
            ActionItem(description="Do thing B", completed=True),
        ]
        result = ActionItem.actions_to_string(items)
        assert "Do thing A (pending)" in result
        assert "Do thing B (completed)" in result

    def test_action_item_to_string_empty(self):
        from models.structured import ActionItem

        assert ActionItem.actions_to_string([]) == 'None'

    def test_event_to_string(self):
        from models.structured import Event

        events = [Event(title="Standup", start=datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc), duration=15)]
        result = Event.events_to_string(events)
        assert "Standup" in result
        assert "15 mins" in result

    def test_photo_to_string(self):
        from models.conversation_photo import ConversationPhoto

        photos = [ConversationPhoto(base64="abc", description="A cat")]
        result = ConversationPhoto.photos_as_string(photos)
        assert '"A cat"' in result

    def test_photo_to_string_empty(self):
        from models.conversation_photo import ConversationPhoto

        assert ConversationPhoto.photos_as_string([]) == 'None'

    def test_event_as_dict_cleaned_dates(self):
        from models.structured import Event

        e = Event(title="Meeting", start=datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc))
        d = e.as_dict_cleaned_dates()
        assert isinstance(d['start'], str)
        assert '2025-06-15' in d['start']

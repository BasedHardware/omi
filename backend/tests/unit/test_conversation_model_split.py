"""Tests for conversation model split (#6423) and Phase 4 decoupling (#6484).

Verifies that splitting models/conversation.py into separate files
maintains correct behavior and that re-exports have been removed.
"""

from datetime import datetime, timezone

import pytest


class TestLocallyDefinedModelsImportable:
    """Models defined in conversation.py must be importable."""

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


class TestReExportsRemoved:
    """Phase 4a (#6484): re-exports removed — use canonical modules."""

    def test_no_reexport_symbols_in_all(self):
        """__all__ must only contain locally-defined symbols."""
        import models.conversation as mod

        reexport_symbols = [
            'ActionItem',
            'ActionItemsExtraction',
            'AudioFile',
            'CalendarMeetingContext',
            'CategoryEnum',
            'ConversationPhoto',
            'ConversationSource',
            'ConversationStatus',
            'ConversationVisibility',
            'Event',
            'ExternalIntegrationConversationSource',
            'Geolocation',
            'MeetingParticipant',
            'Message',
            'Person',
            'PostProcessingModel',
            'PostProcessingStatus',
            'Structured',
            'TranscriptSegment',
        ]
        if hasattr(mod, '__all__'):
            for sym in reexport_symbols:
                assert sym not in mod.__all__, f'{sym} should not be in __all__ (use canonical module)'

    def test_canonical_imports_work(self):
        """All moved symbols import from their canonical modules."""
        from models.conversation_enums import CategoryEnum, ConversationSource, ConversationStatus
        from models.structured import Structured, ActionItem, Event, ActionItemsExtraction
        from models.audio_file import AudioFile
        from models.calendar_context import CalendarMeetingContext, MeetingParticipant
        from models.conversation_photo import ConversationPhoto
        from models.geolocation import Geolocation

        assert CategoryEnum.other.value == 'other'
        assert ConversationSource.omi.value == 'omi'
        assert Structured().title == ''
        assert ActionItem(description="test").description == "test"
        assert Geolocation(latitude=0, longitude=0).latitude == 0

    def test_star_import_excludes_reexports(self):
        """Star import only provides locally-defined symbols."""
        ns = {}
        exec('from models.conversation import *', ns)
        assert 'Conversation' in ns
        assert 'CreateConversation' in ns
        assert 'AppResult' in ns
        # Re-exported symbols no longer in __all__
        assert 'CategoryEnum' not in ns
        assert 'Structured' not in ns
        assert 'TranscriptSegment' not in ns
        assert 'ActionItem' not in ns
        # Typing symbols excluded
        assert 'List' not in ns


class TestDirectImportsFromNewModules:
    """New modules are independently importable."""

    def test_conversation_enums(self):
        from models.conversation_enums import CategoryEnum

        # Verify key members exist rather than brittle count assertion
        assert CategoryEnum.other.value == 'other'
        assert CategoryEnum.work.value == 'work'
        assert CategoryEnum.personal.value == 'personal'

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

    def test_event_to_string_empty(self):
        from models.structured import Event

        assert Event.events_to_string([]) == 'None'

    def test_action_item_to_string_with_timestamps(self):
        from models.structured import ActionItem

        items = [
            ActionItem(
                description="Review PR",
                completed=True,
                created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
                due_at=datetime(2025, 3, 2, 10, 0, 0, tzinfo=timezone.utc),
                completed_at=datetime(2025, 3, 1, 15, 0, 0, tzinfo=timezone.utc),
            ),
        ]
        result = ActionItem.actions_to_string(items)
        assert "Created: 2025-03-01 10:00:00 UTC" in result
        assert "Due: 2025-03-02 10:00:00 UTC" in result
        assert "Completed: 2025-03-01 15:00:00 UTC" in result

    def test_photo_to_string_with_timestamps(self):
        from models.conversation_photo import ConversationPhoto

        photos = [
            ConversationPhoto(
                base64="abc",
                description="A dog",
                created_at=datetime(2025, 6, 15, 14, 30, 45, tzinfo=timezone.utc),
            )
        ]
        result = ConversationPhoto.photos_as_string(photos, include_timestamps=True)
        assert "[14:30:45]" in result
        assert '"A dog"' in result

    def test_photo_to_string_no_description(self):
        """Photos with no description should be excluded."""
        from models.conversation_photo import ConversationPhoto

        photos = [ConversationPhoto(base64="abc", description=None)]
        assert ConversationPhoto.photos_as_string(photos) == 'None'

    def test_event_as_dict_cleaned_dates(self):
        from models.structured import Event

        e = Event(title="Meeting", start=datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc))
        d = e.as_dict_cleaned_dates()
        assert isinstance(d['start'], str)
        assert '2025-06-15' in d['start']


class TestConversationSummary:
    """Phase 2: ConversationSummary lightweight view model."""

    def test_basic_creation(self):
        from models.conversation_summary import ConversationSummary

        s = ConversationSummary(id="test-1", title="Test", overview="Overview")
        assert s.id == "test-1"
        assert s.title == "Test"
        assert s.category == "other"
        assert s.person_ids == []

    def test_from_conversation(self):
        from models.conversation import Conversation
        from models.conversation_enums import CategoryEnum, ConversationSource
        from models.conversation_summary import ConversationSummary
        from models.structured import Structured

        now = datetime.now(timezone.utc)
        conv = Conversation(
            id="conv-1",
            created_at=now,
            started_at=now,
            finished_at=now,
            source=ConversationSource.omi,
            structured=Structured(
                title="Team standup",
                overview="Daily sync",
                category=CategoryEnum.work,
            ),
        )
        summary = ConversationSummary.from_conversation(conv)
        assert summary.id == "conv-1"
        assert summary.title == "Team standup"
        assert summary.overview == "Daily sync"
        assert summary.category == "work"
        assert summary.created_at == now
        assert summary.person_ids == []

    def test_defaults(self):
        from models.conversation_summary import ConversationSummary

        s = ConversationSummary(id="x")
        assert s.title == ''
        assert s.overview == ''
        assert s.category == 'other'
        assert s.transcript_text == ''
        assert s.created_at is None


class TestPhase3NarrowImports:
    """Phase 3: Verify callers import from canonical modules, not conversation.py."""

    def test_enums_from_canonical_module(self):
        from models.conversation_enums import CategoryEnum, ConversationSource, ConversationStatus

        assert CategoryEnum.other.value == 'other'
        assert ConversationSource.omi.value == 'omi'
        assert ConversationStatus.completed.value == 'completed'

    def test_structured_from_canonical_module(self):
        from models.structured import Structured, ActionItem, Event

        assert Structured().title == ''
        assert ActionItem(description="test").description == "test"

    def test_domain_models_from_canonical_modules(self):
        from models.audio_file import AudioFile
        from models.calendar_context import CalendarMeetingContext, MeetingParticipant
        from models.conversation_photo import ConversationPhoto
        from models.geolocation import Geolocation

        assert Geolocation(latitude=0, longitude=0).latitude == 0
        assert MeetingParticipant().name is None
        assert ConversationPhoto(base64="abc").base64 == "abc"

    def test_all_controls_star_import(self):
        """__all__ restricts star import to locally-defined symbols only."""
        import models.conversation as mod

        assert hasattr(mod, '__all__')
        assert 'Conversation' in mod.__all__
        # Re-exports removed in Phase 4a (#6484)
        assert 'CategoryEnum' not in mod.__all__
        assert 'Structured' not in mod.__all__
        # Typing symbols excluded
        assert 'List' not in mod.__all__
        assert 'Optional' not in mod.__all__
        assert 'Dict' not in mod.__all__


class TestConversationInitSideEffects:
    """Conversation.__init__ backward-compat side effects."""

    def test_apps_results_synced_to_plugins_results(self):
        from models.conversation import AppResult, Conversation
        from models.conversation_enums import ConversationSource
        from models.structured import Structured

        now = datetime.now(timezone.utc)
        conv = Conversation(
            id="side-effect-1",
            created_at=now,
            started_at=now,
            finished_at=now,
            source=ConversationSource.omi,
            structured=Structured(title="Test"),
            apps_results=[AppResult(app_id="app1", content="result1")],
        )
        assert len(conv.plugins_results) == 1
        assert conv.plugins_results[0].plugin_id == "app1"
        assert conv.plugins_results[0].content == "result1"

    def test_processing_conversation_id_synced_to_processing_memory_id(self):
        from models.conversation import Conversation
        from models.conversation_enums import ConversationSource
        from models.structured import Structured

        now = datetime.now(timezone.utc)
        conv = Conversation(
            id="side-effect-2",
            created_at=now,
            started_at=now,
            finished_at=now,
            source=ConversationSource.omi,
            structured=Structured(title="Test"),
            processing_conversation_id="proc-123",
        )
        assert conv.processing_memory_id == "proc-123"


class TestGetPersonIds:
    """get_person_ids with duplicates and None values."""

    def test_deduplicates_person_ids(self):
        from models.conversation import Conversation
        from models.conversation_enums import ConversationSource
        from models.structured import Structured
        from models.transcript_segment import TranscriptSegment

        now = datetime.now(timezone.utc)
        conv = Conversation(
            id="dedup-1",
            created_at=now,
            started_at=now,
            finished_at=now,
            source=ConversationSource.omi,
            structured=Structured(title="Test"),
            transcript_segments=[
                TranscriptSegment(text="a", speaker="SPEAKER_00", start=0.0, end=1.0, is_user=False, person_id="p1"),
                TranscriptSegment(text="b", speaker="SPEAKER_01", start=1.0, end=2.0, is_user=False, person_id="p1"),
                TranscriptSegment(text="c", speaker="SPEAKER_02", start=2.0, end=3.0, is_user=False, person_id="p2"),
            ],
        )
        ids = conv.get_person_ids()
        assert sorted(ids) == ["p1", "p2"]

    def test_filters_none_person_ids(self):
        from models.conversation import Conversation
        from models.conversation_enums import ConversationSource
        from models.structured import Structured
        from models.transcript_segment import TranscriptSegment

        now = datetime.now(timezone.utc)
        conv = Conversation(
            id="none-filter",
            created_at=now,
            started_at=now,
            finished_at=now,
            source=ConversationSource.omi,
            structured=Structured(title="Test"),
            transcript_segments=[
                TranscriptSegment(text="a", speaker="SPEAKER_00", start=0.0, end=1.0, is_user=False, person_id=None),
                TranscriptSegment(text="b", speaker="SPEAKER_01", start=1.0, end=2.0, is_user=False, person_id="p1"),
            ],
        )
        assert conv.get_person_ids() == ["p1"]

    def test_empty_segments_returns_empty(self):
        from models.conversation import Conversation
        from models.conversation_enums import ConversationSource
        from models.structured import Structured

        now = datetime.now(timezone.utc)
        conv = Conversation(
            id="empty-seg",
            created_at=now,
            started_at=now,
            finished_at=now,
            source=ConversationSource.omi,
            structured=Structured(title="Test"),
        )
        assert conv.get_person_ids() == []


class TestAsDictCleanedDates:
    """as_dict_cleaned_dates recursive datetime conversion."""

    def test_datetimes_converted_to_iso(self):
        from models.conversation import Conversation
        from models.conversation_enums import ConversationSource
        from models.structured import Structured

        now = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        conv = Conversation(
            id="dates-1",
            created_at=now,
            started_at=now,
            finished_at=now,
            source=ConversationSource.omi,
            structured=Structured(title="Test"),
        )
        d = conv.as_dict_cleaned_dates()
        assert isinstance(d['created_at'], str)
        assert '2025-06-15' in d['created_at']
        assert isinstance(d['started_at'], str)
        assert isinstance(d['finished_at'], str)


class TestConversationSummaryWithTranscript:
    """ConversationSummary.from_conversation with real data."""

    def test_from_conversation_with_transcript_and_person_ids(self):
        from models.conversation import Conversation
        from models.conversation_enums import CategoryEnum, ConversationSource
        from models.conversation_summary import ConversationSummary
        from models.structured import Structured
        from models.transcript_segment import TranscriptSegment

        now = datetime.now(timezone.utc)
        conv = Conversation(
            id="summary-1",
            created_at=now,
            started_at=now,
            finished_at=now,
            source=ConversationSource.omi,
            structured=Structured(
                title="Team standup",
                overview="Daily sync",
                category=CategoryEnum.work,
            ),
            transcript_segments=[
                TranscriptSegment(
                    text="Hello team", speaker="SPEAKER_00", start=0.0, end=1.0, is_user=True, person_id="p1"
                ),
                TranscriptSegment(
                    text="Hi there", speaker="SPEAKER_01", start=1.0, end=2.0, is_user=False, person_id="p2"
                ),
            ],
        )
        summary = ConversationSummary.from_conversation(conv)
        assert summary.id == "summary-1"
        assert summary.title == "Team standup"
        assert summary.category == "work"
        assert "Hello team" in summary.transcript_text
        assert "Hi there" in summary.transcript_text
        assert sorted(summary.person_ids) == ["p1", "p2"]


class TestPhase4ConsumerMigration:
    """Phase 4b (#6484): consumers decoupled from Conversation import."""

    def test_trends_extractor_accepts_segments_and_person_ids(self):
        """trends_extractor no longer accepts Conversation object."""
        import ast
        import pathlib

        source = pathlib.Path('utils/llm/trends.py').read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'trends_extractor':
                params = [arg.arg for arg in node.args.args]
                assert params == ['uid', 'transcript_segments', 'person_ids']
                return
        pytest.fail('trends_extractor function not found')

    def test_retrieve_memory_context_params_accepts_segments(self):
        """retrieve_memory_context_params no longer accepts Conversation object."""
        import ast
        import pathlib

        source = pathlib.Path('utils/llm/chat.py').read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'retrieve_memory_context_params':
                params = [arg.arg for arg in node.args.args]
                assert params == ['uid', 'transcript_segments', 'person_ids']
                return
        pytest.fail('retrieve_memory_context_params function not found')

    def test_obtain_emotional_message_accepts_segments(self):
        """obtain_emotional_message no longer accepts Conversation object."""
        import ast
        import pathlib

        source = pathlib.Path('utils/llm/chat.py').read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'obtain_emotional_message':
                params = [arg.arg for arg in node.args.args]
                assert params == ['uid', 'transcript_segments', 'person_ids', 'context', 'emotion']
                return
        pytest.fail('obtain_emotional_message function not found')

    def test_removed_imports_not_present(self):
        """Files that had Conversation import removed no longer import it."""
        import pathlib

        for file_path in [
            'utils/retrieval/agentic.py',
            'routers/speech_profile.py',
            'utils/llm/trends.py',
            'routers/chat.py',
            'utils/chat.py',
        ]:
            source = pathlib.Path(file_path).read_text()
            assert (
                'from models.conversation import' not in source
            ), f'{file_path} still imports from models.conversation'

    def test_type_checking_only_imports(self):
        """Files using TYPE_CHECKING should not have runtime Conversation import."""
        import pathlib

        source = pathlib.Path('utils/retrieval/graph.py').read_text()
        assert 'TYPE_CHECKING' in source, 'graph.py should use TYPE_CHECKING'
        assert 'from __future__ import annotations' in source


class TestPhase4RuntimeBehavior:
    """Phase 4b (#6484): runtime tests for narrowed interfaces."""

    def test_extract_memory_ids_from_dicts(self):
        """extract_memory_ids handles dict inputs (used by routers/chat.py and utils/chat.py)."""
        from utils.conversation_helpers import extract_memory_ids

        memories = [
            {'id': 'conv-1', 'structured': {'title': 'Test'}},
            {'id': 'conv-2', 'structured': {'title': 'Test 2'}},
        ]
        assert extract_memory_ids(memories) == ['conv-1', 'conv-2']

    def test_extract_memory_ids_from_objects(self):
        """extract_memory_ids handles Conversation objects."""
        from models.conversation import Conversation
        from models.structured import Structured
        from utils.conversation_helpers import extract_memory_ids

        now = datetime.now(timezone.utc)
        conv = Conversation(
            id='conv-obj',
            created_at=now,
            started_at=now,
            finished_at=now,
            structured=Structured(title='Test'),
        )
        assert extract_memory_ids([conv]) == ['conv-obj']

    def test_extract_memory_ids_mixed(self):
        """extract_memory_ids handles mixed dict/object inputs."""
        from models.conversation import Conversation
        from models.structured import Structured
        from utils.conversation_helpers import extract_memory_ids

        now = datetime.now(timezone.utc)
        conv = Conversation(
            id='conv-obj',
            created_at=now,
            started_at=now,
            finished_at=now,
            structured=Structured(title='Test'),
        )
        memories = [{'id': 'conv-dict'}, conv]
        assert extract_memory_ids(memories) == ['conv-dict', 'conv-obj']

    def test_extract_memory_ids_limit(self):
        """extract_memory_ids respects the limit parameter."""
        from utils.conversation_helpers import extract_memory_ids

        memories = [{'id': f'conv-{i}'} for i in range(10)]
        assert len(extract_memory_ids(memories, limit=3)) == 3

    def test_extract_memory_ids_empty(self):
        """extract_memory_ids handles empty list."""
        from utils.conversation_helpers import extract_memory_ids

        assert extract_memory_ids([]) == []

    def test_call_sites_use_extract_memory_ids(self):
        """Verify routers/chat.py and utils/chat.py use the shared helper."""
        import pathlib

        for file_path in ['routers/chat.py', 'utils/chat.py']:
            source = pathlib.Path(file_path).read_text()
            assert 'extract_memory_ids' in source, f'{file_path} should use extract_memory_ids'
            assert 'from utils.conversation_helpers import extract_memory_ids' in source

    def test_trends_extractor_signature_callable(self):
        """trends_extractor can be called with the new signature shape."""
        import sys
        from unittest.mock import patch, MagicMock
        from models.transcript_segment import TranscriptSegment

        segments = [
            TranscriptSegment(text="Tesla stock is up", speaker="SPEAKER_00", start=0.0, end=1.0, is_user=True),
        ]
        person_ids = ['p1']

        # Pre-mock heavy dependencies to avoid GCP credential chain
        mock_db_module = MagicMock()
        mock_llm_clients = MagicMock()
        saved_modules = {}
        for mod_name in ['database._client', 'database.users', 'database.auth', 'utils.llm.clients']:
            saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = mock_db_module if 'database' in mod_name else mock_llm_clients

        try:
            # Force reimport with mocked deps
            for mod_name in ['utils.llm.trends']:
                sys.modules.pop(mod_name, None)

            import utils.llm.trends as trends_mod

            trends_mod.users_db = MagicMock()
            trends_mod.users_db.get_people_by_ids.return_value = []
            trends_mod.get_user_name = MagicMock(return_value='TestUser')
            trends_mod.llm_mini = MagicMock()
            trends_mod.llm_mini.with_structured_output.return_value.invoke.return_value = MagicMock(items=[])

            result = trends_mod.trends_extractor('test-uid', segments, person_ids)
            assert result == []
        finally:
            for mod_name, saved in saved_modules.items():
                if saved is None:
                    sys.modules.pop(mod_name, None)
                else:
                    sys.modules[mod_name] = saved
            sys.modules.pop('utils.llm.trends', None)

    def test_save_trends_accepts_str(self):
        """database/trends.py save_trends accepts memory_id as str."""
        import sys
        from unittest.mock import MagicMock
        from models.trend import Trend, TrendEnum, TrendType

        trends = [Trend(category=TrendEnum.company, topics=['Tesla'], type=TrendType.best)]

        # Mock Firestore
        mock_client = MagicMock()
        saved = sys.modules.get('database._client')
        sys.modules['database._client'] = MagicMock(db=mock_client, document_id_from_seed=lambda s: f'id-{s}')

        try:
            sys.modules.pop('database.trends', None)
            import database.trends as trends_db_mod

            mock_doc_ref = MagicMock()
            mock_client.collection.return_value.document.return_value = mock_doc_ref
            mock_doc_ref.collection.return_value.document.return_value = mock_doc_ref

            trends_db_mod.save_trends('conv-123', trends)

            # Verify the string ID was used in the ArrayUnion call
            mock_doc_ref.update.assert_called()
            call_args = mock_doc_ref.update.call_args[0][0]
            assert 'memory_ids' in call_args
        finally:
            if saved is None:
                sys.modules.pop('database._client', None)
            else:
                sys.modules['database._client'] = saved
            sys.modules.pop('database.trends', None)

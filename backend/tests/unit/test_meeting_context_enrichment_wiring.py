"""Production wiring for pre-summarization meeting identity.

`test_meeting_context_resolution.py` covers the pure selection/ordering rules.
This file exercises `process_conversation._enrich_meeting_context` itself, so a
future refactor cannot leave the resolver correct but unreachable — the original
defect was reachability, not logic: the only lookup was a Redis mapping that is
never written for most desktop conversations.

`process_conversation` is loaded through the sanctioned `stub_modules` +
`load_module_fresh` seam (`backend/docs/test_isolation.md`) so nothing stub-fed
leaks into other test modules.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

CONVERSATION_START = datetime(2026, 8, 18, 19, 29, tzinfo=timezone.utc)
CONVERSATION_END = datetime(2026, 8, 18, 19, 58, tzinfo=timezone.utc)

_STUBBED = [
    'anthropic',
    'av',
    'database._client',
    'database.firestore_read_metrics',
    'database.cache',
    'database.redis_db',
    'database.conversations',
    'database.memories',
    'database.short_term_memories',
    'database.action_items',
    'database.folders',
    'database.users',
    'database.user_usage',
    'database.vector_db',
    'database.chat',
    'database.apps',
    'database.goals',
    'database.notifications',
    'database.tasks',
    'database.trends',
    'database.calendar_meetings',
    'database.screen_activity',
    'database.auth',
    'deepgram',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'langchain_core',
    'langchain_core.output_parsers',
    'langchain_core.callbacks',
    'langchain_core.language_models',
    'langchain_core.prompts',
    'langchain_core.runnables',
    'langchain_core.tools',
    'langchain_openai',
    'openai',
    'pinecone',
    'pytz',
    'tiktoken',
    'typesense',
    'modal',
    'utils.cloud_tasks',
    'utils.other.storage',
    'utils.other.hume',
    'utils.webhooks',
    'utils.task_sync',
    'utils.analytics',
    'utils.retrieval.rag',
    'utils.llm.memories',
    'utils.llm.conversation_processing',
    'utils.llm.external_integrations',
    'utils.llm.trends',
    'utils.llm.goals',
    'utils.llm.chat',
    'utils.llm.clients',
    'utils.llm.usage_tracker',
    'utils.conversations.factory',
    'utils.conversations.subjects',
    'utils.conversations.transcript_chunks',
    'utils.conversations.calendar_linking',
    'utils.notifications',
    'utils.apps',
    'utils.executors',
    'utils.subscription',
    'utils.task_intelligence.workstream_association',
]

pc = None


@pytest.fixture(scope='module', autouse=True)
def _loaded_process_conversation():
    global pc
    fakes: dict[str, ModuleType | None] = {}
    for name in _STUBBED:
        module = AutoMockModule(name)
        if name == 'langchain_core' or name.startswith('langchain_core.'):
            module.__path__ = []  # type: ignore[attr-defined]
        fakes[name] = module

    import hashlib
    import uuid as uuid_mod

    def _document_id_from_seed(seed: str) -> str:
        return str(uuid_mod.UUID(hashlib.sha256(seed.encode()).hexdigest()[:32]))

    fakes['database._client'].document_id_from_seed = _document_id_from_seed  # type: ignore[attr-defined]

    with stub_modules(fakes):
        # `calendar_linking` is stubbed, so the real coroutine never runs; the module
        # only needs the names to exist at import time.
        module = load_module_fresh(
            'utils.conversations.process_conversation',
            str(BACKEND_DIR / 'utils' / 'conversations' / 'process_conversation.py'),
        )
        pc = module
        try:
            yield module
        finally:
            pc = None
            sys.modules.pop('utils.conversations.process_conversation', None)


def _desktop_conversation():
    from models.conversation import Conversation
    from models.conversation_enums import ConversationSource
    from models.structured import Structured

    return Conversation(
        id='ff8b9998-1169-5c66-9998-8af7837045d9',
        created_at=CONVERSATION_START,
        started_at=CONVERSATION_START,
        finished_at=CONVERSATION_END,
        structured=Structured(),
        # Meeting-treatment eligibility (#11832) is the authority for desktop meeting-role
        # conversations, so a realistic fixture must clear it: 29 minutes of wall clock and
        # more than 60s of transcribed speech. A silent fixture is correctly skipped now.
        transcript_segments=_qualifying_segments(),
        source=ConversationSource.desktop,
        external_data={'conversation_role': 'meeting'},
    )


def _qualifying_segments(seconds: float = 120.0):
    from models.transcript_segment import TranscriptSegment

    return [
        TranscriptSegment(
            id='seg-1',
            text='Talking for long enough to earn meeting treatment.',
            speaker='SPEAKER_00',
            speaker_id=0,
            is_user=True,
            start=0.0,
            end=seconds,
        )
    ]


def _ineligible_conversation():
    """A desktop meeting-role conversation the finalization policy rules out (too short)."""
    conversation = _desktop_conversation()
    conversation.finished_at = CONVERSATION_START
    conversation.transcript_segments = []
    return conversation


def _meeting_record():
    return {
        'id': 'doc-evt',
        'calendar_event_id': 'evt-scaling-forever',
        'title': 'Scaling Forever sync',
        'start_time': datetime(2026, 8, 18, 19, 30, tzinfo=timezone.utc),
        'end_time': datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc),
        'duration_minutes': 30,
        'participants': [{'name': 'David Zhang'}, {'name': 'Ash', 'email': 'ash@example.com'}],
        'calendar_source': 'macos_calendar',
    }


def _enrich(conversation, *, meetings=None, mapped_id=None, mapped_meeting=None, env=None):
    """Run the production enrichment with the Firestore/Redis reads faked."""
    range_calls: list[tuple] = []

    def _get_meetings_in_time_range(uid, start, end):
        range_calls.append((uid, start, end))
        return list(meetings or [])

    with (
        patch.dict(os.environ, env or {}, clear=False),
        patch.object(pc.redis_db, 'get_conversation_meeting_id', return_value=mapped_id),
        patch.object(pc.calendar_db, 'get_meeting', return_value=mapped_meeting),
        patch.object(pc.calendar_db, 'get_meetings_in_time_range', side_effect=_get_meetings_in_time_range),
    ):
        pc._enrich_meeting_context('uid-meeting', conversation)
    return range_calls


def _stored_context(conversation):
    raw = (conversation.external_data or {}).get('calendar_meeting_context')
    return CalendarMeetingContext(**raw) if raw else None


class TestTimeOverlapReachesTheConversation:
    def test_stored_meeting_populates_context_without_any_redis_mapping(self):
        conversation = _desktop_conversation()
        _enrich(conversation, meetings=[_meeting_record()])

        context = _stored_context(conversation)
        assert context is not None, 'the conversation reached summarization with no identity metadata'
        assert context.title == 'Scaling Forever sync'
        assert [p.name for p in context.participants] == ['David Zhang', 'Ash']
        assert context.calendar_source == 'macos_calendar'

    def test_an_ineligible_desktop_meeting_spends_no_provider_lookups(self):
        """A short or silent call still opens as a meeting; enrichment must not pay for it.

        conversation_role is open-time identity, not the treatment decision (#11832), so the
        authoritative finalization policy gates enrichment for desktop meeting-role
        conversations. Otherwise a 90-second call costs a Google Calendar read, a
        screen-activity query, and a stored-meetings row for something that never becomes a
        meeting."""
        conversation = _ineligible_conversation()
        calls = _enrich(conversation, meetings=[_meeting_record()])

        assert calls == [], 'an ineligible conversation triggered a stored-meeting range query'
        assert _stored_context(conversation) is None

    def test_the_time_range_query_brackets_the_conversation_window(self):
        conversation = _desktop_conversation()
        calls = _enrich(conversation, meetings=[])

        assert len(calls) == 1
        _, start, end = calls[0]
        assert start < CONVERSATION_START
        assert end > CONVERSATION_END

    def test_an_exact_mapping_short_circuits_the_range_query(self):
        conversation = _desktop_conversation()
        calls = _enrich(conversation, mapped_id='doc-evt', mapped_meeting=_meeting_record())

        assert calls == []
        assert _stored_context(conversation).calendar_event_id == 'evt-scaling-forever'

    def test_client_supplied_context_is_kept_and_enriched(self):
        conversation = _desktop_conversation()
        conversation.external_data = {
            'conversation_role': 'meeting',
            'calendar_meeting_context': CalendarMeetingContext(
                calendar_event_id='client-evt',
                title='Client title',
                participants=[MeetingParticipant(name='Someone Else')],
                start_time=CONVERSATION_START,
                duration_minutes=29,
            ).model_dump(mode='json'),
        }
        _enrich(conversation, meetings=[_meeting_record()])

        context = _stored_context(conversation)
        # Stored calendar outranks the client payload, but no name is lost.
        assert context.calendar_event_id == 'evt-scaling-forever'
        assert {p.name for p in context.participants} == {'David Zhang', 'Ash', 'Someone Else'}


class TestDegradation:
    def test_no_matching_meeting_leaves_the_conversation_untouched(self):
        conversation = _desktop_conversation()
        _enrich(conversation, meetings=[])

        assert conversation.external_data == {'conversation_role': 'meeting'}

    def test_a_failing_meetings_read_does_not_raise(self):
        conversation = _desktop_conversation()
        with (
            patch.object(pc.redis_db, 'get_conversation_meeting_id', return_value=None),
            patch.object(
                pc.calendar_db,
                'get_meetings_in_time_range',
                side_effect=RuntimeError('firestore unavailable'),
            ),
        ):
            pc._enrich_meeting_context('uid-meeting', conversation)

        assert 'calendar_meeting_context' not in (conversation.external_data or {})

    def test_the_kill_switch_skips_the_stored_lookup_entirely(self):
        conversation = _desktop_conversation()
        calls = _enrich(
            conversation,
            meetings=[_meeting_record()],
            env={'CONVERSATION_STORED_MEETING_CONTEXT_ENABLED': 'false'},
        )

        assert calls == []
        assert _stored_context(conversation) is None

    def test_the_google_and_ocr_layers_stay_off_by_default(self):
        conversation = _desktop_conversation()
        cleared = {'CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED': '', 'CONVERSATION_OCR_CONTEXT_ENABLED': ''}
        with (
            patch.dict(os.environ, cleared, clear=False),
            patch.object(pc.redis_db, 'get_conversation_meeting_id', return_value=None),
            patch.object(pc.calendar_db, 'get_meetings_in_time_range', return_value=[]),
            patch.object(pc, 'get_overlapping_calendar_event', MagicMock()) as calendar,
            patch.object(pc.screen_activity_db, 'get_screen_activity', MagicMock()) as screen,
        ):
            pc._enrich_meeting_context('uid-meeting', conversation)

        calendar.assert_not_called()
        screen.assert_not_called()


class TestNeverMutatesTheUsersCalendar:
    def test_enrichment_does_not_write_back_to_google_calendar(self):
        conversation = _desktop_conversation()
        with patch.object(pc, 'write_conversation_link_to_calendar_event', MagicMock()) as write_back:
            _enrich(
                conversation,
                meetings=[_meeting_record()],
                env={'CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED': 'true'},
            )
        write_back.assert_not_called()

"""Calendar overlap outranks discard (SCA-381).

`utils.llm.conversation_processing.should_discard_conversation` discards short
scraps with no calendar awareness, so a 25s recording made *inside* a booked
meeting vanished. At the discard decision in `process_conversation._get_structured`
a positive overlap against a non-declined calendar meeting — stored meeting
intent (`users/{uid}/meetings`) first, then a read-only Google Calendar lookup —
keeps the conversation. Every other outcome (no overlap, declined/cancelled
event, disconnected calendar, lookup error) leaves the discard verdict standing:
the override only fires on a positive hit, it never fails a conversation.

`process_conversation` is loaded through the sanctioned `stub_modules` +
`load_module_fresh` seam (see `backend/docs/test_isolation.md`) so nothing
stub-fed leaks into other test modules. `utils.conversations.calendar_linking`
is stubbed here; its matching rules are covered by
`test_calendar_linking_overlap_selection.py`.
"""

import os
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFgX7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

CONVERSATION_START = datetime(2026, 8, 18, 19, 35, tzinfo=timezone.utc)
CONVERSATION_END = CONVERSATION_START + timedelta(seconds=25)  # the 25s scrap
MEETING_START = datetime(2026, 8, 18, 19, 30, tzinfo=timezone.utc)
MEETING_END = datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc)

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


def _scrap_conversation():
    from models.conversation import Conversation
    from models.conversation_enums import ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    return Conversation(
        id='conv-scrap',
        created_at=CONVERSATION_START,
        started_at=CONVERSATION_START,
        finished_at=CONVERSATION_END,
        structured=Structured(),
        transcript_segments=[
            TranscriptSegment(
                id='seg-1',
                text='Two people are discussing the scaling plan.',
                speaker='SPEAKER_00',
                speaker_id=0,
                is_user=True,
                start=0.0,
                end=25.0,
            )
        ],
        source=ConversationSource.desktop,
    )


def _meeting_record() -> dict:
    return {
        'id': 'doc-evt',
        'calendar_event_id': 'evt-scaling-forever',
        'title': 'Scaling Forever sync',
        'start_time': MEETING_START,
        'end_time': MEETING_END,
        'duration_minutes': 30,
        'participants': [],
        'calendar_source': 'macos_calendar',
    }


def _run_discard(conversation, *, meetings, google_result=None, google_error=None):
    """Run `_get_structured` with the discard verdict forced True.

    Returns `(structured, discarded, google_mock)`; `google_mock` captures the
    read-only Google lookup so tests can assert it was (or was not) reached.
    """
    from models.structured import Structured

    google_mock = AsyncMock(return_value=google_result, side_effect=google_error)
    with (
        patch.object(pc.notification_db, 'get_user_time_zone', MagicMock(return_value=None)),
        patch.object(pc.users_db, 'get_user_language_preference', MagicMock(return_value=None)),
        patch.object(pc, 'track_usage', lambda *args, **kwargs: nullcontext()),
        patch.object(pc, 'should_discard_conversation', MagicMock(return_value=True)),
        patch.object(pc.calendar_db, 'get_meetings_in_time_range', MagicMock(return_value=list(meetings or []))),
        patch.object(pc, 'get_overlapping_calendar_event', google_mock),
        patch.object(
            pc,
            'get_transcript_structure',
            MagicMock(return_value=Structured(title='Kept by calendar overlap')),
        ),
        patch.object(pc, 'extract_action_items', MagicMock(return_value=[])),
        patch.object(pc, '_fetch_dedup_candidates', MagicMock(return_value=[])),
        patch.object(pc, '_primary_user_name', MagicMock(return_value=None)),
    ):
        structured, discarded = pc._get_structured('uid-scrap', 'en', conversation)

    return structured, discarded, google_mock


class TestOverlapKeepsTheScrap:
    def test_stored_meeting_overlap_keeps_a_discarded_scrap(self):
        structured, discarded, google = _run_discard(_scrap_conversation(), meetings=[_meeting_record()])

        assert discarded is False, 'a scrap recorded inside a booked meeting must not be discarded'
        assert structured.title == 'Kept by calendar overlap'
        google.assert_not_called(), 'a stored-meeting hit must not also pay the Google lookup'

    def test_google_event_overlap_keeps_a_scrap_with_no_stored_meeting(self):
        from models.conversation import CalendarEventLink

        link = CalendarEventLink(
            event_id='evt-1',
            title='Scaling Forever sync',
            start_time=MEETING_START,
            end_time=MEETING_END,
        )
        structured, discarded, google = _run_discard(_scrap_conversation(), meetings=[], google_result=link)

        assert discarded is False
        assert structured.title == 'Kept by calendar overlap'
        google.assert_awaited_once()

    def test_the_google_keep_lookup_requires_an_accepted_event(self):
        """The discard override must not keep on declined/cancelled events."""
        from models.conversation import CalendarEventLink

        link = CalendarEventLink(
            event_id='evt-1',
            title='Declined sync',
            start_time=MEETING_START,
            end_time=MEETING_END,
        )
        _, _, google = _run_discard(_scrap_conversation(), meetings=[], google_result=link)

        assert google.await_args.kwargs.get('require_accepted') is True


class TestEverythingElseStillDiscards:
    def test_no_overlapping_meeting_discards(self):
        structured, discarded, _ = _run_discard(_scrap_conversation(), meetings=[], google_result=None)

        assert discarded is True
        assert structured.title == ''

    def test_non_overlapping_stored_meeting_discards(self):
        wrong_window = _meeting_record()
        wrong_window['start_time'] = MEETING_START + timedelta(hours=2)
        wrong_window['end_time'] = MEETING_START + timedelta(hours=2, minutes=30)
        _, discarded, google = _run_discard(_scrap_conversation(), meetings=[wrong_window])

        assert discarded is True
        google.assert_awaited_once(), 'a stored miss must fall through to the Google lookup'

    def test_calendar_lookup_errors_fail_open_to_discarded(self):
        _, discarded, _ = _run_discard(
            _scrap_conversation(),
            meetings=[],
            google_error=RuntimeError('google unavailable'),
        )

        assert discarded is True

    def test_stored_meetings_read_error_falls_through_to_google_then_discards(self):
        from models.structured import Structured

        google_mock = AsyncMock(return_value=None)
        with (
            patch.object(pc.notification_db, 'get_user_time_zone', MagicMock(return_value=None)),
            patch.object(pc.users_db, 'get_user_language_preference', MagicMock(return_value=None)),
            patch.object(pc, 'track_usage', lambda *args, **kwargs: nullcontext()),
            patch.object(pc, 'should_discard_conversation', MagicMock(return_value=True)),
            patch.object(
                pc.calendar_db,
                'get_meetings_in_time_range',
                MagicMock(side_effect=RuntimeError('firestore unavailable')),
            ),
            patch.object(pc, 'get_overlapping_calendar_event', google_mock),
            patch.object(pc, 'get_transcript_structure', MagicMock(return_value=Structured(title='x'))),
        ):
            structured, discarded = pc._get_structured('uid-scrap', 'en', _scrap_conversation())

        assert discarded is True
        google_mock.assert_awaited_once()
        assert structured.title == ''

    def test_a_kept_scrap_still_reaches_summarization_only_once(self):
        structure = MagicMock()
        with (
            patch.object(pc.notification_db, 'get_user_time_zone', MagicMock(return_value=None)),
            patch.object(pc.users_db, 'get_user_language_preference', MagicMock(return_value=None)),
            patch.object(pc, 'track_usage', lambda *args, **kwargs: nullcontext()),
            patch.object(pc, 'should_discard_conversation', MagicMock(return_value=True)),
            patch.object(pc.calendar_db, 'get_meetings_in_time_range', MagicMock(return_value=[_meeting_record()])),
            patch.object(pc, 'get_overlapping_calendar_event', AsyncMock(return_value=None)),
            patch.object(pc, 'get_transcript_structure', structure),
            patch.object(pc, 'extract_action_items', MagicMock(return_value=[])),
            patch.object(pc, '_fetch_dedup_candidates', MagicMock(return_value=[])),
            patch.object(pc, '_primary_user_name', MagicMock(return_value=None)),
        ):
            from models.structured import Structured

            structure.return_value = Structured(title='Kept by calendar overlap')
            _, discarded = pc._get_structured('uid-scrap', 'en', _scrap_conversation())

        assert discarded is False
        assert structure.call_count == 1

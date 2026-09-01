import os
import sys
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.conversation import CalendarEventLink, CreateConversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
START = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)

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
    fakes: dict[str, ModuleType] = {}
    for name in _STUBBED:
        module = AutoMockModule(name)
        if name == 'langchain_core' or name.startswith('langchain_core.'):
            module.__path__ = []  # type: ignore[attr-defined]
        fakes[name] = module

    import hashlib
    import uuid

    fakes['database._client'].document_id_from_seed = lambda seed: str(  # type: ignore[attr-defined]
        uuid.UUID(hashlib.sha256(seed.encode()).hexdigest()[:32])
    )

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


def _request(source: ConversationSource) -> CreateConversation:
    return CreateConversation(
        started_at=START,
        finished_at=START + timedelta(seconds=30),
        source=source,
        transcript_segments=[
            TranscriptSegment(
                id='segment-1',
                text='Please capture this onboarding proof.',
                speaker='SPEAKER_00',
                is_user=True,
                person_id='person-1',
                start=0,
                end=30,
            )
        ],
    )


def _run(source: ConversationSource):
    structured = Structured(title='Welcome to Omi', overview='The first-run walkthrough completed.')
    calendar_event = CalendarEventLink(
        event_id='calendar-1',
        title='Walkthrough',
        attendees=['Ada'],
        attendee_emails=['ada@example.com'],
        start_time=START,
        end_time=START + timedelta(seconds=30),
        html_link='https://calendar.example/event',
    )
    calls = {
        'structured': MagicMock(return_value=(structured, False)),
        'enrich': MagicMock(),
        'people': MagicMock(return_value=[{'id': 'person-1', 'name': 'Ada'}]),
        'create': MagicMock(return_value=True),
        'persist': MagicMock(return_value=True),
        'memory': MagicMock(),
        'action_items': MagicMock(),
        'goals': MagicMock(),
        'apps': MagicMock(),
        'calendar_lookup': AsyncMock(return_value=calendar_event),
        'calendar_link': AsyncMock(),
        'folders': MagicMock(return_value=[{'id': 'folder-1'}]),
        'folder_assign': MagicMock(return_value=('folder-1', 0.99, 'fixture')),
        'webhook': AsyncMock(),
        'structured_vector': MagicMock(),
        'transcript_vectors': MagicMock(),
    }

    def run_inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    patches = [
        patch.dict(os.environ, {'GOOGLE_CALENDAR_AUTO_LINK_ENABLED': 'true'}, clear=False),
        patch.object(pc, 'is_trial_paywalled', return_value=False),
        patch.object(pc, 'should_defer_desktop_processing', return_value=False),
        patch.object(pc, '_get_structured', calls['structured']),
        patch.object(pc, '_enrich_meeting_context', calls['enrich']),
        patch.object(pc.users_db, 'get_people_by_ids', calls['people']),
        patch.object(pc.lifecycle_service, 'create_completed_conversation', calls['create']),
        patch.object(pc.lifecycle_service, 'persist_processed_conversation', calls['persist']),
        patch.object(pc, 'resolve_authorized_first_open_plan', return_value=SimpleNamespace(defer_derived_work=False)),
        patch.object(pc, '_extract_memories', calls['memory']),
        patch.object(pc, '_save_action_items', calls['action_items']),
        patch.object(pc, 'update_goal_progress', calls['goals']),
        patch.object(pc, 'trigger_conversation_apps', calls['apps']),
        patch.object(pc, 'get_overlapping_calendar_event', calls['calendar_lookup']),
        patch.object(pc, 'write_conversation_link_to_calendar_event', calls['calendar_link']),
        patch.object(pc.folders_db, 'get_folders', calls['folders']),
        patch.object(pc.folders_db, 'resolve_category_folder_id', return_value='folder-1'),
        patch.object(pc, 'assign_conversation_to_folder', calls['folder_assign']),
        patch.object(pc, 'conversation_created_webhook', calls['webhook']),
        patch.object(pc, 'save_structured_vector', calls['structured_vector']),
        patch.object(pc, 'save_transcript_chunk_vectors', calls['transcript_vectors']),
        patch.object(pc, 'TRANSCRIPT_CHUNK_INDEXING_ENABLED', True),
        patch.object(pc, 'conversation_apps_opt_in_only', return_value=False),
        patch.object(pc, 'submit_with_context', side_effect=run_inline),
    ]
    with ExitStack() as stack:
        for active_patch in patches:
            stack.enter_context(active_patch)
        result = pc.process_conversation('uid-policy', 'en', _request(source), bypass_jit_first_open=True)

    return result, calls


def test_onboarding_persists_completed_summary_before_skipping_every_derived_effect():
    result, calls = _run(ConversationSource.onboarding)

    calls['structured'].assert_called_once()
    calls['create'].assert_called_once()
    calls['persist'].assert_not_called()
    persisted_payload = calls['create'].call_args.args[1]
    assert persisted_payload['status'] == ConversationStatus.completed
    assert persisted_payload['structured']['title'] == 'Welcome to Omi'
    assert result.status == ConversationStatus.completed

    for stage in (
        'enrich',
        'people',
        'memory',
        'action_items',
        'goals',
        'apps',
        'calendar_lookup',
        'calendar_link',
        'folders',
        'folder_assign',
        'webhook',
        'structured_vector',
        'transcript_vectors',
    ):
        assert calls[stage].call_count == 0, f'onboarding unexpectedly reached {stage}'


def test_normal_source_reaches_every_derived_effect_after_completed_persistence():
    result, calls = _run(ConversationSource.phone)

    calls['structured'].assert_called_once()
    calls['create'].assert_called_once()
    calls['persist'].assert_not_called()
    persisted_payload = calls['create'].call_args.args[1]
    assert persisted_payload['status'] == ConversationStatus.completed
    assert result.status == ConversationStatus.completed

    for stage in (
        'enrich',
        'people',
        'memory',
        'action_items',
        'goals',
        'apps',
        'calendar_lookup',
        'calendar_link',
        'folders',
        'folder_assign',
        'webhook',
        'structured_vector',
        'transcript_vectors',
    ):
        assert calls[stage].call_count >= 1, f'normal processing never reached {stage}'

"""Overlap linking must never short-circuit the ordinary content discard gate.

The requested metadata-only wire contract supersedes #13703's auto-discard.
The durable-finalizer and transaction cases live in test_duplicate_capture_policy.
"""

import os
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFgX7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

T0 = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)
ROOM_TEXT = (
    'okay so the plan for the pendant firmware release is to ship the codec fix first '
    'that works for me but the app team wants the opus change behind a flag '
    'i think we should also bump the advertised battery estimate once the new curve lands '
    'the battery curve is not validated yet so keep the estimate where it is '
    'let me write the release notes tonight and send them to the hardware channel'
)
OTHER_TEXT = (
    'the quarterly numbers came in above forecast because renewals held up better than we modeled '
    'marketing wants a bigger event budget for the conference season and finance is pushing back '
    'we agreed to revisit hiring for the support team after the next board meeting closes'
)

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


def _segments(text: str, seconds: float):
    from models.transcript_segment import TranscriptSegment

    words = text.split()
    half = len(words) // 2
    return [
        TranscriptSegment(
            id='seg-1',
            text=' '.join(words[:half]),
            speaker='SPEAKER_00',
            speaker_id=0,
            is_user=True,
            start=0.0,
            end=seconds / 2,
        ),
        TranscriptSegment(
            id='seg-2',
            text=' '.join(words[half:]),
            speaker='SPEAKER_01',
            speaker_id=1,
            is_user=False,
            start=seconds / 2,
            end=seconds,
        ),
    ]


def _pendant_conversation(*, seconds: float = 300.0):
    """The Omi device stream, arriving through the phone app, mid-finalization."""
    from models.conversation import Conversation
    from models.conversation_enums import ConversationSource, ConversationStatus
    from models.structured import Structured

    return Conversation(
        id='pendant-conv',
        created_at=T0 + timedelta(seconds=4),
        started_at=T0 + timedelta(seconds=4),
        finished_at=T0 + timedelta(seconds=4 + seconds),
        structured=Structured(),
        transcript_segments=_segments(ROOM_TEXT, seconds),
        source=ConversationSource.omi,
        status=ConversationStatus.processing,
        client_device_id='phone-hash',
        client_platform='ios',
        external_data={'conversation_role': 'ambient'},
    )


def _mac_row(*, text: str = ROOM_TEXT, status: str = 'completed', created_at: datetime = T0, seconds: float = 310.0):
    """The macOS microphone capture as `get_conversations_finished_after` returns it."""
    words = text.split()
    half = len(words) // 2
    return {
        'id': 'mac-conv',
        'created_at': created_at,
        'started_at': T0,
        'finished_at': T0 + timedelta(seconds=seconds),
        'status': status,
        'source': 'desktop',
        'discarded': False,
        'client_device_id': 'mac-hash',
        'client_platform': 'macos',
        'transcript_segments': [
            {'text': ' '.join(words[:half]), 'start': 0.0, 'end': seconds / 2},
            {'text': ' '.join(words[half:]), 'start': seconds / 2, 'end': seconds},
        ],
    }


def _run(conversation, *, rows=None, lookup_error=None, force_process=False):
    """Run `_get_structured` with the LLM gates mocked and the capture lookup controlled.

    Returns `(structured, discarded, lookup_mock, discard_gate_mock, fallback_mock)`.
    """
    from models.structured import Structured

    lookup = MagicMock(return_value=list(rows or []), side_effect=lookup_error)
    discard_gate = MagicMock(return_value=True)
    fallback = MagicMock()
    with (
        patch.object(pc.notification_db, 'get_user_time_zone', MagicMock(return_value=None)),
        patch.object(pc.users_db, 'get_user_language_preference', MagicMock(return_value=None)),
        patch.object(pc, 'track_usage', lambda *args, **kwargs: nullcontext()),
        patch.object(pc.conversations_db, 'get_conversations_finished_after', lookup),
        patch.object(pc, 'should_discard_conversation', discard_gate),
        patch.object(pc, '_calendar_overlap_retains_conversation', MagicMock(return_value=False)),
        patch.object(pc, 'record_fallback', fallback),
        patch.object(pc, 'get_transcript_structure', MagicMock(return_value=Structured(title='Summarized'))),
        patch.object(pc, 'get_reprocess_transcript_structure', MagicMock(return_value=Structured(title='Reprocessed'))),
        patch.object(pc, 'extract_action_items', MagicMock(return_value=[])),
        patch.object(pc, '_fetch_dedup_candidates', MagicMock(return_value=[])),
        patch.object(pc, '_primary_user_name', MagicMock(return_value=None)),
    ):
        structured, discarded = pc._get_structured('uid-3244', 'en', conversation, force_process=force_process)
    return structured, discarded, lookup, discard_gate, fallback


def test_cross_device_overlap_does_not_short_circuit_content_gate():
    conversation = _pendant_conversation()
    _, discarded, lookup, discard_gate, fallback = _run(conversation, rows=[_mac_row()])
    discard_gate.assert_called_once()
    lookup.assert_not_called()
    fallback.assert_not_called()
    assert discarded is True, 'only the mocked content verdict discards this capture'
    assert conversation.external_data == {'conversation_role': 'ambient'}


def test_reprocessing_still_never_discards():
    conversation = _pendant_conversation()
    structured, discarded, lookup, _, _ = _run(conversation, force_process=True)
    assert discarded is False
    assert structured.title == 'Reprocessed'
    lookup.assert_not_called()

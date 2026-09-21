"""The release probe must terminalize through the kept path, not the discard verdict.

Run 35583992730 (2026-09-21): the dev pusher release probe's conversation
was durably persisted with content, but only ~6 of 8 fixture passes were in
the client conversation when finalization read it (the trailing passes'
transcripts flushed at teardown, into the rollover generation). The durable
word count fell to the discard LLM, which fenced the synthetic transcript as
trivial; `_conversation_admits_fanout` correctly rejects a discarded row, so
the lane terminalized `stale` and the probe failed `terminal_failure`.

The discard gate is therefore exempted for the synthetic release-probe uid,
like every other desktop post-processing gate (see utils/release_probe.py).
These tests drive the real seam — `process_conversation._get_structured` and
`process_conversation._get_conversation_obj` — and pin both verdict arms:
the LLM discard decision and the empty-title fallback.

`process_conversation` is loaded through the sanctioned `stub_modules` +
`load_module_fresh` seam (see `backend/docs/test_isolation.md`) so nothing
stub-fed leaks into other test modules.
"""

import os
import sys
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Warm the jsonschema -> referencing -> rpds chain before any `stub_modules`
# block can snapshot sys.modules (same hazard note as
# test_discard_gate_duration_input.py).
import jsonschema  # noqa: F401
import pydantic.root_model  # noqa: F401

from testing.import_isolation import AutoMockModule, load_module_fresh, package_submodule_stubs, stub_modules

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

from utils.release_probe import RELEASE_PROBE_UID  # noqa: E402

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

SESSION_ORIGIN = datetime(2026, 9, 21, 9, 38, 21, tzinfo=timezone.utc)

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

    # Prometheus collectors register at import; stub so a later fresh-load in
    # the same pytest process does not die on a duplicated timeseries.
    fakes['utils.metrics'] = AutoMockModule('utils.metrics')
    for name, module in package_submodule_stubs('utils.observability').items():
        fakes[name] = module

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


def _conversation(segments):
    from models.conversation import Conversation
    from models.conversation_enums import ConversationSource
    from models.structured import Structured

    return Conversation(
        id='conv-probe',
        created_at=SESSION_ORIGIN,
        started_at=SESSION_ORIGIN,
        finished_at=SESSION_ORIGIN,
        structured=Structured(),
        transcript_segments=segments,
        source=ConversationSource.desktop,
    )


def _segment(text: str, start: float, end: float):
    from models.transcript_segment import TranscriptSegment

    return TranscriptSegment(
        id=f'seg-{start}-{end}',
        text=text,
        speaker='SPEAKER_00',
        speaker_id=0,
        is_user=True,
        start=start,
        end=end,
    )


def _structured(title: str):
    from models.structured import Structured

    return Structured(title=title)


class TestReleaseProbeSkipsTheDiscardVerdict:
    def test_probe_uid_never_consults_the_discard_gate(self):
        """631d6ced's fixture loop could not make the keep line deterministic:
        the durable word count depends on STT yield and late flushes, so the
        gate itself must not run for the probe uid."""
        conversation = _conversation([_segment('he began a confused complaint against the wizard', 0.0, 4.0)])
        gate = MagicMock(return_value=True)

        with (
            patch.object(pc.notification_db, 'get_user_time_zone', MagicMock(return_value=None)),
            patch.object(pc.users_db, 'get_user_language_preference', MagicMock(return_value=None)),
            patch.object(pc, 'track_usage', lambda *args, **kwargs: nullcontext()),
            patch.object(pc, 'should_discard_conversation', gate),
            patch.object(pc, '_conversation_notes_v2_enabled', MagicMock(return_value=False)),
            patch.object(pc, 'get_transcript_structure', MagicMock(return_value=_structured('Release probe reading'))),
            patch.object(pc, 'extract_action_items', MagicMock(return_value=[])),
            patch.object(pc.calendar_db, 'get_meetings_in_time_range', MagicMock(return_value=[])),
            patch.object(pc, 'get_overlapping_calendar_event', AsyncMock(return_value=None)),
        ):
            structured, discarded = pc._get_structured(RELEASE_PROBE_UID, 'en', conversation)

        gate.assert_not_called()
        assert discarded is False
        assert structured.title == 'Release probe reading'

    def test_regular_uid_still_receives_the_discard_verdict(self):
        conversation = _conversation([_segment('okay sure', 0.0, 3.0)])
        gate = MagicMock(return_value=True)

        with (
            patch.object(pc.notification_db, 'get_user_time_zone', MagicMock(return_value=None)),
            patch.object(pc.users_db, 'get_user_language_preference', MagicMock(return_value=None)),
            patch.object(pc, 'track_usage', lambda *args, **kwargs: nullcontext()),
            patch.object(pc, 'should_discard_conversation', gate),
            patch.object(pc.calendar_db, 'get_meetings_in_time_range', MagicMock(return_value=[])),
            patch.object(pc, 'get_overlapping_calendar_event', AsyncMock(return_value=None)),
        ):
            _, discarded = pc._get_structured('uid-human', 'en', conversation)

        gate.assert_called_once()
        assert discarded is True


class TestReleaseProbeSkipsTheEmptyTitleFallback:
    def test_probe_uid_with_an_empty_llm_title_is_not_discarded(self):
        result = pc._get_conversation_obj(RELEASE_PROBE_UID, _structured(''), _conversation([]))

        assert result.discarded is False

    def test_regular_uid_with_an_empty_llm_title_is_discarded(self):
        result = pc._get_conversation_obj('uid-human', _structured(''), _conversation([]))

        assert result.discarded is True

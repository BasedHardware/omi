"""The discard gate must be told the transcript span, not the wall window.

Measured on a real account 2026-09-07: `started_at` for live-socket
conversations is the streaming-session origin, so an 8-second dictation scrap
recorded 42 minutes into the socket arrived at
`should_discard_conversation` labelled 2565 seconds. The prompt only applies its
stricter "under 2 minutes" bar when `duration_seconds < 120`, so the short-content
rule never fired and the scrap was kept.

This drives the real seam — `process_conversation._get_structured` — and captures
the `duration_seconds` the gate actually receives.

`process_conversation` is loaded through the sanctioned `stub_modules` +
`load_module_fresh` seam (see `backend/docs/test_isolation.md`) so nothing
stub-fed leaks into other test modules.
"""

import os
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Warm the jsonschema -> referencing -> rpds chain before any `stub_modules`
# block can snapshot sys.modules. `rpds`'s package init reads an attribute the
# parent package only gains on a first import, so a fixture that fresh-loads
# `process_conversation` (which reaches jsonschema through
# `utils.llm.gateway_client`) and then evicts the chain breaks the NEXT such
# fixture in the same pytest process. Importing here, at collection time, keeps
# the chain inside every fixture's snapshot. Same family of hazard as the
# prometheus/Cloud Tasks warm-ups in `test_process_conversation_free_tier_branch`.
import jsonschema  # noqa: F401
import pydantic.root_model  # noqa: F401

from testing.import_isolation import AutoMockModule, load_module_fresh, package_submodule_stubs, stub_modules

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFgX7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


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


# Astra's Cost, 2026-09-07: started_at 23:32:33, finished_at 00:15:18, 8s of speech.
SESSION_ORIGIN = datetime(2026, 9, 7, 23, 32, 33, tzinfo=timezone.utc)
FINISHED_AT = datetime(2026, 9, 8, 0, 15, 18, tzinfo=timezone.utc)
WALL_WINDOW_SECONDS = (FINISHED_AT - SESSION_ORIGIN).total_seconds()
TRANSCRIPT_SPAN_SECONDS = 8.0

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

    # `utils.metrics` and `utils.observability.*` register Prometheus collectors at
    # import. Fresh-loading and then evicting them leaves the process-wide
    # CollectorRegistry populated, so the NEXT fixture in this pytest process that
    # fresh-loads `process_conversation` dies on a duplicated timeseries. Stub them
    # here for the same reason `test_process_conversation_free_tier_branch` does.
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
        id='conv-scrap',
        created_at=SESSION_ORIGIN,
        started_at=SESSION_ORIGIN,
        finished_at=FINISHED_AT,
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


def _duration_seen_by_the_discard_gate(conversation):
    """Run `_get_structured` and return the duration the gate was handed."""
    seen: list = []

    def _capture(transcript, photos=None, duration_seconds=None, **kwargs):
        seen.append(duration_seconds)
        return True  # discard, so the run stops at the calendar override below

    with (
        patch.object(pc.notification_db, 'get_user_time_zone', MagicMock(return_value=None)),
        patch.object(pc.users_db, 'get_user_language_preference', MagicMock(return_value=None)),
        patch.object(pc, 'track_usage', lambda *args, **kwargs: nullcontext()),
        patch.object(pc, 'should_discard_conversation', MagicMock(side_effect=_capture)),
        patch.object(pc.calendar_db, 'get_meetings_in_time_range', MagicMock(return_value=[])),
        patch.object(pc, 'get_overlapping_calendar_event', AsyncMock(return_value=None)),
    ):
        pc._get_structured('uid-scrap', 'en', conversation)

    assert len(seen) == 1, 'the discard gate must be consulted exactly once'
    return seen[0]


class TestDiscardGateDuration:
    def test_the_gate_receives_the_transcript_span_not_the_session_wall_window(self):
        conversation = _conversation([_segment('how much does astra cost', 0.0, TRANSCRIPT_SPAN_SECONDS)])

        duration = _duration_seen_by_the_discard_gate(conversation)

        assert duration == TRANSCRIPT_SPAN_SECONDS
        assert duration < 120, (
            'the prompt only applies its short-content bar below 120s; '
            f'the wall window would have reported {WALL_WINDOW_SECONDS}s'
        )

    def test_the_wall_window_would_have_hidden_the_scrap(self):
        """Pins the magnitude of the defect so the vector cannot rot silently."""
        assert WALL_WINDOW_SECONDS == 2565.0

    def test_a_transcript_free_record_still_reports_the_wall_window(self):
        """Photo-only captures have no transcript span to prefer."""
        duration = _duration_seen_by_the_discard_gate(_conversation([]))

        assert duration == WALL_WINDOW_SECONDS

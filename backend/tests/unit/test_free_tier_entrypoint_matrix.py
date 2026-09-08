"""S6 named proof: every process_conversation entry point × free-tier cell.

Routers, sync, merge, listen, and postprocess cannot be driven hermetically under
0.3s CPU (Firestore/STT/FastAPI/Cloud Tasks). Each row therefore calls the
coordinator with the exact kwargs that entry's call site passes; the file:line
is in the row label. Isolation: stub_modules + load_module_fresh (same pattern
as test_process_conversation_free_tier_branch / test_authorize_managed_compute).

Observer contract (finalizer.py): persistence_observer(owned) and, when the
call site defers derived effects, derived_effects_observer(runner). owned False
→ ConversationFinalizationDisposition.fenced. owned True + a runner → the
finalizer runs that runner (completed). The minimum path must report actual
persistence (owned True) with a terminal no-derived-effects disposition — never
owned False, which would fence a conversation that was stored.

red-proof (1): force plan.mode to process_normally → flag-ON basic desktop rows fail
red-proof (2): remove the flag-OFF elif deferral → flag-OFF basic desktop no-force rows fail
red-proof (3): report_persistence(False) on the minimum → basic desktop rows fail
red-proof (4): reprocess_force cell without overlaying force_process=True → flag-OFF
    listen would defer instead of bypassing, so _get_structured would not be called
red-proof (5): desktop-sourced merge left on the legacy path (force bypasses deferral)
    → flag-ON basic merge would call _get_structured
red-proof (6): payload builders keep Conversation.dict()'s null processing_state
    default → flag-off / non-desktop / process_normally rows fail the persist contract
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from config.plan_catalog import PlanType
from models.conversation import Conversation, CreateConversation, ExternalIntegrationCreateConversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]
from models.transcript_segment import TranscriptSegment
from testing.import_isolation import AutoMockModule, load_module_fresh, package_submodule_stubs, stub_modules
import utils.managed_compute as managed_compute
from utils.managed_compute import Decision

_BACKEND = Path(__file__).resolve().parents[2]
_UID = 'matrix-uid'
_STARTED = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
_FINISHED = datetime(2026, 9, 2, 12, 5, tzinfo=timezone.utc)

# Real reprocess (routers/conversations.py:495, sync/pipeline.py:785) overlays these
# on the conversation it already holds. The reprocess_force cell must actually pass them.
_REPROCESS_FORCE_KWARGS: dict[str, bool] = {
    'force_process': True,
    'is_reprocess': True,
    'bypass_jit_first_open': True,
}

_PENDING_JIT: dict[str, Any] = {
    'state': 'pending',
    'effects': {
        'folder_assignment': {'state': 'pending'},
        'app_fanout': {'state': 'pending'},
    },
}


def _build_fakes() -> dict[str, ModuleType | None]:
    """Copied from test_process_conversation_free_tier_branch so this file stays standalone."""
    fakes: dict[str, ModuleType | None] = {}

    def add(name: str, mod: ModuleType) -> ModuleType:
        fakes[name] = mod
        return mod

    def put(mod: ModuleType, attr: str, value: Any) -> None:
        setattr(mod, attr, value)

    database_pkg = ModuleType('database')
    put(database_pkg, '__path__', [str(_BACKEND / 'database')])
    add('database', database_pkg)

    client_mod = ModuleType('database._client')
    put(client_mod, 'db', MagicMock(name='db'))
    put(client_mod, 'get_firestore_client', lambda: getattr(client_mod, 'db'))
    put(client_mod, 'document_id_from_seed', lambda seed: 'seed-id')
    add('database._client', client_mod)

    vector_db = add('database.vector_db', AutoMockModule('database.vector_db'))
    for attr in (
        'find_similar_memories',
        'upsert_memory_vector',
        'delete_memory_vector',
        'upsert_vector2',
        'update_vector_metadata',
        'upsert_action_item_vectors_batch',
        'delete_action_item_vectors_batch',
        'find_similar_action_items',
        'upsert_transcript_chunk_vectors',
        'upsert_memory_vectors_batch',
        'delete_memory_vectors_batch',
        'query_vectors',
    ):
        setattr(vector_db, attr, MagicMock())

    apps = add('database.apps', AutoMockModule('database.apps'))
    for attr in ('record_app_usage', 'get_omi_personas_by_uid_db', 'get_app_by_id_db'):
        setattr(apps, attr, MagicMock())

    users = add('database.users', AutoMockModule('database.users'))
    put(users, 'get_user_language_preference', MagicMock(return_value=None))
    put(users, 'get_people_by_ids', MagicMock(return_value=[]))
    put(users, 'get_data_protection_level', MagicMock(return_value='enhanced'))
    put(users, 'is_byok_active', MagicMock(return_value=False))

    add('database.screen_activity', AutoMockModule('database.screen_activity'))
    put(add('database.auth', AutoMockModule('database.auth')), 'get_user_name', MagicMock(return_value='Test User'))

    memories = add('database.memories', AutoMockModule('database.memories'))
    put(memories, 'save_memories', MagicMock())
    put(memories, 'delete_memories_for_conversation', MagicMock(return_value={'vector_delete_ids': []}))
    put(memories, 'get_memories', MagicMock(return_value=[]))

    for name in (
        'database.redis_db',
        'database.conversations',
        'database.notifications',
        'database.tasks',
        'database.trends',
        'database.action_items',
        'database.folders',
        'database.calendar_meetings',
        'database.short_term_memories',
        'database.review_queue',
        'database.llm_usage',
        'database.entities',
        'database.firestore_read_metrics',
        'database.goals',
    ):
        add(name, AutoMockModule(name))

    utils_pkg = ModuleType('utils')
    put(utils_pkg, '__path__', [str(_BACKEND / 'utils')])
    add('utils', utils_pkg)
    utils_llm_pkg = ModuleType('utils.llm')
    put(utils_llm_pkg, '__path__', [str(_BACKEND / 'utils' / 'llm')])
    add('utils.llm', utils_llm_pkg)
    utils_conv_pkg = ModuleType('utils.conversations')
    put(utils_conv_pkg, '__path__', [str(_BACKEND / 'utils' / 'conversations')])
    add('utils.conversations', utils_conv_pkg)

    conv_proc = ModuleType('utils.llm.conversation_processing')
    for attr in (
        'get_transcript_structure',
        'get_app_result',
        'should_discard_conversation',
        'get_suggested_apps_for_conversation',
        'get_reprocess_transcript_structure',
        'extract_action_items',
        'get_conversation_notes',
    ):
        setattr(conv_proc, attr, MagicMock())
    add('utils.llm.conversation_processing', conv_proc)

    add('utils.llm.conversation_prompt_prefix', AutoMockModule('utils.llm.conversation_prompt_prefix'))
    add('utils.apps', AutoMockModule('utils.apps'))
    put(add('utils.analytics', AutoMockModule('utils.analytics')), 'record_usage', MagicMock())
    add('utils.conversations.transcript_chunks', AutoMockModule('utils.conversations.transcript_chunks'))
    add('utils.conversations.calendar_linking', AutoMockModule('utils.conversations.calendar_linking'))
    meeting_context = add('utils.conversations.meeting_context', AutoMockModule('utils.conversations.meeting_context'))
    put(meeting_context, 'MAX_SCREEN_CONTEXT_ROWS', 80)
    put(meeting_context, 'MEETING_SEARCH_TOLERANCE_MINUTES', 5)
    add('utils.conversations.factory', AutoMockModule('utils.conversations.factory'))
    lifecycle = add('utils.conversations.lifecycle', AutoMockModule('utils.conversations.lifecycle'))
    put(lifecycle, 'persist_processed_conversation', MagicMock(return_value=True))
    put(lifecycle, 'create_completed_conversation', MagicMock(return_value=True))
    put(lifecycle, 'create_processing_conversation', MagicMock(return_value=True))
    put(
        add('utils.conversations.subjects', AutoMockModule('utils.conversations.subjects')),
        'infer_subject_from_segments',
        lambda segments: (None, None),
    )

    subscription = add('utils.subscription', AutoMockModule('utils.subscription'))
    put(subscription, 'is_trial_paywalled', MagicMock(return_value=False))
    put(subscription, 'should_defer_desktop_processing', MagicMock(return_value=False))
    put(subscription, 'request_has_llm_byok_key', MagicMock(return_value=False))

    byok = ModuleType('utils.byok')
    put(byok, 'get_byok_key', lambda _provider: None)
    put(byok, 'has_validated_byok_keys', lambda: False)
    add('utils.byok', byok)

    executors = add('utils.executors', AutoMockModule('utils.executors'))
    put(executors, 'db_executor', MagicMock())
    put(executors, 'llm_executor', MagicMock())
    put(executors, 'postprocess_executor', MagicMock())
    put(executors, 'submit_with_context', MagicMock())

    add('utils.llm.memories', AutoMockModule('utils.llm.memories'))
    add('utils.llm.external_integrations', AutoMockModule('utils.llm.external_integrations'))
    add('utils.llm.trends', AutoMockModule('utils.llm.trends'))
    add('utils.llm.goals', AutoMockModule('utils.llm.goals'))
    add('utils.llm.chat', AutoMockModule('utils.llm.chat'))
    add('utils.llm.clients', AutoMockModule('utils.llm.clients'))
    add('utils.notifications', AutoMockModule('utils.notifications'))
    add('utils.other.hume', AutoMockModule('utils.other.hume'))
    add('utils.retrieval.rag', AutoMockModule('utils.retrieval.rag'))
    add('utils.webhooks', AutoMockModule('utils.webhooks'))
    add('utils.task_sync', AutoMockModule('utils.task_sync'))
    add('utils.other.storage', AutoMockModule('utils.other.storage'))
    cloud_tasks = add('utils.cloud_tasks', AutoMockModule('utils.cloud_tasks'))
    put(cloud_tasks, 'is_audio_merge_dispatch_enabled', MagicMock(return_value=False))

    # process_conversation imports utils.metrics and utils.observability.finalization,
    # which register prometheus counters at import (omi_capture_finalization_failures_*).
    # Fresh-loading then evicting them leaves CollectorRegistry populated, so a later
    # real import duplicate-registers. Stub the whole chain so this fixture never
    # executes those modules; stub_modules restores sys.modules so a later real
    # import is the first-and-only registration.
    add('utils.metrics', AutoMockModule('utils.metrics'))
    for name, mod in package_submodule_stubs('utils.observability').items():
        add(name, mod)

    add('utils.memory.canonical_activation', AutoMockModule('utils.memory.canonical_activation'))
    add('utils.memory.memory_service', AutoMockModule('utils.memory.memory_service'))
    memory_system = ModuleType('utils.memory.memory_system')

    class _MemorySystem:
        LEGACY = 'legacy'
        CANONICAL = 'canonical'

    put(memory_system, 'MemorySystem', _MemorySystem)
    add('utils.memory.memory_system', memory_system)
    add('utils.memory.canonical_memory_adapter', AutoMockModule('utils.memory.canonical_memory_adapter'))
    add('utils.memory.decision_path_telemetry', AutoMockModule('utils.memory.decision_path_telemetry'))
    add('utils.memory.rejected_memory_feedback', AutoMockModule('utils.memory.rejected_memory_feedback'))

    task_intelligence = ModuleType('utils.task_intelligence')
    put(task_intelligence, '__path__', [])
    add('utils.task_intelligence', task_intelligence)
    capture = AutoMockModule('utils.task_intelligence.conversation_capture')
    put(capture, 'capture_enabled', MagicMock(return_value=False))
    add('utils.task_intelligence.conversation_capture', capture)
    put(task_intelligence, 'conversation_capture', capture)
    add(
        'utils.task_intelligence.workstream_association',
        AutoMockModule('utils.task_intelligence.workstream_association'),
    )

    return fakes


@pytest.fixture(scope='module')
def pc() -> Any:
    fakes = _build_fakes()
    with stub_modules(fakes):
        yield load_module_fresh(
            'utils.conversations.process_conversation',
            os.path.join(str(_BACKEND), 'utils', 'conversations', 'process_conversation.py'),
        )


def _segment() -> TranscriptSegment:
    return TranscriptSegment(text='Hello from capture', speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0)


def _create(source: ConversationSource) -> CreateConversation:
    return CreateConversation(
        started_at=_STARTED,
        finished_at=_FINISHED,
        transcript_segments=[_segment()],
        source=source,
        language='en',
    )


def _existing(source: ConversationSource) -> Conversation:
    return Conversation(
        id='conv-matrix',
        created_at=_STARTED,
        started_at=_STARTED,
        finished_at=_FINISHED,
        transcript_segments=[_segment()],
        source=source,
        language='en',
        structured=Structured(title='existing'),
        status=ConversationStatus.processing,
    )


def _external() -> ExternalIntegrationCreateConversation:
    return ExternalIntegrationCreateConversation(
        text='Hello from an external integration',
        started_at=_STARTED,
        finished_at=_FINISHED,
        language='en',
        source=ConversationSource.external_integration,
    )


class _ObserverCapture:
    """Mirrors finalizer.py: owned + derived_effects.append + derived_disposition."""

    def __init__(self) -> None:
        self.owned: list[bool] = []
        self.derived_runners: list[Any] = []
        self.dispositions: list[Any] = []


# Call-site kwargs read from the cited line. Drive the coordinator with those
# exact arguments; routers/sync/merge/listen/postprocess are not hermetic here.
# merge preserves the earliest conversation's source (merge_conversations.py:269).
# sync carries the client's source (pipeline.py:1051 → CreateConversation :1172;
# reprocess reads the stored conversation's source).
_ENTRIES: list[dict[str, Any]] = [
    {
        'id': 'conversations_enrich_187',
        'label': (
            'routers/conversations.py:187 _enrich_deferred_conversation '
            '(coordinator-with-exact-args; first-open force_process=True)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'force_process': True, 'is_reprocess': False},
        'attribution': 'non_user_reprocess',
    },
    {
        'id': 'conversations_create_351',
        'label': (
            'routers/conversations.py:351 process_in_progress_conversation '
            '(coordinator-with-exact-args; POST /v1/conversations force_process=True)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'force_process': True},
        'observer': True,
    },
    {
        'id': 'conversations_reprocess_495',
        'label': (
            'routers/conversations.py:495 reprocess_conversation '
            '(coordinator-with-exact-args; force+is_reprocess+bypass_jit)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'force_process': True, 'is_reprocess': True, 'bypass_jit_first_open': True},
        'attribution': 'non_user_reprocess',
    },
    {
        'id': 'developer_text_1500',
        'label': (
            'routers/developer.py:1500 create-from-text '
            '(coordinator-with-exact-args; source=external_integration, §1.2 non-desktop)'
        ),
        'kind': 'external',
        'source': ConversationSource.external_integration,
        'kwargs': {},
    },
    {
        'id': 'developer_from_segments_1776',
        'label': (
            'routers/developer.py:1776 from-segments '
            '(coordinator-with-exact-args; default source=phone, §1.2 non-desktop)'
        ),
        'kind': 'create',
        'source': ConversationSource.phone,
        'kwargs': {},
    },
    {
        'id': 'listen_157_via_finalizer_137',
        'label': (
            'routers/listen/conversations.py:157 → finalizer.py:137 '
            '(coordinator-with-exact-args; listen enqueues, cannot drive WS hermetically; '
            'source=desktop is a supported listen source at conversations.py:318; '
            'force_process defaults False, defer_derived_effects=True)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'force_process': False, 'defer_derived_effects': True},
        'observer': True,
        'derived_observer': True,
    },
    {
        'id': 'merge_354_omi',
        'label': (
            'utils/conversations/merge_conversations.py:354 '
            '(coordinator-with-exact-args; force_process=True is_reprocess=False; '
            'source from earliest conv :269 default omi — §1.2 non-desktop process_normally)'
        ),
        'kind': 'existing',
        'source': ConversationSource.omi,
        'kwargs': {'force_process': True, 'is_reprocess': False},
        'scenario': 'merge',
    },
    {
        'id': 'merge_354_desktop',
        'label': (
            'utils/conversations/merge_conversations.py:354 '
            '(coordinator-with-exact-args; force_process=True is_reprocess=False; '
            'source from earliest conv :269 desktop — flag-on basic lands at the minimum)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'force_process': True, 'is_reprocess': False},
        'scenario': 'merge',
    },
    {
        # The postprocess_conversation.py:164 row this replaces cited a module
        # deleted from main by a7bc5fd0c2. routers/integration.py:173 is the
        # live call site that was missing from the matrix entirely (the matrix
        # must see it even though it is safe today only because the route
        # forces source=external_integration).
        'id': 'integration_173',
        'label': (
            'routers/integration.py:173 external-integration capture '
            '(coordinator-with-exact-args; route forces source=external_integration '
            ':165, no extra kwargs; replaces the postprocess_conversation.py:164 '
            'row — module deleted by a7bc5fd0c2)'
        ),
        'kind': 'external',
        'source': ConversationSource.external_integration,
        'kwargs': {},
    },
    {
        'id': 'sync_reprocess_785_omi',
        'label': (
            'utils/sync/pipeline.py:785 _reprocess_conversation_after_update '
            '(coordinator-with-exact-args; force+is_reprocess+bypass_jit; '
            'source carried from the stored conversation, default omi — §1.2 non-desktop)'
        ),
        'kind': 'existing',
        'source': ConversationSource.omi,
        'kwargs': {'force_process': True, 'is_reprocess': True, 'bypass_jit_first_open': True},
        'observer': True,
        'scenario': 'sync',
    },
    {
        'id': 'sync_reprocess_785_desktop',
        'label': (
            'utils/sync/pipeline.py:785 _reprocess_conversation_after_update '
            '(coordinator-with-exact-args; force+is_reprocess+bypass_jit; '
            'source carried from the stored conversation — desktop flag-on basic → minimum)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'force_process': True, 'is_reprocess': True, 'bypass_jit_first_open': True},
        'observer': True,
        'scenario': 'sync',
    },
    {
        'id': 'sync_create_1179_omi',
        'label': (
            'utils/sync/pipeline.py:1179 process_segment create '
            '(coordinator-with-exact-args; source= parameter :1051 default omi — §1.2 non-desktop)'
        ),
        'kind': 'create',
        'source': ConversationSource.omi,
        'kwargs': {},
        'observer': True,
        'scenario': 'sync',
    },
    {
        'id': 'sync_create_1179_desktop',
        'label': (
            'utils/sync/pipeline.py:1179 process_segment create '
            '(coordinator-with-exact-args; source= parameter :1051 carried onto CreateConversation :1172; '
            'desktop-sourced sync of a basic user → flag-on minimum)'
        ),
        'kind': 'create',
        'source': ConversationSource.desktop,
        'kwargs': {},
        'observer': True,
        'scenario': 'sync',
    },
]


_CELLS: tuple[str, ...] = (
    'basic_with_projection',
    'basic_no_projection',
    'paid',
    'byok',
    'unknown_plan',
    'reprocess_force',
    'sync',
    'merge',
)

_BASIC_CELLS = frozenset({'basic_with_projection', 'basic_no_projection', 'reprocess_force', 'sync', 'merge'})


def _conversation_for(entry: dict[str, Any]) -> Any:
    source: ConversationSource = entry['source']
    kind = entry['kind']
    if kind == 'create':
        return _create(source)
    if kind == 'external':
        return _external()
    return _existing(source)


def _decision_for_cell(cell: str, funding_owner: str) -> Decision:
    if cell == 'paid':
        return Decision(
            allowed=True,
            reason='plan_paid',
            feature='conv_structure',
            funding_owner=funding_owner,
            plan=PlanType.plus,
            plan_resolved=True,
        )
    if cell == 'byok':
        return Decision(
            allowed=True,
            reason='byok',
            feature='conv_structure',
            funding_owner='byok',
            plan=PlanType.basic,
            plan_resolved=True,
        )
    if cell == 'unknown_plan':
        return Decision(
            allowed=True,
            reason='plan_unknown_fail_open',
            feature='conv_structure',
            funding_owner=funding_owner,
            plan=None,
            plan_resolved=False,
        )
    return Decision(
        allowed=False,
        reason='basic_not_entitled',
        feature='conv_structure',
        funding_owner=funding_owner,
        plan=PlanType.basic,
        plan_resolved=True,
    )


def _is_desktop(source: ConversationSource) -> bool:
    return source == ConversationSource.desktop


def _effective_kwargs(entry: dict[str, Any], cell: str) -> dict[str, Any]:
    kwargs = dict(entry['kwargs'])
    if cell == 'reprocess_force':
        kwargs.update(_REPROCESS_FORCE_KWARGS)
    return kwargs


def _legacy_defers(entry: dict[str, Any], cell: str, kwargs: dict[str, Any]) -> bool:
    return (
        _is_desktop(entry['source'])
        and cell in _BASIC_CELLS
        and not kwargs.get('force_process')
        and not kwargs.get('is_reprocess')
    )


def _flag_on_denies(entry: dict[str, Any], cell: str) -> bool:
    return _is_desktop(entry['source']) and cell in _BASIC_CELLS


def _process_normally(entry: dict[str, Any], cell: str, flag_on: bool, kwargs: dict[str, Any]) -> bool:
    return not (_flag_on_denies(entry, cell) if flag_on else _legacy_defers(entry, cell, kwargs))


def _expected_calls(entry: dict[str, Any], cell: str, flag_on: bool, kwargs: dict[str, Any]) -> dict[str, bool]:
    if not _process_normally(entry, cell, flag_on, kwargs):
        return {
            'get_structured': False,
            'extract_memories': False,
            'trigger_apps': False,
            'assign_folder': False,
            'init_first_open': False,
        }
    derived = not kwargs.get('defer_derived_effects', False)
    jit_eligible = not kwargs.get('bypass_jit_first_open', False) and not kwargs.get('is_reprocess', False)
    return {
        'get_structured': True,
        'extract_memories': derived,
        'trigger_apps': derived and not jit_eligible,
        'assign_folder': derived and not jit_eligible and not kwargs.get('is_reprocess', False),
        'init_first_open': jit_eligible,
    }


def _expected_observer(entry: dict[str, Any], cell: str, flag_on: bool, kwargs: dict[str, Any]) -> tuple[bool, str]:
    """Finalizer contract: (owned, DerivedEffectsDisposition value).

    Flag-on minimum reports actual persistence with TERMINAL_NO_DERIVED_EFFECTS.
    Legacy deferral still reports owned False (fenced) with the default RUN.
    Process-normally reports persist True with RUN.
    """
    if _process_normally(entry, cell, flag_on, kwargs):
        return True, 'run'
    if flag_on:
        return True, 'terminal_no_derived_effects'
    return False, 'run'


def _seed_pending_jit(conversation: Any) -> None:
    """Put a pending first-open obligation on the existing conversation's persist dump.

    jit_first_open lives on the Firestore doc, not the Pydantic model. Conversation.dict()
    delegates to model_dump, so wrapping only model_dump is enough for the pending
    obligation to reach _terminal_persist_payload.
    """
    original_dump = conversation.model_dump

    def dump_with_obligation(*args: Any, **kwargs: Any) -> dict[str, Any]:
        data = original_dump(*args, **kwargs)
        data['jit_first_open'] = dict(_PENDING_JIT)
        return data

    try:
        conversation.model_dump = dump_with_obligation
    except (AttributeError, ValueError, TypeError):
        object.__setattr__(conversation, 'model_dump', dump_with_obligation)


def _jit_cleared(payload: dict[str, Any]) -> bool:
    # persist_processing_result_with_lifecycle uses merge=True: omitting the field
    # leaves a pending obligation in place. The terminal write must set it.
    if 'jit_first_open' not in payload:
        return False
    value = payload['jit_first_open']
    if isinstance(value, dict) and value.get('state') == 'pending':
        return False
    return True


def _spy_managed_effects(monkeypatch: Any, pc: Any) -> dict[str, Any]:
    persist_payloads: list[dict[str, Any]] = []

    def capture_persist(_uid: str, data: dict[str, Any], *_args: Any, **_kwargs: Any) -> bool:
        persist_payloads.append(data)
        return True

    spies: dict[str, Any] = {
        'get_structured': MagicMock(return_value=(Structured(title='llm-title'), False)),
        'extract_memories': MagicMock(),
        'extract_memories_inner': MagicMock(),
        'trigger_apps': MagicMock(),
        'assign_folder': MagicMock(return_value=(None, 0.0, '')),
        'init_first_open': MagicMock(return_value=True),
        'should_defer': MagicMock(return_value=True),
        'authorize': MagicMock(),
        'persist_payloads': persist_payloads,
    }
    monkeypatch.setattr(pc, '_get_structured', spies['get_structured'])
    monkeypatch.setattr(pc, 'extract_memories', spies['extract_memories'])
    monkeypatch.setattr(pc, '_extract_memories', spies['extract_memories_inner'])
    monkeypatch.setattr(pc, 'trigger_conversation_apps', spies['trigger_apps'])
    monkeypatch.setattr(pc, 'assign_conversation_to_folder', spies['assign_folder'])
    monkeypatch.setattr(pc.conversations_db, 'initialize_first_open_work', spies['init_first_open'])
    monkeypatch.setattr(pc, 'should_defer_desktop_processing', spies['should_defer'])
    monkeypatch.setattr(pc, '_enrich_meeting_context', lambda *args, **kwargs: None)
    monkeypatch.setattr(pc, 'is_trial_paywalled', lambda *args, **kwargs: False)
    monkeypatch.setattr(pc, '_calendar_auto_link_enabled', lambda: False)
    monkeypatch.setattr(pc, 'record_jit_first_open', MagicMock())
    monkeypatch.setattr(pc.folders_db, 'get_folders', MagicMock(return_value=[{'id': 'folder-1'}]))
    monkeypatch.setattr(pc.folders_db, 'resolve_category_folder_id', MagicMock(return_value=None))
    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', capture_persist)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', capture_persist)
    monkeypatch.setattr(pc.lifecycle_service, 'create_processing_conversation', capture_persist)
    monkeypatch.setattr(
        pc,
        'resolve_authorized_first_open_plan',
        lambda **kwargs: SimpleNamespace(defer_derived_work=True),
    )

    @contextmanager
    def _noop_track(*_args: Any, **_kwargs: Any):
        yield

    monkeypatch.setattr(pc, 'track_usage', _noop_track)
    return spies


def _call_coordinator(
    pc: Any,
    entry: dict[str, Any],
    *,
    extra_kwargs: dict[str, Any] | None = None,
    seed_jit: bool = False,
    observer: _ObserverCapture | None = None,
) -> Any:
    conversation = _conversation_for(entry)
    if seed_jit:
        _seed_pending_jit(conversation)
    kwargs = dict(entry['kwargs'])
    if extra_kwargs:
        kwargs.update(extra_kwargs)
    capture = observer if observer is not None else _ObserverCapture()
    kwargs['persistence_observer'] = capture.owned.append
    kwargs['derived_effects_observer'] = capture.derived_runners.append
    kwargs['derived_effects_disposition_observer'] = capture.dispositions.append
    if entry.get('attribution') == 'non_user_reprocess':
        kwargs['app_usage_attribution'] = pc.AppUsageAttribution.NON_USER_REPROCESS
    return pc.process_conversation(_UID, 'en', conversation, **kwargs)


def _assert_spies(spies: dict[str, Any], expected: dict[str, bool]) -> None:
    spy_names = {
        'get_structured': 'get_structured',
        'extract_memories': 'extract_memories_inner',
        'trigger_apps': 'trigger_apps',
        'assign_folder': 'assign_folder',
        'init_first_open': 'init_first_open',
    }
    for name, called in expected.items():
        spy = spies[spy_names[name]]
        if called:
            spy.assert_called()
        else:
            spy.assert_not_called()


def _assert_persist_marker_contract(
    pc: Any,
    spies: dict[str, Any],
    entry: dict[str, Any],
    cell: str,
    flag_on: bool,
    kwargs: dict[str, Any],
) -> None:
    """Flag-off and non-desktop persists must omit the new marker key entirely.

    Missing versus explicit-null is a Firestore distinction. The dark rollout
    must not stamp ``terminal_no_derived_effects: null`` onto documents the
    parent never wrote. The merge-clear (key present, value None) is only for
    flag-on desktop process_normally — a paid reprocess of a prior minimum.
    """
    field = pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD
    payloads = [p for p in spies['persist_payloads'] if isinstance(p, dict)]
    assert payloads, 'coordinator must persist a payload'
    last = payloads[-1]
    consulted_normally = flag_on and _is_desktop(entry['source']) and _process_normally(entry, cell, flag_on, kwargs)
    if consulted_normally:
        assert field in last, 'flag-on desktop process_normally must merge-clear the stale marker'
        assert last[field] is None
        return
    if flag_on and _is_desktop(entry['source']):
        assert last.get(field) is True
        return
    assert field not in last, f'flag-off/non-desktop persist must omit {field!r} entirely; got {last.get(field)!r}'


def _assert_persist_processing_state_contract(
    pc: Any,
    spies: dict[str, Any],
    entry: dict[str, Any],
    cell: str,
    flag_on: bool,
    kwargs: dict[str, Any],
) -> None:
    """The modeled ``processing_state`` follows the marker's dark discipline.

    Missing versus explicit-null is a Firestore distinction and persist is
    merge=True. The dumped None default must never reach a payload: only the
    flag-on minimum writes a real value (``local_pending`` when no projection
    was delivered, absent-with-key-omitted when one was), and every
    process_normally persist leaves the key out entirely (the matrix drives
    fresh conversations, so there is no stale state to merge-clear).
    """
    payloads = [p for p in spies['persist_payloads'] if isinstance(p, dict)]
    assert payloads, 'coordinator must persist a payload'
    last = payloads[-1]
    if flag_on and _flag_on_denies(entry, cell):
        # Every flag-on basic desktop deny lands at the minimum store, whose
        # own has_projection is False in these rows (the basic_with_projection
        # overlay forces the plan's flag, not a delivered projection), so the
        # store writes the real local_pending state. A real value is never a
        # darkness violation — only the null default is.
        assert last.get('processing_state') == 'local_pending', 'the minimum is the one writer of a real state'
        return
    assert (
        'processing_state' not in last
    ), f'persist must omit a null processing_state entirely; got {last.get("processing_state")!r}'


def _assert_observer_contract(
    pc: Any,
    capture: _ObserverCapture,
    *,
    persisted: bool,
    disposition: str,
    kwargs: dict[str, Any],
) -> None:
    expected_disp = (
        pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS
        if disposition == 'terminal_no_derived_effects'
        else pc.DerivedEffectsDisposition.RUN
    )
    assert capture.owned == [
        persisted
    ], f'persistence observer expected {[persisted]} (disposition={disposition}), got {capture.owned}'
    assert capture.dispositions == [
        expected_disp
    ], f'derived-effects disposition expected {[expected_disp]}, got {capture.dispositions}'
    if disposition == 'terminal_no_derived_effects':
        assert persisted is True
        return
    if persisted and kwargs.get('defer_derived_effects'):
        assert len(capture.derived_runners) == 1


def _rows() -> list[tuple[str, dict[str, Any], str, bool]]:
    rows: list[tuple[str, dict[str, Any], str, bool]] = []
    for entry in _ENTRIES:
        for cell in _CELLS:
            if cell == 'sync' and entry.get('scenario') != 'sync':
                continue
            if cell == 'merge' and entry.get('scenario') != 'merge':
                continue
            for flag_on in (True, False):
                flag = 'flag_on' if flag_on else 'flag_off'
                rows.append((f'{flag}/{entry["id"]}/{cell}', entry, cell, flag_on))
    return rows


_MATRIX_ROWS = _rows()


# red-proof: force plan.mode to process_normally (flag-ON basic desktop would call _get_structured)
# red-proof: drop the flag-OFF elif deferral (flag-OFF basic desktop no-force would call _get_structured)
# red-proof: report_persistence(False) on the minimum (flag-ON basic desktop observer.owned != [True])
# red-proof: reprocess_force without overlaying force (flag-OFF listen would not call _get_structured)
# red-proof: desktop merge left on the legacy path (flag-ON basic merge would call _get_structured)
# red-proof: `_normal_persist_payload` always writes terminal_no_derived_effects=None
#   (flag-off and non-desktop persist payloads would contain the key)
# red-proof: the normal persist keeps Conversation.dict()'s null processing_state
#   default (F-1) — flag-off dark rows fail the processing_state persist contract
@pytest.mark.parametrize(
    'row_id, entry, cell, flag_on',
    _MATRIX_ROWS,
    ids=[row[0] for row in _MATRIX_ROWS],
)
def test_entrypoint_matrix(
    monkeypatch: Any, pc: Any, row_id: str, entry: dict[str, Any], cell: str, flag_on: bool
) -> None:
    del row_id
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: flag_on)
    spies = _spy_managed_effects(monkeypatch, pc)
    kwargs = _effective_kwargs(entry, cell)
    extra_kwargs = dict(_REPROCESS_FORCE_KWARGS) if cell == 'reprocess_force' else None
    seed_jit = flag_on and _flag_on_denies(entry, cell) and entry['kind'] == 'existing'

    def fake_authorize(uid: str, feature: str, funding_owner: str, **_kwargs: Any) -> Decision:
        return _decision_for_cell(cell, funding_owner)

    # The decision_for closure lives in utils.managed_compute (hoisted when the
    # connector memory producers started sharing it), so its seams patch there.
    monkeypatch.setattr(managed_compute, 'authorize_managed_compute', fake_authorize)
    monkeypatch.setattr(managed_compute, 'request_carries_validated_byok_key', lambda _feature: cell == 'byok')

    if flag_on and cell == 'basic_with_projection':
        real_resolve = pc.resolve_free_tier_processing_plan

        def resolve_with_projection(**resolve_kwargs: Any):
            resolve_kwargs['has_projection'] = True
            return real_resolve(**resolve_kwargs)

        monkeypatch.setattr(pc, 'resolve_free_tier_processing_plan', resolve_with_projection)

    captured_resolve: list[dict[str, Any]] = []
    if cell == 'reprocess_force':
        real_resolve_force = pc.resolve_free_tier_processing_plan

        def resolve_capturing_force(**resolve_kwargs: Any) -> Any:
            captured_resolve.append(resolve_kwargs)
            return real_resolve_force(**resolve_kwargs)

        monkeypatch.setattr(pc, 'resolve_free_tier_processing_plan', resolve_capturing_force)

    if not flag_on:
        spies['should_defer'].return_value = cell in _BASIC_CELLS and cell != 'byok'

    observer = _ObserverCapture()
    result = _call_coordinator(pc, entry, extra_kwargs=extra_kwargs, seed_jit=seed_jit, observer=observer)
    expected = _expected_calls(entry, cell, flag_on, kwargs)
    _assert_spies(spies, expected)

    persisted, disposition = _expected_observer(entry, cell, flag_on, kwargs)
    _assert_observer_contract(pc, observer, persisted=persisted, disposition=disposition, kwargs=kwargs)
    _assert_persist_marker_contract(pc, spies, entry, cell, flag_on, kwargs)
    _assert_persist_processing_state_contract(pc, spies, entry, cell, flag_on, kwargs)

    if cell == 'reprocess_force' and flag_on and _is_desktop(entry['source']):
        assert captured_resolve, 'reprocess_force must consult the policy with the overlay'
        seen = captured_resolve[0]
        assert seen.get('force_process') is True
        assert seen.get('is_reprocess') is True

    if not expected['get_structured']:
        spies['extract_memories'].assert_not_called()
        if flag_on:
            assert getattr(result, 'deferred', False) is False
            if seed_jit:
                raw_payloads: list[Any] = spies['persist_payloads']
                payloads: list[dict[str, Any]] = [p for p in raw_payloads if isinstance(p, dict)]
                assert payloads, 'minimum store must persist the existing conversation'
                last_payload = payloads[-1]
                assert _jit_cleared(last_payload), (
                    'terminal write must clear jit_first_open; merge=True persist '
                    f'would keep a pending obligation: {last_payload.get("jit_first_open")!r}'
                )
        else:
            assert result.deferred is True
            spies['should_defer'].assert_called()
    else:
        spies['get_structured'].assert_called_once()


# red-proof (1): apply `plan.mode = process_normally` after resolve → basic desktop calls _get_structured
def test_red_proof_flag_on_ignoring_plan_makes_basic_desktop_call_structured(monkeypatch: Any, pc: Any) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: True)
    spies = _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        managed_compute,
        'authorize_managed_compute',
        lambda *args, **kwargs: _decision_for_cell('basic_no_projection', 'omi'),
    )
    real_resolve = pc.resolve_free_tier_processing_plan

    def force_normally(**kwargs: Any):
        plan = real_resolve(**kwargs)
        return pc.FreeTierProcessingPlan(mode='process_normally', reason=plan.reason, decision=plan.decision)

    monkeypatch.setattr(pc, 'resolve_free_tier_processing_plan', force_normally)
    entry = next(e for e in _ENTRIES if e['id'] == 'conversations_create_351')
    _call_coordinator(pc, entry)
    spies['get_structured'].assert_called()


# red-proof (2): flag OFF, legacy elif gone (should_defer always False) → basic desktop no-force calls _get_structured
def test_red_proof_flag_off_legacy_removed_makes_basic_desktop_call_structured(monkeypatch: Any, pc: Any) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: False)
    spies = _spy_managed_effects(monkeypatch, pc)
    spies['should_defer'].return_value = False
    entry = next(e for e in _ENTRIES if e['id'] == 'listen_157_via_finalizer_137')
    _call_coordinator(pc, entry)
    spies['get_structured'].assert_called()


# red-proof (3): coordinator reporting persistence False on the minimum → basic rows fail
def test_red_proof_minimum_must_report_actual_persistence(monkeypatch: Any, pc: Any) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: True)
    _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        managed_compute,
        'authorize_managed_compute',
        lambda *args, **kwargs: _decision_for_cell('basic_no_projection', 'omi'),
    )
    entry = next(e for e in _ENTRIES if e['id'] == 'conversations_create_351')
    observer = _ObserverCapture()
    _call_coordinator(pc, entry, observer=observer)
    assert observer.owned == [True]
    assert observer.dispositions == [pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS]


# red-proof (4): reprocess_force cell not passing force → flag-OFF listen defers, _get_structured not called
def test_red_proof_reprocess_force_overlay_bypasses_legacy_deferral(monkeypatch: Any, pc: Any) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: False)
    spies = _spy_managed_effects(monkeypatch, pc)
    spies['should_defer'].return_value = True
    entry = next(e for e in _ENTRIES if e['id'] == 'listen_157_via_finalizer_137')
    _call_coordinator(pc, entry, extra_kwargs=dict(_REPROCESS_FORCE_KWARGS))
    spies['get_structured'].assert_called()


# red-proof (5): desktop-sourced merge left on the legacy path → force bypasses deferral, _get_structured called
def test_red_proof_desktop_merge_flag_on_basic_is_minimum_not_legacy(monkeypatch: Any, pc: Any) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: True)
    spies = _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        managed_compute,
        'authorize_managed_compute',
        lambda *args, **kwargs: _decision_for_cell('basic_no_projection', 'omi'),
    )
    entry = next(e for e in _ENTRIES if e['id'] == 'merge_354_desktop')
    observer = _ObserverCapture()
    _call_coordinator(pc, entry, observer=observer)
    spies['get_structured'].assert_not_called()
    assert observer.owned == [True]
    assert observer.dispositions == [pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS]


# red-proof (6): the normal persist keeping Conversation.dict()'s null
# processing_state default (the F-1 regression) → the flag-off dark row fails.
# Exercises the real `_normal_persist_payload` (no builder monkeypatch): if the
# builder regresses to a bare `conversation.dict()`, the key is present and
# this goes red.
def test_red_proof_null_processing_state_default_stamped_on_persist(monkeypatch: Any, pc: Any) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: False)
    spies = _spy_managed_effects(monkeypatch, pc)
    spies['should_defer'].return_value = False
    entry = next(e for e in _ENTRIES if e['id'] == 'conversations_create_351')
    _call_coordinator(pc, entry)
    payloads = [p for p in spies['persist_payloads'] if isinstance(p, dict)]
    assert payloads and 'processing_state' not in payloads[-1]

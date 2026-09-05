"""Coordinator free-tier branch (shard S6): flag-on wiring in process_conversation.

The production module pulls in database / langchain / memory chains that construct
clients at import time. Tests load it fresh inside stub_modules so stubs never leak
into sys.modules (see testing/import_isolation.py and test_authorize_managed_compute.py).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from config.plan_catalog import PlanType
from models.client_processing import (
    ClientProcessing,
    ProjectionProvenance,
    ProjectedStructure,
)
from models.conversation import Conversation, CreateConversation
from models.conversation_enums import ConversationProcessingState, ConversationSource, ConversationStatus
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from testing.import_isolation import AutoMockModule, load_module_fresh, package_submodule_stubs, stub_modules
import utils.managed_compute as managed_compute
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from database.first_open_obligations import claim_first_open_work
from utils.conversations import meeting_receipt as meeting_receipt_mod

_BACKEND = Path(__file__).resolve().parents[2]


def _build_fakes() -> dict[str, ModuleType]:
    fakes: dict[str, ModuleType] = {}

    def add(name: str, mod: ModuleType) -> ModuleType:
        fakes[name] = mod
        return mod

    database_pkg = ModuleType('database')
    database_pkg.__path__ = [str(_BACKEND / 'database')]  # type: ignore[attr-defined]
    add('database', database_pkg)

    client_mod = ModuleType('database._client')
    client_mod.db = MagicMock(name='db')
    client_mod.get_firestore_client = lambda: client_mod.db
    client_mod.document_id_from_seed = lambda seed: 'seed-id'
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
    users.get_user_language_preference = MagicMock(return_value=None)
    users.get_people_by_ids = MagicMock(return_value=[])
    users.get_data_protection_level = MagicMock(return_value='enhanced')
    users.is_byok_active = MagicMock(return_value=False)

    add('database.screen_activity', AutoMockModule('database.screen_activity'))
    add('database.auth', AutoMockModule('database.auth')).get_user_name = MagicMock(return_value='Test User')

    memories = add('database.memories', AutoMockModule('database.memories'))
    memories.save_memories = MagicMock()
    memories.delete_memories_for_conversation = MagicMock(return_value={'vector_delete_ids': []})
    memories.get_memories = MagicMock(return_value=[])

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
    utils_pkg.__path__ = [str(_BACKEND / 'utils')]  # type: ignore[attr-defined]
    add('utils', utils_pkg)
    utils_llm_pkg = ModuleType('utils.llm')
    utils_llm_pkg.__path__ = [str(_BACKEND / 'utils' / 'llm')]  # type: ignore[attr-defined]
    add('utils.llm', utils_llm_pkg)
    utils_conv_pkg = ModuleType('utils.conversations')
    utils_conv_pkg.__path__ = [str(_BACKEND / 'utils' / 'conversations')]  # type: ignore[attr-defined]
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
    add('utils.analytics', AutoMockModule('utils.analytics')).record_usage = MagicMock()
    add('utils.conversations.transcript_chunks', AutoMockModule('utils.conversations.transcript_chunks'))
    add('utils.conversations.calendar_linking', AutoMockModule('utils.conversations.calendar_linking'))
    meeting_context = add('utils.conversations.meeting_context', AutoMockModule('utils.conversations.meeting_context'))
    meeting_context.MAX_SCREEN_CONTEXT_ROWS = 80
    meeting_context.MEETING_SEARCH_TOLERANCE_MINUTES = 5
    add('utils.conversations.factory', AutoMockModule('utils.conversations.factory'))
    lifecycle = add('utils.conversations.lifecycle', AutoMockModule('utils.conversations.lifecycle'))
    lifecycle.persist_processed_conversation = MagicMock(return_value=True)
    lifecycle.create_completed_conversation = MagicMock(return_value=True)
    lifecycle.create_processing_conversation = MagicMock(return_value=True)
    add('utils.conversations.subjects', AutoMockModule('utils.conversations.subjects')).infer_subject_from_segments = (
        lambda segments: (None, None)
    )

    subscription = add('utils.subscription', AutoMockModule('utils.subscription'))
    subscription.is_trial_paywalled = MagicMock(return_value=False)
    subscription.should_defer_desktop_processing = MagicMock(return_value=False)
    subscription.request_has_llm_byok_key = MagicMock(return_value=False)

    byok = ModuleType('utils.byok')
    byok.get_byok_key = lambda _provider: None
    byok.has_validated_byok_keys = lambda: False
    add('utils.byok', byok)

    executors = add('utils.executors', AutoMockModule('utils.executors'))
    executors.db_executor = MagicMock()
    executors.llm_executor = MagicMock()
    executors.postprocess_executor = MagicMock()
    executors.submit_with_context = MagicMock()

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
    # process_conversation imports utils.cloud_tasks, which registers
    # google.cloud.tasks_v2 protobuf descriptors. Fresh-loading that chain
    # then evicting it leaves the descriptor pool populated, so a later real
    # import (e.g. test_lazy_conversation_processing) duplicate-registers.
    cloud_tasks = add('utils.cloud_tasks', AutoMockModule('utils.cloud_tasks'))
    cloud_tasks.is_audio_merge_dispatch_enabled = MagicMock(return_value=False)

    # process_conversation imports utils.metrics and utils.observability.finalization,
    # which register prometheus counters at import. Fresh-loading then evicting them
    # leaves CollectorRegistry populated, so a later real import duplicate-registers.
    add('utils.metrics', AutoMockModule('utils.metrics'))
    for name, mod in package_submodule_stubs('utils.observability').items():
        add(name, mod)

    add('utils.memory.canonical_activation', AutoMockModule('utils.memory.canonical_activation'))
    add('utils.memory.memory_service', AutoMockModule('utils.memory.memory_service'))
    memory_system = ModuleType('utils.memory.memory_system')

    class _MemorySystem:
        LEGACY = 'legacy'
        CANONICAL = 'canonical'

    memory_system.MemorySystem = _MemorySystem
    add('utils.memory.memory_system', memory_system)
    add('utils.memory.canonical_memory_adapter', AutoMockModule('utils.memory.canonical_memory_adapter'))
    add('utils.memory.decision_path_telemetry', AutoMockModule('utils.memory.decision_path_telemetry'))
    add('utils.memory.rejected_memory_feedback', AutoMockModule('utils.memory.rejected_memory_feedback'))

    task_intelligence = ModuleType('utils.task_intelligence')
    task_intelligence.__path__ = []  # type: ignore[attr-defined]
    add('utils.task_intelligence', task_intelligence)
    capture = AutoMockModule('utils.task_intelligence.conversation_capture')
    capture.capture_enabled = MagicMock(return_value=False)
    add('utils.task_intelligence.conversation_capture', capture)
    task_intelligence.conversation_capture = capture
    add(
        'utils.task_intelligence.workstream_association',
        AutoMockModule('utils.task_intelligence.workstream_association'),
    )
    add('utils.app_integrations', AutoMockModule('utils.app_integrations'))
    add('utils.conversations.location', AutoMockModule('utils.conversations.location'))
    add('utils.conversations.meeting_receipt', AutoMockModule('utils.conversations.meeting_receipt'))
    add('utils.jit_rollout', AutoMockModule('utils.jit_rollout'))
    add('utils.log_sanitizer', AutoMockModule('utils.log_sanitizer'))
    add('utils.retrieval.frame_request_authority', AutoMockModule('utils.retrieval.frame_request_authority'))
    add('utils.task_intelligence.proactive_engine', AutoMockModule('utils.task_intelligence.proactive_engine'))
    services_pkg = ModuleType('services')
    services_pkg.__path__ = []  # type: ignore[attr-defined]
    add('services', services_pkg)
    add('services.conversation_keyframes', AutoMockModule('services.conversation_keyframes'))

    return fakes


@pytest.fixture(scope='module')
def pc():
    fakes = _build_fakes()
    with stub_modules(fakes):
        yield load_module_fresh(
            'utils.conversations.process_conversation',
            os.path.join(str(_BACKEND), 'utils', 'conversations', 'process_conversation.py'),
        )


def _desktop_create() -> CreateConversation:
    return CreateConversation(
        started_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 2, 12, 5, tzinfo=timezone.utc),
        transcript_segments=[
            TranscriptSegment(
                text='Hello from the desktop capture', speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0
            )
        ],
        source=ConversationSource.desktop,
        language='en',
    )


def _existing_desktop(conversation_id: str = 'paid-then-basic') -> Conversation:
    return Conversation(
        id=conversation_id,
        created_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 1, 12, 5, tzinfo=timezone.utc),
        transcript_segments=[
            TranscriptSegment(
                text='Hello from the desktop capture', speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0
            )
        ],
        source=ConversationSource.desktop,
        language='en',
        structured=Structured(title='Paid-era title'),
        status=ConversationStatus.completed,
        deferred=False,
    )


def _plan(pc, mode: str, reason: str) -> Any:
    return pc.FreeTierProcessingPlan(mode=mode, reason=reason, decision=None)


def _enable_flag(monkeypatch, pc) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: True)


def _spy_managed_effects(monkeypatch, pc) -> dict[str, MagicMock]:
    spies = {
        'get_structured': MagicMock(return_value=(Structured(title='llm-title'), False)),
        'extract_memories': MagicMock(),
        'extract_memories_inner': MagicMock(),
        'trigger_apps': MagicMock(),
        'assign_folder': MagicMock(return_value=(None, 0.0, '')),
        'init_first_open': MagicMock(return_value=True),
        'should_defer': MagicMock(return_value=True),
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
    return spies


def _stub_completed_for_normal_path(monkeypatch, pc, conv_id: str = 'paid-conv') -> MagicMock:
    completed = MagicMock()
    completed.id = conv_id
    completed.source = ConversationSource.desktop
    completed.dict.return_value = {'id': conv_id, 'status': 'completed'}
    completed.discarded = False
    completed.started_at = None
    completed.finished_at = None
    completed.calendar_event = None
    completed.folder_id = None
    completed.structured = Structured(title='llm-title')
    completed.apps_results = []
    completed.suggested_summarization_apps = []
    completed.private_cloud_sync_enabled = False
    monkeypatch.setattr(pc, '_get_conversation_obj', lambda *args, **kwargs: completed)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', MagicMock(return_value=True))
    jit_plan = SimpleNamespace(defer_derived_work=True)
    monkeypatch.setattr(pc, 'resolve_authorized_first_open_plan', lambda **kwargs: jit_plan)
    return completed


# red-proof: `if False and plan.mode != 'process_normally'` (basic would call `_get_structured`)
def test_basic_desktop_without_projection_is_terminal_minimum(monkeypatch, pc) -> None:
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, 'deterministic_minimum', 'basic_not_entitled'),
    )
    created = MagicMock(return_value=True)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', created)
    persisted = MagicMock()
    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', persisted)

    result = pc.process_conversation('basic-uid', 'en', _desktop_create())

    assert result.deferred is False
    assert result.status == ConversationStatus.completed
    created.assert_called_once()
    persisted.assert_not_called()
    spies['get_structured'].assert_not_called()
    spies['extract_memories'].assert_not_called()
    spies['extract_memories_inner'].assert_not_called()
    spies['trigger_apps'].assert_not_called()
    spies['assign_folder'].assert_not_called()
    spies['init_first_open'].assert_not_called()
    spies['should_defer'].assert_not_called()


# red-proof: skip `_get_structured` on process_normally (paid desktop would not enrich)
def test_process_normally_reaches_structured_and_jit_block(monkeypatch, pc) -> None:
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, 'process_normally', 'plan_paid'),
    )
    jit_plan = SimpleNamespace(defer_derived_work=True)
    resolve_jit = MagicMock(return_value=jit_plan)
    monkeypatch.setattr(pc, 'resolve_authorized_first_open_plan', resolve_jit)
    monkeypatch.setattr(pc, 'record_jit_first_open', MagicMock())

    completed = MagicMock()
    completed.id = 'paid-conv'
    completed.source = ConversationSource.desktop
    completed.dict.return_value = {'id': 'paid-conv', 'status': 'completed'}
    completed.discarded = False
    completed.started_at = None
    completed.finished_at = None
    completed.calendar_event = None
    completed.folder_id = None
    completed.structured = Structured(title='llm-title')
    completed.apps_results = []
    completed.suggested_summarization_apps = []
    completed.private_cloud_sync_enabled = False
    monkeypatch.setattr(pc, '_get_conversation_obj', lambda *args, **kwargs: completed)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', MagicMock(return_value=True))

    result = pc.process_conversation('paid-uid', 'en', _desktop_create())

    assert result is completed
    spies['get_structured'].assert_called_once()
    resolve_jit.assert_called_once()
    spies['init_first_open'].assert_called_once()
    spies['should_defer'].assert_not_called()


_PLAN_FAIL_OPEN_FALLBACK = {
    'component': 'other',
    'from_mode': 'unresolved_plan',
    'to_mode': 'managed_processing',
    'reason': 'policy',
    'outcome': 'degraded',
}


# red-proof: skip record_fallback when plan.reason is plan_identification_fail_open
def test_plan_identification_fail_open_records_fallback_once(monkeypatch, pc) -> None:
    _enable_flag(monkeypatch, pc)
    _spy_managed_effects(monkeypatch, pc)
    fallback = MagicMock()
    monkeypatch.setattr(pc, 'record_fallback', fallback)
    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, 'process_normally', 'plan_identification_fail_open'),
    )
    _stub_completed_for_normal_path(monkeypatch, pc)

    pc.process_conversation('uid', 'en', _desktop_create())

    fallback.assert_called_once()
    kwargs = fallback.call_args.kwargs
    for key, value in _PLAN_FAIL_OPEN_FALLBACK.items():
        assert kwargs[key] == value
    assert set(kwargs) <= {'component', 'from_mode', 'to_mode', 'reason', 'outcome', 'log'}
    assert 'uid' not in kwargs
    assert 'conversation_id' not in kwargs
    assert 'plan' not in kwargs


# red-proof: emit record_fallback on every process_normally (paid allow would fire)
# red-proof: emit record_fallback on deterministic_minimum (basic deny would fire)
@pytest.mark.parametrize(
    'mode, reason',
    [
        ('process_normally', 'plan_paid'),
        ('deterministic_minimum', 'basic_not_entitled'),
    ],
)
def test_ordinary_allow_and_deny_do_not_record_plan_fail_open_fallback(monkeypatch, pc, mode: str, reason: str) -> None:
    _enable_flag(monkeypatch, pc)
    _spy_managed_effects(monkeypatch, pc)
    fallback = MagicMock()
    monkeypatch.setattr(pc, 'record_fallback', fallback)
    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, mode, reason),
    )
    if mode == 'process_normally':
        _stub_completed_for_normal_path(monkeypatch, pc)
    else:
        monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', MagicMock(return_value=True))

    pc.process_conversation('uid', 'en', _desktop_create())

    fallback.assert_not_called()


# red-proof: let force_process/is_reprocess skip the free-tier branch (basic would hit `_get_structured`)
def test_force_and_reprocess_do_not_rescue_basic_minimum(monkeypatch, pc) -> None:
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, 'deterministic_minimum', 'basic_not_entitled'),
    )
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', MagicMock(return_value=True))

    result = pc.process_conversation(
        'basic-uid',
        'en',
        _desktop_create(),
        force_process=True,
        is_reprocess=True,
    )

    assert result.deferred is False
    spies['get_structured'].assert_not_called()
    spies['extract_memories'].assert_not_called()
    spies['extract_memories_inner'].assert_not_called()
    spies['init_first_open'].assert_not_called()
    spies['should_defer'].assert_not_called()


# red-proof: call resolve_free_tier_processing_plan when the flag helper returns False
def test_flag_off_consults_legacy_deferral_and_skips_policy(monkeypatch, pc) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: False)
    spies = _spy_managed_effects(monkeypatch, pc)
    resolve = MagicMock(side_effect=AssertionError('policy must not run when flag is off'))
    monkeypatch.setattr(pc, 'resolve_free_tier_processing_plan', resolve)
    deferred = MagicMock()
    deferred.id = 'legacy-deferred'
    deferred.deferred = True
    store = MagicMock(return_value=deferred)
    monkeypatch.setattr(pc, '_store_deferred_conversation', store)
    owned: list[bool] = []

    result = pc.process_conversation(
        'basic-uid',
        'en',
        _desktop_create(),
        persistence_observer=owned.append,
    )

    assert result is deferred
    assert owned == [False]
    spies['should_defer'].assert_called_once_with('basic-uid')
    store.assert_called_once()
    resolve.assert_not_called()
    spies['get_structured'].assert_not_called()


# red-proof: compute funding_owner before resolve_free_tier_processing_plan
# (a raising request_carries_validated_byok_key would never reach decision_for)
@pytest.mark.parametrize('carries_validated_key, expected_owner', [(True, 'byok'), (False, 'omi')])
def test_funding_owner_is_computed_inside_decision_for_not_before_policy(
    monkeypatch, pc, carries_validated_key: bool, expected_owner: str
) -> None:
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    captured: list[tuple[str, str, str]] = []
    resolve_kwargs: dict[str, Any] = {}

    def fake_authorize(uid: str, feature: str, funding_owner: str, **_kwargs: Any):
        captured.append((uid, feature, funding_owner))
        return SimpleNamespace(
            allowed=True,
            reason='byok' if funding_owner == 'byok' else 'plan_paid',
            feature=feature,
            funding_owner=funding_owner,
            plan=None,
            plan_resolved=False,
        )

    def fake_resolve(**kwargs: Any):
        resolve_kwargs.update(kwargs)
        kwargs['decision_for']('conv_structure')
        return _plan(pc, 'process_normally', 'plan_paid')

    # The decision_for closure lives in utils.managed_compute (hoisted when the
    # connector memory producers started sharing it), so its seams patch there.
    monkeypatch.setattr(managed_compute, 'authorize_managed_compute', fake_authorize)
    monkeypatch.setattr(
        managed_compute,
        'request_carries_validated_byok_key',
        lambda feature: carries_validated_key,
    )
    monkeypatch.setattr(pc, 'resolve_free_tier_processing_plan', fake_resolve)
    jit_plan = SimpleNamespace(defer_derived_work=False)
    monkeypatch.setattr(pc, 'resolve_authorized_first_open_plan', lambda **kwargs: jit_plan)
    completed = MagicMock()
    completed.id = 'byok-conv'
    completed.source = ConversationSource.desktop
    completed.dict.return_value = {'id': 'byok-conv', 'status': 'completed'}
    completed.discarded = False
    completed.started_at = None
    completed.finished_at = None
    completed.calendar_event = None
    completed.folder_id = None
    completed.structured = Structured(title='llm-title')
    completed.apps_results = []
    completed.suggested_summarization_apps = []
    completed.private_cloud_sync_enabled = False
    monkeypatch.setattr(pc, '_get_conversation_obj', lambda *args, **kwargs: completed)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', MagicMock(return_value=True))

    pc.process_conversation('uid', 'en', _desktop_create())

    assert 'funding_owner' not in resolve_kwargs
    assert captured == [('uid', 'conv_structure', expected_owner)]
    spies['get_structured'].assert_called_once()


# red-proof: drop jit_first_open from the persist payload (merge=True keeps the obligation)
def test_minimum_store_clears_pending_jit_obligation_so_first_open_dispatches_nothing(monkeypatch, pc) -> None:
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, 'deterministic_minimum', 'basic_not_entitled'),
    )

    uid = 'basic-uid'
    conv_id = 'paid-then-basic'
    path = ('users', uid, 'conversations', conv_id)
    pending = {
        'version': 1,
        'state': 'pending',
        'attempt': 0,
        'account_generation': 3,
        'source_generation': 7,
        'effects': {
            'folder_assignment': {'state': 'pending'},
            'app_fanout': {'state': 'pending'},
        },
    }
    store = StrictFirestore(
        {
            ('users', uid): {'uid': uid},
            ('users', uid, 'memory_state', 'apply_control'): {
                'uid': uid,
                'head_commit_id': 'head0',
                'account_generation': 3,
                'source_generation': 7,
            },
            path: {'id': conv_id, 'status': 'completed', 'jit_first_open': pending},
        }
    )

    def persist(_uid: str, data: dict[str, Any]) -> bool:
        # Production persist_processing_result_with_lifecycle writes merge=True.
        store.rows[path].update(data)
        return True

    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', persist)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', MagicMock())

    result = pc.process_conversation(
        uid,
        'en',
        _existing_desktop(conv_id),
        force_process=True,
        is_reprocess=True,
    )

    assert result.status == ConversationStatus.completed
    assert result.deferred is False
    assert store.rows[path].get('jit_first_open') is None
    spies['get_structured'].assert_not_called()
    spies['init_first_open'].assert_not_called()

    token = claim_first_open_work(uid, conv_id, firestore_client=store)
    assert token is None
    # get_conversation_by_id dispatches only when conversation.get('jit_first_open') is truthy.
    assert not store.rows[path].get('jit_first_open')


# red-proof: report_persistence(False) after a successful minimum store (finalizer fences)
def test_minimum_store_reports_persisted_with_terminal_no_derived_effects(monkeypatch, pc) -> None:
    _enable_flag(monkeypatch, pc)
    _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, 'deterministic_minimum', 'basic_not_entitled'),
    )
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', MagicMock(return_value=True))
    owned: list[bool] = []
    dispositions: list[Any] = []

    result = pc.process_conversation(
        'basic-uid',
        'en',
        _desktop_create(),
        persistence_observer=owned.append,
        derived_effects_disposition_observer=dispositions.append,
    )

    assert result.deferred is False
    assert owned == [True]
    assert dispositions == [pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS]


@pytest.mark.anyio
@pytest.mark.parametrize('anyio_backend', ['asyncio'])
async def test_finalizer_completes_minimum_store_without_extracting_memories(monkeypatch, pc, anyio_backend) -> None:
    """Drive the real finalizer with the coordinator mocked at its observer seam."""
    del anyio_backend
    persisted_finalizer = load_module_fresh(
        'utils.conversations.finalizer',
        os.path.join(str(_BACKEND), 'utils', 'conversations', 'finalizer.py'),
    )

    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    conversation = SimpleNamespace(
        id='conversation-1',
        status=ConversationStatus.processing,
        language='en',
        discarded=False,
        geolocation=None,
    )
    extract = MagicMock()
    integrations = MagicMock()

    def minimum_process(_uid, _lang, conv, **kwargs):
        observer = kwargs.get('persistence_observer')
        if observer:
            observer(True)
        disposition = kwargs.get('derived_effects_disposition_observer')
        if disposition:
            disposition(pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS)
        conv.status = ConversationStatus.completed
        return conv

    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {
            'id': 'conversation-1',
            'status': ConversationStatus.processing.value,
            'discarded': False,
        },
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', minimum_process)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', extract)
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', integrations)
    monkeypatch.setattr(
        persisted_finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *args: {'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization'},
    )
    complete = MagicMock(return_value=True)
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'complete_finalization_fanout', complete)
    monkeypatch.setattr(persisted_finalizer, 'record_and_persist_finalized_meeting_receipt', MagicMock())
    monkeypatch.setattr(
        persisted_finalizer,
        'resolve_frame_request_authority',
        AsyncMock(return_value=SimpleNamespace(enabled=False, account_generation=None)),
    )
    monkeypatch.setattr(persisted_finalizer, 'persist_capture_arrival_intent', MagicMock())

    disposition = await persisted_finalizer.finalize_persisted_conversation(
        'uid-1',
        'conversation-1',
        finalization_job_id='job-1',
        dispatch_generation=2,
        lease_epoch=3,
    )

    assert disposition == persisted_finalizer.ConversationFinalizationDisposition.completed
    extract.assert_not_called()
    integrations.assert_not_called()
    complete.assert_called_once_with('job-1', 2, 3)


# red-proof: restore the skip_derived_effects early return that complete_fanout
# and returns before record_and_persist_finalized_meeting_receipt
@pytest.mark.anyio
@pytest.mark.parametrize('anyio_backend', ['asyncio'])
async def test_finalizer_minimum_desktop_meeting_still_persists_receipt_and_chat_intent(
    monkeypatch, pc, anyio_backend
) -> None:
    """A free-tier terminal minimum on a desktop meeting still wakes Chat."""
    del anyio_backend
    persisted_finalizer = load_module_fresh(
        'utils.conversations.finalizer',
        os.path.join(str(_BACKEND), 'utils', 'conversations', 'finalizer.py'),
    )

    async def inline_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    started = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    conversation = SimpleNamespace(
        id='meeting-1',
        status=ConversationStatus.processing,
        language='en',
        discarded=False,
        geolocation=None,
        deferred=False,
        source=SimpleNamespace(value='desktop'),
        external_data={'conversation_role': 'meeting'},
        started_at=started,
        finished_at=started + timedelta(minutes=10),
        transcript_segments=[SimpleNamespace(text='Hello from the desktop capture', start=0.0, end=60.0)],
        structured=SimpleNamespace(title='Recording', overview='', action_items=[]),
    )
    extract = MagicMock()
    integrations = MagicMock()
    intent_spy = MagicMock(return_value=SimpleNamespace(intent_id='intent-1'))

    def minimum_process(_uid, _lang, conv, **kwargs):
        observer = kwargs.get('persistence_observer')
        if observer:
            observer(True)
        disposition = kwargs.get('derived_effects_disposition_observer')
        if disposition:
            disposition(pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS)
        conv.status = ConversationStatus.completed
        conv.deferred = False
        return conv

    monkeypatch.setattr(persisted_finalizer, 'run_blocking', inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: {
            'id': 'meeting-1',
            'status': ConversationStatus.processing.value,
            'discarded': False,
        },
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', lambda value: conversation)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', minimum_process)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', extract)
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', integrations)
    monkeypatch.setattr(
        persisted_finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *args: {'status': 'claimed', 'fanout_key': 'conversation:meeting-1:finalization'},
    )
    complete = MagicMock(return_value=True)
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'complete_finalization_fanout', complete)
    monkeypatch.setattr(
        persisted_finalizer,
        'resolve_frame_request_authority',
        AsyncMock(return_value=SimpleNamespace(enabled=False, account_generation=None)),
    )
    monkeypatch.setattr(persisted_finalizer, 'persist_capture_arrival_intent', MagicMock())
    monkeypatch.setattr(meeting_receipt_mod, 'persist_capture_arrival_intent', intent_spy)
    monkeypatch.setattr(
        meeting_receipt_mod.jobs_db,
        'record_meeting_receipt',
        lambda *args, **kwargs: {
            'status': 'recorded',
            'job_id': 'job-1',
            'meeting_treatment_eligible': True,
        },
    )
    monkeypatch.setattr(
        meeting_receipt_mod.jobs_db,
        'mark_meeting_receipt_intent_persisted',
        MagicMock(return_value=True),
    )
    monkeypatch.setattr(
        persisted_finalizer,
        'record_and_persist_finalized_meeting_receipt',
        meeting_receipt_mod.record_and_persist_finalized_meeting_receipt,
    )

    disposition = await persisted_finalizer.finalize_persisted_conversation(
        'uid-1',
        'meeting-1',
        finalization_job_id='job-1',
        dispatch_generation=2,
        lease_epoch=3,
    )

    assert disposition == persisted_finalizer.ConversationFinalizationDisposition.completed
    extract.assert_not_called()
    integrations.assert_not_called()
    complete.assert_called_once_with('job-1', 2, 3)
    intent_spy.assert_called_once()
    assert intent_spy.call_args.args == ('uid-1',)
    assert intent_spy.call_args.kwargs['conversation_id'] == 'meeting-1'
    assert intent_spy.call_args.kwargs['is_desktop_meeting'] is True


# red-proof: call _funding_owner_for_feature / request_carries_validated_byok_key
# before resolve_free_tier_processing_plan (raising BYOK lookup crashes processing)
def test_raising_byok_lookup_is_deterministic_minimum_not_a_crash(monkeypatch, pc) -> None:
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        managed_compute,
        'request_carries_validated_byok_key',
        MagicMock(side_effect=RuntimeError('byok lookup boom')),
    )
    authorize = MagicMock(side_effect=AssertionError('must not authorize'))
    monkeypatch.setattr(managed_compute, 'authorize_managed_compute', authorize)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', MagicMock(return_value=True))

    result = pc.process_conversation('uid', 'en', _desktop_create())

    assert result.deferred is False
    assert result.status == ConversationStatus.completed
    spies['get_structured'].assert_not_called()
    spies['extract_memories'].assert_not_called()
    spies['init_first_open'].assert_not_called()
    authorize.assert_not_called()


def _load_finalizer():
    return load_module_fresh(
        'utils.conversations.finalizer',
        os.path.join(str(_BACKEND), 'utils', 'conversations', 'finalizer.py'),
    )


async def _inline_run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


# red-proof: drop `elif conversation_data.get(TERMINAL_NO_DERIVED_EFFECTS_FIELD)`
# in finalizer.py (attempt 2 would extract memories from a completed minimum)
@pytest.mark.anyio
@pytest.mark.parametrize('anyio_backend', ['asyncio'])
async def test_finalizer_retry_after_minimum_persist_emits_no_derived_effects(monkeypatch, pc, anyio_backend) -> None:
    """Attempt 1 persists the minimum then fails; attempt 2 must not extract."""
    del anyio_backend
    persisted_finalizer = _load_finalizer()
    field = pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD
    doc: dict[str, Any] = {
        'id': 'conversation-1',
        'status': ConversationStatus.processing.value,
        'discarded': False,
    }
    process_calls: list[Any] = []
    extract = MagicMock()
    integrations = AsyncMock()
    complete = MagicMock(return_value=True)
    receipt_calls = {'n': 0}

    def deserialize(data: dict[str, Any]) -> SimpleNamespace:
        status = data['status']
        return SimpleNamespace(
            id=data['id'],
            status=ConversationStatus(status) if isinstance(status, str) else status,
            language='en',
            discarded=False,
            geolocation=None,
            source=SimpleNamespace(value='desktop'),
            structured=SimpleNamespace(title='Recording', overview=''),
        )

    def minimum_process(_uid, _lang, conv, **kwargs):
        process_calls.append(conv)
        observer = kwargs.get('persistence_observer')
        if observer:
            observer(True)
        disposition = kwargs.get('derived_effects_disposition_observer')
        if disposition:
            disposition(pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS)
        conv.status = ConversationStatus.completed
        doc['status'] = ConversationStatus.completed.value
        doc[field] = True
        doc['jit_first_open'] = None
        return conv

    def receipt(*_args, **_kwargs):
        receipt_calls['n'] += 1
        if receipt_calls['n'] == 1:
            raise RuntimeError('receipt boom')

    monkeypatch.setattr(persisted_finalizer, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(
        persisted_finalizer.conversations_db,
        'get_conversation',
        lambda *args, **kwargs: dict(doc),
    )
    monkeypatch.setattr(persisted_finalizer, 'deserialize_conversation', deserialize)
    monkeypatch.setattr(persisted_finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(persisted_finalizer, 'process_conversation', minimum_process)
    monkeypatch.setattr(persisted_finalizer, 'extract_memories', extract)
    monkeypatch.setattr(persisted_finalizer, 'trigger_external_integrations', integrations)
    monkeypatch.setattr(
        persisted_finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *args: {'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization'},
    )
    monkeypatch.setattr(persisted_finalizer.lifecycle_service, 'complete_finalization_fanout', complete)
    monkeypatch.setattr(persisted_finalizer, 'record_and_persist_finalized_meeting_receipt', receipt)
    monkeypatch.setattr(
        persisted_finalizer,
        'resolve_frame_request_authority',
        AsyncMock(return_value=SimpleNamespace(enabled=False, account_generation=None)),
    )
    monkeypatch.setattr(persisted_finalizer, 'persist_capture_arrival_intent', MagicMock())

    finalize_kwargs = {
        'finalization_job_id': 'job-1',
        'dispatch_generation': 2,
        'lease_epoch': 3,
    }
    with pytest.raises(persisted_finalizer.ConversationFinalizationError):
        await persisted_finalizer.finalize_persisted_conversation('uid-1', 'conversation-1', **finalize_kwargs)

    assert doc['status'] == ConversationStatus.completed.value
    assert doc[field] is True
    assert len(process_calls) == 1
    extract.assert_not_called()
    integrations.assert_not_called()
    complete.assert_not_called()

    disposition = await persisted_finalizer.finalize_persisted_conversation(
        'uid-1', 'conversation-1', **finalize_kwargs
    )

    assert disposition == persisted_finalizer.ConversationFinalizationDisposition.completed
    assert len(process_calls) == 1
    extract.assert_not_called()
    integrations.assert_not_called()
    complete.assert_called_once_with('job-1', 2, 3)


# red-proof: keep `_normal_persist_payload` from writing the marker as None
# (merge=True would leave True and suppress derived effects after upgrade)
def test_paid_reprocess_clears_stale_terminal_marker_and_runs_derived_effects(monkeypatch, pc) -> None:
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, 'process_normally', 'plan_paid'),
    )
    jit_plan = SimpleNamespace(defer_derived_work=False)
    monkeypatch.setattr(pc, 'resolve_authorized_first_open_plan', lambda **kwargs: jit_plan)

    uid = 'upgraded-uid'
    conv_id = 'paid-then-basic'
    field = pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD
    path = ('users', uid, 'conversations', conv_id)
    store = StrictFirestore(
        {
            ('users', uid): {'uid': uid},
            path: {
                'id': conv_id,
                'status': 'completed',
                field: True,
                'jit_first_open': None,
            },
        }
    )

    def persist(_uid: str, data: dict[str, Any]) -> bool:
        store.rows[path].update(data)
        return True

    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', persist)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', MagicMock())
    dispositions: list[Any] = []

    result = pc.process_conversation(
        uid,
        'en',
        _existing_desktop(conv_id),
        force_process=True,
        is_reprocess=True,
        derived_effects_disposition_observer=dispositions.append,
    )

    assert result.status == ConversationStatus.completed
    assert field in store.rows[path]
    assert store.rows[path][field] is None
    spies['get_structured'].assert_called_once()
    spies['extract_memories_inner'].assert_called()
    spies['trigger_apps'].assert_called()
    spies['init_first_open'].assert_not_called()
    assert dispositions == [pc.DerivedEffectsDisposition.RUN]


# red-proof: drop `payload[TERMINAL_NO_DERIVED_EFFECTS_FIELD] = True` from
# `_terminal_persist_payload` (terminal persist would omit the marker)
# red-proof: omit the field from `_normal_persist_payload` instead of writing
# None (the normal persist dict would not carry the merge-clear)
def test_terminal_persist_writes_marker_and_normal_persist_clears_it(monkeypatch, pc) -> None:
    _enable_flag(monkeypatch, pc)
    field = pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD
    terminal_payloads: list[dict[str, Any]] = []
    normal_payloads: list[dict[str, Any]] = []

    def capture_terminal(_uid: str, data: dict[str, Any], *_args: Any, **_kwargs: Any) -> bool:
        terminal_payloads.append(data)
        return True

    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, 'deterministic_minimum', 'basic_not_entitled'),
    )
    _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', capture_terminal)
    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', MagicMock())

    pc.process_conversation('basic-uid', 'en', _desktop_create())

    assert terminal_payloads, 'terminal path must persist a payload'
    assert field in terminal_payloads[-1]
    assert terminal_payloads[-1][field] is True

    def capture_normal(_uid: str, data: dict[str, Any], *_args: Any, **_kwargs: Any) -> bool:
        normal_payloads.append(data)
        return True

    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, 'process_normally', 'plan_paid'),
    )
    jit_plan = SimpleNamespace(defer_derived_work=True)
    monkeypatch.setattr(pc, 'resolve_authorized_first_open_plan', lambda **kwargs: jit_plan)
    completed = MagicMock()
    completed.id = 'paid-conv'
    completed.source = ConversationSource.desktop
    completed.dict.return_value = {'id': 'paid-conv', 'status': 'completed'}
    completed.discarded = False
    completed.started_at = None
    completed.finished_at = None
    completed.calendar_event = None
    completed.folder_id = None
    completed.structured = Structured(title='llm-title')
    completed.apps_results = []
    completed.suggested_summarization_apps = []
    completed.private_cloud_sync_enabled = False
    monkeypatch.setattr(pc, '_get_conversation_obj', lambda *args, **kwargs: completed)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', capture_normal)
    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', MagicMock())

    pc.process_conversation('paid-uid', 'en', _desktop_create())

    assert normal_payloads, 'normal path must persist a payload'
    assert (
        field in normal_payloads[-1]
    ), 'normal persist must write the marker as None so merge=True clears a stale terminal'
    assert normal_payloads[-1][field] is None
    assert terminal_payloads[-1][field] is True


# --- S5 (§1.8): managed memory formation stops for basic ----------------------


def _memory_decision(pc, *, allowed: bool, reason: str, plan: Any = None):
    return managed_compute.Decision(
        allowed=allowed,
        reason=reason,
        feature='memories',
        funding_owner='omi',
        plan=plan,
        plan_resolved=plan is not None,
    )


def _extract_memories_probe(monkeypatch, pc, *, suppression_on: bool, decision) -> MagicMock:
    """Drive the real `extract_memories` down to (or past) the §1.8 gate."""
    # A MagicMock result, not a SimpleNamespace: past the gate the real
    # telemetry reads attributes this test does not care about, and the point
    # here is only whether the extractor was reached.
    inner = MagicMock(return_value=MagicMock(count=1, path='eager'))
    monkeypatch.setattr(pc, '_extract_memories_inner', inner)
    monkeypatch.setattr(pc, 'MemoryService', MagicMock())
    monkeypatch.setattr(pc, '_sweep_owned_writer_mode', lambda _uid: None)
    monkeypatch.setattr(pc, 'free_tier_memory_suppression_enabled', lambda: suppression_on)
    # The §1.8 gate's decision_for closure lives in utils.managed_compute, so
    # its authorize seam patches there. The funding-owner resolution is not
    # controlled by any stub in this file: managed_compute binds utils.byok's
    # functions at its own import, and only the stubbed
    # authorize_managed_compute (which ignores its funding_owner argument)
    # matters for the verdict.
    monkeypatch.setattr(managed_compute, 'authorize_managed_compute', lambda *args, **kwargs: decision)
    return inner


# red-proof: delete the `if free_tier_memory_suppression_enabled():` block in extract_memories
def test_basic_uid_forms_no_managed_memory(monkeypatch, pc) -> None:
    """Named proof (a): a finalized conversation on basic makes zero
    memory-extraction provider-lane calls."""
    inner = _extract_memories_probe(
        monkeypatch,
        pc,
        suppression_on=True,
        decision=_memory_decision(pc, allowed=False, reason='basic_not_entitled', plan=PlanType.basic),
    )
    pc.extract_memories('basic-uid', _existing_desktop('basic-conv'))
    inner.assert_not_called()


def test_paid_uid_still_forms_memories_with_the_flag_on(monkeypatch, pc) -> None:
    inner = _extract_memories_probe(
        monkeypatch,
        pc,
        suppression_on=True,
        decision=_memory_decision(pc, allowed=True, reason='plan_paid', plan=PlanType.unlimited),
    )
    pc.extract_memories('paid-uid', _existing_desktop('paid-conv'))
    inner.assert_called_once()


def test_flag_off_is_byte_identical_for_basic(monkeypatch, pc) -> None:
    """Dark rollout: with the flag off, a basic uid extracts exactly as today —
    the policy is not even consulted."""
    consulted: list[str] = []
    inner = _extract_memories_probe(
        monkeypatch,
        pc,
        suppression_on=False,
        decision=_memory_decision(pc, allowed=False, reason='basic_not_entitled', plan=PlanType.basic),
    )
    monkeypatch.setattr(
        pc,
        'memory_formation_verdict',
        lambda **kwargs: consulted.append('called') or pytest.fail('policy consulted with the flag off'),
    )
    pc.extract_memories('basic-uid', _existing_desktop('flag-off-conv'))
    inner.assert_called_once()
    assert consulted == []


def test_sweep_owned_writer_still_short_circuits_before_the_plan_gate(monkeypatch, pc) -> None:
    """The plan gate is a *second* early return in the same boundary, not a
    replacement: a ledger-cutover account is still skipped for its own reason,
    and the plan lookup never runs for it."""
    inner = _extract_memories_probe(
        monkeypatch,
        pc,
        suppression_on=True,
        decision=_memory_decision(pc, allowed=True, reason='plan_paid', plan=PlanType.unlimited),
    )
    monkeypatch.setattr(pc, '_sweep_owned_writer_mode', lambda _uid: 'ledger')
    asked: list[str] = []
    monkeypatch.setattr(pc, 'memory_formation_verdict', lambda **kwargs: asked.append('asked'))
    pc.extract_memories('ledger-uid', _existing_desktop('ledger-conv'))
    inner.assert_not_called()
    assert asked == [], 'the sweep-owned early return must win before any plan lookup'


def test_replayed_finalization_of_a_suppressed_conversation_still_spends_nothing(monkeypatch, pc) -> None:
    """S6's worst defect was request-scoped terminal state: a Cloud Task retry
    re-ran memory extraction for a basic user. The gate must hold on replay."""
    inner = _extract_memories_probe(
        monkeypatch,
        pc,
        suppression_on=True,
        decision=_memory_decision(pc, allowed=False, reason='basic_not_entitled', plan=PlanType.basic),
    )
    conversation = _existing_desktop('replayed-conv')
    for _ in range(3):
        pc.extract_memories('basic-uid', conversation)
    inner.assert_not_called()


def test_a_raising_plan_lookup_suppresses_instead_of_failing_finalization(monkeypatch, pc) -> None:
    inner = _extract_memories_probe(
        monkeypatch,
        pc,
        suppression_on=True,
        decision=_memory_decision(pc, allowed=True, reason='plan_paid', plan=PlanType.unlimited),
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError('authorization exploded')

    monkeypatch.setattr(managed_compute, 'authorize_managed_compute', boom)
    pc.extract_memories('erroring-uid', _existing_desktop('erroring-conv'))
    inner.assert_not_called()


# ---------------------------------------------------------------------------
# processing_state dark persistence (flip-review F-1 + A-5).
#
# The modeled field's None default must never reach a persist payload: persist
# is transaction.set(merge=True), so a dumped None is a real Firestore key, and
# missing versus explicit-null is the exact distinction the dark rollout hangs
# on (the terminal_no_derived_effects marker follows the same discipline).
# Only the flag-on minimum writes a real state; enrichment merge-clears a
# stale one — an omission cannot, because merge keeps an omitted key.
#
# red-proof: pop nothing (payload builders keep conversation.dict()'s default)
#   → every assert of key absence / explicit-null below fails.
# red-proof: enrichment "clears" by omitting the key instead of writing None
#   → the merged document still reads 'local_pending' in the stale-state test.
# ---------------------------------------------------------------------------


def _capture_all_persists(monkeypatch, pc, *, store: Any = None, path: Any = None) -> list[dict[str, Any]]:
    """Capture every lifecycle persist payload, merging into `store` like the
    production transaction.set(merge=True) does."""
    payloads: list[dict[str, Any]] = []

    def capture(_uid: str, data: dict[str, Any], *_args: Any, **_kwargs: Any) -> bool:
        payloads.append(data)
        if store is not None and path is not None:
            store.rows[path].update(data)
        return True

    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', capture)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', capture)
    monkeypatch.setattr(pc.lifecycle_service, 'create_processing_conversation', capture)
    return payloads


def _drive_reprocess(pc, conversation: Any, uid: str = 'paid-uid') -> Any:
    """Exact kwargs the reprocess route passes (routers/conversations.py:495);
    the derived bundle is captured, never run."""
    return pc.process_conversation(
        uid,
        'en',
        conversation,
        force_process=True,
        is_reprocess=True,
        bypass_jit_first_open=True,
        persistence_observer=lambda _owned: None,
        defer_derived_effects=True,
        derived_effects_observer=lambda _runner: None,
    )


def _omi_create() -> CreateConversation:
    return CreateConversation(
        started_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 2, 12, 5, tzinfo=timezone.utc),
        transcript_segments=[
            TranscriptSegment(
                text='Hello from the phone capture', speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0
            )
        ],
        source=ConversationSource.omi,
        language='en',
    )


def _disable_flag(monkeypatch, pc) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: False)


# red-proof: _normal_persist_payload keeps the dumped None default → key present
def test_flag_off_fresh_create_persists_no_processing_state_key(monkeypatch, pc) -> None:
    _disable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    payloads = _capture_all_persists(monkeypatch, pc)

    result = pc.process_conversation(
        'free-uid',
        'en',
        _omi_create(),
        persistence_observer=lambda _owned: None,
        defer_derived_effects=True,
        derived_effects_observer=lambda _runner: None,
    )

    assert result.status == ConversationStatus.completed
    assert payloads, 'fresh create must persist'
    assert (
        'processing_state' not in payloads[-1]
    ), f"both flags off must not stamp the key; got {payloads[-1].get('processing_state')!r}"
    spies['get_structured'].assert_called_once()


# red-proof: _store_deferred_conversation keeps the dumped None default
def test_flag_off_legacy_deferred_store_persists_no_processing_state_key(monkeypatch, pc) -> None:
    _disable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)  # should_defer returns True
    payloads = _capture_all_persists(monkeypatch, pc)

    result = pc.process_conversation('basic-uid', 'en', _desktop_create())

    assert result.deferred is True
    assert result.status == ConversationStatus.processing
    assert payloads, 'deferred store must persist'
    assert 'processing_state' not in payloads[-1]
    spies['get_structured'].assert_not_called()


# red-proof: reprocess persist keeps the dumped None default → key present on a
# document that never had the field
def test_flag_off_reprocess_of_pre_s3_document_persists_no_processing_state_key(monkeypatch, pc) -> None:
    _disable_flag(monkeypatch, pc)
    _spy_managed_effects(monkeypatch, pc)
    uid = 'legacy-uid'
    conv_id = 'pre-s3-legacy'
    path = ('users', uid, 'conversations', conv_id)
    store = StrictFirestore({path: {'id': conv_id, 'status': 'completed'}})
    payloads = _capture_all_persists(monkeypatch, pc, store=store, path=path)

    _drive_reprocess(pc, _existing_desktop(conv_id), uid=uid)

    assert 'processing_state' not in payloads[-1]
    assert 'processing_state' not in store.rows[path], 'merged document must not gain the key'


# red-proof: enrichment clears a stale state by omitting the key instead of
# writing an explicit None → merge=True keeps 'local_pending' on the document
def test_paid_reprocess_merge_clears_stale_local_pending_and_resets_the_object(monkeypatch, pc) -> None:
    _disable_flag(monkeypatch, pc)
    _spy_managed_effects(monkeypatch, pc)
    uid = 'upgraded-uid'
    conv_id = 'upgraded-then-paid'
    path = ('users', uid, 'conversations', conv_id)
    store = StrictFirestore({path: {'id': conv_id, 'status': 'completed', 'processing_state': 'local_pending'}})
    payloads = _capture_all_persists(monkeypatch, pc, store=store, path=path)
    conversation = _existing_desktop(conv_id)
    conversation.processing_state = ConversationProcessingState.local_pending

    result = _drive_reprocess(pc, conversation, uid=uid)

    # An omitted key would survive the merge; the clear must be an explicit null.
    assert payloads[-1]['processing_state'] is None
    assert store.rows[path]['processing_state'] is None
    # The object the caller returns must agree — not answer a stale pending
    # state back to the client on an enriched conversation.
    assert result.processing_state is None


def test_flag_on_minimum_writes_local_pending_and_a_delivered_projection_stays_absent(monkeypatch, pc) -> None:
    """The one writer of a real state is the flag-on minimum; a delivered
    projection is 'nothing pending', so the field stays absent (omitted), not
    null."""
    _enable_flag(monkeypatch, pc)
    _spy_managed_effects(monkeypatch, pc)
    payloads = _capture_all_persists(monkeypatch, pc)
    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(
            pc, 'store_projection' if kwargs.get('has_projection') else 'deterministic_minimum', 'basic_not_entitled'
        ),
    )

    result = pc.process_conversation('basic-uid', 'en', _desktop_create())

    assert result.deferred is False
    assert payloads[-1]['processing_state'] == 'local_pending'

    payloads.clear()
    projection = ClientProcessing(
        schema_version=1,
        transcript_sha256='ab' * 32,
        structure=ProjectedStructure(title='local title', overview='local overview'),
        provenance=ProjectionProvenance(
            model_id='local-test-model',
            runtime='test-runtime',
            device_class='test-device',
            generated_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        ),
    )
    pc.process_conversation(
        'basic-uid',
        'en',
        _desktop_create(),
        client_projection=projection,
    )
    assert 'processing_state' not in payloads[-1], 'projected minimum must omit the field, not write null'
    assert payloads[-1]['client_processing'] is not None


# red-proof: the flag-on process_normally persist stamps the modeled default →
# key present on an enriched conversation
def test_flag_on_enrichment_omits_processing_state_while_merge_clearing_the_marker(monkeypatch, pc) -> None:
    _enable_flag(monkeypatch, pc)
    _spy_managed_effects(monkeypatch, pc)
    payloads = _capture_all_persists(monkeypatch, pc)
    monkeypatch.setattr(
        pc,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: _plan(pc, 'process_normally', 'plan_paid'),
    )

    _drive_reprocess(pc, _existing_desktop('paid-upgrade'), uid='paid-uid')

    last = payloads[-1]
    assert 'processing_state' not in last, 'nothing to say ⇒ the key stays absent, even flag-on'
    assert last[pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD] is None, 'the upgrade marker clear still lands'

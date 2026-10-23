"""Enrichment, replay and retired-flag parity contracts.

The coordinator is loaded with scoped offline fakes; no provider or database
network is permitted. Capped projection/backlog coverage lives in the entrypoint
matrix and processing-backlog suites.
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

from utils.conversations import meeting_receipt as meeting_receipt_mod

_BACKEND = Path(__file__).resolve().parents[2]


def _build_fakes() -> dict[str, ModuleType]:
    fakes: dict[str, ModuleType] = {}

    def add(name: str, mod: ModuleType) -> ModuleType:
        fakes[name] = mod
        return mod

    refresh = ModuleType('utils.conversations.action_item_refresh')
    refresh.preserve = lambda *a, **k: False
    add('utils.conversations.action_item_refresh', refresh)

    database_pkg = ModuleType('database')
    database_pkg.__path__ = [str(_BACKEND / 'database')]  # type: ignore[attr-defined]
    add('database', database_pkg)

    client_mod = ModuleType('database._client')
    client_mod.db = MagicMock(name='db')
    client_mod.get_firestore_client = lambda: client_mod.db
    client_mod.get_data_plane_firestore_client = lambda: client_mod.db
    client_mod.document_id_from_seed = lambda seed: 'seed-id'
    client_mod.run_transactional = MagicMock()
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
        'get_app_result',
        'should_discard_conversation',
        'get_conversation_notes',
        'validate_structured_source_segment_ids',
    ):
        setattr(conv_proc, attr, MagicMock())
    add('utils.llm.conversation_processing', conv_proc)

    add('utils.llm.conversation_prompt_prefix', AutoMockModule('utils.llm.conversation_prompt_prefix'))
    gateway_error_contract = add('utils.llm.gateway_error_contract', AutoMockModule('utils.llm.gateway_error_contract'))
    gateway_error_contract.conversation_processing_http_exception = lambda error: error
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
    subscription.should_skip_omi_paid_postprocessing = MagicMock(return_value=False)

    byok = ModuleType('utils.byok')
    byok.get_byok_key = lambda _provider: None
    byok.has_validated_byok_keys = lambda: False
    add('utils.byok', byok)
    speaker_id = add('utils.speaker_identification', AutoMockModule('utils.speaker_identification'))
    speaker_id.extract_speaker_samples = AsyncMock()
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
    # The finalizer's smart-merge step is off by default; its own tests drive it.
    smart_merge = add('utils.conversations.smart_merge', AutoMockModule('utils.conversations.smart_merge'))
    smart_merge.smart_merge_step = AsyncMock(return_value=False)
    add('utils.log_sanitizer', AutoMockModule('utils.log_sanitizer'))
    add('utils.retrieval.frame_request_authority', AutoMockModule('utils.retrieval.frame_request_authority'))
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


def _spy_managed_effects(monkeypatch, pc) -> dict[str, MagicMock]:
    spies = {
        'get_structured': MagicMock(return_value=(Structured(title='llm-title'), False)),
        'extract_memories': MagicMock(),
        'extract_memories_inner': MagicMock(),
        'trigger_apps': MagicMock(),
        'assign_folder': MagicMock(return_value=(None, 0.0, '')),
        'should_defer': MagicMock(return_value=True),
    }
    monkeypatch.setattr(pc, '_get_structured', spies['get_structured'])
    monkeypatch.setattr(pc, 'extract_memories', spies['extract_memories'])
    monkeypatch.setattr(pc, '_extract_memories', spies['extract_memories_inner'])
    monkeypatch.setattr(pc, 'trigger_conversation_apps', spies['trigger_apps'])
    monkeypatch.setattr(pc, 'assign_conversation_to_folder', spies['assign_folder'])
    monkeypatch.setattr(pc, 'should_defer_desktop_processing', spies['should_defer'])
    monkeypatch.setattr(pc, '_enrich_meeting_context', lambda *args, **kwargs: None)
    monkeypatch.setattr(pc, 'resolve_speakers_for_processing', lambda *args, **kwargs: False)
    monkeypatch.setattr(pc, 'is_trial_paywalled', lambda *args, **kwargs: False)
    return spies


def _stub_completed_for_normal_path(monkeypatch, pc, conv_id: str = 'paid-conv') -> MagicMock:
    completed = MagicMock()
    completed.id = conv_id
    completed.source = ConversationSource.desktop
    completed.dict.return_value = {'id': conv_id, 'status': 'completed'}
    completed.discarded = False
    completed.processing_deferred = False
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
    return completed


def _desktop_custom_stt(conversation_id: str = 'desktop-custom-stt') -> Conversation:
    conversation = _existing_desktop(conversation_id)
    conversation.uses_custom_stt = True
    return conversation


def _local_projection() -> ClientProcessing:
    return ClientProcessing(
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


_PLAN_FAIL_OPEN_FALLBACK = {
    'component': 'other',
    'from_mode': 'unresolved_plan',
    'to_mode': 'managed_processing',
    'reason': 'policy',
    'outcome': 'degraded',
}


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
    monkeypatch.setattr(persisted_finalizer, 'record_finalized_meeting_receipt', MagicMock())
    monkeypatch.setattr(
        persisted_finalizer,
        'resolve_frame_request_authority',
        AsyncMock(return_value=SimpleNamespace(enabled=False, account_generation=None)),
    )

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
    vector = MagicMock(return_value=True)
    monkeypatch.setattr(persisted_finalizer, 'save_structured_vector', vector)
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
        MagicMock(side_effect=AssertionError('automatic Chat intents are retired')),
    )
    monkeypatch.setattr(
        persisted_finalizer,
        'record_finalized_meeting_receipt',
        meeting_receipt_mod.record_finalized_meeting_receipt,
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
    assert vector.call_count == 1
    complete.assert_called_once_with('job-1', 2, 3)


async def _inline_run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.mark.anyio
@pytest.mark.parametrize('anyio_backend', ['asyncio'])
async def test_finalizer_retry_after_minimum_persist_suppresses_intelligence(monkeypatch, pc, anyio_backend) -> None:
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
    vector = MagicMock(return_value=True)
    monkeypatch.setattr(persisted_finalizer, 'save_structured_vector', vector)
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
    monkeypatch.setattr(persisted_finalizer, 'record_finalized_meeting_receipt', receipt)
    monkeypatch.setattr(
        persisted_finalizer,
        'resolve_frame_request_authority',
        AsyncMock(return_value=SimpleNamespace(enabled=False, account_generation=None)),
    )

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
    assert vector.call_count == 2
    complete.assert_called_once_with('job-1', 2, 3)


def _memory_decision(pc, *, allowed: bool, reason: str, plan: Any = None):
    return managed_compute.Decision(
        allowed=allowed,
        reason=reason,
        feature='memories',
        funding_owner='omi',
        plan=plan,
        plan_resolved=plan is not None,
    )


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
        trigger=pc.ProcessingTrigger.USER_REPROCESS,
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


def test_flag_off_fresh_create_persists_no_processing_state_key(monkeypatch, pc) -> None:
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


def test_flag_off_legacy_deferred_store_persists_no_processing_state_key(monkeypatch, pc) -> None:
    spies = _spy_managed_effects(monkeypatch, pc)  # should_defer returns True
    payloads = _capture_all_persists(monkeypatch, pc)

    result = pc.process_conversation('basic-uid', 'en', _desktop_create())

    assert result.deferred is True
    assert result.status == ConversationStatus.processing
    assert payloads, 'deferred store must persist'
    assert 'processing_state' not in payloads[-1]
    spies['get_structured'].assert_not_called()


def test_flag_off_reprocess_of_pre_s3_document_persists_no_processing_state_key(monkeypatch, pc) -> None:
    _spy_managed_effects(monkeypatch, pc)
    # The eager gate consults the managed-compute policy seam on this flag-off
    # desktop reprocess; answer paid/allow hermetically instead of waiting out
    # a real Firestore fail-open.
    monkeypatch.setattr(
        managed_compute,
        'authorize_managed_compute',
        lambda *_a, **_k: _memory_decision(pc, allowed=True, reason='plan_paid', plan=PlanType.unlimited),
    )
    uid = 'legacy-uid'
    conv_id = 'pre-s3-legacy'
    path = ('users', uid, 'conversations', conv_id)
    store = StrictFirestore({path: {'id': conv_id, 'status': 'completed'}})
    payloads = _capture_all_persists(monkeypatch, pc, store=store, path=path)

    _drive_reprocess(pc, _existing_desktop(conv_id), uid=uid)

    assert 'processing_state' not in payloads[-1]
    assert 'processing_state' not in store.rows[path], 'merged document must not gain the key'


def test_paid_reprocess_merge_clears_stale_local_pending_and_resets_the_object(monkeypatch, pc) -> None:
    _spy_managed_effects(monkeypatch, pc)
    # Paid reprocess through the same eager-gate seam — allow, hermetically.
    monkeypatch.setattr(
        managed_compute,
        'authorize_managed_compute',
        lambda *_a, **_k: _memory_decision(pc, allowed=True, reason='plan_paid', plan=PlanType.unlimited),
    )
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


def test_paid_reprocess_clears_a_dead_letter_summary_retryable_marker(monkeypatch, pc) -> None:
    _spy_managed_effects(monkeypatch, pc)
    monkeypatch.setattr(
        managed_compute,
        'authorize_managed_compute',
        lambda *_a, **_k: _memory_decision(pc, allowed=True, reason='plan_paid', plan=PlanType.unlimited),
    )
    uid = 'retry-uid'
    conv_id = 'dead-lettered-then-retried'
    path = ('users', uid, 'conversations', conv_id)
    store = StrictFirestore({path: {'id': conv_id, 'status': 'completed', 'summary_retryable': True}})
    payloads = _capture_all_persists(monkeypatch, pc, store=store, path=path)
    conversation = _existing_desktop(conv_id)
    conversation.summary_retryable = True

    result = _drive_reprocess(pc, conversation, uid=uid)

    assert payloads[-1]['summary_retryable'] is None
    assert store.rows[path]['summary_retryable'] is None
    assert result.summary_retryable is None


@pytest.mark.parametrize('persisted, expected_event', [(True, 'stored'), (False, 'fenced')])
def test_legacy_deferral_records_lazy_store_lifecycle(monkeypatch, pc, persisted: bool, expected_event: str) -> None:
    spies = _spy_managed_effects(monkeypatch, pc)
    recorded: list[str] = []
    monkeypatch.setattr(pc, 'record_lazy_desktop_deferral', lambda *, event: recorded.append(event))
    monkeypatch.setattr(pc.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=persisted))
    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', MagicMock(return_value=persisted))

    result = pc.process_conversation('basic-uid', 'en', _desktop_create())

    assert result.deferred is True
    assert result.status == ConversationStatus.processing
    assert recorded == [expected_event]
    spies['get_structured'].assert_not_called()
    spies['extract_memories'].assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize('anyio_backend', ['asyncio'])
@pytest.mark.parametrize(
    'mode',
    [
        'funded_processing',
        'completed_replay',
        'terminal_replay',
        'budget_waiting_replay',
        'discarded_replay',
        'deleted_replay',
        'unstructured_replay',
    ],
)
@pytest.mark.parametrize('claim_status', ['claimed', 'fenced', 'completed'])
async def test_finalizer_summary_vector_requires_winning_claim(monkeypatch, pc, anyio_backend, mode, claim_status):
    """#21111: replay and suppressed intelligence still index behind the claim.

    The processing case exercises the current coordinator and deferred bundle.
    Replay guards must prevent canonical work for budget-waiting captures.
    """
    del anyio_backend
    finalizer = load_module_fresh('utils.conversations.finalizer', _BACKEND / 'utils/conversations/finalizer.py')
    conversation = _existing_desktop('vector-conv')
    conversation.source = ConversationSource.omi
    if mode == 'funded_processing':
        conversation.status = ConversationStatus.processing
    row = {'id': conversation.id, 'status': conversation.status.value, 'source': 'omi'}
    if mode == 'terminal_replay':
        row[pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD] = True
    if mode == 'discarded_replay':
        conversation.discarded = True
    if mode == 'deleted_replay':
        row['deleted'] = True
    if mode == 'unstructured_replay':
        conversation.structured = None
    if mode == 'budget_waiting_replay':
        conversation.processing_deferred = True
        row['processing_deferred'] = True
        row[pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD] = True
    vector_eligible = mode not in {'discarded_replay', 'deleted_replay', 'unstructured_replay', 'budget_waiting_replay'}
    events = []

    async def inline(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    def claim(*args):
        events.append('claim')
        return {'status': claim_status, 'fanout_key': 'key'}

    def vector(uid, conv):
        assert events == ['claim']
        assert uid == 'uid' and conv is conversation
        events.append('vector')
        return True

    monkeypatch.setattr(finalizer, 'run_blocking', inline)
    monkeypatch.setattr(finalizer.conversations_db, 'get_conversation', lambda *a, **k: row)
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda data: conversation)
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(finalizer, 'await_meeting_evidence', AsyncMock(return_value='not_applicable'))
    monkeypatch.setattr(finalizer, 'link_duplicate_captures', MagicMock())
    monkeypatch.setattr(finalizer.lifecycle_service, 'claim_finalization_fanout', claim)
    monkeypatch.setattr(
        finalizer.lifecycle_service, 'complete_finalization_fanout', lambda *a: events.append('complete') or True
    )
    monkeypatch.setattr(finalizer, 'save_structured_vector', vector)
    monkeypatch.setattr(finalizer, 'extract_memories', MagicMock())
    monkeypatch.setattr(finalizer, 'trigger_external_integrations', AsyncMock())
    monkeypatch.setattr(finalizer, 'record_finalized_meeting_receipt', MagicMock())
    monkeypatch.setattr(finalizer, 'schedule_person_voice_learning_retry', MagicMock())
    monkeypatch.setattr(
        finalizer, 'resolve_frame_request_authority', AsyncMock(return_value=SimpleNamespace(enabled=False))
    )
    monkeypatch.setattr(pc, '_get_structured', lambda *a, **k: (conversation.structured, False))
    monkeypatch.setattr(pc, '_get_conversation_obj', lambda *a, **k: conversation)
    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', MagicMock(return_value=True))
    apps = MagicMock()
    folders = MagicMock(return_value=[])
    submit = MagicMock()
    monkeypatch.setattr(pc, 'trigger_conversation_apps', apps)
    monkeypatch.setattr(pc.folders_db, 'get_folders', folders)
    monkeypatch.setattr(pc, 'submit_with_context', submit)
    monkeypatch.setattr(pc, '_extract_memories', MagicMock())
    monkeypatch.setattr(pc, '_save_action_items', MagicMock())
    monkeypatch.setattr(pc, 'assign_conversation_to_folder', MagicMock(return_value=(None, 0.0, '')))
    monkeypatch.setattr(pc, 'resolve_speakers_for_processing', lambda *a, **k: False)

    result = await finalizer.finalize_persisted_conversation(
        'uid',
        conversation.id,
        finalization_job_id='job',
        dispatch_generation=1,
        lease_epoch=1,
    )
    assert result.value == ('fenced' if claim_status == 'fenced' else 'completed')
    # New contract (#21111 follow-up): summary indexing runs on BOTH the
    # claimed path and the completed-fanout re-finalization path, behind the
    # same guards. Only the claimed path re-runs fanout completion.
    expected = ['claim']
    if claim_status != 'fenced' and vector_eligible:
        expected.append('vector')
    if claim_status == 'claimed':
        expected.append('complete')
    assert events == expected
    if mode == 'funded_processing' and claim_status == 'claimed':
        apps.assert_called_once()
        folders.assert_called_once_with('uid')
    else:
        apps.assert_not_called()
        folders.assert_not_called()
    assert all(call.args[1] is not pc.save_structured_vector for call in submit.call_args_list)
    if mode in {'terminal_replay', 'budget_waiting_replay'}:
        finalizer.extract_memories.assert_not_called()
        finalizer.trigger_external_integrations.assert_not_called()


def _load_finalizer():
    return load_module_fresh(
        "utils.conversations.finalizer",
        os.path.join(str(_BACKEND), "utils", "conversations", "finalizer.py"),
    )


@pytest.mark.parametrize('legacy_value', [None, 'true', 'false'])
def test_retired_basic_flags_do_not_deny_first_open(monkeypatch, pc, legacy_value):
    from utils.conversations.processing_trigger import ProcessingTrigger

    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda uid, lane=None: False)
    for key in (
        'FREE_TIER_LOCAL_PROCESSING',
        'FREE_TIER_LOCAL_PROCESSING_COHORT',
        'BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED',
    ):
        if legacy_value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, legacy_value)
    spies = _spy_managed_effects(monkeypatch, pc)
    _stub_completed_for_normal_path(monkeypatch, pc)
    result = pc.process_conversation('synthetic', 'en', _existing_desktop(), trigger=ProcessingTrigger.FIRST_OPEN)
    spies['get_structured'].assert_called_once()
    assert not result.processing_deferred


def test_successful_explicit_enrichment_clears_retired_terminal_marker_without_overwriting_projection(monkeypatch, pc):
    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda uid, lane=None: False)
    _spy_managed_effects(monkeypatch, pc)
    uid, conv_id = 'upgraded', 'old-terminal'
    path = ('users', uid, 'conversations', conv_id)
    projection = _local_projection().model_dump(mode='json')
    store = StrictFirestore(
        {
            path: {
                'id': conv_id,
                'status': 'completed',
                pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD: True,
                'client_processing': projection,
            }
        }
    )
    _capture_all_persists(monkeypatch, pc, store=store, path=path)
    _drive_reprocess(pc, _existing_desktop(conv_id), uid=uid)
    assert store.rows[path][pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD] is None
    assert store.rows[path]['client_processing'] == projection


@pytest.mark.parametrize('defer', [False, True])
def test_silent_backfill_persists_summary_and_never_schedules_derived_work(monkeypatch, pc, defer):
    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda *_: False)
    spies = _spy_managed_effects(monkeypatch, pc)
    spies['get_structured'].return_value = (Structured(title='Recovered', overview='Synthetic complete summary'), False)
    _stub_completed_for_normal_path(monkeypatch, pc)
    payloads = _capture_all_persists(monkeypatch, pc)
    bundle, disposition = [], []
    lazy = __import__('utils.conversations.demand_processing', fromlist=['lazy_enrichment_enabled'])
    monkeypatch.setattr(lazy, 'lazy_enrichment_enabled', lambda _: True)
    submitted = MagicMock(side_effect=AssertionError('historical work must stay silent'))
    monkeypatch.setattr(pc, 'submit_with_context', submitted)
    pc.process_conversation(
        'uid',
        'en',
        _existing_desktop(),
        trigger=pc.ProcessingTrigger.SILENT_BACKFILL,
        defer_derived_effects=defer,
        derived_effects_observer=bundle.append,
        derived_effects_disposition_observer=disposition.append,
        recovery_transcript_decoded=True,
    )
    assert payloads and payloads[-1][pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD] is True
    assert not bundle
    assert disposition[-1] is pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS
    for key in ['extract_memories', 'extract_memories_inner', 'trigger_apps', 'assign_folder']:
        spies[key].assert_not_called()
    submitted.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize('anyio_backend', ['asyncio'])
@pytest.mark.parametrize('replay', [False, True])
@pytest.mark.parametrize('fanout_status', ['claimed', 'completed', 'fenced'])
async def test_silent_job_retry_and_completed_replay_never_fan_out(
    monkeypatch, pc, anyio_backend, replay, fanout_status
):
    del anyio_backend
    finalizer = _load_finalizer()
    conversation = SimpleNamespace(
        id='historic',
        status=ConversationStatus.completed if replay else ConversationStatus.processing,
        discarded=False,
        geolocation=None,
        language='en',
    )

    async def load(*_):
        return None, {pc.TERMINAL_NO_DERIVED_EFFECTS_FIELD: replay}, conversation

    monkeypatch.setattr(finalizer, '_load_admitted_conversation', load)
    monkeypatch.setattr(finalizer, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda _: None)
    monkeypatch.setattr(finalizer, 'warm_rollout_cohorts', AsyncMock())
    monkeypatch.setattr(finalizer, 'finalization_pending', lambda *_: False)
    monkeypatch.setattr(finalizer, 'is_donor', lambda _: False)

    def process(_uid, _language, conv, **kwargs):
        assert kwargs['trigger'] is pc.ProcessingTrigger.SILENT_BACKFILL
        conv.status = ConversationStatus.completed
        kwargs['persistence_observer'](True)
        return conv

    monkeypatch.setattr(finalizer, 'process_conversation', process)
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *_: {'status': fanout_status, 'fanout_key': 'key'},
    )
    complete = MagicMock(return_value=True)
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_finalization_fanout', complete)
    for name in [
        '_maybe_start_shadow',
        'link_duplicate_captures',
        'extract_memories',
        'record_finalized_meeting_receipt',
        'schedule_person_voice_learning_retry',
    ]:
        monkeypatch.setattr(finalizer, name, MagicMock(side_effect=AssertionError('silent delivery escaped')))
    for name in [
        'smart_merge_step',
        'await_meeting_evidence',
        'trigger_external_integrations',
        '_episode_after_finalization',
        '_episode_after_absorb',
        'resolve_frame_request_authority',
    ]:
        monkeypatch.setattr(finalizer, name, AsyncMock(side_effect=AssertionError('silent trigger escaped')))
    result = await finalizer.finalize_persisted_conversation(
        'uid',
        'historic',
        finalization_job_id='job',
        dispatch_generation=1,
        lease_epoch=2,
        trigger=pc.ProcessingTrigger.SILENT_BACKFILL,
    )
    assert result.value == ('fenced' if fanout_status == 'fenced' else 'completed')
    assert complete.call_count == (1 if fanout_status == 'claimed' else 0)


def test_silent_backfill_budget_denial_cannot_persist_a_title_only_success(monkeypatch, pc):
    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda *_: True)
    monkeypatch.setattr(pc.funded_processing, 'processing_allowed', lambda *_: False)
    spies = _spy_managed_effects(monkeypatch, pc)
    payloads = _capture_all_persists(monkeypatch, pc)
    with pytest.raises(pc.RecoveryStructureUnavailableError, match='processing budget unavailable'):
        pc.process_conversation('uid', 'en', _existing_desktop(), trigger=pc.ProcessingTrigger.SILENT_BACKFILL)
    assert payloads == []
    spies['get_structured'].assert_not_called()

"""S4 Worker C: POST /v1/conversations and /{id}/finalize accept a projection.

Named proofs: a valid projection at the synchronous finalize is stored and a
basic user pays no managed structure call; digest mismatch / malformed payload
drop the projection without 422ing the finished recording; a stored document
projection still sets has_projection; an explicit ingest-time projection wins
over a stored one. The durable POST /{id}/finalize path persists an accepted
projection onto Conversation.client_processing (no Cloud Task payload change)
so the worker's stored-projection path can see it. An idempotent durable retry
hash-binds a late projection against the stored transcript and writes only
client_processing (section 1.7 (c)); mismatch / malformed drops it, still 200.
Rejected-payload provenance is sanitized to one bounded single-line record.
A transcript-text or speaker/person mutation atomically DELETE_FIELDs the
projection in the same write; a losing concurrent synchronous finalize still
persists a projection that hash-binds against ``latest``.
A winning synchronous finalize persists the accepted projection through the
ingress-owned mutation on the admission CAS itself (paid, basic, and flag-off
all survive a Firestore reread). Admission and the stamp are one write: a
later loser late-bind overwrites that stamp, a stalled second write cannot
commit an older winner after the loser, and a mutation failure does not
strand the row on processing. The winner must not stamp again after
processing (section 1.7 (c)). A live-capture opt-out still clears a
projection that is actually present and writes no sentinel when none is.
Hash verification and the projection write are one transaction: a T1-verified
candidate is not stored after a T2 segment update on late-bind, synchronous
admit, or durable admit; the conversation still finalizes.
A route response attaches a projection only when the transaction stored it:
a T1-validated candidate dropped after a T2 race is absent from Firestore
and from the response, and the client receives the deterministic minimum.
A matching transcript still returns the projection that was stored.
The transaction reports that decision; the routes do not reread. A's rejected
T1 is not replaced by B's later T2 in A's response, and a failed read that
used to sit between admission and the guard can no longer strand the row.

Isolation: stub_modules + load_module_fresh. routers.conversations is a heavy
import — paid in the module-scoped fixture, never in a test body.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import zlib
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Mapping
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

import pytest
from google.cloud import firestore as google_firestore
from pydantic import ValidationError

import database.conversations as conversations_db

from config.plan_catalog import PlanType
from models.client_processing import (
    CLIENT_PROCESSING_SCHEMA_VERSION,
    ClientProcessing,
    PROJECTION_FAMILY_FIELDS,
    ProjectedActionItem,
    ProjectedStructure,
    ProjectionProvenance,
)
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations.transcript_hash import transcript_sha256
import utils.managed_compute as managed_compute
from utils.managed_compute import Decision

_BACKEND = Path(__file__).resolve().parents[2]
_UID = 's4-finalize-uid'
_CONV_ID = 's4-finalize-conv'
_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
_SEGMENT_TEXT = 'Hello from the desktop capture'
CANARY = 'UNIQUE_PROJECTION_CANARY_xyzzy_not_in_logs'
PROJECTION_TITLE = 'Local on-device summary'
PROJECTION_TITLE_A = 'Winner earlier projection A'
PROJECTION_TITLE_B = 'Later T2 projection from B'
STORED_TITLE = 'Stored retry projection'
EXPLICIT_TITLE = 'Explicit ingest projection'
_MISMATCH_HASH = '0' * 64


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
        'delete_vector',
        'delete_transcript_chunk_vectors',
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

    redis = add('database.redis_db', AutoMockModule('database.redis_db'))
    redis.get_cached_user_geolocation = MagicMock(return_value=None)
    redis.get_in_progress_conversation_id = MagicMock(return_value=_CONV_ID)
    redis.remove_in_progress_conversation_id = MagicMock()

    for name in (
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
        'generate_summary_with_prompt',
        'SummaryProviderError',
    ):
        setattr(conv_proc, attr, MagicMock())
    add('utils.llm.conversation_processing', conv_proc)

    add('utils.llm.conversation_prompt_prefix', AutoMockModule('utils.llm.conversation_prompt_prefix'))
    add('utils.apps', AutoMockModule('utils.apps'))
    add('utils.analytics', AutoMockModule('utils.analytics')).record_usage = MagicMock()
    add('utils.conversations.transcript_chunks', AutoMockModule('utils.conversations.transcript_chunks'))
    add('utils.conversations.calendar_linking', AutoMockModule('utils.conversations.calendar_linking'))
    add('utils.conversations.calendar_utils', AutoMockModule('utils.conversations.calendar_utils'))
    meeting_context = add('utils.conversations.meeting_context', AutoMockModule('utils.conversations.meeting_context'))
    meeting_context.MAX_SCREEN_CONTEXT_ROWS = 80
    meeting_context.MEETING_SEARCH_TOLERANCE_MINUTES = 5
    add('utils.conversations.factory', AutoMockModule('utils.conversations.factory'))
    lifecycle = add('utils.conversations.lifecycle', AutoMockModule('utils.conversations.lifecycle'))
    lifecycle.persist_processed_conversation = MagicMock(return_value=True)
    lifecycle.create_completed_conversation = MagicMock(return_value=True)
    lifecycle.create_processing_conversation = MagicMock(return_value=True)
    lifecycle.admit_processing = MagicMock(return_value=True)
    lifecycle.processing_admission_guard = lambda *_args, **_kwargs: nullcontext()
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
    byok.has_byok_keys = lambda: False
    add('utils.byok', byok)

    executors = add('utils.executors', AutoMockModule('utils.executors'))
    executors.db_executor = MagicMock()
    executors.llm_executor = MagicMock()
    executors.postprocess_executor = MagicMock()
    executors.submit_with_context = MagicMock()
    executors.run_blocking = MagicMock()

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
    cloud_tasks.is_audio_merge_dispatch_enabled = MagicMock(return_value=False)
    add('utils.observability.fallback', AutoMockModule('utils.observability.fallback'))
    add('utils.observability.finalization', AutoMockModule('utils.observability.finalization'))
    add('utils.metrics', AutoMockModule('utils.metrics'))
    add('utils.product_telemetry', AutoMockModule('utils.product_telemetry'))

    add('utils.memory.canonical_activation', AutoMockModule('utils.memory.canonical_activation'))
    add('utils.memory.memory_service', AutoMockModule('utils.memory.memory_service'))
    memory_system = ModuleType('utils.memory.memory_system')

    class _MemorySystem:
        LEGACY = 'legacy'
        CANONICAL = 'canonical'

    memory_system.MemorySystem = _MemorySystem
    add('utils.memory.memory_system', memory_system)
    canonical_adapter = add(
        'utils.memory.canonical_memory_adapter', AutoMockModule('utils.memory.canonical_memory_adapter')
    )
    canonical_adapter.ConversationReplacementConflictError = type(
        'ConversationReplacementConflictError', (RuntimeError,), {}
    )
    add('utils.memory.decision_path_telemetry', AutoMockModule('utils.memory.decision_path_telemetry'))
    add('utils.memory.rejected_memory_feedback', AutoMockModule('utils.memory.rejected_memory_feedback'))
    retraction = add('utils.memory.retraction_scope', AutoMockModule('utils.memory.retraction_scope'))
    retraction.retraction_can_be_skipped = MagicMock(return_value=False)

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

    return fakes


def _add_conversations_fakes(fakes: dict[str, ModuleType]) -> None:
    """Extra stubs so routers.conversations can load without Firebase / Typesense."""

    def add(name: str, mod: ModuleType) -> ModuleType:
        fakes[name] = mod
        return mod

    endpoints = ModuleType('utils.other.endpoints')

    def _fake_get_current_user_uid() -> str:
        return _UID

    def _fake_with_rate_limit(dependency: Any, _policy: Any) -> Any:
        return dependency

    endpoints.get_current_user_uid = _fake_get_current_user_uid
    endpoints.with_rate_limit = _fake_with_rate_limit
    endpoints.get_user = MagicMock()
    add('utils.other.endpoints', endpoints)

    request_validation = ModuleType('utils.request_validation')
    request_validation.NonNegativeOffset = int
    request_validation.PositiveLimit = int
    add('utils.request_validation', request_validation)

    list_budget = add('utils.other.list_budget', AutoMockModule('utils.other.list_budget'))
    list_budget.OMI_LIST_TRUNCATED_HEADER = 'X-Omi-List-Truncated'
    list_budget.OMI_LIST_TRUNCATED_VALUE = '1'
    list_budget.list_read_budget_for_request = MagicMock(return_value=None)

    search = add('utils.conversations.search', AutoMockModule('utils.conversations.search'))
    search.ConversationSearchUnavailableError = type('ConversationSearchUnavailableError', (Exception,), {})
    add('utils.conversations.mcp_transcript_search', AutoMockModule('utils.conversations.mcp_transcript_search'))
    add('utils.conversations.meeting_receipt', AutoMockModule('utils.conversations.meeting_receipt'))
    add('utils.conversations.render', AutoMockModule('utils.conversations.render'))
    add('utils.conversations.location', AutoMockModule('utils.conversations.location'))
    add('utils.conversations.share_email', AutoMockModule('utils.conversations.share_email'))
    add('utils.conversations.analytics', AutoMockModule('utils.conversations.analytics'))
    add('utils.speaker_identification', AutoMockModule('utils.speaker_identification'))
    add('utils.app_integrations', AutoMockModule('utils.app_integrations'))
    add('utils.retrieval.tools.calendar_tools', AutoMockModule('utils.retrieval.tools.calendar_tools'))
    add('utils.retrieval.tools.google_utils', AutoMockModule('utils.retrieval.tools.google_utils'))
    add('utils.screen_frames', AutoMockModule('utils.screen_frames'))
    add('utils.screen_frames.store', AutoMockModule('utils.screen_frames.store'))
    add('utils.integration_telemetry', AutoMockModule('utils.integration_telemetry'))
    add('utils.journey_metrics_contract', AutoMockModule('utils.journey_metrics_contract'))
    add('utils.memory.product_authorization', AutoMockModule('utils.memory.product_authorization'))
    add('services', AutoMockModule('services'))
    add('services.conversation_frame_evidence', AutoMockModule('services.conversation_frame_evidence'))
    add('ulid', AutoMockModule('ulid'))
    add('pinecone', AutoMockModule('pinecone'))
    add('typesense', AutoMockModule('typesense'))
    add('firebase_admin', AutoMockModule('firebase_admin'))
    add('firebase_admin.messaging', AutoMockModule('firebase_admin.messaging'))
    firebase_auth = ModuleType('firebase_admin.auth')
    firebase_auth.InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
    add('firebase_admin.auth', firebase_auth)
    add('firebase_admin.credentials', AutoMockModule('firebase_admin.credentials'))
    add('firebase_admin.firestore', AutoMockModule('firebase_admin.firestore'))
    add('google.cloud.firestore', AutoMockModule('google.cloud.firestore'))
    add('google.cloud.firestore_v1', AutoMockModule('google.cloud.firestore_v1'))


@pytest.fixture(scope='module')
def stack():
    """Pay routers.conversations + process_conversation import cost in setup."""
    fakes = _build_fakes()
    _add_conversations_fakes(fakes)
    with stub_modules(fakes):
        pc = load_module_fresh(
            'utils.conversations.process_conversation',
            os.path.join(str(_BACKEND), 'utils', 'conversations', 'process_conversation.py'),
        )
        conv = load_module_fresh(
            'routers.conversations',
            os.path.join(str(_BACKEND), 'routers', 'conversations.py'),
        )
        conv.resolve_geolocation = lambda g: g
        yield pc, conv


def _segment() -> TranscriptSegment:
    return TranscriptSegment(text=_SEGMENT_TEXT, speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0)


def _digest() -> str:
    return transcript_sha256([_segment()])


def _projection(*, title: str = PROJECTION_TITLE, digest: str | None = None) -> ClientProcessing:
    return ClientProcessing(
        schema_version=CLIENT_PROCESSING_SCHEMA_VERSION,
        transcript_sha256=digest if digest is not None else _digest(),
        structure=ProjectedStructure(title=title, overview=CANARY),
        action_items=[ProjectedActionItem(description=CANARY, completed=False)],
        provenance=ProjectionProvenance(
            model_id='local-test-model',
            runtime='mlx',
            device_class='apple_silicon',
            generated_at=_NOW,
        ),
    )


def _in_progress(*, client_processing: ClientProcessing | None = None) -> Conversation:
    return Conversation(
        id=_CONV_ID,
        created_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW + timedelta(minutes=5),
        transcript_segments=[_segment()],
        source=ConversationSource.desktop,
        language='en',
        structured=Structured(title=''),
        status=ConversationStatus.in_progress,
        client_processing=client_processing,
        geolocation=None,
    )


def _basic_decision() -> Decision:
    return Decision(
        allowed=False,
        reason='basic_not_entitled',
        feature='conv_structure',
        funding_owner='omi',
        plan=PlanType.basic,
        plan_resolved=True,
    )


def _paid_decision() -> Decision:
    return Decision(
        allowed=True,
        reason='plan_paid',
        feature='conv_structure',
        funding_owner='omi',
        plan=PlanType.plus,
        plan_resolved=True,
    )


def _enable_flag(monkeypatch: pytest.MonkeyPatch, pc: Any) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: True)


def _authorize(monkeypatch: pytest.MonkeyPatch, pc: Any, decision: Decision) -> None:
    monkeypatch.setattr(managed_compute, 'authorize_managed_compute', lambda *_args, **_kwargs: decision)
    monkeypatch.setattr(managed_compute, 'request_carries_validated_byok_key', lambda _feature: False)


def _spy_managed_effects(monkeypatch: pytest.MonkeyPatch, pc: Any) -> dict[str, MagicMock]:
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
    monkeypatch.setattr(
        pc,
        'resolve_authorized_first_open_plan',
        lambda **kwargs: SimpleNamespace(defer_derived_work=True),
    )
    monkeypatch.setattr(pc, 'record_jit_first_open', MagicMock())
    return spies


def _assert_no_managed(spies: dict[str, MagicMock]) -> None:
    spies['get_structured'].assert_not_called()
    spies['extract_memories'].assert_not_called()
    spies['extract_memories_inner'].assert_not_called()
    spies['trigger_apps'].assert_not_called()
    spies['assign_folder'].assert_not_called()
    spies['init_first_open'].assert_not_called()


def _capture_has_projection(monkeypatch: pytest.MonkeyPatch, pc: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    real = pc.resolve_free_tier_processing_plan

    def wrap(**kwargs: Any):
        captured.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(pc, 'resolve_free_tier_processing_plan', wrap)
    return captured


def _persisted_payload(mock: MagicMock) -> dict[str, Any]:
    assert mock.call_args is not None
    payload = mock.call_args.args[1]
    assert isinstance(payload, dict)
    return payload


def _nested(payload: Any, *keys: str) -> Any:
    cur = payload
    for key in keys:
        if isinstance(cur, dict):
            cur = cur[key]
        else:
            cur = getattr(cur, key)
    return cur


def _prepare_finalize(monkeypatch: pytest.MonkeyPatch, conv: Any, conversation: Conversation) -> None:
    monkeypatch.setattr(conv, 'retrieve_in_progress_conversation', lambda uid: {'id': conversation.id})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: conversation)
    monkeypatch.setattr(conv.redis_db, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(conv.redis_db, 'get_in_progress_conversation_id', lambda uid: conversation.id)
    monkeypatch.setattr(conv.redis_db, 'remove_in_progress_conversation_id', lambda uid: None)
    monkeypatch.setattr(conv, 'trigger_external_integrations', AsyncMock(return_value=[]))
    monkeypatch.setattr(conv.lifecycle_service, 'processing_admission_guard', lambda *_args, **_kwargs: nullcontext())


def _commit_write(store: dict[str, Any], payload: dict[str, Any]) -> None:
    merged = dict(store['doc'])
    merged.update(payload)
    store['doc'] = merged


def _stamp_bind_report_from_payload(extra_updates: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> None:
    """Fill the transactional bind report when a fake does not call the helper."""
    if extra_updates is None:
        return
    report = extra_updates.get(conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY)
    if not isinstance(report, dict):
        return
    report['submitted_projection_bound'] = any(field in payload for field in PROJECTION_FAMILY_FIELDS)


def _payload_without_bind_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    written = dict(payload)
    written.pop(conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY, None)
    return written


def _install_sync_finalize_store(monkeypatch: pytest.MonkeyPatch, pc: Any, conv: Any) -> dict[str, Any]:
    """Fake Firestore: atomic admission CAS + coordinator persist + late-bind update."""
    store: dict[str, Any] = {
        'doc': {},
        'persist_payloads': [],
        'updates': [],
        'admits': [],
        'timeline': [],
        'status': ConversationStatus.in_progress.value,
        'before_update': None,
    }

    def fake_persist(_uid: str, payload: dict[str, Any], **_kwargs: Any) -> bool:
        store['timeline'].append('persist')
        store['persist_payloads'].append(dict(payload))
        _commit_write(store, dict(payload))
        return True

    def fake_update(_uid: str, _cid: str, update_data: dict[str, Any]) -> bool:
        hook = store.get('before_update')
        if hook is not None:
            hook(dict(update_data))
        store['timeline'].append('update')
        store['updates'].append(dict(update_data))
        _commit_write(store, dict(update_data))
        return True

    def fake_admit(_uid: str, _cid: str, extra_updates: dict[str, Any] | None = None, **_kwargs: Any) -> bool:
        if store['status'] != ConversationStatus.in_progress.value:
            return False
        payload = dict(extra_updates or {})
        hook = store.get('before_admit')
        if hook is not None:
            hook(store, payload)
        if store.get('bind_on_admit'):
            payload = conversations_db.extra_updates_with_bound_client_processing(_UID, store['doc'], payload)
        else:
            _stamp_bind_report_from_payload(extra_updates, payload)
        payload = _payload_without_bind_report(payload)
        store['timeline'].append('admit')
        store['admits'].append(payload)
        store['status'] = ConversationStatus.processing.value
        if payload:
            _commit_write(store, payload)
        after = store.get('after_admit')
        if after is not None:
            after(store)
        return True

    def fake_bind(_uid: str, _cid: str, mutation: Mapping[str, Any], **_kwargs: Any) -> bool:
        payload = dict(mutation)
        hook = store.get('before_update')
        if hook is not None:
            hook(dict(payload))
        store['timeline'].append('update')
        store['updates'].append(dict(payload))
        _commit_write(store, dict(payload))
        return True

    def fake_get(_uid: str, _cid: str, **_kwargs: Any) -> dict[str, Any]:
        return dict(store['doc'])

    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', fake_persist)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', fake_persist)
    monkeypatch.setattr(conv.conversations_db, 'update_conversation', fake_update)
    monkeypatch.setattr(conv.conversations_db, 'bind_client_processing', fake_bind)
    monkeypatch.setattr(conv.conversations_db, 'get_conversation', fake_get)
    monkeypatch.setattr(conv.lifecycle_service, 'admit_processing', fake_admit)
    return store


def _ingress_projection_mutations(store: dict[str, Any]) -> list[dict[str, Any]]:
    mutations: list[dict[str, Any]] = []
    for payload in store.get('admits', []):
        if 'client_processing' in payload:
            mutations.append({'client_processing': payload['client_processing']})
    for update in store['updates']:
        if update.keys() == {'client_processing'}:
            mutations.append(update)
    return mutations


def _assert_projection_on_reread(store: dict[str, Any]) -> None:
    mutations = _ingress_projection_mutations(store)
    assert mutations, 'ingress mutation never wrote client_processing'
    mutation = mutations[0]
    assert mutation['client_processing']['structure']['title'] == PROJECTION_TITLE
    reread = store['doc']
    assert reread.get('client_processing') is not None
    assert reread['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert store['timeline'], 'winner never wrote'
    assert store['timeline'][0] == 'admit', 'winner must stamp on the admission CAS, before coordinator persist'
    assert 'update' not in store['timeline'], 'winner must not issue a second client_processing write'


def _prepare_durable_finalize(monkeypatch: pytest.MonkeyPatch, conv: Any, conversation: Conversation) -> dict[str, Any]:
    captured: dict[str, Any] = {'doc': {}}
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: conversation)
    monkeypatch.setattr(conv.byok, 'has_byok_keys', lambda: False)

    def fake_request_finalization(*_args: Any, **kwargs: Any):
        captured['kwargs'] = kwargs
        captured['finalization_calls'] = captured.get('finalization_calls', 0) + 1
        extra_updates = kwargs.get('extra_updates')
        extra = dict(extra_updates or {})
        hook = captured.get('before_commit')
        if hook is not None:
            hook(captured['doc'], extra)
        bound = extra
        if captured.get('bind_on_commit'):
            bound = conversations_db.extra_updates_with_bound_client_processing(_UID, captured['doc'], extra)
        else:
            _stamp_bind_report_from_payload(extra_updates, extra)
        bound = _payload_without_bind_report(bound)
        if bound:
            captured['doc'].update(bound)
        after = captured.get('after_commit')
        if after is not None:
            after(captured)
        return {'route': 'cloud_tasks', 'job_id': 'job-1', 'status': 'queued'}

    def fake_get(_uid: str, _cid: str, **_kwargs: Any) -> dict[str, Any]:
        return dict(captured['doc'])

    monkeypatch.setattr(conv.lifecycle_service, 'request_finalization', fake_request_finalization)
    monkeypatch.setattr(conv.conversations_db, 'get_conversation', fake_get)
    monkeypatch.setattr(conv.redis_db, 'get_in_progress_conversation_id', lambda uid: None)
    captured['update'] = conv.conversations_db.bind_client_processing
    captured['update'].reset_mock()
    return captured


def _durable_finalize_without_projection(
    monkeypatch: pytest.MonkeyPatch, conv: Any, conversation: Conversation
) -> tuple[dict[str, Any], str]:
    """First durable finalize with no projection; status becomes processing.

    Returns the finalization capture and a JSON snapshot of ``structured`` after
    the worker-simulated deterministic minimum is applied in-memory. The
    retry must not rewrite those bytes.
    """
    captured = _prepare_durable_finalize(monkeypatch, conv, conversation)
    empty = conv.ProcessConversationRequest()
    response = conv.finalize_conversation(_CONV_ID, request=empty, uid=_UID)
    assert response.conversation.status == ConversationStatus.processing
    assert response.conversation.client_processing is None
    extra = _durable_extra_updates(captured)
    assert extra is None or 'client_processing' not in extra
    # Simulate the Cloud Tasks worker having persisted the deterministic minimum.
    conversation.structured = Structured(title=_SEGMENT_TEXT, overview='')
    structured_json = conversation.structured.model_dump_json()
    captured['update'].reset_mock()
    return captured, structured_json


# red-proof: omit client_projection= from the process_conversation call in the handler
def test_valid_projection_at_finalize_is_stored_no_managed_for_basic(monkeypatch, stack) -> None:
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    captured = _capture_has_projection(monkeypatch, pc)
    store = _install_sync_finalize_store(monkeypatch, pc, conv)
    conversation = _in_progress()
    _prepare_finalize(monkeypatch, conv, conversation)
    projection = _projection()
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})

    response = conv.process_in_progress_conversation(request=request, uid=_UID)

    assert captured.get('has_projection') is True
    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert response.conversation.structured.title == _SEGMENT_TEXT
    assert response.conversation.structured.overview == ''
    assert response.conversation.structured.title != PROJECTION_TITLE
    # Existing-row coordinator persist strips; the ingress mutation is the store.
    assert store['persist_payloads']
    payload = store['persist_payloads'][-1]
    assert 'client_processing' not in payload
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT
    assert _nested(payload, 'structured', 'overview') == ''
    _assert_projection_on_reread(store)
    _assert_no_managed(spies)


# red-proof: skip the hash compare so a mismatch is stored and no warning fires
def test_digest_mismatch_drops_projection_and_still_finalizes(monkeypatch, stack, caplog) -> None:
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    captured = _capture_has_projection(monkeypatch, pc)
    persisted = pc.lifecycle_service.persist_processed_conversation
    persisted.reset_mock()
    conversation = _in_progress()
    _prepare_finalize(monkeypatch, conv, conversation)
    mismatched = _projection(digest=_MISMATCH_HASH)
    request = conv.ProcessConversationRequest.model_validate({'client_processing': mismatched.model_dump(mode='json')})

    with caplog.at_level(logging.WARNING, logger=conv.__name__):
        response = conv.process_in_progress_conversation(request=request, uid=_UID)

    assert captured.get('has_projection') is False
    assert response.conversation.client_processing is None
    assert response.conversation.status == ConversationStatus.completed
    payload = _persisted_payload(persisted)
    assert payload.get('client_processing') is None
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT
    warnings = [record for record in caplog.records if 'hash_mismatch' in record.getMessage()]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert CANARY not in message
    assert PROJECTION_TITLE not in message
    assert _SEGMENT_TEXT not in message
    assert 'local-test-model' in message
    assert 'mlx' in message
    assert 'apple_silicon' in message
    _assert_no_managed(spies)


# red-proof: type ProcessConversationRequest.client_processing as ClientProcessing (malformed would 422)
def test_malformed_projection_does_not_422_and_still_finalizes(monkeypatch, stack, caplog) -> None:
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    captured = _capture_has_projection(monkeypatch, pc)
    persisted = pc.lifecycle_service.persist_processed_conversation
    persisted.reset_mock()
    conversation = _in_progress()
    _prepare_finalize(monkeypatch, conv, conversation)
    malformed = {'schema_version': 2, 'structure': {'title': CANARY}, 'transcript_sha256': _digest()}
    request = conv.ProcessConversationRequest.model_validate({'client_processing': malformed})
    assert request.client_processing == malformed

    with caplog.at_level(logging.WARNING, logger=conv.__name__):
        response = conv.process_in_progress_conversation(request=request, uid=_UID)

    assert captured.get('has_projection') is False
    assert response.conversation.client_processing is None
    assert response.conversation.status == ConversationStatus.completed
    payload = _persisted_payload(persisted)
    assert payload.get('client_processing') is None
    warnings = [record for record in caplog.records if 'schema_invalid' in record.getMessage()]
    assert len(warnings) == 1
    assert CANARY not in warnings[0].getMessage()
    _assert_no_managed(spies)


def test_malformed_non_object_projection_does_not_422(stack) -> None:
    _pc, conv = stack
    request = conv.ProcessConversationRequest.model_validate({'client_processing': CANARY})
    assert request.client_processing == CANARY
    with pytest.raises(ValidationError):
        ClientProcessing.model_validate(CANARY)


# red-proof: has_projection=client_projection is not None (stored-only retry would skip store_projection)
def test_stored_projection_alone_makes_has_projection_true(monkeypatch, stack) -> None:
    pc, _conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    captured = _capture_has_projection(monkeypatch, pc)
    persisted = pc.lifecycle_service.persist_processed_conversation
    persisted.reset_mock()
    stored = _projection(title=STORED_TITLE)

    result = pc.process_conversation(_UID, 'en', _in_progress(client_processing=stored))

    assert captured.get('has_projection') is True
    assert result.client_processing is stored
    assert result.client_processing.structure.title == STORED_TITLE
    assert result.structured.title == _SEGMENT_TEXT
    assert result.structured.overview == ''
    assert result.structured.title != STORED_TITLE
    payload = _persisted_payload(persisted)
    # Existing-row persist omits the field (merge leaves a stored projection).
    assert 'client_processing' not in payload
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT
    _assert_no_managed(spies)


# red-proof: prefer stored client_processing when both are present (explicit would be ignored)
def test_explicit_projection_beats_stored_one(monkeypatch, stack) -> None:
    pc, _conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    captured = _capture_has_projection(monkeypatch, pc)
    persisted = pc.lifecycle_service.persist_processed_conversation
    persisted.reset_mock()
    stored = _projection(title=STORED_TITLE)
    explicit = _projection(title=EXPLICIT_TITLE)

    result = pc.process_conversation(_UID, 'en', _in_progress(client_processing=stored), client_projection=explicit)

    assert captured.get('has_projection') is True
    assert result.client_processing is explicit
    assert result.client_processing.structure.title == EXPLICIT_TITLE
    assert result.structured.title == _SEGMENT_TEXT
    assert result.structured.overview == ''
    assert result.structured.title != EXPLICIT_TITLE
    assert result.structured.title != STORED_TITLE
    payload = _persisted_payload(persisted)
    assert 'client_processing' not in payload
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT
    _assert_no_managed(spies)


def _durable_extra_updates(captured: dict[str, Any]) -> dict[str, Any] | None:
    kwargs = captured.get('kwargs') or {}
    extra = kwargs.get('extra_updates')
    assert extra is None or isinstance(extra, dict)
    return extra


# red-proof: skip extra_updates['client_processing'] = ... (valid projection would enqueue without a stored projection)
def test_durable_finalize_persists_projection_visible_as_has_projection(monkeypatch, stack) -> None:
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    captured_plan = _capture_has_projection(monkeypatch, pc)
    conversation = _in_progress()
    finalization = _prepare_durable_finalize(monkeypatch, conv, conversation)
    projection = _projection()
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})

    response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    extra = _durable_extra_updates(finalization)
    assert extra is not None
    assert extra['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert response.conversation.status == ConversationStatus.processing

    stored = ClientProcessing.model_validate(extra['client_processing'])
    persisted = pc.lifecycle_service.persist_processed_conversation
    persisted.reset_mock()
    result = pc.process_conversation(_UID, 'en', _in_progress(client_processing=stored))
    assert captured_plan.get('has_projection') is True
    assert result.client_processing is stored
    assert result.structured.title == _SEGMENT_TEXT
    assert result.structured.overview == ''
    assert result.structured.title != PROJECTION_TITLE
    payload = _persisted_payload(persisted)
    # Worker persist of an existing row strips; extra_updates already stored it.
    assert 'client_processing' not in payload
    _assert_no_managed(spies)


# red-proof: skip the hash compare (`if False and expected != ...`) so a mismatch is persisted on extra_updates
def test_durable_finalize_digest_mismatch_drops_projection_and_still_finalizes(monkeypatch, stack, caplog) -> None:
    _pc, conv = stack
    conversation = _in_progress()
    finalization = _prepare_durable_finalize(monkeypatch, conv, conversation)
    mismatched = _projection(digest=_MISMATCH_HASH)
    request = conv.ProcessConversationRequest.model_validate({'client_processing': mismatched.model_dump(mode='json')})

    with caplog.at_level(logging.WARNING, logger=conv.__name__):
        response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    extra = _durable_extra_updates(finalization)
    assert extra is None or 'client_processing' not in extra
    assert response.conversation.client_processing is None
    assert response.conversation.status == ConversationStatus.processing
    assert finalization.get('kwargs') is not None
    warnings = [record for record in caplog.records if 'hash_mismatch' in record.getMessage()]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert CANARY not in message
    assert PROJECTION_TITLE not in message
    assert _SEGMENT_TEXT not in message
    assert 'local-test-model' in message


# red-proof: type ProcessConversationRequest.client_processing as ClientProcessing (malformed would 422)
def test_durable_finalize_malformed_projection_does_not_422(monkeypatch, stack, caplog) -> None:
    _pc, conv = stack
    conversation = _in_progress()
    finalization = _prepare_durable_finalize(monkeypatch, conv, conversation)
    malformed = {'schema_version': 2, 'structure': {'title': CANARY}, 'transcript_sha256': _digest()}
    request = conv.ProcessConversationRequest.model_validate({'client_processing': malformed})
    assert request.client_processing == malformed

    with caplog.at_level(logging.WARNING, logger=conv.__name__):
        response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    extra = _durable_extra_updates(finalization)
    assert extra is None or 'client_processing' not in extra
    assert response.conversation.client_processing is None
    assert response.conversation.status == ConversationStatus.processing
    warnings = [record for record in caplog.records if 'schema_invalid' in record.getMessage()]
    assert len(warnings) == 1
    assert CANARY not in warnings[0].getMessage()


# red-proof: return immediately on non-in_progress without examining the new projection
def test_durable_retry_stores_late_projection_without_rewriting_structured(monkeypatch, stack) -> None:
    _pc, conv = stack
    conversation = _in_progress()
    captured, structured_before = _durable_finalize_without_projection(monkeypatch, conv, conversation)
    conversation.status = ConversationStatus.completed
    projection = _projection()
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})

    response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    assert captured.get('finalization_calls') == 1
    captured['update'].assert_called_once()
    uid, cid, update_data = captured['update'].call_args.args
    assert uid == _UID
    assert cid == _CONV_ID
    assert update_data.keys() == {'client_processing'}
    assert 'structured' not in update_data
    assert update_data['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert response.conversation.structured.model_dump_json() == structured_before
    assert response.conversation.structured.title == _SEGMENT_TEXT
    assert response.conversation.structured.title != PROJECTION_TITLE
    assert response.conversation.status == ConversationStatus.completed


# red-proof: bind the late projection without checking the stored transcript digest
def test_durable_retry_mismatched_digest_leaves_conversation_unchanged(monkeypatch, stack, caplog) -> None:
    _pc, conv = stack
    conversation = _in_progress()
    captured, structured_before = _durable_finalize_without_projection(monkeypatch, conv, conversation)
    mismatched = _projection(digest=_MISMATCH_HASH)
    request = conv.ProcessConversationRequest.model_validate({'client_processing': mismatched.model_dump(mode='json')})

    with caplog.at_level(logging.WARNING, logger=conv.__name__):
        response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    assert captured.get('finalization_calls') == 1
    captured['update'].assert_not_called()
    assert response.conversation.client_processing is None
    assert response.conversation.structured.model_dump_json() == structured_before
    assert response.conversation.status == ConversationStatus.processing
    warnings = [record for record in caplog.records if 'hash_mismatch' in record.getMessage()]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert CANARY not in message
    assert PROJECTION_TITLE not in message
    assert _SEGMENT_TEXT not in message


# red-proof: nest ClientProcessing on the request so a malformed retry 422s instead of returning the stored conversation
def test_durable_retry_malformed_projection_leaves_conversation_unchanged(monkeypatch, stack, caplog) -> None:
    _pc, conv = stack
    conversation = _in_progress()
    captured, structured_before = _durable_finalize_without_projection(monkeypatch, conv, conversation)
    malformed = {'schema_version': 2, 'structure': {'title': CANARY}, 'transcript_sha256': _digest()}
    request = conv.ProcessConversationRequest.model_validate({'client_processing': malformed})
    assert request.client_processing == malformed

    with caplog.at_level(logging.WARNING, logger=conv.__name__):
        response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    assert captured.get('finalization_calls') == 1
    captured['update'].assert_not_called()
    assert response.conversation.client_processing is None
    assert response.conversation.structured.model_dump_json() == structured_before
    assert response.conversation.status == ConversationStatus.processing
    warnings = [record for record in caplog.records if 'schema_invalid' in record.getMessage()]
    assert len(warnings) == 1
    assert CANARY not in warnings[0].getMessage()


# red-proof: log raw model_id/runtime/device_class without sanitizing (newlines forge a second record)
def test_rejected_projection_provenance_is_bounded_single_line(monkeypatch, stack, caplog) -> None:
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    persisted = pc.lifecycle_service.persist_processed_conversation
    persisted.reset_mock()
    conversation = _in_progress()
    _prepare_finalize(monkeypatch, conv, conversation)
    oversized = 'Q' * 400
    malformed = {
        'schema_version': 2,
        'structure': {'title': CANARY},
        'transcript_sha256': _digest(),
        'provenance': {
            'model_id': 'local-test-model\nFAKE_LEVEL fake.logger: forged',
            'runtime': 'mlx\x00\x07\rCR',
            'device_class': oversized,
        },
    }
    request = conv.ProcessConversationRequest.model_validate({'client_processing': malformed})

    with caplog.at_level(logging.WARNING, logger=conv.__name__):
        response = conv.process_in_progress_conversation(request=request, uid=_UID)

    assert response.conversation.status == ConversationStatus.completed
    assert response.conversation.client_processing is None
    warnings = [record for record in caplog.records if 'client_processing rejected' in record.getMessage()]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    formatted = logging.Formatter('%(levelname)s:%(name)s:%(message)s').format(warnings[0])
    assert '\n' not in message
    assert '\r' not in message
    assert '\x00' not in message
    assert '\x07' not in message
    assert '\n' not in formatted
    assert CANARY not in message
    assert oversized not in message
    assert message.count('Q') <= 120
    assert 'schema_invalid' in message
    _assert_no_managed(spies)


# ---------------------------------------------------------------------------
# Finding 6 — transcript / attribution mutation atomically clears projection
# ---------------------------------------------------------------------------


class _TextEditSnapshot:
    def __init__(self, data: dict[str, Any] | None, exists: bool = True):
        self._data = data
        self.exists = exists

    def to_dict(self) -> dict[str, Any] | None:
        return None if self._data is None else dict(self._data)


class _TextEditRef:
    def __init__(self, snapshot: _TextEditSnapshot):
        self.snapshot = snapshot
        self.update_calls: list[dict[str, Any]] = []

    def get(self, transaction=None) -> _TextEditSnapshot:
        return self.snapshot

    def update(self, data: dict[str, Any]) -> None:
        self.update_calls.append(data)


class _TextEditPath:
    def __init__(self, ref: _TextEditRef):
        self.ref = ref

    def collection(self, _name: str) -> '_TextEditPath':
        return self

    def document(self, document_id: str) -> Any:
        return self if document_id == _UID else self.ref


class _TextEditFirestore:
    def __init__(self, ref: _TextEditRef):
        self.path = _TextEditPath(ref)

    def collection(self, _name: str) -> _TextEditPath:
        return self.path

    def transaction(self) -> '_TextEditTxn':
        return _TextEditTxn()


class _TextEditTxn:
    def update(self, ref: _TextEditRef, data: dict[str, Any]) -> None:
        ref.update(data)


class _SegmentWriteClient:
    """Minimal firestore_client for update_conversation_segments."""

    def __init__(self, snapshot: dict[str, Any] | None):
        self._snapshot = snapshot
        self.commits: list[dict[str, Any]] = []
        self.exists = snapshot is not None

    def collection(self, _collection_id: str) -> '_SegmentWriteClient':
        return self

    def document(self, _document_id: str) -> '_SegmentWriteClient':
        return self

    def get(self, transaction=None) -> '_SegmentWriteClient':
        return self

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._snapshot) if self._snapshot is not None else None

    def transaction(self) -> '_SegmentWriteClient':
        return self

    def update(self, _doc_ref: Any, payload: dict[str, Any]) -> None:
        self.commits.append(payload)


def _decoded_segments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return json.loads(zlib.decompress(payload['transcript_segments']).decode('utf-8'))


def _install_text_edit_db(monkeypatch: pytest.MonkeyPatch, snapshot: dict[str, Any] | None, *, exists: bool = True):
    ref = _TextEditRef(_TextEditSnapshot(snapshot, exists=exists))
    monkeypatch.setattr(conversations_db, 'db', _TextEditFirestore(ref))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    return ref


def _assignable_conversation(*, with_projection: bool = True) -> Conversation:
    segment = TranscriptSegment(
        id='seg-0',
        text=_SEGMENT_TEXT,
        speaker='SPEAKER_00',
        speaker_id=0,
        is_user=False,
        start=0.0,
        end=1.0,
    )
    return Conversation(
        id=_CONV_ID,
        created_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW + timedelta(minutes=5),
        transcript_segments=[segment],
        source=ConversationSource.desktop,
        language='en',
        structured=Structured(title=_SEGMENT_TEXT, overview='keep-overview'),
        status=ConversationStatus.completed,
        client_processing=_projection() if with_projection else None,
        geolocation=None,
    )


def _route_endpoint(conv: Any, path: str) -> Any:
    for route in conv.router.routes:
        if getattr(route, 'path', None) == path and 'PATCH' in getattr(route, 'methods', set()):
            return route.endpoint
    raise AssertionError(f'route not registered: {path}')


def _capture_segment_write(monkeypatch: pytest.MonkeyPatch, conv: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_update(*args: Any, **kwargs: Any) -> bool:
        captured['args'] = args
        captured['kwargs'] = kwargs
        return True

    monkeypatch.setattr(conv.conversations_db, 'update_conversation_segments', fake_update)
    monkeypatch.setattr(conv, 'emit_product_event', lambda **_kwargs: None)
    return captured


# red-proof: skip `_invalidate_client_processing` so the text write leaves client_processing attached
def test_segment_text_edit_clears_projection_in_the_same_write(monkeypatch) -> None:
    snapshot = {
        'data_protection_level': 'standard',
        'is_locked': False,
        'transcript_segments': [{'id': 's1', 'text': 'old'}, {'id': 's2', 'text': 'keep'}],
        'client_processing': {'structure': {'title': PROJECTION_TITLE}},
        'structured': {'title': 'keep-title', 'overview': 'keep-overview'},
    }
    ref = _install_text_edit_db(monkeypatch, snapshot)

    result = conversations_db.update_conversation_segment_text(_UID, _CONV_ID, 's1', 'new text')

    assert result == 'ok'
    assert len(ref.update_calls) == 1
    payload = ref.update_calls[0]
    assert payload['client_processing'] is conversations_db.firestore.DELETE_FIELD
    assert payload['client_processing'] is google_firestore.DELETE_FIELD
    assert payload['client_processing'] is not None
    assert {segment['id']: segment['text'] for segment in _decoded_segments(payload)} == {
        's1': 'new text',
        's2': 'keep',
    }
    assert 'structured' not in payload


# red-proof: write structured=None alongside the clear so a no-projection doc is mutated
def test_segment_text_edit_without_projection_does_not_touch_other_fields(monkeypatch) -> None:
    snapshot = {
        'data_protection_level': 'standard',
        'is_locked': False,
        'transcript_segments': [{'id': 's1', 'text': 'old'}],
        'structured': {'title': 'keep-title', 'overview': 'keep-overview'},
    }
    ref = _install_text_edit_db(monkeypatch, snapshot)

    result = conversations_db.update_conversation_segment_text(_UID, _CONV_ID, 's1', 'new text')

    assert result == 'ok'
    payload = ref.update_calls[0]
    assert payload['client_processing'] is conversations_db.firestore.DELETE_FIELD
    assert 'structured' not in payload
    assert {segment['id']: segment['text'] for segment in _decoded_segments(payload)} == {'s1': 'new text'}


# red-proof: still call `_invalidate_client_processing` on the not-found path
def test_segment_text_edit_does_not_clear_when_mutation_does_not_write(monkeypatch) -> None:
    snapshot = {
        'data_protection_level': 'standard',
        'is_locked': False,
        'transcript_segments': [{'id': 's1', 'text': 'old'}],
        'client_processing': {'structure': {'title': PROJECTION_TITLE}},
    }
    ref = _install_text_edit_db(monkeypatch, snapshot)

    result = conversations_db.update_conversation_segment_text(_UID, _CONV_ID, 'missing', 'x')

    assert result == 'segment_not_found'
    assert ref.update_calls == []


# red-proof: skip `_invalidate_client_processing` when the flag is set
def test_attribution_segment_write_clears_projection_in_the_same_write(monkeypatch) -> None:
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    client = _SegmentWriteClient(
        {
            'data_protection_level': 'standard',
            'has_content': True,
            'client_processing': {'structure': {'title': PROJECTION_TITLE}},
        }
    )
    segments = [{'id': 'seg-0', 'text': _SEGMENT_TEXT, 'is_user': True, 'person_id': None}]

    assert (
        conversations_db.update_conversation_segments(
            _UID,
            _CONV_ID,
            segments,
            data_protection_level='standard',
            firestore_client=client,
            invalidate_client_processing=True,
        )
        is True
    )
    assert len(client.commits) == 1
    payload = client.commits[0]
    assert payload['client_processing'] is conversations_db.firestore.DELETE_FIELD
    assert _decoded_segments(payload) == segments
    assert 'structured' not in payload


# red-proof: drop the explicit opt-out below (the live path would then clear on every append)
def test_live_segment_write_opts_out_of_the_fail_closed_default(monkeypatch) -> None:
    """The DB default invalidates; live capture skips the unconditional sentinel.

    update_conversation_segments defaults to invalidating because its job is
    replacing the transcript a projection was bound to, and an opt-in default
    would leave every future call site carrying the stale-projection bug. Live
    capture opts out of the unconditional DELETE_FIELD so the ~0.6s write
    loop stays cheap when no projection is present. The transaction still
    clears a projection that is actually on the document.
    """
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    client = _SegmentWriteClient({'data_protection_level': 'standard', 'has_content': True})
    segments = [{'id': 'seg-0', 'text': _SEGMENT_TEXT}]

    assert (
        conversations_db.update_conversation_segments(
            _UID,
            _CONV_ID,
            segments,
            data_protection_level='standard',
            firestore_client=client,
            invalidate_client_processing=False,
        )
        is True
    )
    payload = client.commits[0]
    assert 'client_processing' not in payload
    assert _decoded_segments(payload) == segments


# red-proof: skip the `elif current.get('client_processing') is not None` branch so a live
# append against a document that already has a projection leaves it attached
def test_live_append_clears_projection_that_is_actually_present(monkeypatch) -> None:
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    client = _SegmentWriteClient(
        {
            'data_protection_level': 'standard',
            'has_content': True,
            'client_processing': {'structure': {'title': PROJECTION_TITLE}},
        }
    )
    segments = [{'id': 'seg-0', 'text': _SEGMENT_TEXT}]

    assert (
        conversations_db.update_conversation_segments(
            _UID,
            _CONV_ID,
            segments,
            data_protection_level='standard',
            firestore_client=client,
            invalidate_client_processing=False,
        )
        is True
    )
    assert len(client.commits) == 1
    payload = client.commits[0]
    assert payload['client_processing'] is conversations_db.firestore.DELETE_FIELD
    assert payload['client_processing'] is google_firestore.DELETE_FIELD
    assert _decoded_segments(payload) == segments
    assert 'structured' not in payload


# red-proof: pass invalidate_client_processing=False on the segment-idx assign write
def test_segment_assign_route_invalidates_projection(monkeypatch, stack) -> None:
    _pc, conv = stack
    conversation = _assignable_conversation()
    captured = _capture_segment_write(monkeypatch, conv)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: conversation)
    handler = _route_endpoint(conv, '/v1/conversations/{conversation_id}/segments/{segment_idx}/assign')

    result = handler(_CONV_ID, 0, 'is_user', value='true', uid=_UID)

    assert captured['kwargs'].get('invalidate_client_processing', True) is True
    assert result.client_processing is None
    assert result.structured.overview == 'keep-overview'
    assert result.transcript_segments[0].is_user is True


# red-proof: pass invalidate_client_processing=False on the speaker-id assign write
def test_assign_speaker_route_invalidates_projection(monkeypatch, stack) -> None:
    _pc, conv = stack
    conversation = _assignable_conversation()
    captured = _capture_segment_write(monkeypatch, conv)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: conversation)

    result = conv.set_assignee_conversation_segment(_CONV_ID, 0, 'person_id', value='person-9', uid=_UID)

    assert captured['kwargs'].get('invalidate_client_processing', True) is True
    assert result.client_processing is None
    assert result.structured.overview == 'keep-overview'
    assert result.transcript_segments[0].person_id == 'person-9'


# red-proof: pass invalidate_client_processing=False on the bulk-assign write
def test_bulk_assign_route_invalidates_projection(monkeypatch, stack) -> None:
    _pc, conv = stack
    conversation = _assignable_conversation()
    captured = _capture_segment_write(monkeypatch, conv)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: conversation)
    data = conv.BulkAssignSegmentsRequest(segment_ids=['seg-0'], assign_type='is_user', value='true')

    result = conv.assign_segments_bulk(_CONV_ID, data, conv.BackgroundTasks(), uid=_UID)

    assert captured['kwargs'].get('invalidate_client_processing', True) is True
    assert result.client_processing is None
    assert result.structured.overview == 'keep-overview'
    assert result.transcript_segments[0].is_user is True


# red-proof: skip `_drop_display_projection` so a no-projection assign still looks like a clear-miss
def test_assign_without_projection_is_unaffected(monkeypatch, stack) -> None:
    _pc, conv = stack
    conversation = _assignable_conversation(with_projection=False)
    captured = _capture_segment_write(monkeypatch, conv)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: conversation)

    result = conv.set_assignee_conversation_segment(_CONV_ID, 0, 'is_user', value='true', uid=_UID)

    assert captured['kwargs'].get('invalidate_client_processing', True) is True
    assert result.client_processing is None
    assert result.structured.overview == 'keep-overview'
    assert result.structured.title == _SEGMENT_TEXT


# ---------------------------------------------------------------------------
# Finding 5 — winning synchronous finalize persists through ingress mutation
# ---------------------------------------------------------------------------


def _winning_sync_finalize(
    monkeypatch: pytest.MonkeyPatch,
    stack: Any,
    *,
    enable_flag: bool,
    decision: Decision,
) -> tuple[Any, dict[str, Any], dict[str, MagicMock]]:
    pc, conv = stack
    if enable_flag:
        _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, decision)
    store = _install_sync_finalize_store(monkeypatch, pc, conv)
    conversation = _in_progress()
    _prepare_finalize(monkeypatch, conv, conversation)
    projection = _projection()
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})
    response = conv.process_in_progress_conversation(request=request, uid=_UID)
    return response, store, spies


# red-proof: omit extra_updates=client_processing_mutation(...) from admit_processing (paid persist strips; reread loses it)
def test_paid_sync_finalize_projection_is_in_firestore_on_reread(monkeypatch, stack) -> None:
    response, store, spies = _winning_sync_finalize(monkeypatch, stack, enable_flag=True, decision=_paid_decision())

    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert store['persist_payloads'], 'coordinator never persisted'
    assert 'client_processing' not in store['persist_payloads'][-1]
    _assert_projection_on_reread(store)
    spies['get_structured'].assert_called_once()


# red-proof: omit extra_updates=client_processing_mutation(...) from admit_processing and strip the coordinator persist
def test_basic_sync_finalize_projection_is_in_firestore_on_reread(monkeypatch, stack) -> None:
    response, store, spies = _winning_sync_finalize(monkeypatch, stack, enable_flag=True, decision=_basic_decision())

    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert response.conversation.structured.title == _SEGMENT_TEXT
    assert response.conversation.structured.overview == ''
    _assert_projection_on_reread(store)
    _assert_no_managed(spies)


# red-proof: omit extra_updates=client_processing_mutation(...) from admit_processing (flag-off persist strips; reread loses it)
def test_flag_off_sync_finalize_projection_is_in_firestore_on_reread(monkeypatch, stack) -> None:
    response, store, spies = _winning_sync_finalize(monkeypatch, stack, enable_flag=False, decision=_paid_decision())

    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert store['persist_payloads'], 'coordinator never persisted'
    assert 'client_processing' not in store['persist_payloads'][-1]
    _assert_projection_on_reread(store)
    spies['get_structured'].assert_called_once()


# ---------------------------------------------------------------------------
# Finding 5 — losing concurrent synchronous finalize still persists a projection
# ---------------------------------------------------------------------------


def _prepare_finalize_loser(
    monkeypatch: pytest.MonkeyPatch,
    conv: Any,
    redis_conversation: Conversation,
    latest_conversation: Conversation,
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def deserialize(data: Any) -> Conversation:
        if isinstance(data, dict) and data.get('_which') == 'latest':
            return latest_conversation
        return redis_conversation

    monkeypatch.setattr(conv, 'retrieve_in_progress_conversation', lambda uid: {'id': redis_conversation.id})
    monkeypatch.setattr(conv, 'deserialize_conversation', deserialize)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid, '_which': 'latest'})
    monkeypatch.setattr(conv.redis_db, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(conv.lifecycle_service, 'admit_processing', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(conv, 'process_conversation', MagicMock(name='process_conversation'))
    monkeypatch.setattr(conv, 'trigger_external_integrations', AsyncMock(return_value=[]))
    captured['update'] = conv.conversations_db.bind_client_processing
    captured['update'].reset_mock()
    captured['process'] = conv.process_conversation
    captured['persist'] = conv.lifecycle_service.persist_processed_conversation
    captured['persist'].reset_mock()
    return captured


# red-proof: return latest without `_bind_late_client_projection` (valid projection dropped, still 200)
def test_losing_concurrent_finalize_persists_valid_projection_against_latest(monkeypatch, stack) -> None:
    _pc, conv = stack
    redis_conversation = _in_progress()
    latest = _in_progress()
    latest.status = ConversationStatus.processing
    latest.structured = Structured(title='deterministic-keep', overview='keep-overview')
    captured = _prepare_finalize_loser(monkeypatch, conv, redis_conversation, latest)
    projection = _projection()
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})
    structured_before = latest.structured.model_dump_json()

    response = conv.process_in_progress_conversation(request=request, uid=_UID)

    captured['process'].assert_not_called()
    captured['persist'].assert_not_called()
    captured['update'].assert_called_once()
    uid, cid, update_data = captured['update'].call_args.args
    assert uid == _UID
    assert cid == _CONV_ID
    assert update_data.keys() == {'client_processing'}
    assert 'structured' not in update_data
    assert update_data['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert response.conversation.structured.model_dump_json() == structured_before
    assert response.conversation.structured.title == 'deterministic-keep'
    assert response.conversation.structured.title != PROJECTION_TITLE
    assert response.conversation.status == ConversationStatus.processing


# red-proof: bind against the Redis snapshot instead of latest (mismatch would still persist)
def test_losing_concurrent_finalize_drops_mismatch_against_latest(monkeypatch, stack, caplog) -> None:
    _pc, conv = stack
    redis_conversation = _in_progress()
    latest = Conversation(
        id=_CONV_ID,
        created_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW + timedelta(minutes=5),
        transcript_segments=[
            TranscriptSegment(text='edited later', speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0)
        ],
        source=ConversationSource.desktop,
        language='en',
        structured=Structured(title='deterministic-keep', overview='keep-overview'),
        status=ConversationStatus.processing,
        client_processing=None,
        geolocation=None,
    )
    captured = _prepare_finalize_loser(monkeypatch, conv, redis_conversation, latest)
    projection = _projection()
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})
    structured_before = latest.structured.model_dump_json()

    with caplog.at_level(logging.WARNING, logger=conv.__name__):
        response = conv.process_in_progress_conversation(request=request, uid=_UID)

    captured['process'].assert_not_called()
    captured['persist'].assert_not_called()
    captured['update'].assert_not_called()
    assert response.conversation.client_processing is None
    assert response.conversation.structured.model_dump_json() == structured_before
    assert response.conversation.status == ConversationStatus.processing
    warnings = [record for record in caplog.records if 'hash_mismatch' in record.getMessage()]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert CANARY not in message
    assert PROJECTION_TITLE not in message
    assert _SEGMENT_TEXT not in message
    assert 'edited later' not in message


# ---------------------------------------------------------------------------
# Finding (round 6) — winner must not overwrite a later projection
# ---------------------------------------------------------------------------


def _structured_snapshot(conversation: Conversation) -> str:
    return conversation.structured.model_dump_json()


def _prepare_winner_loser_interleave(
    monkeypatch: pytest.MonkeyPatch,
    pc: Any,
    conv: Any,
    *,
    loser_raw: Any,
    latest: Conversation,
    winner: Conversation,
) -> dict[str, Any]:
    """A wins admission, stamps, then B late-binds while A is still processing."""
    store = _install_sync_finalize_store(monkeypatch, pc, conv)
    _prepare_finalize(monkeypatch, conv, winner)
    admit_calls = {'n': 0}
    original_admit = conv.lifecycle_service.admit_processing

    def admit(*args: Any, **kwargs: Any) -> bool:
        admit_calls['n'] += 1
        return original_admit(*args, **kwargs)

    monkeypatch.setattr(conv.lifecycle_service, 'admit_processing', admit)

    def deserialize(data: Any) -> Conversation:
        if isinstance(data, dict) and data.get('_which') == 'latest':
            return latest
        return winner

    monkeypatch.setattr(conv, 'deserialize_conversation', deserialize)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid, '_which': 'latest'})

    original_process = conv.process_conversation

    def process_with_loser(*args: Any, **kwargs: Any):
        stamped = store['doc'].get('client_processing') or {}
        assert (stamped.get('structure') or {}).get(
            'title'
        ) == PROJECTION_TITLE_A, 'winner must stamp its projection before processing so a later loser can overwrite'
        if not store.get('b_ran'):
            store['b_ran'] = True
            loser_request = conv.ProcessConversationRequest.model_validate({'client_processing': loser_raw})
            store['b_response'] = conv.process_in_progress_conversation(request=loser_request, uid=_UID)
        return original_process(*args, **kwargs)

    monkeypatch.setattr(conv, 'process_conversation', process_with_loser)
    store['admit_calls'] = admit_calls
    store['structured_before'] = _structured_snapshot(latest)
    return store


# red-proof: stamp client_processing again after process_conversation (winner overwrites the later loser)
def test_winner_does_not_overwrite_later_loser_projection(monkeypatch, stack) -> None:
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    winner = _in_progress()
    latest = _in_progress()
    latest.status = ConversationStatus.processing
    latest.structured = Structured(title='deterministic-keep', overview='keep-overview')
    winner_projection = _projection(title=PROJECTION_TITLE_A)
    loser_projection = _projection(title=PROJECTION_TITLE)
    store = _prepare_winner_loser_interleave(
        monkeypatch,
        pc,
        conv,
        loser_raw=loser_projection.model_dump(mode='json'),
        latest=latest,
        winner=winner,
    )
    request_a = conv.ProcessConversationRequest.model_validate(
        {'client_processing': winner_projection.model_dump(mode='json')}
    )

    response_a = conv.process_in_progress_conversation(request=request_a, uid=_UID)

    assert store.get('b_ran') is True
    assert store['admit_calls']['n'] == 2
    titles = [mutation['client_processing']['structure']['title'] for mutation in _ingress_projection_mutations(store)]
    assert titles == [PROJECTION_TITLE_A, PROJECTION_TITLE]
    assert store['timeline'][0] == 'admit'
    assert store['timeline'].count('admit') == 1
    assert store['timeline'].count('update') == 1
    assert 'persist' in store['timeline']
    assert store['timeline'].index('admit') < store['timeline'].index('update')
    assert store['timeline'].index('update') < store['timeline'].index('persist')
    assert store['persist_payloads']
    assert 'client_processing' not in store['persist_payloads'][-1]
    assert 'structured' not in store['admits'][0]
    assert 'structured' not in store['updates'][0]
    stored = store['doc']['client_processing']
    assert stored['structure']['title'] == PROJECTION_TITLE
    assert stored['structure']['title'] != PROJECTION_TITLE_A
    assert _nested(store['doc'], 'structured', 'title') == _SEGMENT_TEXT
    assert _nested(store['doc'], 'structured', 'overview') == ''
    assert _nested(store['doc'], 'structured', 'title') != PROJECTION_TITLE
    assert _nested(store['doc'], 'structured', 'title') != PROJECTION_TITLE_A
    assert store['b_response'].conversation.structured.model_dump_json() == store['structured_before']
    assert store['b_response'].conversation.structured.title == 'deterministic-keep'
    assert response_a.conversation.structured.title == _SEGMENT_TEXT
    assert response_a.conversation.structured.overview == ''
    _assert_no_managed(spies)


# red-proof: skip the hash compare in `_accepted_client_projection` so the loser mismatch is stored
def test_interleaved_loser_mismatch_does_not_overwrite_winner_projection(monkeypatch, stack, caplog) -> None:
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    winner = _in_progress()
    latest = Conversation(
        id=_CONV_ID,
        created_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW + timedelta(minutes=5),
        transcript_segments=[
            TranscriptSegment(text='edited later', speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0)
        ],
        source=ConversationSource.desktop,
        language='en',
        structured=Structured(title='deterministic-keep', overview='keep-overview'),
        status=ConversationStatus.processing,
        client_processing=None,
        geolocation=None,
    )
    winner_projection = _projection(title=PROJECTION_TITLE_A)
    loser_projection = _projection(title=PROJECTION_TITLE)
    store = _prepare_winner_loser_interleave(
        monkeypatch,
        pc,
        conv,
        loser_raw=loser_projection.model_dump(mode='json'),
        latest=latest,
        winner=winner,
    )
    request_a = conv.ProcessConversationRequest.model_validate(
        {'client_processing': winner_projection.model_dump(mode='json')}
    )

    with caplog.at_level(logging.WARNING, logger=conv.__name__):
        response_a = conv.process_in_progress_conversation(request=request_a, uid=_UID)

    assert store.get('b_ran') is True
    titles = [mutation['client_processing']['structure']['title'] for mutation in _ingress_projection_mutations(store)]
    assert titles == [PROJECTION_TITLE_A]
    stored = store['doc']['client_processing']
    assert stored['structure']['title'] == PROJECTION_TITLE_A
    assert stored['structure']['title'] != PROJECTION_TITLE
    assert _nested(store['doc'], 'structured', 'title') == _SEGMENT_TEXT
    assert _nested(store['doc'], 'structured', 'overview') == ''
    assert store['b_response'].conversation.client_processing is None
    assert store['b_response'].conversation.structured.model_dump_json() == store['structured_before']
    assert response_a.conversation.structured.title == _SEGMENT_TEXT
    warnings = [record for record in caplog.records if 'hash_mismatch' in record.getMessage()]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert CANARY not in message
    assert PROJECTION_TITLE not in message
    assert PROJECTION_TITLE_A not in message
    assert 'edited later' not in message
    _assert_no_managed(spies)


# ---------------------------------------------------------------------------
# Finding (round 7) — admission and the projection stamp are one CAS write
# ---------------------------------------------------------------------------


# red-proof: restore a separate post-admission `update_conversation` so
# `before_update` can run the loser and then commit the winner stamp, leaving
# older A stored after B
def test_reversed_commit_order_cannot_store_older_winner_projection(monkeypatch, stack) -> None:
    """The two-write inversion: A is admitted, B late-binds, A's delayed
    projection write then overwrites B. Atomic extra_updates make that
    commit order impossible — A's projection is already in the store
    before admit returns, so a `before_update` hook that would invert a
    separate winner stamp never sees one.
    """
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    winner = _in_progress()
    latest = _in_progress()
    latest.status = ConversationStatus.processing
    latest.structured = Structured(title='deterministic-keep', overview='keep-overview')
    winner_projection = _projection(title=PROJECTION_TITLE_A)
    loser_projection = _projection(title=PROJECTION_TITLE)
    store = _prepare_winner_loser_interleave(
        monkeypatch,
        pc,
        conv,
        loser_raw=loser_projection.model_dump(mode='json'),
        latest=latest,
        winner=winner,
    )

    def invert_winner_stamp(update_data: dict[str, Any]) -> None:
        title = ((update_data.get('client_processing') or {}).get('structure') or {}).get('title')
        if title != PROJECTION_TITLE_A or store.get('b_ran'):
            return
        loser_request = conv.ProcessConversationRequest.model_validate(
            {'client_processing': loser_projection.model_dump(mode='json')}
        )
        store['b_ran'] = True
        store['b_response'] = conv.process_in_progress_conversation(request=loser_request, uid=_UID)

    store['before_update'] = invert_winner_stamp
    request_a = conv.ProcessConversationRequest.model_validate(
        {'client_processing': winner_projection.model_dump(mode='json')}
    )

    response_a = conv.process_in_progress_conversation(request=request_a, uid=_UID)

    assert store.get('b_ran') is True
    titles = [mutation['client_processing']['structure']['title'] for mutation in _ingress_projection_mutations(store)]
    assert titles == [PROJECTION_TITLE_A, PROJECTION_TITLE]
    assert titles[-1] == PROJECTION_TITLE
    assert PROJECTION_TITLE_A not in [
        update['client_processing']['structure']['title']
        for update in store['updates']
        if update.keys() == {'client_processing'}
    ]
    stored = store['doc']['client_processing']
    assert stored['structure']['title'] == PROJECTION_TITLE
    assert stored['structure']['title'] != PROJECTION_TITLE_A
    assert _nested(store['doc'], 'structured', 'title') == _SEGMENT_TEXT
    assert _nested(store['doc'], 'structured', 'overview') == ''
    assert store['b_response'].conversation.structured.model_dump_json() == store['structured_before']
    assert response_a.conversation.structured.title == _SEGMENT_TEXT
    _assert_no_managed(spies)


# red-proof: admit without extra_updates, then let `update_conversation` raise
# before `processing_admission_guard` — the row is left on processing with no
# durable job
def test_projection_mutation_failure_does_not_strand_on_processing(monkeypatch, stack) -> None:
    """A failing projection write must not leave the row on processing.

    Folding the mutation into the admission CAS means a write exception is an
    admission failure: status stays in_progress, the guard never starts, and
    there is no processing row without a durable job.
    """
    _pc, conv = stack
    store = _install_sync_finalize_store(monkeypatch, _pc, conv)
    conversation = _in_progress()
    _prepare_finalize(monkeypatch, conv, conversation)
    process = MagicMock(name='process_conversation')
    monkeypatch.setattr(conv, 'process_conversation', process)
    guard_entered = {'n': 0}

    def admit(_uid: str, _cid: str, extra_updates: dict[str, Any] | None = None, **_kwargs: Any) -> bool:
        extra = extra_updates or {}
        if 'client_processing' in extra:
            raise RuntimeError('client_processing mutation failed')
        store['status'] = ConversationStatus.processing.value
        store['timeline'].append('admit')
        return True

    def fail_projection_update(_uid: str, _cid: str, update_data: dict[str, Any]) -> bool:
        if 'client_processing' in update_data:
            raise RuntimeError('client_processing mutation failed')
        store['timeline'].append('update')
        store['updates'].append(dict(update_data))
        _commit_write(store, dict(update_data))
        return True

    def guard(*_args: Any, **_kwargs: Any):
        guard_entered['n'] += 1
        return nullcontext()

    monkeypatch.setattr(conv.lifecycle_service, 'admit_processing', admit)
    monkeypatch.setattr(conv.conversations_db, 'update_conversation', fail_projection_update)
    monkeypatch.setattr(conv.lifecycle_service, 'processing_admission_guard', guard)
    request = conv.ProcessConversationRequest.model_validate(
        {'client_processing': _projection().model_dump(mode='json')}
    )

    with pytest.raises(RuntimeError, match='client_processing mutation failed'):
        conv.process_in_progress_conversation(request=request, uid=_UID)

    assert store['status'] == ConversationStatus.in_progress.value
    assert conversation.status == ConversationStatus.in_progress
    assert guard_entered['n'] == 0
    process.assert_not_called()
    assert 'admit' not in store['timeline']
    assert store['updates'] == []


# red-proof: bind through `transcript_sha256` instead of `transcript_sha256_for_binding`
# in routers/conversations.py -- the legacy row then matches and the projection is stored.
def test_legacy_noncanonical_stored_row_drops_the_projection(monkeypatch, stack, caplog) -> None:
    """A stored row written before canonicalization must not bind.

    `transcript_sha256` strips identity because clients hash their own JSON, so a
    legacy row holding `person_id=" alice "` produces the SAME digest as a canonical
    `"alice"` row -- while the renderer, which looks up the padded key, still shows
    `Speaker 0`. Equal digests would then not imply identical rendered attribution,
    which is the invariant the whole binding exists to provide. Binding against a
    stored row must therefore refuse a non-canonical one rather than trust the match.

    This test exists because the fail-closed helper alone proved nothing: reverting
    the route to the stripping helper left every other test green.
    """
    _pc, conv = stack
    legacy_segment = TranscriptSegment(
        text=_SEGMENT_TEXT, speaker='SPEAKER_00', is_user=False, person_id=' alice ', start=0.0, end=1.0
    )
    conversation = _in_progress()
    conversation.transcript_segments = [legacy_segment]
    captured = _prepare_durable_finalize(monkeypatch, conv, conversation)

    # The digest a client computes over the same words with the canonical identity.
    canonical_segment = TranscriptSegment(
        text=_SEGMENT_TEXT, speaker='SPEAKER_00', is_user=False, person_id='alice', start=0.0, end=1.0
    )
    matching_digest = transcript_sha256([canonical_segment])
    assert matching_digest == transcript_sha256([legacy_segment]), 'the stripping digest must collide here'

    projection = _projection(digest=matching_digest)
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})

    with caplog.at_level(logging.WARNING, logger=conv.__name__):
        response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    captured['update'].assert_not_called()
    assert response.conversation.client_processing is None
    warnings = [r for r in caplog.records if 'stored_transcript_not_canonical' in r.getMessage()]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert CANARY not in message
    assert PROJECTION_TITLE not in message
    assert _SEGMENT_TEXT not in message


# ---------------------------------------------------------------------------
# Finding (round 8) — verify and write the projection in one transaction
# ---------------------------------------------------------------------------

_CONV_PATH = ('users', _UID, 'conversations', _CONV_ID)
_T2_TEXT = 'edited later after T1 was hashed'


def _t1_segment_dict() -> dict[str, Any]:
    return {
        'id': 's1',
        'text': _SEGMENT_TEXT,
        'speaker': 'SPEAKER_00',
        'speaker_id': 0,
        'is_user': True,
        'start': 0.0,
        'end': 1.0,
    }


def _t1_snapshot(*, status: str = ConversationStatus.completed.value) -> dict[str, Any]:
    return {
        'data_protection_level': 'standard',
        'is_locked': False,
        'status': status,
        'transcript_segments': [_t1_segment_dict()],
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }


def _t1_mutation() -> dict[str, Any]:
    return {'client_processing': _projection().model_dump(mode='json')}


def _install_strict_conversation_db(monkeypatch: pytest.MonkeyPatch, snapshot: dict[str, Any]) -> StrictFirestore:
    store = StrictFirestore({_CONV_PATH: dict(snapshot)})
    monkeypatch.setattr(conversations_db, 'db', store)
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    return store


def _row(store: StrictFirestore) -> dict[str, Any]:
    return store.rows[_CONV_PATH]


def _commit_t2_via_segment_update() -> None:
    result = conversations_db.update_conversation_segment_text(_UID, _CONV_ID, 's1', _T2_TEXT)
    assert result == 'ok'


def _assert_t1_projection_not_stored(store: StrictFirestore) -> None:
    stored = _row(store).get('client_processing')
    if isinstance(stored, dict):
        title = (stored.get('structure') or {}).get('title')
        assert title != PROJECTION_TITLE
        return
    assert stored is conversations_db.firestore.DELETE_FIELD or stored is None


# red-proof: bind_client_processing writes mutation without hashing the transactional snapshot
def test_late_bind_does_not_store_t1_projection_after_t2_segment_update(monkeypatch, stack) -> None:
    """Verify against T1, commit T2 (clears projection), then the write sees T2.

    The route hash-binds against the in-memory T1 snapshot. The segment-text
    mutation commits T2 and DELETE_FIELDs the projection before bind's
    transaction starts. Bind must not resurrect the T1 projection.
    """
    _pc, conv = stack
    store = _install_strict_conversation_db(monkeypatch, _t1_snapshot())
    conversation = _in_progress()
    conversation.status = ConversationStatus.completed
    conversation.structured = Structured(title=_SEGMENT_TEXT, overview='')
    projection = _projection()
    assert projection.transcript_sha256 == transcript_sha256([_segment()])
    _commit_t2_via_segment_update()
    monkeypatch.setattr(conv, 'conversations_db', conversations_db)

    result = conv._bind_late_client_projection(_UID, conversation, projection.model_dump(mode='json'))

    assert result.client_processing is None
    assert result.structured.title == _SEGMENT_TEXT
    assert result.structured.overview == ''
    assert result.status == ConversationStatus.completed
    _assert_t1_projection_not_stored(store)


# red-proof: claim_conversation_status copies extra_updates['client_processing'] onto the snapshot
def test_sync_admit_does_not_store_t1_projection_after_t2_segment_update(monkeypatch) -> None:
    """Synchronous admission receives a T1-validated extra_updates payload.

    A concurrent segment update commits T2 and clears the projection before the
    claim transaction writes. Admission still succeeds; the T1 projection
    does not land on T2.
    """
    store = _install_strict_conversation_db(monkeypatch, _t1_snapshot(status=ConversationStatus.in_progress.value))
    extra = _t1_mutation()
    extra['processing_admitted_at'] = _NOW
    assert extra['client_processing']['transcript_sha256'] == transcript_sha256([_segment()])
    _commit_t2_via_segment_update()

    claimed = conversations_db.claim_conversation_status(
        _UID,
        _CONV_ID,
        ConversationStatus.in_progress,
        ConversationStatus.processing,
        extra_updates=extra,
    )

    assert claimed is True
    assert _row(store)['status'] == ConversationStatus.processing.value
    assert _row(store)['processing_admitted_at'] == _NOW
    _assert_t1_projection_not_stored(store)
    assert _row(store)['structured']['title'] == _SEGMENT_TEXT


# red-proof: check ``field in updates`` by exact name only in
# extra_updates_with_bound_client_processing -- the dotted key short-circuits the
# helper as "no projection here" and rides through to the document unbound.
def test_sync_admit_drops_dotted_projection_field_paths(monkeypatch) -> None:
    """Firestore reads ``a.b`` as a field path, so an exact-name check is not a filter.

    Synchronous admission merges caller ``extra_updates`` into its claim write.
    ``client_processing.structure.title`` is a write INTO the stored projection
    that never passes the digest bind; it must not reach the document, and it
    must not be mistaken for an absent projection.
    """
    store = _install_strict_conversation_db(monkeypatch, _t1_snapshot(status=ConversationStatus.in_progress.value))
    extra = {
        'processing_admitted_at': _NOW,
        'client_processing.structure.title': 'unbound forgery',
        'client_processing.transcript_sha256': 'deadbeef',
    }

    claimed = conversations_db.claim_conversation_status(
        _UID,
        _CONV_ID,
        ConversationStatus.in_progress,
        ConversationStatus.processing,
        extra_updates=extra,
    )

    assert claimed is True
    row = _row(store)
    assert row['status'] == ConversationStatus.processing.value
    assert not [key for key in row if '.' in key], f'field paths reached the document: {sorted(row)}'
    assert 'client_processing' not in row


# red-proof: split the key on '.' instead of parsing it with FieldPath -- a
# backtick-quoted root is not a dotted string, so both forms ride through.
def test_bind_helper_drops_backtick_quoted_projection_field_paths() -> None:
    """Backticks quote a Firestore field-path segment, so the root can be spelled two ways.

    ``client_processing`` and its backtick-quoted form resolve to the same
    protected field. A string comparison sees two unrelated keys; Firestore
    sees one write into the projection.
    """
    quoted_root = '`client_processing`'
    quoted_path = '`client_processing`.structure.title'

    bound = conversations_db.extra_updates_with_bound_client_processing(
        _UID,
        _t1_snapshot(),
        {'external_data': {'k': 'v'}, quoted_root: {'title': 'forged'}, quoted_path: 'forged'},
    )

    assert quoted_root not in bound
    assert quoted_path not in bound
    assert 'client_processing' not in bound
    assert bound['external_data'] == {'k': 'v'}
    assert bound.submitted_projection_bound is False


def test_bind_helper_keeps_the_plain_projection_field_and_unrelated_keys() -> None:
    """The filter rejects spellings, not the field itself: a plain projection still binds."""
    bound = conversations_db.extra_updates_with_bound_client_processing(_UID, _t1_snapshot(), _t1_mutation())

    assert bound.submitted_projection_bound is True
    assert bound['client_processing']['structure']['title'] == PROJECTION_TITLE
    # A key that Firestore cannot parse as a field path is left alone; it is not
    # a path into anything, and the write rejects it.
    passthrough = conversations_db.extra_updates_with_bound_client_processing(
        _UID, _t1_snapshot(), {'not a field': 1, 'external_data': {'k': 'v'}}
    )
    assert passthrough['not a field'] == 1


# red-proof: as above, but through the shared helper directly
def test_bind_helper_drops_dotted_projection_field_paths() -> None:
    bound = conversations_db.extra_updates_with_bound_client_processing(
        _UID,
        _t1_snapshot(),
        {'external_data': {'k': 'v'}, 'client_processing.structure.title': 'unbound forgery'},
    )

    assert 'client_processing.structure.title' not in bound
    assert bound['external_data'] == {'k': 'v'}
    assert bound.submitted_projection_bound is False


# red-proof: skip the transactional digest so a matching T1 projection is dropped
def test_late_bind_stores_when_transcript_is_still_t1(monkeypatch) -> None:
    store = _install_strict_conversation_db(monkeypatch, _t1_snapshot())

    stored = conversations_db.bind_client_processing(_UID, _CONV_ID, _t1_mutation())

    assert stored is True
    stored_proj = _row(store)['client_processing']
    assert stored_proj['structure']['title'] == PROJECTION_TITLE
    assert stored_proj['transcript_sha256'] == transcript_sha256([_segment()])


# red-proof: skip the transactional digest so a matching T1 extra_updates is dropped on admit
def test_sync_admit_stores_when_transcript_is_still_t1(monkeypatch) -> None:
    store = _install_strict_conversation_db(monkeypatch, _t1_snapshot(status=ConversationStatus.in_progress.value))
    extra = _t1_mutation()
    extra['processing_admitted_at'] = _NOW

    claimed = conversations_db.claim_conversation_status(
        _UID,
        _CONV_ID,
        ConversationStatus.in_progress,
        ConversationStatus.processing,
        extra_updates=extra,
    )

    assert claimed is True
    assert _row(store)['status'] == ConversationStatus.processing.value
    assert _row(store)['client_processing']['structure']['title'] == PROJECTION_TITLE


def test_transactional_bind_drops_legacy_noncanonical_stored_row(monkeypatch, caplog) -> None:
    legacy = {
        'data_protection_level': 'standard',
        'is_locked': False,
        'status': ConversationStatus.completed.value,
        'transcript_segments': [
            {
                'id': 's1',
                'text': _SEGMENT_TEXT,
                'speaker': 'SPEAKER_00',
                'is_user': False,
                'person_id': ' alice ',
                'start': 0.0,
                'end': 1.0,
            }
        ],
    }
    store = _install_strict_conversation_db(monkeypatch, legacy)
    canonical_segment = TranscriptSegment(
        text=_SEGMENT_TEXT, speaker='SPEAKER_00', is_user=False, person_id='alice', start=0.0, end=1.0
    )
    mutation = {'client_processing': _projection(digest=transcript_sha256([canonical_segment])).model_dump(mode='json')}

    with caplog.at_level(logging.WARNING, logger=conversations_db.__name__):
        stored = conversations_db.bind_client_processing(_UID, _CONV_ID, mutation)

    assert stored is False
    assert 'client_processing' not in _row(store) or _row(store).get('client_processing') is None
    warnings = [r for r in caplog.records if 'stored_transcript_not_canonical' in r.getMessage()]
    assert len(warnings) == 1
    assert CANARY not in warnings[0].getMessage()
    assert PROJECTION_TITLE not in warnings[0].getMessage()


# ---------------------------------------------------------------------------
# Finding (round 9) — the response must say what was actually stored
# ---------------------------------------------------------------------------


def _t2_segment_dict() -> dict[str, Any]:
    return {**_t1_segment_dict(), 'text': _T2_TEXT}


def _assert_deterministic_minimum(conversation: Conversation) -> None:
    assert conversation.client_processing is None
    assert conversation.structured.title == _SEGMENT_TEXT
    assert conversation.structured.overview == ''
    assert conversation.structured.title != PROJECTION_TITLE


# red-proof: attach conversation.client_processing = client_projection after admit
# without reading the committed document (response would keep the dropped T1 summary)
def test_sync_route_transcript_race_omits_projection_from_storage_and_response(monkeypatch, stack) -> None:
    """Route hashes T1; the admission CAS sees T2 and drops. Response matches storage."""
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    store = _install_sync_finalize_store(monkeypatch, pc, conv)
    store['doc'] = {
        'data_protection_level': 'standard',
        'transcript_segments': [_t1_segment_dict()],
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }
    store['bind_on_admit'] = True

    def before_admit(current: dict[str, Any], _payload: dict[str, Any]) -> None:
        current['doc']['transcript_segments'] = [_t2_segment_dict()]

    store['before_admit'] = before_admit
    conversation = _in_progress()
    _prepare_finalize(monkeypatch, conv, conversation)
    projection = _projection()
    assert projection.transcript_sha256 == transcript_sha256([_segment()])
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})

    response = conv.process_in_progress_conversation(request=request, uid=_UID)

    assert 'client_processing' not in store['admits'][-1]
    assert store['doc'].get('client_processing') is None
    _assert_deterministic_minimum(response.conversation)
    _assert_no_managed(spies)


# red-proof: do not attach conversation.client_processing after the storage reread
# (matching projection is stored, response is the deterministic minimum)
def test_sync_route_matching_projection_is_in_storage_and_response(monkeypatch, stack) -> None:
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    store = _install_sync_finalize_store(monkeypatch, pc, conv)
    store['doc'] = {
        'data_protection_level': 'standard',
        'transcript_segments': [_t1_segment_dict()],
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }
    store['bind_on_admit'] = True
    conversation = _in_progress()
    _prepare_finalize(monkeypatch, conv, conversation)
    projection = _projection()
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})

    response = conv.process_in_progress_conversation(request=request, uid=_UID)

    assert store['admits'][-1]['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert store['doc']['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert response.conversation.structured.title == _SEGMENT_TEXT
    assert response.conversation.structured.overview == ''
    _assert_no_managed(spies)


# red-proof: attach conversation.client_processing = client_projection before
# request_finalization (response would keep the dropped T1 summary)
def test_durable_route_transcript_race_omits_projection_from_storage_and_response(monkeypatch, stack) -> None:
    """Route hashes T1; the outbox bind sees T2 and drops. Response matches storage."""
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    conversation = _in_progress()
    captured = _prepare_durable_finalize(monkeypatch, conv, conversation)
    captured['bind_on_commit'] = True
    captured['doc'].update(_t1_snapshot(status=ConversationStatus.in_progress.value))
    captured['doc']['transcript_segments'] = [_t2_segment_dict()]
    projection = _projection()
    assert projection.transcript_sha256 == transcript_sha256([_segment()])
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})

    response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    extra = _durable_extra_updates(captured)
    assert extra is not None and 'client_processing' in extra
    assert captured['doc'].get('client_processing') is None
    assert response.conversation.client_processing is None
    assert response.conversation.structured.title != PROJECTION_TITLE
    assert response.conversation.structured.overview == ''
    assert response.conversation.status == ConversationStatus.processing
    _assert_no_managed(spies)


# red-proof: do not attach conversation.client_processing after the storage reread
# (matching projection is stored, response has none)
def test_durable_route_matching_projection_is_in_storage_and_response(monkeypatch, stack) -> None:
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    conversation = _in_progress()
    captured = _prepare_durable_finalize(monkeypatch, conv, conversation)
    captured['bind_on_commit'] = True
    captured['doc'].update(_t1_snapshot(status=ConversationStatus.in_progress.value))
    projection = _projection()
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})

    response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    extra = _durable_extra_updates(captured)
    assert extra is not None
    assert extra['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert captured['doc']['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert response.conversation.status == ConversationStatus.processing
    _assert_no_managed(spies)


# ---------------------------------------------------------------------------
# Finding (round 10) — the transaction reports; the routes do not reread
# ---------------------------------------------------------------------------


def _t2_digest() -> str:
    return transcript_sha256([TranscriptSegment(text=_T2_TEXT, speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0)])


def _b_projection_dump() -> dict[str, Any]:
    return _projection(title=PROJECTION_TITLE_B, digest=_t2_digest()).model_dump(mode='json')


# red-proof: return a plain dict so submitted_projection_bound is missing / always False
def test_bind_helper_returns_whether_submitted_projection_was_accepted() -> None:
    accepted = conversations_db.extra_updates_with_bound_client_processing(_UID, _t1_snapshot(), _t1_mutation())
    assert accepted.submitted_projection_bound is True
    assert accepted['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY not in accepted

    t2 = dict(_t1_snapshot())
    t2['transcript_segments'] = [_t2_segment_dict()]
    rejected = conversations_db.extra_updates_with_bound_client_processing(_UID, t2, _t1_mutation())
    assert rejected.submitted_projection_bound is False
    assert 'client_processing' not in rejected
    assert conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY not in rejected


# red-proof: leave CLIENT_PROCESSING_BIND_REPORT_KEY on the write payload
def test_bind_helper_stamps_attached_report_and_omits_it_from_the_write() -> None:
    report = {'submitted_projection_bound': False}
    extra = {**_t1_mutation(), conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY: report}
    accepted = conversations_db.extra_updates_with_bound_client_processing(_UID, _t1_snapshot(), extra)
    assert report['submitted_projection_bound'] is True
    assert accepted.submitted_projection_bound is True
    assert conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY not in accepted

    flipped = {'submitted_projection_bound': True}
    extra_rejected = {**_t1_mutation(), conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY: flipped}
    t2 = dict(_t1_snapshot())
    t2['transcript_segments'] = [_t2_segment_dict()]
    rejected = conversations_db.extra_updates_with_bound_client_processing(_UID, t2, extra_rejected)
    assert flipped['submitted_projection_bound'] is False
    assert rejected.submitted_projection_bound is False
    assert conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY not in rejected


# red-proof: skip extra_updates_with_bound_client_processing so the report stays at its default
def test_claim_reports_rejected_t1_on_the_attached_report(monkeypatch) -> None:
    store = _install_strict_conversation_db(monkeypatch, _t1_snapshot(status=ConversationStatus.in_progress.value))
    extra = _t1_mutation()
    extra['processing_admitted_at'] = _NOW
    report = {'submitted_projection_bound': False}
    extra[conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY] = report
    _commit_t2_via_segment_update()

    claimed = conversations_db.claim_conversation_status(
        _UID,
        _CONV_ID,
        ConversationStatus.in_progress,
        ConversationStatus.processing,
        extra_updates=extra,
    )

    assert claimed is True
    assert report['submitted_projection_bound'] is False
    assert conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY not in _row(store)
    _assert_t1_projection_not_stored(store)


def test_claim_reports_accepted_t1_on_the_attached_report(monkeypatch) -> None:
    store = _install_strict_conversation_db(monkeypatch, _t1_snapshot(status=ConversationStatus.in_progress.value))
    extra = _t1_mutation()
    extra['processing_admitted_at'] = _NOW
    report = {'submitted_projection_bound': False}
    extra[conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY] = report

    claimed = conversations_db.claim_conversation_status(
        _UID,
        _CONV_ID,
        ConversationStatus.in_progress,
        ConversationStatus.processing,
        extra_updates=extra,
    )

    assert claimed is True
    assert report['submitted_projection_bound'] is True
    assert conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY not in _row(store)
    assert _row(store)['client_processing']['structure']['title'] == PROJECTION_TITLE


def test_bind_report_key_matches_router_constant(stack) -> None:
    _pc, conv = stack
    assert conv._CLIENT_PROCESSING_BIND_REPORT_KEY == conversations_db.CLIENT_PROCESSING_BIND_REPORT_KEY


# red-proof: attach conversation.client_processing = client_projection when store['doc'] has some dict
def test_sync_rejected_t1_response_does_not_echo_later_t2_projection(monkeypatch, stack) -> None:
    """A's T1 is rejected; B binds T2 before A would have reread; A's response has neither."""
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    store = _install_sync_finalize_store(monkeypatch, pc, conv)
    store['doc'] = {
        'data_protection_level': 'standard',
        'transcript_segments': [_t1_segment_dict()],
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }
    store['bind_on_admit'] = True

    def before_admit(current: dict[str, Any], _payload: dict[str, Any]) -> None:
        current['doc']['transcript_segments'] = [_t2_segment_dict()]

    def after_admit(current: dict[str, Any]) -> None:
        current['doc']['client_processing'] = _b_projection_dump()

    store['before_admit'] = before_admit
    store['after_admit'] = after_admit
    conversation = _in_progress()
    _prepare_finalize(monkeypatch, conv, conversation)
    projection = _projection()
    assert projection.transcript_sha256 == transcript_sha256([_segment()])
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})

    response = conv.process_in_progress_conversation(request=request, uid=_UID)

    assert 'client_processing' not in store['admits'][-1]
    assert store['doc']['client_processing']['structure']['title'] == PROJECTION_TITLE_B
    _assert_deterministic_minimum(response.conversation)
    assert response.conversation.client_processing is None
    _assert_no_managed(spies)


# red-proof: attach conversation.client_processing = client_projection when captured['doc'] has some dict
def test_durable_rejected_t1_response_does_not_echo_later_t2_projection(monkeypatch, stack) -> None:
    """A's T1 is rejected; B binds T2 before A would have reread; A's response has neither."""
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    conversation = _in_progress()
    captured = _prepare_durable_finalize(monkeypatch, conv, conversation)
    captured['bind_on_commit'] = True
    captured['doc'].update(_t1_snapshot(status=ConversationStatus.in_progress.value))
    captured['doc']['transcript_segments'] = [_t2_segment_dict()]

    def after_commit(current: dict[str, Any]) -> None:
        current['doc']['client_processing'] = _b_projection_dump()

    captured['after_commit'] = after_commit
    projection = _projection()
    request = conv.ProcessConversationRequest.model_validate({'client_processing': projection.model_dump(mode='json')})

    response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    extra = _durable_extra_updates(captured)
    assert extra is not None and 'client_processing' in extra
    assert captured['doc']['client_processing']['structure']['title'] == PROJECTION_TITLE_B
    assert response.conversation.client_processing is None
    assert response.conversation.structured.title != PROJECTION_TITLE
    assert response.conversation.structured.title != PROJECTION_TITLE_B
    assert response.conversation.status == ConversationStatus.processing
    _assert_no_managed(spies)


# red-proof: wrap the post-admission get_conversation in try/except (calls would be 1, row stranded if uncaught)
def test_sync_winner_does_not_reread_between_admission_and_guard(monkeypatch, stack) -> None:
    """The former reread is gone: a failing get_conversation cannot strand the row."""
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    store = _install_sync_finalize_store(monkeypatch, pc, conv)
    store['doc'] = {
        'data_protection_level': 'standard',
        'transcript_segments': [_t1_segment_dict()],
        'structured': {'title': _SEGMENT_TEXT, 'overview': ''},
    }
    store['bind_on_admit'] = True
    reread_calls: list[int] = []

    def boom(_uid: str, _cid: str, **_kwargs: Any) -> dict[str, Any]:
        reread_calls.append(1)
        raise RuntimeError('post-admission reread failed')

    monkeypatch.setattr(conv.conversations_db, 'get_conversation', boom)
    conversation = _in_progress()
    _prepare_finalize(monkeypatch, conv, conversation)
    request = conv.ProcessConversationRequest.model_validate(
        {'client_processing': _projection().model_dump(mode='json')}
    )

    response = conv.process_in_progress_conversation(request=request, uid=_UID)

    assert reread_calls == []
    assert store['admits'][-1]['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert response.conversation.structured.title == _SEGMENT_TEXT
    _assert_no_managed(spies)


# red-proof: wrap the post-commit get_conversation in try/except (calls would be 1)
def test_durable_winner_does_not_reread_after_outbox_commit(monkeypatch, stack) -> None:
    pc, conv = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    conversation = _in_progress()
    captured = _prepare_durable_finalize(monkeypatch, conv, conversation)
    captured['bind_on_commit'] = True
    captured['doc'].update(_t1_snapshot(status=ConversationStatus.in_progress.value))
    reread_calls: list[int] = []

    def boom(_uid: str, _cid: str, **_kwargs: Any) -> dict[str, Any]:
        reread_calls.append(1)
        raise RuntimeError('post-commit reread failed')

    monkeypatch.setattr(conv.conversations_db, 'get_conversation', boom)
    request = conv.ProcessConversationRequest.model_validate(
        {'client_processing': _projection().model_dump(mode='json')}
    )

    response = conv.finalize_conversation(_CONV_ID, request=request, uid=_UID)

    assert reread_calls == []
    extra = _durable_extra_updates(captured)
    assert extra is not None
    assert extra['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert response.conversation.client_processing is not None
    assert response.conversation.client_processing.structure.title == PROJECTION_TITLE
    assert response.conversation.status == ConversationStatus.processing
    _assert_no_managed(spies)

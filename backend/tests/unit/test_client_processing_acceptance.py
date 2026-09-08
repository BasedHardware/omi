"""S4 Worker B: from-segments hash acceptance and projection storage.

Named proofs: (a) matching projection on basic ⇒ zero managed LLM calls, stored
as display-only ``client_processing`` with deterministic-minimum ``structured``;
(c) hash mismatch ⇒ projection dropped, one content-free warning, deterministic
minimum, still no managed call.

Isolation: stub_modules + load_module_fresh (same pattern as
test_process_conversation_free_tier_branch). ``utils.cloud_tasks`` is stubbed so
protobufs do not double-register.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from config.plan_catalog import PlanType
from models.client_processing import (
    CLIENT_PROCESSING_SCHEMA_VERSION,
    ClientProcessing,
    ProjectedActionItem,
    ProjectedStructure,
    ProjectionProvenance,
)
from models.conversation import Conversation, CreateConversation
from models.conversation_enums import ConversationProcessingState, ConversationSource, ConversationStatus
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations.projection_payload import PROVENANCE_LOG_MAX_CHARS
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from utils.conversations.transcript_hash import transcript_sha256
import utils.managed_compute as managed_compute
from utils.managed_compute import Decision

_BACKEND = Path(__file__).resolve().parents[2]
_UID = 's4-acceptance-uid'
_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
_SEGMENT_TEXT = 'Hello from the desktop capture'
# Unique token that must never appear in the hash-mismatch warning.
CANARY = 'UNIQUE_PROJECTION_CANARY_xyzzy_not_in_logs'
PROJECTION_TITLE = 'Local on-device summary'
PROJECTION_TITLE_A = 'Stale in-memory projection A'
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
    # Same class of leak: real observability modules register Prometheus
    # collectors at import. Stub them so a later file can load the real
    # process_conversation without Duplicate timeseries.
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

    return fakes


def _add_developer_fakes(fakes: dict[str, ModuleType]) -> None:
    """Extra stubs so routers.developer can load without Firebase / Typesense."""

    def add(name: str, mod: ModuleType) -> ModuleType:
        fakes[name] = mod
        return mod

    add('dependencies', AutoMockModule('dependencies'))
    add('utils.other.endpoints', AutoMockModule('utils.other.endpoints'))
    search = add('utils.conversations.search', AutoMockModule('utils.conversations.search'))
    search.ConversationSearchUnavailableError = type('ConversationSearchUnavailableError', (Exception,), {})
    add('utils.conversations.mcp_transcript_search', AutoMockModule('utils.conversations.mcp_transcript_search'))
    add('utils.conversations.meeting_receipt', AutoMockModule('utils.conversations.meeting_receipt'))
    add('utils.conversations.render', AutoMockModule('utils.conversations.render'))
    add('utils.conversations.location', AutoMockModule('utils.conversations.location'))
    add('utils.memory.product_authorization', AutoMockModule('utils.memory.product_authorization'))


@pytest.fixture(scope='module')
def stack():
    fakes = _build_fakes()
    _add_developer_fakes(fakes)
    with stub_modules(fakes):
        pc = load_module_fresh(
            'utils.conversations.process_conversation',
            os.path.join(str(_BACKEND), 'utils', 'conversations', 'process_conversation.py'),
        )
        dev = load_module_fresh(
            'routers.developer',
            os.path.join(str(_BACKEND), 'routers', 'developer.py'),
        )
        dev.resolve_geolocation = lambda g: g
        dev.record_and_persist_finalized_meeting_receipt = lambda *_args, **_kwargs: None
        yield pc, dev


def _segment() -> TranscriptSegment:
    return TranscriptSegment(text=_SEGMENT_TEXT, speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0)


def _desktop_create() -> CreateConversation:
    return CreateConversation(
        started_at=_NOW,
        finished_at=_NOW + timedelta(minutes=5),
        transcript_segments=[_segment()],
        source=ConversationSource.desktop,
        language='en',
    )


def _digest() -> str:
    return transcript_sha256([_segment()])


def _projection(digest: str | None = None, *, title: str = PROJECTION_TITLE) -> ClientProcessing:
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


def _enable_flag(monkeypatch, pc) -> None:
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: True)


def _authorize(monkeypatch, pc, decision: Decision) -> None:
    monkeypatch.setattr(managed_compute, 'authorize_managed_compute', lambda *_args, **_kwargs: decision)
    monkeypatch.setattr(managed_compute, 'request_carries_validated_byok_key', lambda _feature: False)


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


def _from_segments_request(dev: Any, projection: Any, **overrides: Any) -> Any:
    payload: dict[str, Any] = dict(
        transcript_segments=[
            dev.DevTranscriptSegment(text=_SEGMENT_TEXT, speaker='SPEAKER_00', is_user=True, start=0.0, end=1.0)
        ],
        client_processing=projection,
        source=ConversationSource.desktop,
        started_at=_NOW,
        finished_at=_NOW + timedelta(seconds=2),
        language='en',
    )
    payload.update(overrides)
    return dev.CreateConversationFromTranscriptRequest(**payload)


def _from_segments_raw_payload(client_processing: Any, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'transcript_segments': [
            {'text': _SEGMENT_TEXT, 'speaker': 'SPEAKER_00', 'is_user': True, 'start': 0.0, 'end': 1.0}
        ],
        'client_processing': client_processing,
        'source': 'desktop',
        'started_at': _NOW,
        'finished_at': _NOW + timedelta(seconds=2),
        'language': 'en',
    }
    payload.update(overrides)
    return payload


def _projection_dict(digest: str | None = None, *, title: str = PROJECTION_TITLE) -> dict[str, Any]:
    return _projection(digest, title=title).model_dump(mode='json')


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _stored_minimum(conversation_id: str) -> dict[str, Any]:
    return {
        'id': conversation_id,
        'status': 'completed',
        'discarded': False,
        'transcript_segments': [
            {'text': _SEGMENT_TEXT, 'speaker': 'SPEAKER_00', 'is_user': True, 'start': 0.0, 'end': 1.0}
        ],
        'structured': {'title': _SEGMENT_TEXT, 'overview': '', 'emoji': '🧠', 'category': 'other'},
        'client_processing': None,
    }


def _conversation(*, projection: ClientProcessing | None = None) -> Conversation:
    return Conversation(
        id='persist-conv',
        created_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW + timedelta(seconds=2),
        source=ConversationSource.desktop,
        language='en',
        structured=Structured(title=_SEGMENT_TEXT, overview=''),
        transcript_segments=[_segment()],
        status=ConversationStatus.completed,
        client_processing=projection,
    )


def _firestore_merge(store: dict[str, Any], payload: dict[str, Any]) -> None:
    """Simulate Firestore ``set(..., merge=True)``: explicit nulls overwrite."""
    existing = store.get('doc')
    if existing is None:
        store['doc'] = copy.deepcopy(payload)
        return
    merged = dict(existing)
    merged.update(copy.deepcopy(payload))
    store['doc'] = merged


def _capture_has_projection(monkeypatch, pc) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    real = pc.resolve_free_tier_processing_plan

    def wrap(**kwargs: Any):
        captured.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(pc, 'resolve_free_tier_processing_plan', wrap)
    return captured


# red-proof: `has_projection=False` in the S6 plan call (basic matching projection would skip store_projection and not persist client_processing)
def test_basic_matching_projection_persists_display_skips_managed(monkeypatch, stack) -> None:
    pc, _dev = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    captured = _capture_has_projection(monkeypatch, pc)
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()

    projection = _projection()
    result = pc.process_conversation(_UID, 'en', _desktop_create(), client_projection=projection)

    assert captured.get('has_projection') is True
    assert result.deferred is False
    assert result.status == ConversationStatus.completed
    assert result.client_processing is projection
    assert result.structured.title == _SEGMENT_TEXT
    assert result.structured.overview == ''
    assert result.structured.title != PROJECTION_TITLE
    payload = _persisted_payload(created)
    assert _nested(payload, 'client_processing', 'structure', 'title') == PROJECTION_TITLE
    assert _nested(payload, 'client_processing', 'structure', 'overview') == CANARY
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT
    assert _nested(payload, 'structured', 'overview') == ''
    _assert_no_managed(spies)
    spies['should_defer'].assert_not_called()


# red-proof: skip the hash compare (`if False and expected != ...`) so a mismatch is stored and no warning fires
def test_hash_mismatch_rejects_projection_stores_minimum_no_managed(monkeypatch, stack, caplog) -> None:
    pc, dev = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    captured = _capture_has_projection(monkeypatch, pc)
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()
    mismatched = _projection(_MISMATCH_HASH)

    with caplog.at_level(logging.WARNING, logger=dev.__name__):
        dev._create_conversation_from_segments(_UID, _from_segments_request(dev, mismatched))

    assert captured.get('has_projection') is False
    payload = _persisted_payload(created)
    assert payload.get('client_processing') is None
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT
    assert _nested(payload, 'structured', 'overview') == ''
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


# red-proof: re-add client_processing to `_normal_persist_payload` (generic persist would overwrite a newer ingest write)
def test_paid_plan_generic_persist_omits_projection_keeps_it_in_memory(monkeypatch, stack) -> None:
    pc, _dev = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _paid_decision())
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()
    projection = _projection()

    result = pc.process_conversation(_UID, 'en', _desktop_create(), client_projection=projection)

    spies['get_structured'].assert_called_once()
    assert result.client_processing is projection
    payload = _persisted_payload(created)
    assert 'client_processing' not in payload
    assert _nested(payload, 'structured', 'title') == 'llm-title'


# red-proof: re-add client_processing to the deferred persist (generic persist would overwrite a newer ingest write)
# Rule change: deferred is a generic processor persist, not the projection's owner.
# In-memory attach still happens; the field is written only by ingest mutation.
def test_flag_off_deferred_persist_omits_projection_keeps_it_in_memory(monkeypatch, stack) -> None:
    pc, _dev = stack
    monkeypatch.setattr(pc, 'free_tier_local_processing_enabled', lambda: False)
    spies = _spy_managed_effects(monkeypatch, pc)
    resolve = MagicMock(side_effect=AssertionError('policy must not run when flag is off'))
    monkeypatch.setattr(pc, 'resolve_free_tier_processing_plan', resolve)
    processing = pc.lifecycle_service.create_processing_conversation
    processing.reset_mock()
    projection = _projection()

    result = pc.process_conversation(_UID, 'en', _desktop_create(), client_projection=projection)

    assert result.deferred is True
    assert result.status == ConversationStatus.processing
    assert result.client_processing is projection
    spies['should_defer'].assert_called_once_with(_UID)
    resolve.assert_not_called()
    _assert_no_managed(spies)
    payload = _persisted_payload(processing)
    assert 'client_processing' not in payload


# red-proof: pass `client_projection=request.client_processing` without the hash check (mismatch would still reach the coordinator)
def test_handler_passes_client_projection_only_when_hash_matched(monkeypatch, stack) -> None:
    _pc, dev = stack
    captured: list[ClientProcessing | None] = []

    def fake_process(uid, language, conversation, *args, **kwargs):
        captured.append(kwargs.get('client_projection'))
        return Conversation(
            id='handler-conv',
            created_at=_NOW,
            started_at=conversation.started_at,
            finished_at=conversation.finished_at,
            source=conversation.source,
            language=conversation.language,
            structured=Structured(title='ok'),
            transcript_segments=conversation.transcript_segments,
            status=ConversationStatus.completed,
        )

    monkeypatch.setattr(dev, 'process_conversation', fake_process)

    matched = _projection()
    dev._create_conversation_from_segments(_UID, _from_segments_request(dev, matched))
    mismatched = _projection(_MISMATCH_HASH)
    dev._create_conversation_from_segments(_UID, _from_segments_request(dev, mismatched))

    assert captured == [matched, None]


def _malformed_projection_cases() -> list[Any]:
    dumped = _projection_dict()
    missing_provenance = dict(dumped)
    del missing_provenance['provenance']
    return [
        pytest.param({**dumped, 'unexpected_field': 'nope'}, id='unknown_field'),
        pytest.param(CANARY, id='string'),
        pytest.param([CANARY], id='list'),
        pytest.param(missing_provenance, id='missing_provenance'),
    ]


# red-proof: nest ClientProcessing on CreateConversationFromTranscriptRequest so model_validate 422s
@pytest.mark.parametrize('raw_projection', _malformed_projection_cases())
def test_malformed_projection_stores_conversation_without_projection(
    monkeypatch, stack, caplog, raw_projection: Any
) -> None:
    pc, dev = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()

    request = dev.CreateConversationFromTranscriptRequest.model_validate(_from_segments_raw_payload(raw_projection))

    with caplog.at_level(logging.WARNING, logger=dev.__name__):
        response = dev._create_conversation_from_segments(_UID, request)

    assert response.status == 'completed'
    created.assert_called()
    payload = _persisted_payload(created)
    assert payload.get('client_processing') is None
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT
    warnings = [record for record in caplog.records if 'schema_invalid' in record.getMessage()]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert CANARY not in message
    assert PROJECTION_TITLE not in message
    assert _SEGMENT_TEXT not in message
    _assert_no_managed(spies)


# red-proof: return existing conversation on idempotency hit before examining the new projection
def test_idempotent_retry_binds_late_projection_without_rewriting_structured(monkeypatch, stack) -> None:
    pc, dev = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())

    session = 'late-proj-session'
    conv_id = dev._from_segments_conversation_id(_UID, session)
    stored: dict[str, Any] = {'doc': None}

    def fake_get(_uid: str, _cid: str, **_kwargs: Any) -> Any:
        return stored['doc']

    def fake_persist(_uid: str, payload: dict[str, Any], **_kwargs: Any) -> bool:
        stored['doc'] = copy.deepcopy(payload)
        return True

    def fake_bind(_uid: str, _cid: str, mutation: dict[str, Any], **_kwargs: Any) -> bool:
        stored['doc'] = {**stored['doc'], **mutation}
        stored['update'] = dict(mutation)
        return True

    monkeypatch.setattr(dev.conversations_db, 'get_conversation', fake_get)
    monkeypatch.setattr(dev.conversations_db, 'bind_client_processing', fake_bind)
    monkeypatch.setattr(dev.conversations_db, 'update_conversation', fake_bind)
    monkeypatch.setattr(dev.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(dev.lifecycle_service, 'persist_processed_conversation', fake_persist)

    process_calls: list[int] = []
    orig_process = dev.process_conversation

    def wrapped(*args: Any, **kwargs: Any):
        process_calls.append(1)
        return orig_process(*args, **kwargs)

    monkeypatch.setattr(dev, 'process_conversation', wrapped)

    first = _from_segments_request(dev, None, client_session_id=session)
    response1 = dev._create_conversation_from_segments(_UID, first)
    assert response1.id == conv_id
    assert stored['doc'] is not None
    assert stored['doc'].get('client_processing') is None
    structured_before = copy.deepcopy(stored['doc']['structured'])
    assert len(process_calls) == 1

    retry = dev.CreateConversationFromTranscriptRequest.model_validate(
        _from_segments_raw_payload(_projection_dict(), client_session_id=session)
    )
    response2 = dev._create_conversation_from_segments(_UID, retry)

    assert response2.id == conv_id
    assert len(process_calls) == 1
    assert _canonical(stored['doc']['structured']) == _canonical(structured_before)
    assert stored['update'].keys() == {'client_processing'}
    assert 'structured' not in stored['update']
    assert stored['doc']['client_processing']['structure']['title'] == PROJECTION_TITLE
    spies['get_structured'].assert_not_called()


# red-proof: bind the late projection without checking the stored transcript digest
def test_idempotent_retry_mismatched_digest_leaves_conversation_unchanged(monkeypatch, stack, caplog) -> None:
    _pc, dev = stack
    session = 'late-proj-mismatch'
    conv_id = dev._from_segments_conversation_id(_UID, session)
    existing = _stored_minimum(conv_id)
    snapshot = copy.deepcopy(existing)
    update = MagicMock()
    bind = MagicMock()
    process = MagicMock()
    monkeypatch.setattr(dev.conversations_db, 'get_conversation', MagicMock(return_value=existing))
    monkeypatch.setattr(dev.conversations_db, 'update_conversation', update)
    monkeypatch.setattr(dev.conversations_db, 'bind_client_processing', bind)
    monkeypatch.setattr(dev, 'process_conversation', process)

    retry = dev.CreateConversationFromTranscriptRequest.model_validate(
        _from_segments_raw_payload(_projection_dict(_MISMATCH_HASH), client_session_id=session)
    )
    with caplog.at_level(logging.WARNING, logger=dev.__name__):
        response = dev._create_conversation_from_segments(_UID, retry)

    assert response.id == conv_id
    process.assert_not_called()
    update.assert_not_called()
    bind.assert_not_called()
    assert existing == snapshot
    warnings = [record for record in caplog.records if 'hash_mismatch' in record.getMessage()]
    assert len(warnings) == 1
    assert CANARY not in warnings[0].getMessage()


# red-proof: nest ClientProcessing on the request so a malformed retry 422s instead of returning the stored conversation
def test_idempotent_retry_malformed_projection_leaves_conversation_unchanged(monkeypatch, stack, caplog) -> None:
    _pc, dev = stack
    session = 'late-proj-malformed'
    conv_id = dev._from_segments_conversation_id(_UID, session)
    existing = _stored_minimum(conv_id)
    snapshot = copy.deepcopy(existing)
    update = MagicMock()
    bind = MagicMock()
    process = MagicMock()
    monkeypatch.setattr(dev.conversations_db, 'get_conversation', MagicMock(return_value=existing))
    monkeypatch.setattr(dev.conversations_db, 'update_conversation', update)
    monkeypatch.setattr(dev.conversations_db, 'bind_client_processing', bind)
    monkeypatch.setattr(dev, 'process_conversation', process)

    malformed = {**_projection_dict(), 'unexpected_field': 'nope'}
    retry = dev.CreateConversationFromTranscriptRequest.model_validate(
        _from_segments_raw_payload(malformed, client_session_id=session)
    )
    with caplog.at_level(logging.WARNING, logger=dev.__name__):
        response = dev._create_conversation_from_segments(_UID, retry)

    assert response.id == conv_id
    process.assert_not_called()
    update.assert_not_called()
    bind.assert_not_called()
    assert existing == snapshot
    warnings = [record for record in caplog.records if 'schema_invalid' in record.getMessage()]
    assert len(warnings) == 1
    assert CANARY not in warnings[0].getMessage()


# red-proof: skip `strip_client_processing` (leave `client_processing: None` in the persist dict)
def test_persist_without_projection_omits_client_processing_key(stack) -> None:
    pc, _dev = stack
    conv = _conversation()
    terminal = pc._terminal_persist_payload(conv)
    normal = pc._normal_persist_payload(conv, clear_terminal_marker=False)
    cleared = pc._normal_persist_payload(conv, clear_terminal_marker=True)
    assert 'client_processing' not in terminal
    assert 'client_processing' not in normal
    assert 'client_processing' not in cleared
    omitted = pc.strip_client_processing({'client_processing': None, 'structured': {'title': 't'}})
    assert 'client_processing' not in omitted
    assert omitted['structured'] == {'title': 't'}


# red-proof: keep a present client_processing key in `_terminal_persist_payload` / `_normal_persist_payload`
def test_generic_persist_strips_even_when_in_memory_projection_is_present(stack) -> None:
    pc, _dev = stack
    conv = _conversation(projection=_projection())
    terminal = pc._terminal_persist_payload(conv)
    normal = pc._normal_persist_payload(conv, clear_terminal_marker=False)
    assert 'client_processing' not in terminal
    assert 'client_processing' not in normal
    stripped = pc.strip_client_processing(
        {'client_processing': {'structure': {'title': PROJECTION_TITLE}}, 'structured': {'title': 't'}}
    )
    assert 'client_processing' not in stripped
    assert stripped['structured'] == {'title': 't'}
    owned = pc.client_processing_mutation(_projection())
    assert owned.keys() == {'client_processing'}
    assert owned['client_processing']['structure']['title'] == PROJECTION_TITLE


def _projection_plan(pc) -> Any:
    return pc.FreeTierProcessingPlan(
        mode='store_projection',
        reason='basic_has_projection',
        decision=_basic_decision(),
    )


def _minimum_plan(pc) -> Any:
    return pc.FreeTierProcessingPlan(
        mode='deterministic_minimum',
        reason='basic_no_projection',
        decision=_basic_decision(),
    )


# red-proof: skip `payload.update(client_processing_mutation(client_projection))` on the ingress-create branch
def test_store_projected_conversation_persists_owned_projection(stack) -> None:
    pc, _dev = stack
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()
    projection = _projection()
    stored, persisted = pc._store_projected_conversation(
        _UID, _desktop_create(), _projection_plan(pc), client_projection=projection
    )
    assert persisted is True
    assert stored.client_processing is projection
    payload = _persisted_payload(created)
    assert _nested(payload, 'client_processing', 'structure', 'title') == PROJECTION_TITLE
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT
    assert _nested(payload, 'structured', 'overview') == ''


# red-proof: `payload.update(client_processing_mutation(client_projection))` without `_is_ingress_create`
# Rule change: an existing-conversation processor persist always omits the field.
# Ingress is the sole writer; `_store_projected_conversation` is a writer only when
# this persist is the document create.
def test_processor_projected_store_on_existing_conversation_omits_field(stack) -> None:
    pc, _dev = stack
    persisted = pc.lifecycle_service.persist_processed_conversation
    persisted.reset_mock()
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()
    projection = _projection()
    stored, ok = pc._store_projected_conversation(
        _UID, _conversation(), _projection_plan(pc), client_projection=projection
    )
    assert ok is True
    assert stored.client_processing is projection
    created.assert_not_called()
    payload = _persisted_payload(persisted)
    assert 'client_processing' not in payload
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT
    assert _nested(payload, 'structured', 'overview') == ''


# red-proof: `payload.update(client_processing_mutation(_projection()))` on the no-projection minimum persist
def test_store_deterministic_minimum_without_projection_omits_field(stack) -> None:
    pc, _dev = stack
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()
    stored, persisted = pc._store_deterministic_minimum(_UID, _desktop_create(), _minimum_plan(pc))
    assert persisted is True
    assert stored.client_processing is None
    payload = _persisted_payload(created)
    assert 'client_processing' not in payload
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT


# --- S3: §1.7 processing_state on the terminal persist ------------------------


# red-proof: drop `conversation.processing_state = _minimum_processing_state(...)`
def test_desktop_minimum_without_projection_is_local_pending(stack) -> None:
    """A capable client is expected to deliver, so the client spins with a
    timeout rather than showing a permanent empty state (§1.7 row 5)."""
    pc, _dev = stack
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()
    stored, persisted = pc._store_deterministic_minimum(_UID, _desktop_create(), _minimum_plan(pc))
    assert persisted is True
    assert stored.processing_state is ConversationProcessingState.local_pending
    assert _persisted_payload(created)['processing_state'] == 'local_pending'


# red-proof: return `local_pending` unconditionally from `_minimum_processing_state`
def test_non_desktop_minimum_is_none_because_no_projection_is_coming(stack) -> None:
    pc, _dev = stack
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()
    create = _desktop_create()
    create.source = ConversationSource.omi
    stored, persisted = pc._store_deterministic_minimum(_UID, create, _minimum_plan(pc))
    assert persisted is True
    assert stored.processing_state is ConversationProcessingState.none
    assert _persisted_payload(created)['processing_state'] == 'none'


# red-proof: set a processing_state when a projection is already in hand
def test_projected_conversation_carries_no_processing_state(stack) -> None:
    """Nothing is pending: the projection IS the summary.

    The field is absent from the persist payload, not an explicit null —
    persist is merge=True, and a dumped null is a real Firestore key that
    stamps every projected conversation (flip-review F-1).
    """
    pc, _dev = stack
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()
    stored, persisted = pc._store_projected_conversation(
        _UID, _desktop_create(), _projection_plan(pc), client_projection=_projection()
    )
    assert persisted is True
    assert stored.processing_state is None
    assert 'processing_state' not in _persisted_payload(created)


# red-proof: revert `_store_deterministic_minimum` to `_build_deferred_structured`
def test_minimum_structured_is_the_spec_row_not_the_deferred_placeholder(stack) -> None:
    """§1.7: first *sentence*, empty overview, category `other`. The deferred
    placeholder's first-8-words title is a different algorithm on a different
    path and must not leak into the terminal store."""
    pc, _dev = stack
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()
    create = _desktop_create()
    create.transcript_segments = [
        TranscriptSegment(
            text='One two three four five six seven eight nine ten. Second sentence.',
            speaker='SPEAKER_00',
            is_user=False,
            start=0.0,
            end=4.0,
        )
    ]
    pc._store_deterministic_minimum(_UID, create, _minimum_plan(pc))
    payload = _persisted_payload(created)
    assert _nested(payload, 'structured', 'title') == 'One two three four five six seven eight nine ten.'
    assert _nested(payload, 'structured', 'overview') == ''
    assert _nested(payload, 'structured', 'category') == 'other'
    assert _nested(payload, 'structured', 'action_items') == []
    assert _nested(payload, 'structured', 'events') == []


# red-proof: skip the after-process `client_processing_mutation` on non-idempotent ingest (paid persist strips and never stores)
def test_from_segments_ingest_stores_projection_via_dedicated_mutation(monkeypatch, stack) -> None:
    pc, dev = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _paid_decision())
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()
    updates: list[dict[str, Any]] = []

    def fake_bind(_uid: str, _cid: str, mutation: dict[str, Any], **_kwargs: Any) -> bool:
        updates.append(dict(mutation))
        return True

    monkeypatch.setattr(dev.conversations_db, 'bind_client_processing', fake_bind)
    monkeypatch.setattr(dev.conversations_db, 'update_conversation', fake_bind)
    projection = _projection()
    response = dev._create_conversation_from_segments(_UID, _from_segments_request(dev, projection))

    assert response.status == 'completed'
    payload = _persisted_payload(created)
    assert 'client_processing' not in payload
    assert _nested(payload, 'structured', 'title') == 'llm-title'
    assert len(updates) == 1
    assert updates[0].keys() == {'client_processing'}
    assert updates[0]['client_processing']['structure']['title'] == PROJECTION_TITLE
    spies['get_structured'].assert_called_once()


def _race_store_harness(monkeypatch, stack, *, first_projection: Any, retry_title: str) -> dict[str, Any]:
    pc, dev = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    session = 'race-late-projection'
    conv_id = dev._from_segments_conversation_id(_UID, session)
    store: dict[str, Any] = {'spies': spies, 'conv_id': conv_id}

    def fake_get(_uid: str, _cid: str, **_kwargs: Any) -> Any:
        return store.get('doc')

    def fake_create(_uid: str, payload: dict[str, Any], **_kwargs: Any) -> bool:
        _firestore_merge(store, payload)
        if store.get('b_ran'):
            return True
        store['b_ran'] = True
        retry = dev.CreateConversationFromTranscriptRequest.model_validate(
            _from_segments_raw_payload(_projection_dict(title=retry_title), client_session_id=session)
        )
        store['b_response'] = dev._create_conversation_from_segments(_UID, retry)
        return True

    def fake_persist(_uid: str, payload: dict[str, Any], **_kwargs: Any) -> bool:
        _firestore_merge(store, payload)
        return True

    def fake_bind(_uid: str, _cid: str, mutation: dict[str, Any], **_kwargs: Any) -> bool:
        _firestore_merge(store, mutation)
        store['update'] = dict(mutation)
        return True

    monkeypatch.setattr(dev.conversations_db, 'get_conversation', fake_get)
    monkeypatch.setattr(dev.conversations_db, 'bind_client_processing', fake_bind)
    monkeypatch.setattr(dev.conversations_db, 'update_conversation', fake_bind)
    monkeypatch.setattr(dev.lifecycle_service, 'create_processing_conversation', fake_create)
    monkeypatch.setattr(dev.lifecycle_service, 'persist_processed_conversation', fake_persist)
    monkeypatch.setattr(dev.lifecycle_service, 'create_completed_conversation', fake_persist)
    store['first'] = _from_segments_request(dev, first_projection, client_session_id=session)
    return store


# red-proof: skip `strip_client_processing` on A's persist (merge writes explicit null and erases B)
def test_late_projection_survives_older_processor_persist(monkeypatch, stack) -> None:
    pc, dev = stack
    _authorize(monkeypatch, pc, _basic_decision())
    store = _race_store_harness(monkeypatch, stack, first_projection=None, retry_title=PROJECTION_TITLE)

    response_a = dev._create_conversation_from_segments(_UID, store['first'])

    assert response_a.id == store['conv_id']
    assert store.get('b_ran') is True
    assert store['b_response'].id == store['conv_id']
    assert store['update'].keys() == {'client_processing'}
    assert store['doc']['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert _nested(store['doc'], 'structured', 'title') == _SEGMENT_TEXT
    store['spies']['get_structured'].assert_not_called()


# red-proof: re-add client_processing to `_normal_persist_payload` (A's stale in-memory A would overwrite B)
def test_stale_in_memory_projection_does_not_overwrite_later_ingest_write(monkeypatch, stack) -> None:
    pc, dev = stack
    _authorize(monkeypatch, pc, _paid_decision())
    store = _race_store_harness(
        monkeypatch, stack, first_projection=_projection(title=PROJECTION_TITLE_A), retry_title=PROJECTION_TITLE
    )

    response_a = dev._create_conversation_from_segments(_UID, store['first'])

    assert response_a.id == store['conv_id']
    assert store.get('b_ran') is True
    assert store['b_response'].id == store['conv_id']
    assert store['update'].keys() == {'client_processing'}
    assert store['doc']['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert store['doc']['client_processing']['structure']['title'] != PROJECTION_TITLE_A
    store['spies']['get_structured'].assert_called()


# red-proof: stamp client_processing on the existing-conversation processor persist
# (A's terminal `_store_projected_conversation` would resurrect stale A over B)
def test_basic_stale_projection_does_not_overwrite_later_ingest_write(monkeypatch, stack) -> None:
    pc, dev = stack
    _authorize(monkeypatch, pc, _basic_decision())
    store = _race_store_harness(
        monkeypatch, stack, first_projection=_projection(title=PROJECTION_TITLE_A), retry_title=PROJECTION_TITLE
    )

    response_a = dev._create_conversation_from_segments(_UID, store['first'])

    assert response_a.id == store['conv_id']
    assert store.get('b_ran') is True
    assert store['b_response'].id == store['conv_id']
    assert store['update'].keys() == {'client_processing'}
    assert store['doc']['client_processing']['structure']['title'] == PROJECTION_TITLE
    assert store['doc']['client_processing']['structure']['title'] != PROJECTION_TITLE_A
    assert _nested(store['doc'], 'structured', 'title') == _SEGMENT_TEXT
    store['spies']['get_structured'].assert_not_called()


# red-proof: log raw model_id/runtime/device_class without sanitize_untrusted_provenance_field
def test_rejected_payload_provenance_is_sanitized_single_line(monkeypatch, stack, caplog) -> None:
    pc, dev = stack
    _enable_flag(monkeypatch, pc)
    spies = _spy_managed_effects(monkeypatch, pc)
    _authorize(monkeypatch, pc, _basic_decision())
    created = pc.lifecycle_service.create_completed_conversation
    created.reset_mock()

    injected = 'ERROR forged-log-entry uid=admin action=wipe'
    oversize = 'W' * 5000
    poisoned = {
        **_projection_dict(),
        'unexpected_field': 'nope',
        'provenance': {
            **_projection_dict()['provenance'],
            'model_id': f'ok-model\n{injected}',
            'runtime': 'mlx\x00hidden',
            'device_class': oversize,
        },
    }
    request = dev.CreateConversationFromTranscriptRequest.model_validate(_from_segments_raw_payload(poisoned))

    with caplog.at_level(logging.WARNING, logger=dev.__name__):
        response = dev._create_conversation_from_segments(_UID, request)

    assert response.status == 'completed'
    created.assert_called()
    payload = _persisted_payload(created)
    assert payload.get('client_processing') is None
    assert _nested(payload, 'structured', 'title') == _SEGMENT_TEXT
    reject_records = [record for record in caplog.records if 'client_processing rejected' in record.getMessage()]
    assert len(reject_records) == 1
    message = reject_records[0].getMessage()
    assert '\n' not in message
    assert '\r' not in message
    assert injected not in message
    assert injected not in caplog.text
    assert 'hidden' not in message
    assert oversize not in message
    assert CANARY not in message
    assert PROJECTION_TITLE not in message
    assert _SEGMENT_TEXT not in message
    assert '<invalid>' in message
    reason, model_id, runtime, device_class = reject_records[0].args
    assert reason == 'schema_invalid'
    assert model_id == '<invalid>'
    assert runtime == '<invalid>'
    assert device_class == oversize[:PROVENANCE_LOG_MAX_CHARS]
    assert len(device_class) == PROVENANCE_LOG_MAX_CHARS
    _assert_no_managed(spies)


def test_projection_payload_imports_while_the_models_package_is_stubbed() -> None:
    """Importing this module must survive a stubbed ``models`` package (#12779).

    ``utils.conversations.projection_payload`` is deliberately import-light — its own
    docstring says importing it must not drag in the coordinator's module graph. A
    module-scope ``from models.client_processing import ...`` broke that quietly: seven
    suites under ``tests/unit`` replace ``sys.modules['models']`` with a stub, and while
    one is installed, merely *collecting* any module that reaches this one fails with
    ``ModuleNotFoundError: No module named 'models.client_processing'``.

    That is how `main` went red for unrelated PRs: the failure lands during collection of
    a later, alphabetically-sorted suite, so it reads as a broken test file rather than as
    leaked global state. This drives the real mechanism — stub the package the way those
    suites do, then import through a fresh module object.
    """
    import sys
    import importlib
    from types import ModuleType

    saved = sys.modules.get('models')
    saved_module = sys.modules.pop('utils.conversations.projection_payload', None)
    # Also evict the submodule. Leaving it cached makes this test vacuous: a cached
    # models.client_processing satisfies the import without ever consulting the stub's
    # __path__, so the module-scope version passes too. In CI the submodule genuinely
    # has not been imported yet when the polluted collection happens.
    saved_submodule = sys.modules.pop('models.client_processing', None)
    try:
        # Exactly the shape the polluting suites install: a bare package whose empty
        # __path__ makes every models.* submodule unimportable.
        stub = ModuleType('models')
        stub.__path__ = []  # type: ignore[attr-defined]
        sys.modules['models'] = stub

        module = importlib.import_module('utils.conversations.projection_payload')
        assert module is not None
    finally:
        sys.modules.pop('utils.conversations.projection_payload', None)
        if saved is None:
            sys.modules.pop('models', None)
        else:
            sys.modules['models'] = saved
        if saved_submodule is not None:
            sys.modules['models.client_processing'] = saved_submodule
        if saved_module is not None:
            sys.modules['utils.conversations.projection_payload'] = saved_module

    # The deferred import still resolves once the stub is gone, so laziness bought
    # collection-time resilience without breaking the function itself.
    from utils.conversations.projection_payload import strip_client_processing

    payload = {'client_processing': {'x': 1}, 'keep': 'me'}
    assert strip_client_processing(payload) == {'keep': 'me'}

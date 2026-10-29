"""Operator minimal redrive: Parakeet-only STT, attach-first, one cheap title per new row."""

import inspect
import json
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from google.cloud import firestore

from database import conversations as conversations_db
from utils import byok
from models.transcript_segment import TranscriptSegment
from routers import sync as sync_router
from utils.llm import clients as llm_clients
from utils.stt.outcomes import TranscriptionFailure, sync_failure_from_exception
from utils.sync import minimal_redrive, pipeline

PARAKEET = ('parakeet', 'multi', 'parakeet')
BASE = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


# --- payload parsing and kill switch -------------------------------------------------


@pytest.mark.parametrize(
    'payload,expected',
    [
        ({'redrive_mode': 'minimal'}, 'minimal'),
        ({'redrive_mode': 'MINIMAL'}, None),
        ({'redrive_mode': 'full'}, None),
        ({'redrive_mode': True}, None),
        ({'redrive_mode': None}, None),
        ({}, None),
        ('minimal', None),
        (None, None),
    ],
)
def test_only_the_exact_minimal_value_selects_the_mode(payload, expected):
    assert minimal_redrive.parse_mode(payload) == expected


@pytest.mark.parametrize(
    'value,expected', [(None, True), ('true', True), ('false', False), ('0', False), ('off', False)]
)
def test_kill_switch_defaults_on(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('SYNC_MINIMAL_REDRIVE_ENABLED', raising=False)
    else:
        monkeypatch.setenv('SYNC_MINIMAL_REDRIVE_ENABLED', value)
    assert minimal_redrive.enabled() is expected


def _task_request(**extra):
    request = MagicMock()
    request.json = AsyncMock(
        return_value={'job_id': 'job-1', 'uid': 'uid-1', 'raw_blob_paths': ['raw/a.bin'], 'lane': 'backfill', **extra}
    )
    return request


@pytest.mark.asyncio
@pytest.mark.parametrize('sequenced', [False, True])
async def test_kill_switch_off_refuses_before_sequencer_lease_and_any_work(monkeypatch, sequenced):
    monkeypatch.setenv('SYNC_MINIMAL_REDRIVE_ENABLED', 'false')
    monkeypatch.setattr(
        sync_router.uid_sequencer,
        'production_fence_mode',
        Mock(return_value=sync_router.SyncLedgerFenceMode.ACTIVE),
    )
    monkeypatch.setattr(sync_router, 'warm_rollout_cohorts', AsyncMock())
    begin = Mock(return_value=True)
    monkeypatch.setattr(sync_router.sync_backfill_sequencer, 'begin_job', begin)
    body = AsyncMock()
    monkeypatch.setattr(sync_router, '_run_sync_job_body', body)
    extra = {'sequencer_epoch': 3} if sequenced else {}

    response = await sync_router.run_sync_job(_task_request(redrive_mode='minimal', **extra), task_retry_count=0)

    assert response.status_code == 409
    assert json.loads(response.body) == {'status': 'minimal_redrive_disabled'}
    begin.assert_not_called()  # No sequencer lease is taken or renewed.
    body.assert_not_awaited()  # No lock, download or provider call.


def test_redrive_mode_is_a_valid_optional_task_payload_key():
    from utils.cloud_tasks import SYNC_JOB_TASK_PAYLOAD_KEYS, sync_job_payload_keys_valid

    # Budget replacements and sequencer re-dispatch revalidate the stored payload.
    assert sync_job_payload_keys_valid(SYNC_JOB_TASK_PAYLOAD_KEYS | {'redrive_mode'})
    assert sync_job_payload_keys_valid(SYNC_JOB_TASK_PAYLOAD_KEYS | {'redrive_mode', 'sequencer_epoch'})


@pytest.mark.asyncio
async def test_kill_switch_never_refuses_a_normal_payload(monkeypatch):
    monkeypatch.setenv('SYNC_MINIMAL_REDRIVE_ENABLED', 'false')
    monkeypatch.setattr(
        sync_router, 'get_sync_ledger_fence_mode', Mock(return_value=sync_router.SyncLedgerFenceMode.ACTIVE)
    )
    monkeypatch.setattr(sync_router, 'get_sync_job', Mock(return_value=None))
    monkeypatch.setattr(sync_router, 'sync_job_uses_ledger_fence', Mock(return_value=False))
    monkeypatch.setattr(sync_router, 'try_acquire_job_run_lock', Mock(return_value=None))
    response = await sync_router._run_sync_job_attempt(_task_request(redrive_mode='full'), 0, {})
    # Reached the normal lock boundary (held elsewhere -> 409 locked), not the kill switch.
    assert json.loads(response.body) == {'status': 'locked'}
    sync_router.try_acquire_job_run_lock.assert_called_once()


# --- STT: Parakeet only ---------------------------------------------------------------


def test_parakeet_is_pinned_for_a_supported_language(monkeypatch):
    monkeypatch.setattr(minimal_redrive, 'provider_is_enabled', lambda *_: True)
    assert minimal_redrive.parakeet_service('multi') == PARAKEET
    assert minimal_redrive.parakeet_service('de-DE') == ('parakeet', 'de', 'parakeet')


@pytest.mark.parametrize('enabled,language', [(True, 'ja'), (False, 'multi')])
def test_unservable_language_fails_retryably_with_distinct_reason(monkeypatch, enabled, language):
    monkeypatch.setattr(minimal_redrive, 'provider_is_enabled', lambda *_: enabled)
    with pytest.raises(TranscriptionFailure) as raised:
        minimal_redrive.parakeet_service(language)
    # The task boundary maps the typed failure without losing the reason code.
    failure = sync_failure_from_exception(raised.value, provider='parakeet')
    assert failure.retryable is True
    assert failure.error_code == minimal_redrive.PROVIDER_UNAVAILABLE == 'sync_minimal_provider_unavailable'


def _segment_fixture(monkeypatch, stt_result):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('SYNC_EMPTY_MULTILINGUAL_RECOVERY_ENABLED', 'true')
    monkeypatch.setattr(minimal_redrive, 'provider_is_enabled', lambda *_: True)
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', lambda *_: False)
    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', Mock(return_value='url'))
    monkeypatch.setattr(pipeline, 'keyterms', AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline, 'get_prerecorded_service', Mock(return_value=('modulate', 'en', 'velma-2')))
    stt = Mock(return_value=stt_result)
    monkeypatch.setattr(pipeline, 'prerecorded', stt)
    modulate = Mock(side_effect=AssertionError('paid vendor called'))
    monkeypatch.setattr(pipeline, 'modulate_prerecorded_from_bytes', modulate)
    recover = Mock(return_value=None)
    monkeypatch.setattr(pipeline, '_recover_empty_segment', recover)
    silence = Mock()
    monkeypatch.setattr(pipeline, '_record_empty_segment_as_silence', silence)
    return stt, modulate, recover, silence


def _run_segment(**kwargs):
    response = {'new_memories': set(), 'updated_memories': set()}
    errors = []
    ok = pipeline.process_segment(f'{int(BASE.timestamp())}.wav', 'uid-1', response, threading.Lock(), errors, **kwargs)
    return ok, response, errors


def test_minimal_double_empty_pins_parakeet_and_records_silence_without_recovery(monkeypatch):
    stt, modulate, recover, silence = _segment_fixture(monkeypatch, ([], 'en'))
    ok, _, errors = _run_segment(redrive_mode='minimal')
    assert ok is False and errors == []
    assert stt.call_count == 2  # Bounded Parakeet confirmation retry only.
    assert all(call.kwargs['selected_service'] == PARAKEET for call in stt.call_args_list)
    pipeline.get_prerecorded_service.assert_not_called()
    recover.assert_not_called()
    modulate.assert_not_called()
    silence.assert_called_once()
    assert silence.call_args.kwargs['provider'] == 'parakeet'


def test_normal_double_empty_keeps_selection_and_paid_recovery(monkeypatch):
    stt, _, recover, silence = _segment_fixture(monkeypatch, ([], 'en'))
    ok, _, _ = _run_segment()
    assert ok is False
    pipeline.get_prerecorded_service.assert_called_once()
    # Ordinary unknown-language dispatch pins the provider selected after LID;
    # minimal mode's independent Parakeet pin remains separate above.
    assert all(call.kwargs['selected_service'] == ('modulate', 'multi', 'velma-2') for call in stt.call_args_list)
    recover.assert_called_once()
    silence.assert_called_once()


def test_minimal_unservable_language_never_dispatches(monkeypatch):
    stt, modulate, _, _ = _segment_fixture(monkeypatch, ([], 'ja'))
    # Re-raised past the segment boundary so the task handler retries the job.
    with pytest.raises(minimal_redrive.ProviderUnavailable):
        _run_segment(redrive_mode='minimal', transcription_prefs={'language': 'ja', 'single_language_mode': True})
    stt.assert_not_called()
    modulate.assert_not_called()


# --- attach first ---------------------------------------------------------------------


def _row(conversation_id, *, offset, device='dev-1', **extra):
    started = BASE + timedelta(seconds=offset)
    return {
        'id': conversation_id,
        'started_at': started,
        'finished_at': started + timedelta(seconds=60),
        'source': 'omi',
        'client_device_id': device,
        'is_locked': False,
        'status': 'completed',
        **extra,
    }


def _attach(monkeypatch, rows):
    fake_db = MagicMock()
    query = fake_db.collection.return_value.document.return_value.collection.return_value
    ordered = query.where.return_value.where.return_value.order_by.return_value
    ordered.stream.return_value = [Mock(to_dict=Mock(return_value=row)) for row in rows]
    monkeypatch.setattr(conversations_db, 'db', fake_db)
    # Exercise the real query builder and selector; skip only read decoration.
    monkeypatch.setattr(
        conversations_db,
        'get_closest_conversation_to_timestamps',
        inspect.unwrap(conversations_db.get_closest_conversation_to_timestamps),
    )
    start = int(BASE.timestamp())
    capture = {'source': 'omi', 'client_device_id': 'dev-1', 'is_locked': False}
    chosen = minimal_redrive.attach_target('uid-1', start, start + 30, capture)
    lower = query.where.call_args.kwargs['filter']
    return chosen, lower


def test_attaches_to_compatible_row_five_minutes_away(monkeypatch):
    chosen, lower = _attach(monkeypatch, [_row('near', offset=-360)])
    assert chosen == 'near'
    assert lower.value == BASE - timedelta(seconds=600)  # ±10 min only in minimal mode.


@pytest.mark.parametrize(
    'row',
    [
        _row('other-device', offset=-300, device='dev-2'),
        _row('locked', offset=-300, is_locked=True),
        _row('deleted', offset=-300, deleted=True),
        _row('merged', offset=-300, sync_merged_into='x'),
        _row('live', offset=-300, status='in_progress'),
    ],
)
def test_never_attaches_to_an_incompatible_or_deleted_row(monkeypatch, row):
    chosen, _ = _attach(monkeypatch, [row])
    assert chosen is None


def test_incompatible_closer_row_does_not_hide_compatible_one(monkeypatch):
    chosen, _ = _attach(monkeypatch, [_row('closer', offset=0, device='dev-2'), _row('near', offset=-300)])
    assert chosen == 'near'


def test_normal_candidate_query_keeps_two_minute_window(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(conversations_db, 'db', fake_db)
    query = fake_db.collection.return_value.document.return_value.collection.return_value
    query.where.return_value.where.return_value.order_by.return_value.stream.return_value = []
    inspect.unwrap(conversations_db.get_closest_conversation_to_timestamps)('uid-1', 1000, 1060)
    assert query.where.call_args.kwargs['filter'].value == datetime.fromtimestamp(1000 - 120, tz=timezone.utc)


def _assignment_fixture(monkeypatch, attach_id):
    _segment_fixture(monkeypatch, ([{'text': 'hello'}], 'en'))
    monkeypatch.setattr(
        pipeline,
        'postprocess_words',
        Mock(return_value=[TranscriptSegment(text='Hello there', start=0, end=5, is_user=False)]),
    )
    attach = Mock(return_value=attach_id)
    monkeypatch.setattr(minimal_redrive, 'attach_target', attach)
    closest = Mock(return_value=None)
    monkeypatch.setattr(pipeline, 'get_closest_conversation_to_timestamps', closest)
    monkeypatch.setattr(pipeline, 'identify_speakers_for_segments', Mock())
    monkeypatch.setattr(pipeline, 'sync_enabled_for', Mock(return_value=False))
    monkeypatch.setattr(pipeline.conversations_db, 'get_manual_speaker_receipt', Mock(return_value={}))
    from utils.conversations import lifecycle

    ingest = Mock(side_effect=RuntimeError('stop after assignment'))
    monkeypatch.setattr(lifecycle, 'ingest_sync_conversation', ingest)
    return attach, closest, ingest


def test_minimal_passes_attach_as_explicit_target_through_lifecycle(monkeypatch):
    attach, closest, ingest = _assignment_fixture(monkeypatch, 'near')
    _run_segment(redrive_mode='minimal', client_device_id='dev-1')
    attach.assert_called_once()
    assert attach.call_args.args[3] == {'source': 'omi', 'client_device_id': 'dev-1', 'is_locked': False}
    closest.assert_not_called()
    assert ingest.call_args.kwargs['target_id'] == 'near'


def test_minimal_without_attach_falls_back_to_normal_temporal_assignment(monkeypatch):
    _, closest, ingest = _assignment_fixture(monkeypatch, None)
    _run_segment(redrive_mode='minimal', client_device_id='dev-1')
    closest.assert_called_once()
    assert ingest.call_args.kwargs['target_id'] is None


def test_normal_path_never_consults_attach(monkeypatch):
    attach, closest, ingest = _assignment_fixture(monkeypatch, 'near')
    _run_segment(client_device_id='dev-1')
    attach.assert_not_called()
    closest.assert_called_once()
    assert ingest.call_args.kwargs['target_id'] is None


# --- minimal finalize -----------------------------------------------------------------


def _finalize_fixture(monkeypatch, rows, reply='{"title": "Lunch plans", "overview": "Agreed to meet at noon."}'):
    monkeypatch.setattr(minimal_redrive.conversations_db, 'get_conversation', lambda uid, cid: rows.get(cid))
    persist = Mock(return_value=True)
    monkeypatch.setattr(minimal_redrive.lifecycle_service, 'persist_processed_conversation', persist)
    llm = Mock()
    llm.invoke = Mock(side_effect=reply) if isinstance(reply, Exception) else Mock(return_value=Mock(content=reply))
    get_llm = Mock(return_value=llm)
    monkeypatch.setattr(llm_clients, 'get_llm', get_llm)
    return persist, llm, get_llm


def _stored(conversation_id, **extra):
    return {
        'id': conversation_id,
        'status': 'completed',
        'sync_relevance': 'keep',
        'sync_content_revision': 3,
        'data_protection_level': 'standard',
        'structured': {'title': 'Hello there', 'overview': '', 'title_provenance': 'server_minimum'},
        'transcript_segments': [{'text': 'Hello there'}],
        **extra,
    }


def test_new_row_gets_exactly_one_cheap_llm_call_and_lifecycle_persist(monkeypatch):
    persist, llm, get_llm = _finalize_fixture(monkeypatch, {'new': _stored('new')})
    response = {'new_memories': {'new'}, 'updated_memories': set(), '_merged': {'new': 'en'}}
    minimal_redrive.finalize('uid-1', response)
    get_llm.assert_called_once_with('sync_redrive_title', uid='uid-1')
    llm.invoke.assert_called_once()
    payload = persist.call_args.args[1]
    # Title and overview only: no memories, action items, apps, folders or other effects.
    assert payload == {
        'id': 'new',
        'status': 'completed',
        'structured': {
            'title': 'Lunch plans',
            'overview': 'Agreed to meet at noon.',
            'title_provenance': firestore.DELETE_FIELD,
        },
        'sync_content_revision': 3,
        'data_protection_level': 'standard',  # Stored level, never re-stamped.
    }
    assert '_merged' not in response


def test_updated_rows_get_zero_llm_calls_and_no_writes(monkeypatch):
    persist, llm, _ = _finalize_fixture(monkeypatch, {'old': _stored('old')})
    minimal_redrive.finalize('uid-1', {'new_memories': set(), 'updated_memories': {'old'}, '_merged': {'old': 'en'}})
    llm.invoke.assert_not_called()
    persist.assert_not_called()


@pytest.mark.parametrize(
    'row',
    [
        _stored('new', structured={'title': 'Done', 'overview': 'Already titled.'}),
        _stored('new', deleted=True),
        _stored('new', discarded=True, sync_relevance='review'),
        None,
    ],
)
def test_repeat_or_unavailable_new_row_creates_no_new_work(monkeypatch, row):
    persist, llm, _ = _finalize_fixture(monkeypatch, {'new': row})
    minimal_redrive.finalize('uid-1', {'new_memories': {'new'}, 'updated_memories': set()})
    llm.invoke.assert_not_called()
    persist.assert_not_called()


@pytest.mark.parametrize('reply', [RuntimeError('gateway down'), 'not json', '{"title": "", "overview": ""}'])
def test_llm_failure_keeps_deterministic_minimum_with_no_write(monkeypatch, reply):
    persist, llm, _ = _finalize_fixture(monkeypatch, {'new': _stored('new')}, reply=reply)
    minimal_redrive.finalize('uid-1', {'new_memories': {'new'}, 'updated_memories': set()})
    llm.invoke.assert_called_once()
    persist.assert_not_called()


def test_fenced_new_row_is_not_titled(monkeypatch):
    persist, llm, _ = _finalize_fixture(monkeypatch, {'new': _stored('new')})
    minimal_redrive.finalize(
        'uid-1', {'new_memories': {'new'}, 'updated_memories': set(), '_fenced_conversation_ids': {'new'}}
    )
    llm.invoke.assert_not_called()


def test_finalize_never_enters_full_post_processing(monkeypatch):
    reprocess = Mock(side_effect=AssertionError('full post-processing'))
    monkeypatch.setattr(pipeline, '_reprocess_conversation_after_update', reprocess)
    monkeypatch.setattr(pipeline, 'process_conversation', reprocess)
    _finalize_fixture(monkeypatch, {'new': _stored('new')})
    minimal_redrive.finalize('uid-1', {'new_memories': {'new'}, 'updated_memories': {'old'}, '_merged': {}})
    reprocess.assert_not_called()


# --- coordinator wiring ----------------------------------------------------------------


@pytest.fixture(scope='module')
def coordinator():
    from pathlib import Path

    from testing.import_isolation import load_module_fresh, stub_modules
    from tests.unit.test_sync_geolocation_enrichment import _build_pipeline_fakes

    with stub_modules(_build_pipeline_fakes()):
        yield load_module_fresh(
            'utils.sync.pipeline', str(Path(__file__).resolve().parents[2] / 'utils/sync/pipeline.py')
        )


async def _run_coordinator(module, **kwargs):
    from types import SimpleNamespace

    from tests.unit.test_sync_geolocation_enrichment import _prepare

    _prepare(module, ['/tmp/1720000000.wav'])

    async def same(value):
        return value

    module.async_resolve_geolocation = same
    module.schedule_person_voice_learning_retries = MagicMock()
    module._finalize_sync_job_for_run = MagicMock()
    seen = []

    def segment(_path, _uid, response, _lock, _errors, *args, **segment_kwargs):
        seen.append(segment_kwargs.get('redrive_mode'))
        response['new_memories'].add('conv-1')
        return True

    module.process_segment = segment
    module.minimal_redrive = SimpleNamespace(
        MINIMAL='minimal',
        ProviderUnavailable=minimal_redrive.ProviderUnavailable,
        parakeet_service=MagicMock(return_value=PARAKEET),
        finalize=MagicMock(),
    )
    await module._run_full_pipeline_background_async('job', 'uid', ['/tmp/a.opus'], 'omi', False, '/tmp/job', **kwargs)
    return seen, module._finalize_sync_job_for_run.call_args.args[2]


@pytest.mark.asyncio
async def test_coordinator_minimal_pins_provider_replaces_postprocess_and_records_mode(coordinator):
    seen, result = await _run_coordinator(coordinator, redrive_mode='minimal')
    assert seen == ['minimal']
    coordinator.get_prerecorded_service.assert_not_called()
    coordinator.minimal_redrive.finalize.assert_called_once()
    coordinator._reprocess_merged_conversations.assert_not_called()
    assert result['redrive_mode'] == 'minimal'
    assert (result['provider'], result['model']) == ('parakeet', 'parakeet')


@pytest.mark.asyncio
async def test_coordinator_normal_path_is_unchanged(coordinator):
    seen, result = await _run_coordinator(coordinator)
    assert seen == [None]
    coordinator.get_prerecorded_service.assert_called_once()
    coordinator.minimal_redrive.finalize.assert_not_called()
    coordinator._reprocess_merged_conversations.assert_called_once()
    assert 'redrive_mode' not in result


def test_explicit_or_lineage_bound_targets_are_never_replaced(monkeypatch):
    attach = Mock(return_value='near')
    monkeypatch.setattr(minimal_redrive, 'attach_target', attach)
    args = ('uid-1', 1000, 1060, 'omi', 'dev-1', False)
    assert minimal_redrive.segment_target('minimal', 'given', None, *args) == 'given'
    assert minimal_redrive.segment_target('minimal', None, 'stamp_fallback', *args) is None
    assert minimal_redrive.segment_target(None, None, None, *args) is None
    attach.assert_not_called()
    assert minimal_redrive.segment_target('minimal', None, None, *args) == 'near'


def test_title_call_never_uses_a_users_own_key(monkeypatch):
    seen = []

    def fake_get_llm(feature, uid=None):
        seen.append(byok.get_byok_keys())
        return Mock(invoke=Mock(return_value=Mock(content='{"title": "T", "overview": "O."}')))

    monkeypatch.setattr(llm_clients, 'get_llm', fake_get_llm)
    byok.set_byok_keys({'openrouter': 'user-key', 'anthropic': 'user-key'})
    try:
        assert minimal_redrive.generate_title('uid-1', 'hello') == ('T', 'O.')
        assert seen == [{}]  # Company gpt-5-nano lane only.
        assert byok.get_byok_keys() == {'openrouter': 'user-key', 'anthropic': 'user-key'}
    finally:
        byok.set_byok_keys({})


@pytest.mark.asyncio
async def test_coordinator_retries_provider_unavailable_instead_of_finalizing(coordinator):
    from tests.unit.test_sync_geolocation_enrichment import _prepare

    _prepare(coordinator, ['/tmp/1720000000.wav'])

    async def same(value):
        return value

    coordinator.async_resolve_geolocation = same
    coordinator._finalize_sync_job_for_run = MagicMock()

    def segment(*_args, **_kwargs):
        raise minimal_redrive.ProviderUnavailable()

    coordinator.process_segment = segment
    coordinator.minimal_redrive = minimal_redrive
    with pytest.raises(TranscriptionFailure) as raised:
        await coordinator._run_full_pipeline_background_async(
            'job', 'uid', ['/tmp/a.opus'], 'omi', False, '/tmp/job', task_mode=True
        )
    assert raised.value.error_code == 'sync_minimal_provider_unavailable'
    assert sync_failure_from_exception(raised.value).retryable is True
    coordinator._finalize_sync_job_for_run.assert_not_called()

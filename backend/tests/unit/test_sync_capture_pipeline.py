"""Real VAD export and process_segment preserve speech extents; silence creates nothing."""

import logging
from pathlib import Path
import threading
from unittest.mock import MagicMock
import uuid

import fakeredis
import httpx
import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cloud_tasks import _load_sync_jobs, _seed_fenced_job
from tests.unit.test_sync_cross_job_assignment import intake, conversations
from tests.unit.test_sync_geolocation_enrichment import _build_pipeline_fakes
from utils.sync import telemetry
from utils.sync.capture import chunk_identity


@pytest.fixture
def pipeline():
    from models import conversation, conversation_enums, transcript_segment
    from pydub import AudioSegment
    from utils.conversations import deterministic_minimum
    from utils.sync import bridge as real_bridge

    fakes = _build_pipeline_fakes()
    lifecycle = AutoMockModule('utils.conversations.lifecycle')
    bridge = AutoMockModule('utils.sync.bridge')
    bridge.finish_sync_bridges = lambda uid, cid: cid
    fakes.update(
        {
            'models.conversation': conversation,
            'models.conversation_enums': conversation_enums,
            'models.transcript_segment': transcript_segment,
            'utils.conversations.deterministic_minimum': deterministic_minimum,
            'utils.conversations.lifecycle': lifecycle,
            'utils.sync.bridge': bridge,
        }
    )
    with stub_modules(fakes):
        module = load_module_fresh(
            'utils.sync.pipeline', Path(__file__).resolve().parents[2] / 'utils/sync/pipeline.py'
        )
        module.real_bridge = real_bridge
        module.AudioSegment = AudioSegment
        module.get_timestamp_from_path = lambda path: float(Path(path).stem)
        module.get_syncing_file_temporal_signed_url = lambda path: path
        module.schedule_syncing_temporal_file_deletion = lambda path: None
        module.get_prerecorded_service = lambda language: ('test', None, 'test')
        module.identify_speakers_for_segments = lambda *a: None
        module.get_closest_conversation_to_timestamps = lambda *a: None
        module.prerecorded = MagicMock(return_value=([{}], 'en'))
        module.postprocess_words = lambda *a: [
            transcript_segment.TranscriptSegment(text='Keep the capture.', start=0, end=3, is_user=False)
        ]
        store = StrictFirestore()
        lifecycle.ingest_sync_conversation = lambda uid, row, **kw: intake(store, row, **kw)
        yield module, store


@pytest.mark.parametrize('quiet', [False, True])
def test_vad_preserves_speech_origin_and_exports_nothing_for_silence(pipeline, tmp_path, quiet):
    module, store = pipeline
    original = tmp_path / '1700000000.wav'
    module.AudioSegment.silent(duration=70000).export(original, format='wav')
    module.vad_is_empty = lambda *a, **kw: [] if quiet else [{'start': 20, 'end': 23}]
    paths = set()
    module.retrieve_vad_segments(str(original), paths, [])
    if quiet:
        assert paths == set() and not conversations(store)
        module.prerecorded.assert_not_called()
        assert list(tmp_path.iterdir()) == [original]
        return
    path = next(iter(paths))
    assert Path(path).stem == '1700000020.0'
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert module.process_segment(path, 'u', response, threading.Lock(), errors, deferred_outcome=outcome)
    assert errors == []
    row = conversations(store)[0]
    assert row['finished_at'].timestamp() == 1700000023
    assert row['started_at'].timestamp() == 1700000020
    assert row['transcript_segments'][0]['start'] == 0
    assert row['id'] == chunk_identity('u', 'omi', None, False, 1700000020)
    assert outcome['outcome'].value == 'success'


@pytest.mark.parametrize('empty_words', [True, False])
def test_empty_transcription_creates_nothing_and_cannot_bridge(pipeline, empty_words):
    module, store = pipeline
    if empty_words:
        module.prerecorded.return_value = ([], 'en')
    else:
        module.postprocess_words = lambda *a: []
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert (
        module.process_segment('1700000000.wav', 'u', response, threading.Lock(), errors, deferred_outcome=outcome)
        is False
    )
    assert module.prerecorded.call_count == 2
    assert not store.rows and not errors
    assert response == {'new_memories': set(), 'updated_memories': set()}
    assert outcome['outcome'].value == 'expected_silence' and not outcome['retryable']


def test_empty_retry_recovers_through_original_path_once(pipeline):
    module, store = pipeline
    module.prerecorded = MagicMock(side_effect=[([], 'en'), ([{}], 'en')])
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert module.process_segment('1700000000.wav', 'u', response, threading.Lock(), errors, deferred_outcome=outcome)
    assert module.prerecorded.call_count == 2
    first, second = module.prerecorded.call_args_list
    assert first == second
    assert len(conversations(store)) == 1
    assert errors == []
    assert outcome['outcome'].value == 'success'


def test_retry_exception_keeps_failure_classification_with_provider_call_phase(pipeline):
    module, store = pipeline
    request = httpx.Request('POST', 'https://stt.invalid/transcribe')
    module.prerecorded = MagicMock(
        side_effect=[
            ([], 'en'),
            httpx.HTTPStatusError('503', request=request, response=httpx.Response(503, request=request)),
        ]
    )
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert (
        module.process_segment('1700000000.wav', 'u', response, threading.Lock(), errors, deferred_outcome=outcome)
        is False
    )
    assert module.prerecorded.call_count == 2
    assert not conversations(store)
    assert errors == ['stt_upstream_error']
    assert outcome['outcome'].value == 'upstream_error' and outcome['retryable']
    assert outcome['phase'] == 'provider_call'
    assert outcome['exception_type'] == 'HTTPStatusError'


def test_provider_timeout_is_distinct_from_other_provider_failures(pipeline):
    module, store = pipeline
    module.prerecorded = MagicMock(side_effect=TimeoutError('provider read timed out'))
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert (
        module.process_segment('1700000000.wav', 'u', response, threading.Lock(), errors, deferred_outcome=outcome)
        is False
    )
    assert module.prerecorded.call_count == 1
    assert errors == ['stt_timeout']
    assert outcome['outcome'].value == 'timeout' and outcome['retryable']
    assert outcome['phase'] == 'provider_call'
    assert outcome['exception_type'] == 'TimeoutError'


def test_downstream_exception_after_provider_success_is_not_attributed_to_provider(pipeline):
    module, store = pipeline
    module.postprocess_words = MagicMock(side_effect=RuntimeError('normalize failed'))
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert (
        module.process_segment('1700000000.wav', 'u', response, threading.Lock(), errors, deferred_outcome=outcome)
        is False
    )
    assert module.prerecorded.call_count == 1
    assert not conversations(store)
    assert outcome['outcome'].value == 'upstream_error'
    assert outcome['phase'] == 'parse'
    assert outcome['exception_type'] == 'RuntimeError'


def test_success_does_not_retry_and_failure_log_has_no_identifiers(pipeline, caplog):
    module, store = pipeline
    response = {'new_memories': set(), 'updated_memories': set()}
    assert module.process_segment('1700000000.wav', 'u', response, threading.Lock(), [])
    assert module.prerecorded.call_count == 1

    request = httpx.Request('POST', 'https://stt.invalid/transcribe')
    module.prerecorded = MagicMock(
        side_effect=httpx.HTTPStatusError(
            'detail user@example.com /tmp/private.wav', request=request, response=httpx.Response(503, request=request)
        )
    )
    with caplog.at_level(logging.ERROR):
        assert module.process_segment('1700000001.wav', 'u', response, threading.Lock(), []) is False
    record = next(r for r in caplog.records if 'event=sync_transcription_segment' in r.getMessage())
    message = record.getMessage()
    assert 'phase=provider_call' in message
    assert 'exception_type=HTTPStatusError' in message
    assert 'job_ref=none' in message and 'attempt_ref=none' in message
    assert 'user@example.com' not in message and '/tmp/private.wav' not in message
    assert 'stt.invalid' not in message


def test_correlation_refs_accept_uuid4_only():
    job = uuid.uuid4()
    assert telemetry.bounded_correlation_ref(str(job)) == job.hex
    assert telemetry.bounded_correlation_ref(job.hex) == job.hex
    assert telemetry.bounded_correlation_ref(str(uuid.uuid1())) == 'none'
    assert telemetry.bounded_correlation_ref('user-uid-123') == 'none'
    assert telemetry.bounded_correlation_ref('/tmp/audio.wav') == 'none'
    assert telemetry.bounded_correlation_ref(None) == 'none'
    first, second = telemetry.new_attempt_ref(), telemetry.new_attempt_ref()
    assert first != second
    assert uuid.UUID(first).version == 4


@pytest.mark.parametrize('second_pass', ['words', 'empty', 'exception'])
def test_empty_retry_event_carries_bounded_correlation(pipeline, caplog, second_pass):
    module, _store = pipeline
    job_id = str(uuid.uuid4())
    attempt_ref = uuid.uuid4().hex
    module.get_prerecorded_service = lambda language: ('deepgram', None, 'nova-3')
    second = {'words': ([{}], 'en'), 'empty': ([], 'en')}.get(second_pass, RuntimeError('provider exploded'))
    module.prerecorded = MagicMock(side_effect=[([], 'en'), second])
    response = {'new_memories': set(), 'updated_memories': set()}
    outcome = {}
    with caplog.at_level(logging.INFO):
        module.process_segment(
            '1700000000.wav',
            'uid-secret-9f2c',
            response,
            threading.Lock(),
            [],
            deferred_outcome=outcome,
            job_id=job_id,
            segment_key='seg-1',
            attempt_ref=attempt_ref,
        )
    retry_events = [r.getMessage() for r in caplog.records if 'sync_transcription_empty_retry' in r.getMessage()]
    expected = ['started', {'words': 'recovered', 'empty': 'still_empty'}.get(second_pass)]
    if expected[1] is None:
        expected.pop()
        assert outcome['phase'] == 'provider_call' and outcome['exception_type'] == 'RuntimeError'
    assert [m.split('outcome=')[1].split(' ')[0] for m in retry_events] == expected
    for message in retry_events:
        assert 'provider=deepgram' in message and 'lane=fresh' in message
        assert f'job_ref={uuid.UUID(job_id).hex}' in message and f'attempt_ref={attempt_ref}' in message
        assert 'uid-secret-9f2c' not in message and '1700000000.wav' not in message


def test_job_finalized_event_shares_segment_correlation(pipeline, caplog):
    module, _store = pipeline
    job_id = str(uuid.uuid4())
    attempt_ref = uuid.uuid4().hex
    module.try_mark_once = MagicMock(return_value=True)
    module.record_sync_transcription_outcome = MagicMock()

    redis_client = fakeredis.FakeRedis()
    sync_jobs, _ = _load_sync_jobs(redis_client)
    _seed_fenced_job(
        redis_client,
        sync_jobs,
        job_id,
        {
            'job_id': job_id,
            'status': 'processing',
            'ledger_fence_mode': 'legacy',
            'result': None,
            'failed_segments': 0,
        },
    )

    with caplog.at_level(logging.INFO):
        module._record_sync_segment_outcome(
            module.TranscriptionOutcome.SUCCESS,
            provider='deepgram',
            model='nova-3',
            lane='fresh',
            retryable=False,
            job_id=job_id,
            segment_key='seg-1',
            attempt_ref=attempt_ref,
        )
        finalized = sync_jobs.finalize_sync_job(
            job_id,
            {'failed_segments': 0, 'total_segments': 1, 'errors': [], 'outcome': 'success'},
            attempt_ref=attempt_ref,
        )

    assert finalized is not None
    shared_ref = f'job_ref={uuid.UUID(job_id).hex} attempt_ref={attempt_ref}'
    segment_msg = next(r.getMessage() for r in caplog.records if 'event=sync_transcription_segment' in r.getMessage())
    job_msg = next(r.getMessage() for r in caplog.records if 'event=sync_transcription_job_finalized' in r.getMessage())
    assert shared_ref in segment_msg and shared_ref in job_msg
    assert 'failure_phase=none' in job_msg and 'failure_class=none' in job_msg
    assert set(module.record_sync_transcription_outcome.call_args.kwargs) == {
        'kind',
        'provider',
        'model',
        'lane',
        'outcome',
    }


def test_bridge_finishes_once_at_process_segment_completion(pipeline, monkeypatch):
    module, store = pipeline
    bridge = module.real_bridge
    module.finish_sync_segment = bridge.finish_sync_segment
    finish = MagicMock(side_effect=lambda uid, cid, **kw: cid)
    monkeypatch.setattr(bridge, 'finish_sync_bridges', finish)
    response = {'new_memories': set(), 'updated_memories': set()}
    for timestamp in (1000, 1240, 1120):
        assert module.process_segment(f'{timestamp}.wav', 'u', response, threading.Lock(), [])
    assert len(conversations(store)) == 1
    finish.assert_called_once_with('u', conversations(store)[0]['id'], audio_source_id=None)


@pytest.mark.parametrize('condition', ['anchor_deleted', 'lineage_deleted', 'user_managed', 'provenance', 'cycle'])
def test_assignment_outcomes_through_process_segment(pipeline, condition):
    from copy import deepcopy
    from tests.unit.test_sync_cross_job_assignment import chunk

    module, store = pipeline
    cid = chunk_identity('u', 'omi', None, False, 1000)
    row = chunk(cid, 1000, device=None)
    row['sync_content_revision'] = 1
    target = None
    if condition == 'anchor_deleted':
        row['deleted'] = True
    elif condition == 'lineage_deleted':
        row.update(deleted=True, sync_merged_into='survivor')
        store.rows[('users', 'u', 'conversations', 'survivor')] = dict(row, id='survivor', sync_merged_into=None)
    elif condition == 'user_managed':
        row['user_title'] = 'Preserve my edit'
    elif condition == 'cycle':
        row.update(deleted=True, sync_merged_into=cid)
    else:
        row = chunk('live', 1000, device='another-device')
        cid = target = 'live'
    store.rows[('users', 'u', 'conversations', cid)] = row
    before = deepcopy(store.rows)
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert (
        module.process_segment(
            '1000.wav', 'u', response, threading.Lock(), errors, target_conversation_id=target, deferred_outcome=outcome
        )
        is False
    )
    assert store.rows == before
    assert response == {'new_memories': set(), 'updated_memories': set()}
    if condition in ('provenance', 'cycle'):
        assert errors == ['stt_upstream_error']
        assert outcome['outcome'].value == 'upstream_error' and outcome['retryable']
    else:
        assert errors == []
        assert outcome['outcome'].value == 'success' and not outcome['retryable']

"""Real VAD export and process_segment preserve speech extents; silence creates nothing."""

import logging
from copy import deepcopy
from google.api_core.exceptions import InvalidArgument, ServiceUnavailable, TooManyRequests
from pathlib import Path
from types import SimpleNamespace
import threading
from unittest.mock import AsyncMock, MagicMock
import hashlib
import uuid

import fakeredis
import httpx
import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from database.firestore_transaction_retry import FirestoreContentionExhausted
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cloud_tasks import _load_sync_jobs, _seed_fenced_job
from tests.unit.test_sync_cross_job_assignment import intake, conversations, chunk
from tests.unit.test_sync_geolocation_enrichment import _build_pipeline_fakes
from utils.stt.pre_recorded import postprocess_words
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
    final_pass = AutoMockModule('utils.conversations.final_pass_sync')
    bridge.finish_sync_bridges = lambda uid, cid: cid
    fakes.update(
        {
            'models.conversation': conversation,
            'models.conversation_enums': conversation_enums,
            'models.transcript_segment': transcript_segment,
            'utils.conversations.deterministic_minimum': deterministic_minimum,
            'utils.conversations.lifecycle': lifecycle,
            'utils.sync.bridge': bridge,
            'utils.conversations.final_pass_sync': final_pass,
        }
    )
    with stub_modules(fakes):
        module = load_module_fresh(
            'utils.sync.pipeline', Path(__file__).resolve().parents[2] / 'utils/sync/pipeline.py'
        )
        module.ingest_test_seam = lifecycle
        module.final_pass_test_seam = final_pass
        module.real_bridge = real_bridge
        module.AudioSegment = AudioSegment
        module.get_timestamp_from_path = lambda path: float(Path(path).stem)
        module.get_syncing_file_temporal_signed_url = lambda path: path
        module.get_prerecorded_service = lambda language: ('test', None, 'test')
        module.identify_speakers_for_segments = lambda *a: None
        module.get_closest_conversation_to_timestamps = lambda *a: None
        module.prerecorded = MagicMock(return_value=([{}], 'en'))
        module.postprocess_words = lambda *a: [
            transcript_segment.TranscriptSegment(text='Keep the capture.', start=0, end=3, is_user=False)
        ]
        store = StrictFirestore()
        lifecycle.ingest_sync_conversation = lambda uid, row, **kw: intake(store, row, **kw)
        # The episodes intake attach is fail-open; the harness stand-in skips like a
        # user whose app never called the episodes API. The wiring test spies on it.
        module.schedule_synced_intake_attach = lambda uid, cid, row: None
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


def test_provider_failure_after_eight_minutes_never_releases_staging(pipeline, monkeypatch, tmp_path):
    module, _ = pipeline
    path = tmp_path / '1700000000.wav'
    module.AudioSegment.silent(duration=1000).export(path, format='wav')
    pending = []
    staging = {'exists': True}

    def schedule(_path):
        pending.append(lambda: staging.update(exists=False))

    # Fault injection: callbacks scheduled at URL creation would now be due.
    # Restoring the old call causes this production-path test to lose staging.
    monkeypatch.setattr(module, 'schedule_syncing_temporal_file_deletion', schedule, raising=False)

    def late_failure(*args, **kwargs):
        for delete in pending:
            delete()
        raise RuntimeError('synthetic provider failure after 481 seconds')

    module.prerecorded = late_failure
    errors = []
    response = {'new_memories': set(), 'updated_memories': set()}
    assert module.process_segment(str(path), 'u', response, threading.Lock(), errors) is False
    assert errors
    assert staging['exists'] and pending == []


@pytest.mark.parametrize('recovered', [False, True])
def test_late_first_word_stays_on_the_vad_file_clock(pipeline, monkeypatch, tmp_path, recovered):
    """A cough 20 s before speech opens their shared VAD file (gaps under 120 s merge).

    postprocess_words times lines from the first word. They must land where they were
    spoken on the file clock that started_at and the stored audio use, and finished_at
    and the merge lookup must end at the last word.
    """
    module, store = pipeline
    original = tmp_path / '1700000000.wav'
    module.AudioSegment.silent(duration=50000).export(original, format='wav')
    module.vad_is_empty = lambda *a, **kw: [{'start': 20, 'end': 21}, {'start': 40, 'end': 45}]
    paths = set()
    module.retrieve_vad_segments(str(original), paths, [])
    path = next(iter(paths))
    assert Path(path).stem == '1700000020.0'
    # Provider clocks are relative to the exported file: speech starts 20.5 s in.
    words = [
        {'timestamp': [20.5, 21.0], 'speaker': 'SPEAKER_00', 'text': 'Keep'},
        {'timestamp': [21.0, 24.25], 'speaker': 'SPEAKER_00', 'text': 'this'},
    ]
    if recovered:
        monkeypatch.setenv('SYNC_EMPTY_MULTILINGUAL_RECOVERY_ENABLED', 'true')
        module.get_prerecorded_service = lambda language: ('parakeet', None, 'parakeet')
        module.prerecorded = MagicMock(return_value=([], 'multi'))
        recovery = MagicMock(return_value=(words, 'en', 25.0, [{'start': 20.5, 'end': 24.25}]))
        monkeypatch.setattr(module.empty_recovery, 'recover', recovery)
    else:
        module.prerecorded = MagicMock(return_value=(words, 'en'))
    module.postprocess_words = postprocess_words
    module.get_closest_conversation_to_timestamps = MagicMock(return_value=None)
    response = {'new_memories': set(), 'updated_memories': set()}
    errors = []
    assert module.process_segment(path, 'u', response, threading.Lock(), errors)
    assert errors == []
    row = conversations(store)[0]
    assert row['started_at'].timestamp() == 1700000020
    assert [(s['text'], s['start'], s['end']) for s in row['transcript_segments']] == [('Keep this', 20.5, 24.25)]
    assert row['finished_at'].timestamp() == 1700000044.25
    module.get_closest_conversation_to_timestamps.assert_called_once_with('u', 1700000020.0, 1700000044.25)


def test_colliding_absolute_timestamps_from_distinct_sources_keep_both_segments(pipeline, tmp_path):
    """Two sources can independently compute the same capture_start + vad_offset;
    the second must not silently overwrite the first's exported audio (#20686)."""
    module, store = pipeline
    first = tmp_path / '1700000000.wav'
    second = tmp_path / '1700000001.wav'
    module.AudioSegment.silent(duration=4000).export(first, format='wav')
    module.AudioSegment.silent(duration=4000).export(second, format='wav')

    def vad_for(path, *a, **kw):
        return [{'start': 1, 'end': 3}] if path == str(first) else [{'start': 0, 'end': 4}]

    module.vad_is_empty = vad_for
    paths = set()
    module.retrieve_vad_segments(str(first), paths, [])
    module.retrieve_vad_segments(str(second), paths, [])

    assert len(paths) == 2
    stems = sorted(Path(p).stem for p in paths)
    assert stems == ['1700000001.0', 'dup1_1700000001.0']
    durations = sorted(round(module.AudioSegment.from_wav(p).duration_seconds) for p in paths)
    assert durations == [2, 4]


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


@pytest.mark.parametrize('failed_read', [False, True])
def test_sync_passes_real_dream_keyterms_to_stt_with_nonfatal_fallback(pipeline, monkeypatch, failed_read):
    module, store = pipeline
    dream_store = AutoMockModule('database.dream_store')
    dream_store.vocabulary = MagicMock(
        return_value=[{'spelling': 'Quorbi'}, {'spelling': 'Tala'}, {'spelling': 'x' * 51}],
        side_effect=RuntimeError('synthetic unavailable') if failed_read else None,
    )
    with stub_modules({'database.dream_store': dream_store}):
        helper = load_module_fresh(
            'utils.dream_vocabulary', Path(__file__).resolve().parents[2] / 'utils/dream_vocabulary.py'
        )
        helper.run_blocking = AsyncMock(side_effect=lambda executor, fn, uid: fn(uid))
        helper.record_fallback = MagicMock()
        monkeypatch.setenv('DREAM_AGENT_VOCABULARY_STT', 'true')
        monkeypatch.setattr(module, 'keyterms', helper.keyterms)
        errors = []
        assert module.process_segment(
            '1700000000.wav',
            'synthetic-owner',
            {'new_memories': set(), 'updated_memories': set()},
            threading.Lock(),
            errors,
            transcription_prefs={'vocabulary': ['Tala', 'Omi', 'Tala']},
        )
        assert errors == [] and len(conversations(store)) == 1
        expected = ['Omi', 'Tala'] if failed_read else ['Omi', 'Tala', 'Quorbi']
        assert module.prerecorded.call_args.kwargs['keywords'] == expected
        dream_store.vocabulary.assert_called_once_with('synthetic-owner')
        assert helper.record_fallback.call_count == int(failed_read)


def test_sync_keyterm_cap_keeps_product_and_preferences_first(pipeline, monkeypatch):
    module, _ = pipeline
    dream_store = AutoMockModule('database.dream_store')
    dream_store.vocabulary = MagicMock(return_value=[{'spelling': f'Learned {i}'} for i in range(150)])
    with stub_modules({'database.dream_store': dream_store}):
        helper = load_module_fresh(
            'utils.dream_vocabulary', Path(__file__).resolve().parents[2] / 'utils/dream_vocabulary.py'
        )
        helper.run_blocking = AsyncMock(side_effect=lambda executor, fn, uid: fn(uid))
        monkeypatch.setenv('DREAM_AGENT_VOCABULARY_STT', 'true')
        monkeypatch.setattr(module, 'keyterms', helper.keyterms)
        assert module.process_segment(
            '1700000000.wav',
            'synthetic-owner',
            {'new_memories': set(), 'updated_memories': set()},
            threading.Lock(),
            [],
            transcription_prefs={'vocabulary': ['Tala']},
        )
        keywords = module.prerecorded.call_args.kwargs['keywords']
        assert len(keywords) == 100
        assert keywords[:3] == ['Omi', 'Tala', 'Learned 0']
        assert keywords[-1] == 'Learned 97'


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
    assert telemetry.bounded_correlation_ref(str(job)) == hashlib.sha256(job.hex.encode('ascii')).hexdigest()[:32]
    assert telemetry.bounded_correlation_ref(job.hex) == hashlib.sha256(job.hex.encode('ascii')).hexdigest()[:32]
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
    if second_pass == 'words':
        # A recovered segment must confirm persistence with durable_recovered.
        expected.append('durable_recovered')
    if expected[1] is None:
        expected.pop()
        assert outcome['phase'] == 'provider_call' and outcome['exception_type'] == 'RuntimeError'
    assert [m.split('outcome=')[1].split(' ')[0] for m in retry_events] == expected
    for message in retry_events:
        assert 'provider=deepgram' in message and 'lane=fresh' in message
        assert (
            f'job_ref={telemetry.bounded_correlation_ref(job_id)}' in message
            and f'attempt_ref={telemetry.bounded_correlation_ref(attempt_ref)}' in message
        )
        assert 'uid-secret-9f2c' not in message and '1700000000.wav' not in message


def test_job_finalized_event_shares_segment_correlation(pipeline, caplog, monkeypatch):
    # The seeded Redis document uses the unchanged production key contract.
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
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

    with caplog.at_level(logging.DEBUG):
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
    shared_ref = f'job_ref={telemetry.bounded_correlation_ref(job_id)} attempt_ref={telemetry.bounded_correlation_ref(attempt_ref)}'
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
        'failure_reason',
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


def test_locked_segments_merge_and_an_identical_locked_retry_is_not_a_conflict(pipeline, monkeypatch):

    module, store = pipeline
    response = {'new_memories': set(), 'updated_memories': set()}
    errors = []
    # The last call repeats a segment whose assignment already committed.
    for timestamp in (1000, 1060, 1060):
        outcome = {}
        module.process_segment(
            f'{timestamp}.wav', 'u', response, threading.Lock(), errors, is_locked=True, deferred_outcome=outcome
        )
        assert outcome['outcome'].value == 'success'
    assert errors == []
    rows = conversations(store)
    assert len(rows) == 1
    assert rows[0]['is_locked'] is True and len(rows[0]['transcript_segments']) == 2


@pytest.mark.parametrize('condition', ['anchor_deleted', 'lineage_deleted', 'user_managed', 'provenance', 'cycle'])
def test_assignment_outcomes_through_process_segment(pipeline, condition, monkeypatch):

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
        cid = 'live'
        target = 'donor'
        store.rows[('users', 'u', 'conversations', 'donor')] = dict(
            row, id='donor', deleted=True, sync_merged_into='live', smart_merge={'role': 'donor'}
        )
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
        assert errors == ['sync_persistence_failed']
        assert outcome['outcome'].value == 'upstream_error' and not outcome['retryable']
        assert outcome['failure_subtype'] == ('provenance_mismatch' if condition == 'provenance' else 'redirect_cycle')
    else:
        assert errors == []
        assert outcome['outcome'].value == 'success' and not outcome['retryable']


@pytest.mark.parametrize(
    'error,expected,kind,retryable',
    [
        (InvalidArgument('Document private-id exceeds the maximum allowed size'), 'document_size_limit', 'none', False),
        (
            InvalidArgument(
                "Document 'projects/p/databases/(default)/documents/users/private-uid/conversations/private-id' "
                'cannot be written because its size (1,048,601 bytes) exceeds the maximum allowed size'
            ),
            'document_size_limit',
            'conversation',
            False,
        ),
        (
            InvalidArgument(
                "Document 'projects/p/databases/(default)/documents/users/private-uid/sync_assignment/2026-10-03' "
                'cannot be written because its size (1,048,601 bytes) exceeds the maximum allowed size'
            ),
            'document_size_limit',
            'sync_day_index',
            False,
        ),
        (InvalidArgument('private unexpected input'), 'invalid_argument_other', 'none', True),
        (InvalidArgument('The transaction has expired private-id'), 'expired_transaction', 'none', True),
        (ServiceUnavailable('private detail'), 'ServiceUnavailable', 'none', True),
    ],
)
def test_persistence_errors_keep_audio_and_do_not_blame_stt(pipeline, caplog, error, expected, kind, retryable):
    module, store = pipeline
    module.ingest_test_seam.ingest_sync_conversation = MagicMock(side_effect=error)
    module.get_prerecorded_service = lambda language: ('deepgram', None, 'nova-3')
    errors, outcome = [], {}
    response = {'new_memories': set(), 'updated_memories': set()}
    assert (
        module.process_segment(
            '1000.wav',
            'u',
            response,
            threading.Lock(),
            errors,
            deferred_outcome=outcome,
            job_id=str(uuid.UUID(int=1, version=4)),
            attempt_ref=str(uuid.UUID(int=2, version=4)),
        )
        is False
    )
    assert not store.rows and not response['new_memories']
    assert errors == ['sync_persistence_failed']
    assert outcome['provider'] == outcome['model'] == 'unknown'
    assert outcome['retryable'] is retryable
    assert ('repeat_failure_fingerprint' in outcome) is (not retryable)
    event = next(r.message for r in caplog.records if 'event=sync_persistence_exception' in r.message)
    assert f'firestore_error={expected}' in event
    assert 'job_ref=' + telemetry.bounded_correlation_ref(str(uuid.UUID(int=1, version=4))) in event
    assert 'attempt_ref=' + telemetry.bounded_correlation_ref(str(uuid.UUID(int=2, version=4))) in event
    assert 'segments_bucket=1' in event and 'speech_seconds_bucket=' in event
    assert 'rollover_target_kind=none' in event
    assert ('outcome=rejected' in event) is (expected == 'document_size_limit')
    assert f'firestore_doc_kind={kind} ' in event
    assert 'private' not in event and '2026-10-03' not in event
    module.prerecorded.assert_called_once()


@pytest.mark.parametrize(
    'error,reason',
    [
        (ValueError('open_loop_extractions must be an object'), 'open_loop_extractions_not_object'),
        (ValueError('synthetic confidential detail'), 'other_value_error'),
        (ValueError('open_loop_extractions must be an object synthetic confidential detail'), 'other_value_error'),
        (ValueError('Failed to commit transaction in 5 attempts.'), 'sdk_commit_attempts_exhausted'),
        (
            ValueError('The transaction has no transaction ID, so it cannot be rolled back.'),
            'sdk_transaction_not_in_progress',
        ),
        (RuntimeError('synthetic confidential detail'), 'none'),
    ],
)
@pytest.mark.parametrize('phase', ['persistence', 'finalize'])
def test_value_error_diagnostics_use_only_closed_tokens(pipeline, caplog, error, reason, phase):
    module, _ = pipeline
    if phase == 'persistence':
        module.ingest_test_seam.ingest_sync_conversation = MagicMock(side_effect=error)
    else:
        module.finish_sync_segment = MagicMock(side_effect=error)
    module.get_prerecorded_service = lambda language: ('deepgram', None, 'nova-3')
    module.process_segment(
        '1000.wav', 'u', {'new_memories': set(), 'updated_memories': set()}, threading.Lock(), [], deferred_outcome={}
    )
    event = next(r.message for r in caplog.records if f'event=sync_{phase}_exception' in r.message)
    assert f'value_error_reason={reason}' in event
    assert 'confidential' not in event and 'must be an object' not in event


@pytest.mark.parametrize(
    ('error', 'code', 'reason'),
    [
        (FirestoreContentionExhausted('busy'), 'sync_firestore_contention', 'firestore_contention'),
        (TooManyRequests('per-object rate'), 'sync_storage_rate_limited', 'storage_rate_limited'),
        (ServiceUnavailable('down'), 'sync_persistence_failed', 'persistence_error'),
    ],
)
def test_internal_persistence_failure_names_its_cause_inside_the_fresh_turn(
    pipeline, caplog, monkeypatch, error, code, reason
):
    module, _store = pipeline
    turns = []
    lease = SimpleNamespace(
        acquire=lambda uid, conversation_id, lane: turns.append(('acquire', lane)) or 'turn',
        release=lambda turn: turns.append(('release', turn)),
    )
    monkeypatch.setattr(module, 'conversation_turn_lease', lease)
    module.ingest_test_seam.ingest_sync_conversation = MagicMock(side_effect=error)
    module.get_prerecorded_service = lambda language: ('deepgram', None, 'nova-3')
    errors = []
    response = {'new_memories': set(), 'updated_memories': set()}
    with caplog.at_level(logging.INFO):
        assert module.process_segment('1000.wav', 'u', response, threading.Lock(), errors) is False
    assert errors == [code]
    assert turns == [('acquire', 'fresh'), ('release', 'turn')]
    segment = next(r.message for r in caplog.records if 'event=sync_transcription_segment' in r.message)
    assert 'outcome=internal_error' in segment and f'failure_reason={reason}' in segment
    assert 'upstream_error' not in segment


def test_redirected_assignment_also_holds_the_finalize_target_turn(pipeline, monkeypatch):
    module, _store = pipeline
    turns = []
    lease = SimpleNamespace(
        acquire=lambda uid, conversation_id, lane: turns.append(('acquire', conversation_id)) or conversation_id,
        release=lambda turn: turns.append(('release', turn)),
    )
    monkeypatch.setattr(module, 'conversation_turn_lease', lease)
    module.ingest_test_seam.ingest_sync_conversation = MagicMock(return_value=({'id': 'survivor'}, False, []))
    monkeypatch.setattr(module, 'complete_sync_intake', MagicMock(side_effect=TooManyRequests('per-object rate')))
    module.get_prerecorded_service = lambda language: ('deepgram', None, 'nova-3')
    errors = []
    response = {'new_memories': set(), 'updated_memories': set()}
    assert module.process_segment('1000.wav', 'u', response, threading.Lock(), errors) is False
    acquired = [conversation_id for kind, conversation_id in turns if kind == 'acquire']
    assert acquired[-1] == 'survivor' and len(acquired) == 2
    assert sorted((turn for kind, turn in turns if kind == 'release'), key=str) == sorted(acquired, key=str)
    assert errors == ['sync_storage_rate_limited']


@pytest.mark.parametrize('legacy_failure', [False, True])
def test_sync_budget_refusal_retains_legacy_and_logs_only_uid_hash(pipeline, monkeypatch, caplog, legacy_failure):
    import hashlib

    module, store = pipeline
    uid = 'synthetic-private-uid'
    monkeypatch.setattr(module, 'sync_enabled_for', lambda _: True)
    monkeypatch.setattr(module, '_download_audio_bytes', lambda _: b'synthetic')
    monkeypatch.setattr(
        module.final_pass_test_seam, 'run_sync_final_pass', lambda *a, **kw: (None, {'outcome': 'skipped_budget'})
    )
    legacy = MagicMock(side_effect=RuntimeError('synthetic') if legacy_failure else None)
    monkeypatch.setattr(module, 'identify_speakers_for_segments', legacy)
    response = {'new_memories': set(), 'updated_memories': set()}
    with caplog.at_level(logging.INFO):
        assert module.process_segment('1700000000.wav', uid, response, threading.Lock(), [])
    legacy.assert_called_once()
    assert conversations(store)[0]['transcript_segments'][0]['text'] == 'Keep the capture.'
    events = [
        r.message
        for r in caplog.records
        if 'event=sync_final_pass' in r.message or 'event=sync_speaker_id' in r.message
    ]
    assert len(events) == (2 if legacy_failure else 1)
    digest = hashlib.sha256(('sync-final-pass:' + uid).encode()).hexdigest()
    assert all(f'uid_hash={digest}' in event and uid not in event for event in events)
    assert 'outcome=skipped_budget' in events[0]
    assert 'lane=' in events[0] and 'duration_seconds=' in events[0]


@pytest.mark.parametrize('result', ['silence', 'speech', 'empty', 'inspection_error'])
def test_dark_empty_recovery_runs_through_real_legacy_assignment(pipeline, monkeypatch, result):
    module, store = pipeline
    monkeypatch.setenv('SYNC_EMPTY_MULTILINGUAL_RECOVERY_ENABLED', 'true')
    module.get_prerecorded_service = lambda language: ('parakeet', None, 'parakeet')
    module.prerecorded = MagicMock(return_value=([], 'multi'))
    recovered = ([{'text': 'Synthetic speech', 'timestamp': [0, 3]}], 'vi', 3.0, [{'start': 0, 'end': 3}])
    if result == 'silence':
        recovered = ([], '', 3.0, [])
    recovery = MagicMock(return_value=recovered)
    if result == 'empty':
        recovery.side_effect = module.TranscriptionFailure(
            module.TranscriptionOutcome.EMPTY_UNEXPECTED, provider='modulate'
        )
    elif result == 'inspection_error':
        recovery.side_effect = RuntimeError('inspection failed')
    monkeypatch.setattr(module.empty_recovery, 'recover', recovery)
    module.postprocess_words = lambda words, *a: (
        [module.TranscriptSegment(text='Synthetic speech', start=0, end=3, is_user=False)] if words else []
    )
    errors, outcome = [], {}
    success = module.process_segment(
        '1700000000.wav',
        'synthetic-owner',
        {'new_memories': set(), 'updated_memories': set()},
        threading.Lock(),
        errors,
        deferred_outcome=outcome,
    )
    assert module.prerecorded.call_count == 2
    recovery.assert_called_once()
    assert success == (result == 'speech')
    assert len(conversations(store)) == int(result == 'speech')
    if result in ('empty', 'inspection_error'):
        assert errors and outcome['retryable'] and outcome['outcome'].value != 'expected_silence'
    else:
        assert not errors
        assert outcome['outcome'].value == ('success' if result == 'speech' else 'expected_silence')


def test_cached_multilingual_response_does_not_increment_submitted_audio(pipeline, monkeypatch):
    module, _ = pipeline
    module.cap_enabled = lambda uid, lane: True
    module.sync_allowed = lambda uid, *, lane='sync', **kwargs: True
    module.compute_sync_segment_id = lambda *args: 'stable-synthetic-segment'
    module.dispatch_empty_recovery_once = lambda uid, sid, dispatch: (
        [{'text': 'Synthetic', 'timestamp': [0, 3]}],
        'vi',
    )
    module.modulate_prerecorded_from_bytes = MagicMock()
    module.record_cap_audio = MagicMock()

    def inspect_and_recover(path, *, transcribe, authorize, observe):
        observe(3, [{'start': 0, 'end': 3}])
        authorize()
        words, language = transcribe(b'synthetic-canonical-wav')
        return words, language, 3, [{'start': 0, 'end': 3}]

    monkeypatch.setattr(module.empty_recovery, 'recover', inspect_and_recover)
    assert module._recover_empty_segment('synthetic.wav', 'synthetic-owner', 'parakeet', 'fresh', None, None)
    module.modulate_prerecorded_from_bytes.assert_not_called()
    module.record_cap_audio.assert_not_called()


@pytest.mark.parametrize(
    'spans,outcome', [([], 'silence'), ([{'start': 0, 'end': 3}], 'speech'), (None, 'inspection_error')]
)
def test_strict_vad_log_survives_failed_recovery_without_content(pipeline, monkeypatch, caplog, spans, outcome):
    module, _ = pipeline
    module.compute_sync_segment_id = lambda *args: 'synthetic-sealed-segment'

    def inspect_then_fail(path, *, transcribe, authorize, observe):
        observe(None if spans is None else 3, spans)
        raise RuntimeError('synthetic recovery failure')

    monkeypatch.setattr(module.empty_recovery, 'recover', inspect_then_fail)
    with caplog.at_level('INFO'), pytest.raises(RuntimeError, match='synthetic recovery failure'):
        module._recover_empty_segment('private-path.wav', 'private-owner', 'parakeet', 'fresh', None, None)
    events = [record.message for record in caplog.records if 'event=sync_empty_strict_vad ' in record.message]
    assert len(events) == 1
    assert f'outcome={outcome} lane=fresh provider=parakeet segment_ref=synthetic-sealed-segment' in events[0]
    assert 'private-owner' not in events[0] and 'private-path' not in events[0]


@pytest.mark.parametrize(
    'error', [ValueError('internal refresh'), TypeError('internal type'), RuntimeError('transient')]
)
def test_finalize_internal_failure_is_retryable_and_has_no_provider_label(pipeline, monkeypatch, tmp_path, error):
    module, store = pipeline
    path = tmp_path / '1700000000.wav'
    module.AudioSegment.silent(duration=3000).export(path, format='wav')
    monkeypatch.setattr(module, 'finish_sync_segment', MagicMock(side_effect=error))
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    assert module.process_segment(str(path), 'u', response, threading.Lock(), errors, deferred_outcome=outcome) is False
    assert conversations(store)
    assert errors == ['sync_finalize_failed']
    assert outcome['outcome'].value == 'upstream_error'
    assert outcome['retryable'] is True
    assert outcome['provider'] == 'unknown' and outcome['model'] == 'unknown'
    assert outcome['phase'] == 'finalize' and not outcome.get('provider_invalid_input')


@pytest.mark.parametrize('phase', ['provider_select', 'provider_call', 'parse'])
@pytest.mark.parametrize(
    'error_type,code,retryable',
    [
        (ValueError, 'stt_invalid_input', False),
        (httpx.ReadTimeout, 'stt_timeout', True),
        (RuntimeError, 'stt_upstream_error', True),
    ],
)
def test_segment_failure_phase_preserves_retry_labels_and_turnstile(
    pipeline, monkeypatch, caplog, phase, error_type, code, retryable
):
    module, store = pipeline
    error = error_type('private-provider-body-and-transcript')
    module.get_prerecorded_service = MagicMock(return_value=('deepgram', None, 'nova-3'))
    seam = {'provider_select': 'get_prerecorded_service', 'provider_call': 'prerecorded', 'parse': 'postprocess_words'}[
        phase
    ]
    monkeypatch.setattr(module, seam, MagicMock(side_effect=error))
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, outcome = [], {}
    turnstile = MagicMock()
    assert (
        module.process_segment(
            '1700000000.wav',
            'u',
            response,
            threading.Lock(),
            errors,
            deferred_outcome=outcome,
            turnstile=turnstile,
        )
        is False
    )
    assert errors == [code]
    assert outcome['retryable'] is retryable
    assert outcome['phase'] == phase
    assert outcome['provider'] == ('unknown' if phase == 'provider_select' else 'deepgram')
    assert outcome['model'] == ('unknown' if phase == 'provider_select' else 'nova-3')
    assert bool(outcome.get('provider_invalid_input')) is (error_type is ValueError and phase != 'provider_select')
    assert 'repeat_failure_fingerprint' not in outcome
    assert not store.rows and not response['new_memories'] and not response['updated_memories']
    turnstile.complete.assert_called_once_with('1700000000.wav')
    assert 'private-provider-body-and-transcript' not in caplog.text


def test_destructive_fence_still_propagates_without_recording_a_provider_failure(pipeline):
    class DestructiveOperationInProgress(RuntimeError):
        pass

    module, store = pipeline
    error = DestructiveOperationInProgress('private-account-fence')
    module.prerecorded = MagicMock(side_effect=error)
    errors, outcome = [], {}
    turnstile = MagicMock()
    with pytest.raises(DestructiveOperationInProgress) as caught:
        module.process_segment(
            '1700000000.wav',
            'u',
            {'new_memories': set(), 'updated_memories': set()},
            threading.Lock(),
            errors,
            deferred_outcome=outcome,
            turnstile=turnstile,
        )
    assert caught.value is error
    assert not errors and not outcome and not store.rows
    turnstile.complete.assert_called_once_with('1700000000.wav')


def test_process_segment_attaches_the_landed_row_to_the_live_episode(pipeline, monkeypatch):
    module, _store = pipeline
    attached = []
    monkeypatch.setattr(module, 'sync_enabled_for', lambda _: True)
    monkeypatch.setattr(module, '_download_audio_bytes', lambda _: b'synthetic')
    monkeypatch.setattr(
        module.final_pass_test_seam, 'run_sync_final_pass', lambda *a, **kw: (None, {'outcome': 'skipped_budget'})
    )
    monkeypatch.setattr(
        module,
        'schedule_synced_intake_attach',
        lambda uid, cid, row: attached.append((uid, cid, dict(row))) or 'joined',
    )
    response = {'new_memories': set(), 'updated_memories': set()}
    assert module.process_segment('1700000000.wav', 'u', response, threading.Lock(), [])
    # The row the intake persisted is the row handed to the episode join.
    assert len(attached) == 1
    uid, conversation_id, row = attached[0]
    assert uid == 'u' and row['id'] == conversation_id and conversation_id in response['new_memories']

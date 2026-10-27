"""Synthetic PCM only: context recovery, closed custody, paid-once and VAD CAS."""

from types import SimpleNamespace
import time
from unittest.mock import Mock

import numpy as np
import pytest

from config.batch_pipeline_empty_asr import safety_net_enabled
from diarizer.batch_pipeline import PipelineWorker
from diarizer.batch_pipeline_models import ParakeetWords
from tests.unit.test_batch_pipeline_worker import item
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row  # noqa: F401
from tests.unit.test_batch_pipeline_terminal_empty import terminal_setup
from utils.batch_pipeline.contracts import FailedWork, RecoveryWork, ValidationFailureWork, vad_receipt
from tests.unit.test_batch_pipeline_flight import FakeFlight
from utils.stt import local_vad
from utils.batch_pipeline.recovery_recognizers import transcribe
from utils.batch_pipeline.recovery_disposition import terminal_empty_payload, MultilingualEmpty
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.pump import Pump


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')


def test_ship_on_and_explicit_kill_switch(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED')
    assert safety_net_enabled()
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    assert not safety_net_enabled()
    assert terminal_empty_payload(2, [{'start': 0, 'end': 1}])['outcome'] == 'no_recoverable_speech'


def make_worker(*, vad, retry, decode=None, stream=None):
    words = Mock()
    words.transcribe_batch.side_effect = lambda batch: [[] for _ in batch]
    return PipelineWorker(
        language_of=lambda _: 'en',
        stream_of=stream,
        decode=decode or (lambda work: np.ones(int(work.duration_seconds * 16000), dtype=np.float32)),
        vad=vad,
        words_providers={'parakeet': words},
        diarizers={'pyannote': lambda _: {'turns': []}},
        recover_words=retry,
        persist=lambda work, payload: 'result://' + work.segment_id,
        io_concurrency=1,
    )


def test_mid_utterance_retry_gets_predecessor_tail_and_discards_its_words():
    retry = Mock(
        return_value=[
            {'word': 'predecessor', 'timestamp': [0.1, 0.4]},
            {'word': 'recovered', 'timestamp': [2.6, 3.0]},
        ]
    )
    previous = item('p', 4)
    current = type(previous)('s', previous.owner_id, previous.capture_at + 4, 'audio://s', 4, previous.priority)
    worker = make_worker(
        vad=lambda _: [(2, 4)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=lambda work: np.full(64000, 0.25 if work.segment_id == 'p' else 0.5, dtype=np.float32),
    )
    # Remember actual predecessor VAD without ever needing real speech/audio.
    worker.left_context.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    result = worker.process_batch([current])[0]
    assert result.outcome == 'success'
    samples = retry.call_args.args[0]
    assert len(samples) == 104000  # 2.5s predecessor onset/margin + full 4s unit
    assert samples[0] == pytest.approx(0.25) and samples[-1] == pytest.approx(0.5)
    assert saved['s']['words'] == [{'word': 'recovered', 'timestamp': pytest.approx([0.1, 0.5])}]
    assert retry.call_count == 1


def test_onset_retry_keeps_one_second_preroll_and_restores_clocks():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [1, 2]}])
    worker = make_worker(vad=lambda _: [(3, 5)], retry=retry)
    saved = {}
    worker.persist = lambda work, payload: saved.update(payload) or 'result://a'
    assert worker.process_batch([item('a', 8)])[0].outcome == 'success'
    assert len(retry.call_args.args[0]) == 6 * 16000
    assert saved['words'][0]['timestamp'] == [3, 4]


def test_real_retry_adapter_accepts_synthetic_context_and_restores_unit_clock():
    calls = []

    def model_transcribe(arrays, **_):
        calls.append(arrays)
        # Stand-in for the TDT start-state property: the segmented first pass
        # stays blank; a single-item onset/preroll retry produces word clocks.
        return [
            SimpleNamespace(
                text='recovered' if len(calls) == 2 else '',
                timestamp={'word': [{'word': 'recovered', 'start': 3, 'end': 4}] if len(calls) == 2 else []},
            )
            for _ in arrays
        ]

    provider = ParakeetWords(SimpleNamespace(transcribe=model_transcribe))
    worker = make_worker(vad=lambda _: [(3, 5)], retry=provider.recover_empty)
    worker.words = provider
    saved = {}
    worker.persist = lambda _, payload: saved.update(payload) or 'result://a'
    assert worker.process_batch([item('a', 8)])[0].outcome == 'success'
    assert len(calls) == 2
    assert len(calls[1][0]) == 10 * 16000  # 6 real seconds + adapter margins
    assert saved['words'][0]['timestamp'] == [3, 4]


def test_retry_authorization_refusal_cannot_dispatch_or_terminally_complete(monkeypatch):
    from config import stt_cap_dispatch

    monkeypatch.setattr(stt_cap_dispatch, 'offline_admission_enabled', lambda *_: True)
    # The worker imports the decision at module scope.
    from diarizer import batch_pipeline

    monkeypatch.setattr(batch_pipeline, 'cap_dispatch_enabled', lambda *_: True)
    provider = ParakeetWords(Mock())
    provider.transcribe_batch = Mock(side_effect=lambda arrays: [[] for _ in arrays])
    worker = make_worker(vad=lambda _: [(0, 2)], retry=provider.recover_empty)
    worker.words = provider
    decisions = iter([{'a': None}, {'a': 'plan_allowance_exhausted'}])
    result = worker.process_batch([item('a', 4)], authorize_dispatch=lambda _: next(decisions))[0]
    assert result.reason == 'plan_allowance_exhausted'
    provider.transcribe_batch.assert_called_once()


@pytest.mark.parametrize('near_empty', [False, True])
def test_empty_or_near_empty_retry_hands_off_with_measured_vad(near_empty):
    retry = Mock(return_value=[{'word': '.', 'timestamp': [1, 2]}] if near_empty else [])
    worker = make_worker(vad=lambda _: [(0, 2)], retry=retry)
    if near_empty:
        worker.words.transcribe_batch.side_effect = lambda batch: [
            [{'word': '.', 'timestamp': [0.1, 0.2]}] for _ in batch
        ]
    result = worker.process_batch([item('a', 4)])[0]
    assert isinstance(result, RecoveryWork)
    assert result.measured_held_vad_speech_seconds == 2
    assert result.worker_vad_receipt == vad_receipt(item('a', 4).audio_uri, 64000, 2)
    assert retry.call_count == 1


@pytest.mark.parametrize('speech', [0.46, 1.0, 7.1])
def test_empty_fenced_provider_holds_positive_vad_never_terminal(setup, monkeypatch, legacy_dependencies, speech):
    client, _, binding, artifacts, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setattr(legacy_dependencies[1], 'offline_pcm_speech_segments', lambda _: [{'start': 0, 'end': speech}])
    row(client).update(duration_seconds=10)
    from tests.unit.test_batch_pipeline_empty_disposition import wav

    artifacts.fetch_audio.return_value = wav(10)
    row(client).pop('recovery')
    row(client)['recovery_state'] = 'held'
    recovery = setup[-1]
    recovery.stt = transcribe
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    assert row(client)['measured_held_vad_speech_seconds'] == speech
    assert row(client)['recovery']['failure']['reason'] == 'empty_asr'
    assert not row(client).get('result')
    assert recovery.recover('bad', binding.owner_id) == 'held'
    alternate.assert_called_once()
    legacy.assert_not_called()
    artifacts.persist_recovery_result.assert_not_called()


def test_terminal_constructor_refuses_speech_by_default():
    with pytest.raises(MultilingualEmpty):
        terminal_empty_payload(2, [{'start': 0, 'end': 0.46}])


def test_vad_receipt_is_lease_fenced_and_unknown_is_not_zero():
    store = MemoryStore()
    scheduler = Scheduler(store)
    for sid, measured in [('known', 1.25), ('unknown', None)]:
        scheduler.enqueue(item(sid, 4), 0)
        lease = scheduler.pull(1)[0]
        assert not scheduler.fail(sid, 'foreign', 2, quarantine=True, measured_held_vad_speech_seconds=measured)
        assert scheduler.fail(sid, lease.token, 2, quarantine=True, measured_held_vad_speech_seconds=measured)
        job = store.run(lambda tx: tx.get('jobs', sid))
        assert 'measured_held_vad_speech_seconds' in job
        assert job['measured_held_vad_speech_seconds'] == measured


def test_valid_decode_rounding_cannot_block_failure_receipt():
    store = MemoryStore()
    scheduler = Scheduler(store)
    work = item('rounded', 3.99)
    scheduler.enqueue(work, 0)
    lease = scheduler.pull(1)[0]
    assert scheduler.fail(
        work.segment_id,
        lease.token,
        2,
        quarantine=True,
        measured_held_vad_speech_seconds=4,
        worker_vad_receipt=vad_receipt(work.audio_uri, 64000, 4),
    )
    assert store.rows['jobs', work.segment_id]['measured_held_vad_speech_seconds'] == 4


def test_untimed_parakeet_text_enters_the_context_retry():
    model = Mock()
    model.transcribe.return_value = [SimpleNamespace(text='.', timestamp={'word': []})]
    provider = ParakeetWords(model)
    worker = make_worker(vad=lambda _: [(0, 2)], retry=provider.recover_empty)
    worker.words = provider
    result = worker.process_batch([item('untimed', 4)])[0]
    assert isinstance(result, RecoveryWork)
    assert model.transcribe.call_count == 2
    assert result.measured_held_vad_speech_seconds == 2


def test_allowance_hold_retains_strict_vad_without_starting_paid_intent(setup, monkeypatch, legacy_dependencies):
    from utils.batch_pipeline import quarantine_recovery

    client, _, binding, artifacts, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setattr(quarantine_recovery, 'sync_allowed', lambda *_args, **_kwargs: False)
    row(client).pop('recovery')
    row(client)['recovery_state'] = 'held'
    recovery = setup[-1]
    recovery.stt = transcribe
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert row(client)['recovery_state'] == 'prepared'
    assert 'started_at' not in row(client)['recovery']
    assert row(client)['measured_held_vad_speech_seconds'] == 1
    legacy.assert_not_called()
    alternate.assert_not_called()
    artifacts.persist_recovery_result.assert_not_called()


@pytest.mark.parametrize('corrupt', ['input', 'speech', 'capture', 'version', 'rate', 'scalar'])
def test_bound_worker_vad_receipt_rejects_foreign_or_inconsistent_evidence(corrupt):
    store = MemoryStore()
    scheduler = Scheduler(store)
    work = item('bound', 4)
    scheduler.enqueue(work, 0)
    lease = scheduler.pull(1)[0]
    receipt = vad_receipt(work.audio_uri, 64000, 2)
    measured = 2
    if corrupt == 'input':
        receipt['input_uri_sha256'] = 'f' * 64
    elif corrupt == 'speech':
        receipt['speech_samples'] = 64001
    elif corrupt == 'capture':
        receipt['captured_samples'] = 16000
    elif corrupt == 'version':
        receipt['version'] = True
    elif corrupt == 'rate':
        receipt['sample_rate_hz'] = 8000
    else:
        measured = 1
    with pytest.raises(ValueError, match='bound VAD'):
        scheduler.fail(
            'bound',
            lease.token,
            2,
            quarantine=True,
            measured_held_vad_speech_seconds=measured,
            worker_vad_receipt=receipt,
        )
    assert store.rows['jobs', 'bound']['state'] == 'leased'


def test_bound_worker_receipt_persists_with_unchanged_empty_evidence():
    store = MemoryStore()
    scheduler = Scheduler(store)
    work = item('bound', 4)
    scheduler.enqueue(work, 0)
    lease = scheduler.pull(1)[0]
    receipt = vad_receipt(work.audio_uri, 64000, 2)
    assert scheduler.fail(
        'bound',
        lease.token,
        2,
        quarantine=True,
        padded_retry='empty',
        measured_held_vad_speech_seconds=2,
        worker_vad_receipt=receipt,
    )
    job = store.rows['jobs', 'bound']
    assert job['worker_vad_receipt'] == receipt
    assert job['worker_empty_evidence'] == {'padded_retry': 'empty', 'version': 1}


def test_short_unit_cannot_claim_measured_vad_from_zero_captured_samples():
    store = MemoryStore()
    scheduler = Scheduler(store)
    work = item('short-bound', 0.02)
    scheduler.enqueue(work, 0)
    lease = scheduler.pull(1)[0]
    with pytest.raises(ValueError, match='bound VAD'):
        scheduler.fail(
            work.segment_id,
            lease.token,
            2,
            quarantine=True,
            measured_held_vad_speech_seconds=0,
            worker_vad_receipt=vad_receipt(work.audio_uri, 0, 0),
        )


@pytest.mark.asyncio
async def test_worker_to_pump_to_scheduler_persists_bound_receipt():
    store = MemoryStore()
    scheduler = Scheduler(store)
    work = item('through-pump', 4)
    scheduler.enqueue(work, time.time())
    worker = make_worker(vad=lambda _: [(0, 2)], retry=lambda *_: [])
    await Pump(scheduler, worker).run_once()
    job = store.rows['jobs', work.segment_id]
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'held'
    assert job['worker_vad_receipt'] == vad_receipt(work.audio_uri, 64000, 2)
    assert job['measured_held_vad_speech_seconds'] == 2


def test_language_blocked_fast_path_records_strict_positive_vad_before_state_exists(monkeypatch):
    monkeypatch.setattr(local_vad, 'offline_pcm_speech_segments', lambda _: [{'start': 0.5, 'end': 2.5}])
    worker = make_worker(
        decode=lambda _: np.zeros(64000, dtype=np.float32),
        vad=Mock(side_effect=AssertionError('language blocked must skip GPU VAD')),
        retry=Mock(side_effect=AssertionError('language blocked must skip Parakeet')),
    )
    worker.language_of = lambda _: 'vi'
    worker.flight = FakeFlight()
    result = worker.process_batch([item('blocked', 4)])[0]
    assert isinstance(result, ValidationFailureWork) and result.reason == 'unsupported_language'
    assert result.measured_held_vad_speech_seconds == 2
    assert result.worker_vad_receipt == vad_receipt(item('blocked', 4).audio_uri, 64000, 2)
    worker.words.transcribe_batch.assert_not_called()


@pytest.mark.parametrize('measured', [True, -1, float('nan'), float('inf'), 5])
def test_invalid_vad_receipts_cannot_be_written(measured):
    store = MemoryStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item('bad', 4), 0)
    lease = scheduler.pull(1)[0]
    with pytest.raises(ValueError, match='measured VAD'):
        scheduler.fail('bad', lease.token, 2, quarantine=True, measured_held_vad_speech_seconds=measured)


def test_non_validation_failure_retains_measured_vad_and_pre_vad_is_unknown():
    def fail(*_):
        raise RuntimeError('synthetic')

    worker = make_worker(vad=lambda _: [(0, 2)], retry=lambda *_: [])
    worker.words.transcribe_batch.side_effect = fail
    result = worker.process_batch([item('a', 4)])[0]
    assert isinstance(result, FailedWork) and result.measured_held_vad_speech_seconds == 2
    worker.decode = fail
    result = worker.process_batch([item('a', 4)])[0]
    assert isinstance(result, FailedWork) and result.measured_held_vad_speech_seconds is None

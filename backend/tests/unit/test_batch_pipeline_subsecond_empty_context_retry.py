# Failure-Class: FC-subsecond-vad-speech-empty-retry-resends-identical-audio
"""Sub-second speech rides the same context-bearing empty retry as any other band.

The GPU worker's empty-ASR retry selects its audio by measured VAD speech.
The eligibility boundary is measured speech > 0: a unit with 0 < speech < 1s
used to fall back to byte-identical raw samples, which the recognizer answers
with blanks by the same documented start-state mechanism (a clip starting
mid-utterance decodes nothing) that the predecessor prefix and onset trim
exist to break. Synthetic PCM only; every custody, ownership, budget, debris
and kill-switch contract below is pinned unchanged.
"""

import logging
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from config.batch_pipeline_providers import ProviderConfig
from config.batch_pipeline_empty_asr import safety_net_enabled, terminal_empty_allowed
from diarizer.batch_pipeline import (
    PipelineWorker,
    bounded_window_words,
    crop_model_vad_spans,
    long_speech_handoff,
    near_empty_words,
    padded_retry_fits,
    padded_retry_seconds,
    speech_windows,
    vad_speech_spans,
)
from diarizer.batch_pipeline_context import (
    MAX_SEAM_GAP_SECONDS,
    MAX_SEAM_OVERLAP_SECONDS,
    ONSET_MARGIN_SECONDS,
    SILENT_TAIL_SECONDS,
    START_IN_SPEECH_SECONDS,
    LeftContextIndex,
    empty_retry_audio,
    select_context,
    starts_in_speech,
)
from diarizer.batch_pipeline_models import ParakeetWords
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.contracts import (
    FailedWork,
    HeldWork,
    RecoveryWork,
    ValidationFailureWork,
    WorkResult,
    vad_receipt,
)
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.word_validation import BatchValidationError, validate_words

SAMPLE_RATE = 16000


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')


def make_worker(*, vad, retry, decode=None, stream=None, config=None, words=None):
    words = words or Mock()
    if words.transcribe_batch.side_effect is None and not Mock().side_effect:
        words.transcribe_batch.side_effect = lambda batch: [[] for _ in batch]
    return PipelineWorker(
        language_of=lambda _: 'en',
        stream_of=stream,
        decode=decode or (lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32)),
        vad=vad,
        words_providers={'parakeet': words},
        diarizers={'pyannote': lambda _: {'turns': []}},
        recover_words=retry,
        persist=lambda work, payload: 'result://' + work.segment_id,
        io_concurrency=1,
        config=config,
    )


def successor(previous, key='s', duration=4, gap=0.0):
    """The next capture unit of the same owner/stream after ``previous``."""
    return type(previous)(
        key,
        previous.owner_id,
        previous.capture_at + previous.duration_seconds + gap,
        'audio://' + key,
        duration,
        previous.priority,
    )


def remember_tail(worker, unit, samples, spans, stream):
    worker.left_context.remember(unit, samples, spans, stream)


def flat_decode(value_for_previous=0.25, value_for_unit=0.5):
    def decode(work):
        value = value_for_previous if work.segment_id == 'p' else value_for_unit
        return np.full(int(work.duration_seconds * SAMPLE_RATE), value, dtype=np.float32)

    return decode


# ---------------------------------------------------------------------------
# Group 1: sub-second speech takes the predecessor-tail retry (the fix).
# ---------------------------------------------------------------------------


def test_subsecond_empty_asr_retries_with_predecessor_prefix():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [3.0, 3.4]}])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    result = worker.process_batch([current])[0]
    assert result.outcome == 'success'
    samples = retry.call_args.args[0]
    assert len(samples) == int(2.5 * SAMPLE_RATE) + 64000


def test_subsecond_prefix_carries_predecessor_audio_then_the_unit():
    retry = Mock(return_value=[])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([current])
    samples = retry.call_args.args[0]
    assert samples[0] == pytest.approx(0.25)
    assert samples[int(2.5 * SAMPLE_RATE)] == pytest.approx(0.5)
    assert samples[-1] == pytest.approx(0.5)


def test_subsecond_retry_offset_maps_prefix_words_out_of_the_unit():
    retry = Mock(
        return_value=[
            {'word': 'predecessor', 'timestamp': [0.1, 0.4]},
            {'word': 'recovered', 'timestamp': [3.0, 3.4]},
        ]
    )
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    assert worker.process_batch([current])[0].outcome == 'success'
    assert [w['word'] for w in saved['s']['words']] == ['recovered']
    assert saved['s']['words'][0]['timestamp'] == pytest.approx([0.5, 0.9])


def test_subsecond_straddling_retry_word_clamps_to_capture_start():
    retry = Mock(return_value=[{'word': 'seam', 'timestamp': [2.3, 2.7]}])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    assert worker.process_batch([current])[0].outcome == 'success'
    assert saved['s']['words'][0]['timestamp'] == pytest.approx([0.0, 0.2])


def test_subsecond_prefix_words_never_double_count_asr_words():
    retry = Mock(
        return_value=[
            {'word': 'predecessor', 'timestamp': [0.1, 0.4]},
            {'word': 'recovered', 'timestamp': [3.0, 3.4]},
        ]
    )
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    worker.process_batch([current])
    assert len(saved['s']['words']) == 1


def test_subsecond_retry_runs_exactly_once():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [3.0, 3.4]}])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([current])
    assert retry.call_count == 1


def test_subsecond_retry_reads_the_predecessor_speech_run_onset():
    retry = Mock(return_value=[])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    # Speech ending at 4.0 crosses the seam at 4.0 (>= seam - 0.3): the prefix
    # starts at the run onset 2.0 minus the 0.5s margin.
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2.0, 4.0)], 'same-device')
    worker.process_batch([current])
    assert len(retry.call_args.args[0]) == int((2.5 + 4) * SAMPLE_RATE)


def test_subsecond_predecessor_ending_in_silence_prefixes_silent_tail():
    retry = Mock(return_value=[])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(0, 1)], 'same-device')
    worker.process_batch([current])
    assert len(retry.call_args.args[0]) == int((SILENT_TAIL_SECONDS + 4) * SAMPLE_RATE)


def test_subsecond_prefix_is_bounded_by_the_padded_room():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [2.5, 2.9]}])
    previous = item('p', 4)
    current = successor(previous)
    config = ProviderConfig(max_padded_seconds=10, window_seconds=4, context_seconds=1)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
        config=config,
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    assert worker.process_batch([current])[0].outcome == 'success'
    # room = (min(120, 10) - 4 - 4)s = 2s of predecessor tail.
    assert len(retry.call_args.args[0]) == int((2 + 4) * SAMPLE_RATE)
    assert saved['s']['words'][0]['timestamp'] == pytest.approx([0.5, 0.9])


def test_subsecond_unit_at_the_padded_room_limit_keeps_raw_samples():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [0.3, 0.7]}])
    config = ProviderConfig(max_padded_seconds=8, window_seconds=4, context_seconds=1)
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=retry, config=config)
    assert worker.process_batch([item('a', 4)])[0].outcome == 'success'
    assert len(retry.call_args.args[0]) == 64000


def test_oversize_unit_keeps_raw_samples_and_holds_for_fenced_recovery():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [0.3, 0.7]}])
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=retry)
    results = worker.process_batch([item('a', 118)])
    assert len(results) == 1 and isinstance(results[0], RecoveryWork)
    assert results[0].reason == 'empty_asr' and results[0].padded_retry == 'skipped_oversize'
    assert len(retry.call_args.args[0]) == 118 * SAMPLE_RATE


def test_earlier_flights_tail_is_reused_for_a_later_subsecond_unit():
    calls = []

    def model_transcribe(arrays, **_):
        calls.append([len(a) for a in arrays])
        first = len(calls) == 1
        return [
            SimpleNamespace(
                text='first' if first else '',
                timestamp={'word': [{'word': 'first', 'start': 2, 'end': 3}] if first else []},
            )
            for _ in arrays
        ]

    provider = ParakeetWords(SimpleNamespace(transcribe=model_transcribe))
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda s: [(2, 4)] if abs(float(s[0]) - 0.25) < 1e-6 else [(0.2, 0.8)],
        retry=provider.recover_empty,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    worker.words = provider
    assert worker.process_batch([previous])[0].outcome == 'success'
    retry_mock = Mock(return_value=[{'word': 'recovered', 'timestamp': [3.0, 3.4]}])
    worker.recover_words = retry_mock
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    assert worker.process_batch([current])[0].outcome == 'success'
    assert len(retry_mock.call_args.args[0]) == int(2.5 * SAMPLE_RATE) + 64000


def test_same_flight_predecessor_serves_a_subsecond_unit():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [3.0, 3.4]}])
    previous = item('p', 4)
    current = successor(previous)
    words = Mock()
    words.transcribe_batch.side_effect = lambda batch: [
        [{'word': 'hello', 'timestamp': [1.0, 1.5]}] if abs(float(a[0]) - 0.25) < 1e-6 else [] for a in batch
    ]
    worker = make_worker(
        vad=lambda s: [(2, 4)] if abs(float(s[0]) - 0.25) < 1e-6 else [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
        words=words,
    )
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://x'
    results = worker.process_batch([previous, current])
    by_id = {result.segment_id: result for result in results}
    assert by_id['p'].outcome == 'success'
    assert by_id['s'].outcome == 'success'
    assert len(retry.call_args.args[0]) == int(2.5 * SAMPLE_RATE) + 64000


def test_empty_predecessor_tail_still_serves_a_subsecond_unit():
    retry = Mock(side_effect=[[], [{'word': 'recovered', 'timestamp': [3.0, 3.4]}]])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    results = worker.process_batch([previous, current])
    by_id = {result.segment_id: result for result in results}
    # The empty predecessor itself holds with a raw retry; the surviving unit
    # still retries with the tail the flight remembered before the failure.
    assert isinstance(by_id['p'], RecoveryWork) and by_id['p'].padded_retry == 'empty'
    assert by_id['s'].outcome == 'success'
    assert retry.call_count == 2
    # The flight remembered p's own speech only inside [0.2, 0.8]; with no run
    # crossing the seam the tail is the 1s silent ending.
    assert len(retry.call_args_list[1].args[0]) == int((SILENT_TAIL_SECONDS + 4) * SAMPLE_RATE)


def test_subsecond_gap_beyond_seam_tolerance_gets_raw_fallback():
    retry = Mock(return_value=[])
    previous = item('p', 4)
    current = successor(previous, gap=1.5)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([current])
    assert len(retry.call_args.args[0]) == 64000


def test_subsecond_overlap_beyond_tolerance_gets_raw_fallback():
    retry = Mock(return_value=[])
    previous = item('p', 4)
    current = successor(previous, gap=-0.8)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([current])
    assert len(retry.call_args.args[0]) == 64000


def test_subsecond_other_stream_gets_raw_fallback():
    retry = Mock(return_value=[])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda unit: 'device-a' if unit.segment_id == 'p' else 'device-b',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'device-a')
    worker.process_batch([current])
    assert len(retry.call_args.args[0]) == 64000


def test_subsecond_overlap_within_tolerance_trims_the_replayed_audio():
    retry = Mock(return_value=[{'word': 'seam', 'timestamp': [2.8, 3.2]}])
    previous = item('p', 4)
    current = successor(previous, gap=-0.5)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    assert worker.process_batch([current])[0].outcome == 'success'
    # 0.5s of the predecessor tail overlaps the unit and is never replayed.
    assert len(retry.call_args.args[0]) == int((2.0 + 4) * SAMPLE_RATE)
    assert saved['s']['words'][0]['timestamp'] == pytest.approx([0.8, 1.2])


# ---------------------------------------------------------------------------
# Group 2: the eligibility boundary is measured speech > 0, not >= 1.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('vad_spans', [([(0.1, 0.5)]), ([(0.2, 0.8)]), ([(0.3, 0.9)])])
def test_every_subsecond_band_prefixes_the_predecessor(vad_spans):
    retry = Mock(return_value=[])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: vad_spans,
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([current])
    assert len(retry.call_args.args[0]) > 64000


@pytest.mark.parametrize('vad_spans', [([(1.0, 2.0)]), ([(0, 1.2)]), ([(0, 4)])])
def test_bands_at_or_above_one_second_keep_the_predecessor_retry(vad_spans):
    retry = Mock(return_value=[])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: vad_spans,
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([current])
    assert len(retry.call_args.args[0]) > 64000


def test_gate_reads_measured_speech_not_unit_duration():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [14.0, 14.4]}])
    previous = item('p', 4)
    current = successor(previous, duration=12)
    worker = make_worker(
        vad=lambda _: [(5.0, 5.4)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(value_for_unit=0.5),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    assert worker.process_batch([current])[0].outcome == 'success'
    assert len(retry.call_args.args[0]) == int(2.5 * SAMPLE_RATE) + 12 * SAMPLE_RATE


def test_silence_units_never_reach_the_retry():
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [], retry=retry)
    results = worker.process_batch([item('a', 4)])
    assert retry.call_count == 0
    assert isinstance(results[0], WorkResult)


def test_no_predecessor_onset_near_zero_keeps_bytes_identical():
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=retry)
    worker.process_batch([item('a', 4)])
    sent = retry.call_args.args[0]
    assert len(sent) == 64000 and sent[0] == pytest.approx(0.5) and sent[-1] == pytest.approx(0.5)


def test_no_predecessor_onset_trim_starts_one_second_before_speech():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [1.2, 1.6]}])
    worker = make_worker(vad=lambda _: [(3.0, 3.5)], retry=retry)
    saved = {}
    worker.persist = lambda work, payload: saved.update(payload) or 'result://a'
    assert worker.process_batch([item('a', 6)])[0].outcome == 'success'
    assert len(retry.call_args.args[0]) == 4 * SAMPLE_RATE
    assert saved['words'][0]['timestamp'] == pytest.approx([3.2, 3.6])


def test_onset_trim_clamps_at_capture_start():
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [(0.5, 0.9)], retry=retry)
    worker.process_batch([item('a', 4)])
    assert len(retry.call_args.args[0]) == 4 * SAMPLE_RATE


def test_earliest_speech_span_wins_the_onset_trim():
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [(1.5, 2.0), (3.0, 3.5)], retry=retry)
    worker.process_batch([item('a', 6)])
    assert len(retry.call_args.args[0]) == int(5.5 * SAMPLE_RATE)


def test_onset_trim_retains_every_later_speech_span():
    retry = Mock(return_value=[])
    samples = np.linspace(0.1, 0.4, 6 * SAMPLE_RATE, dtype=np.float32)
    worker = make_worker(vad=lambda _: [(1.5, 2.0), (3.0, 3.5)], retry=retry, decode=lambda work: samples)
    worker.process_batch([item('a', 6)])
    sent = retry.call_args.args[0]
    assert sent[0] == pytest.approx(samples[int(0.5 * SAMPLE_RATE)])
    assert sent[-1] == pytest.approx(samples[-1])


def test_subsecond_and_full_band_predecessors_in_one_flight():
    retry = Mock(return_value=[])
    previous = item('p', 4)
    short = successor(previous, key='s', duration=4)
    long = successor(previous, key='l', duration=6)
    worker = make_worker(
        vad=lambda s: [(0.2, 0.8)] if abs(float(s[0]) - 0.5) < 1e-6 else [(0, 5)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([short, long])
    lengths = sorted(len(call.args[0]) for call in retry.call_args_list)
    assert lengths[0] > 4 * SAMPLE_RATE and lengths[1] > 6 * SAMPLE_RATE


def test_shadow_unit_subsecond_empty_also_prefixes_the_retry():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [3.0, 3.4]}])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    shadow = replace(current, shadow=True)
    result = worker.process_batch([shadow])[0]
    assert result.outcome == 'success'
    assert len(retry.call_args.args[0]) == int(2.5 * SAMPLE_RATE) + 64000


# ---------------------------------------------------------------------------
# Group 3: empty_retry_audio / LeftContextIndex selection, directly.
# ---------------------------------------------------------------------------


def index_with(tail=None):
    index = Mock()
    index.lookup = Mock(return_value=tail)
    return index


def retry_state(samples, onset=0.2, end=0.8, stream=None, unit=None):
    return {
        'samples': samples,
        'item': unit or item('a', len(samples) / SAMPLE_RATE),
        'speech_spans': [{'start': onset, 'end': end}],
        'stream': stream,
    }


def real_tailed_index(previous, value=0.25):
    index = LeftContextIndex(max_seconds=8, max_units=4)
    index.remember(previous, np.full(64000, value, dtype=np.float32), [(2, 4)], 'capture:x')
    return index


def test_context_prefix_precedes_the_whole_unit():
    samples = np.full(32000, 0.5, dtype=np.float32)
    tail = np.full(48000, 0.25, dtype=np.float32)
    retry, offset = empty_retry_audio(retry_state(samples), index_with(tail), 272)
    assert offset == pytest.approx(-3.0)
    assert len(retry) == 80000
    assert retry[0] == pytest.approx(0.25) and retry[48000] == pytest.approx(0.5)


def test_context_prefix_casts_to_the_unit_dtype():
    previous = item('p', 4)
    index = real_tailed_index(previous)
    unit = successor(previous)
    samples = np.full(32000, 0.5, dtype=np.float32)
    retry, offset = empty_retry_audio(retry_state(samples, stream='capture:x', unit=unit), index, 272)
    assert offset == pytest.approx(-2.5)
    assert retry.dtype == np.float32
    assert retry[0] == pytest.approx(0.25) and retry[40000] == pytest.approx(0.5)


def test_context_prefix_truncates_to_room_keeping_the_tail_end():
    samples = np.full(32000, 0.5, dtype=np.float32)
    tail = np.full(10 * SAMPLE_RATE, 0.25, dtype=np.float32)
    retry, offset = empty_retry_audio(retry_state(samples), index_with(tail), 10)
    # room = (min(120, 10) - 2 - 4)s = 4s kept from the tail end.
    assert offset == pytest.approx(-4.0)
    assert len(retry) == 96000


def test_nonpositive_room_ignores_the_context():
    samples = np.full(118 * SAMPLE_RATE, 0.5, dtype=np.float32)
    tail = np.full(16000, 0.25, dtype=np.float32)
    retry, offset = empty_retry_audio(retry_state(samples), index_with(tail), 272)
    assert offset == 0.0 and len(retry) == len(samples)


def test_non_array_samples_pass_through():
    samples = [0.0] * 100
    retry, offset = empty_retry_audio(retry_state(samples), index_with(np.ones(10)), 272)
    assert retry is samples and offset == 0.0


def test_missing_stream_falls_back_to_the_onset_trim():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    previous = item('p', 4)
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    samples = np.full(32000, 0.5, dtype=np.float32)
    retry, offset = empty_retry_audio(retry_state(samples, stream=None), index, 272)
    assert offset == 0.0 and len(retry) == 32000


def test_lookup_miss_falls_back_to_onset_trim():
    samples = np.arange(96000, dtype=np.float32) / 32768
    retry, offset = empty_retry_audio(retry_state(samples, onset=0.2, stream='capture:x'), index_with(None), 272)
    # Onset 0.2s is inside the 1s preroll: the trim clamps at 0 and the bytes
    # stay identical.
    assert offset == 0.0 and len(retry) == len(samples)


def test_lookup_miss_with_late_onset_trims_the_leading_silence():
    samples = np.arange(96000, dtype=np.float32) / 32768
    retry, offset = empty_retry_audio(
        retry_state(samples, onset=1.5, end=2.0, stream='capture:x'), index_with(None), 272
    )
    assert offset == pytest.approx(0.5)
    assert len(retry) == int(5.5 * SAMPLE_RATE)
    assert retry[0] == pytest.approx(samples[int(0.5 * SAMPLE_RATE)])


def test_fallback_trim_clamps_at_zero():
    samples = np.arange(32000, dtype=np.float32) / 32768
    retry, offset = empty_retry_audio(retry_state(samples), index_with(None), 272)
    assert offset == 0.0 and len(retry) == 32000


def test_fallback_trim_uses_the_earliest_span():
    samples = np.arange(160000, dtype=np.float32) / 32768
    state = retry_state(samples, onset=1.5, end=2.0)
    state['speech_spans'] = [{'start': 1.5, 'end': 2.0}, {'start': 3.0, 'end': 3.5}]
    retry, offset = empty_retry_audio(state, index_with(None), 272)
    assert offset == pytest.approx(0.5)
    assert len(retry) == int(9.5 * SAMPLE_RATE)


def test_fallback_without_spans_keeps_everything():
    samples = np.arange(32000, dtype=np.float32) / 32768
    state = retry_state(samples)
    state['speech_spans'] = []
    retry, offset = empty_retry_audio(state, index_with(None), 272)
    assert offset == 0.0 and len(retry) == 32000


def test_select_context_starts_at_crossing_onset_minus_margin():
    samples = np.zeros(8 * SAMPLE_RATE, dtype=np.float32)
    first, last = select_context(samples, [(2.0, 8.0)], 8.0)
    assert first == int((2.0 - ONSET_MARGIN_SECONDS) * SAMPLE_RATE) and last == len(samples)


def test_select_context_clamps_to_max_seconds_floor():
    samples = np.zeros(8 * SAMPLE_RATE, dtype=np.float32)
    first, _ = select_context(samples, [(0.5, 8.0)], 3.0)
    assert first == int((8.0 - 3.0) * SAMPLE_RATE)


def test_select_context_treats_speech_within_margin_as_crossing():
    samples = np.zeros(8 * SAMPLE_RATE, dtype=np.float32)
    first, _ = select_context(samples, [(1.0, 7.7)], 8.0)
    assert first == int((1.0 - ONSET_MARGIN_SECONDS) * SAMPLE_RATE)


def test_select_context_silent_predecessor_keeps_a_short_tail():
    samples = np.zeros(8 * SAMPLE_RATE, dtype=np.float32)
    first, _ = select_context(samples, [], 8.0)
    assert first == int((8.0 - SILENT_TAIL_SECONDS) * SAMPLE_RATE)


def test_select_context_rejects_empty_samples_and_nonpositive_budget():
    assert select_context(np.zeros(0, dtype=np.float32), [(0, 1)], 8.0) is None
    assert select_context(np.zeros(1000, dtype=np.float32), [(0, 0.06)], 0.0) is None


def test_select_context_never_yields_an_empty_range():
    samples = np.zeros(SAMPLE_RATE // 2, dtype=np.float32)
    first, last = select_context(samples, [(0, 0.03)], 8.0)
    assert 0 <= first < last <= len(samples)


def test_index_remember_without_stream_is_a_noop():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    index.remember(item('p', 4), np.zeros(64000, dtype=np.float32), [(2, 4)], None)
    assert not index._tails


def test_index_remember_non_array_samples_is_a_noop():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    index.remember(item('p', 4), [0.0] * 100, [(2, 4)], 'capture:x')
    assert not index._tails


def test_index_remember_zero_units_is_a_noop():
    index = LeftContextIndex(max_seconds=8, max_units=0)
    index.remember(item('p', 4), np.zeros(64000, dtype=np.float32), [(2, 4)], 'capture:x')
    assert not index._tails


def test_index_lookup_without_stream_is_none():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    unit = item('p', 4)
    index.remember(unit, np.zeros(64000, dtype=np.float32), [(2, 4)], 'capture:x')
    assert index.lookup(unit, 4.0, None) is None


def test_index_lookup_skips_the_units_own_tail():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    unit = item('p', 4)
    index.remember(unit, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    assert index.lookup(unit, 4.0, 'capture:x') is None


def test_index_lookup_serves_a_contiguous_successor():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    previous = item('p', 4)
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    context = index.lookup(successor(previous), 4.0, 'capture:x')
    assert context is not None
    assert len(context) == int(2.5 * SAMPLE_RATE)
    assert context[0] == pytest.approx(0.25, abs=1e-3)


def test_index_lookup_returns_float32_context():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    previous = item('p', 4)
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    context = index.lookup(successor(previous), 4.0, 'capture:x')
    assert context.dtype == np.float32 and context[-1] == pytest.approx(0.25, abs=1e-3)


def test_index_lookup_prefers_the_smallest_gap_tail():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    far = item('far', 4)
    near = successor(far, key='near')
    index.remember(far, np.full(64000, 0.2, dtype=np.float32), [(2, 4)], 'capture:x')
    index.remember(near, np.full(64000, 0.3, dtype=np.float32), [(2, 4)], 'capture:x')
    follower = successor(near)
    context = index.lookup(follower, 4.0, 'capture:x')
    assert context[0] == pytest.approx(0.3, abs=1e-3)


def test_index_lookup_never_serves_a_one_second_gap():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    previous = item('p', 4)
    current = successor(previous, gap=MAX_SEAM_GAP_SECONDS + 0.01)
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    assert index.lookup(current, 4.0, 'capture:x') is None


def test_index_lookup_serves_a_one_second_gap():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    previous = item('p', 4)
    current = successor(previous, gap=MAX_SEAM_GAP_SECONDS)
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    assert index.lookup(current, 4.0, 'capture:x') is not None


def test_index_lookup_never_serves_a_half_second_overlap():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    previous = item('p', 4)
    current = successor(previous, gap=-MAX_SEAM_OVERLAP_SECONDS - 0.01)
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    assert index.lookup(current, 4.0, 'capture:x') is None


def test_index_lookup_serves_a_half_second_overlap():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    previous = item('p', 4)
    current = successor(previous, gap=-MAX_SEAM_OVERLAP_SECONDS)
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    context = index.lookup(current, 4.0, 'capture:x')
    assert len(context) == int(2.0 * SAMPLE_RATE)


def test_index_lookup_trims_replayed_overlap_from_the_prefix():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    previous = item('p', 4)
    current = successor(previous, gap=-0.25)
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    context = index.lookup(current, 4.0, 'capture:x')
    assert len(context) == int(2.25 * SAMPLE_RATE)


def test_index_lookup_drops_other_generation_tails():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    previous = item('p', 4)
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    moved = replace(previous, privacy_generation=2)
    assert index.lookup(replace(successor(moved), privacy_generation=2), 4.0, 'capture:x') is None


def test_index_lookup_never_crosses_owners():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    previous = item('p', 4)
    current = successor(previous)
    current = replace(current, owner_id='other-owner')
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    assert index.lookup(current, 4.0, 'capture:x') is None


def test_index_evicts_oldest_units_beyond_capacity():
    index = LeftContextIndex(max_seconds=1, max_units=2)
    first = item('a', 2)
    second = successor(first, key='b', duration=2, gap=0.5)
    third = successor(second, key='c', duration=2, gap=0.5)
    for unit, value in ((first, 0.2), (second, 0.3), (third, 0.4)):
        index.remember(unit, np.full(32000, value, dtype=np.float32), [], 'capture:x')
    assert len(index._tails) == 2
    follower = successor(third, duration=2, gap=0.5)
    context = index.lookup(follower, 2.0, 'capture:x')
    assert context is not None and context[0] == pytest.approx(0.4, abs=1e-3)


def test_index_expires_tails_after_ttl():
    ticks = iter([100.0, 701.0])
    index = LeftContextIndex(max_seconds=8, max_units=4, clock=lambda: next(ticks))
    previous = item('p', 4)
    index.remember(previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'capture:x')
    assert index.lookup(successor(previous), 4.0, 'capture:x') is None


def test_index_tail_holds_at_most_max_seconds():
    index = LeftContextIndex(max_seconds=2, max_units=4)
    unit = item('p', 4)
    index.remember(unit, np.zeros(64000, dtype=np.float32), [(2, 4)], 'capture:x')
    tail = next(iter(index._tails.values()))
    assert len(tail.pcm) == 2 * SAMPLE_RATE


def test_index_tail_records_the_capture_end():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    unit = item('p', 4)
    index.remember(unit, np.zeros(64000, dtype=np.float32), [(2, 4)], 'capture:x')
    tail = next(iter(index._tails.values()))
    assert tail.end_at == pytest.approx(unit.capture_at + 4.0, abs=1e-3)


def test_index_tail_quantizes_to_int16():
    index = LeftContextIndex(max_seconds=8, max_units=4)
    unit = item('p', 4)
    index.remember(unit, np.full(64000, 2.0, dtype=np.float32), [(2, 4)], 'capture:x')
    tail = next(iter(index._tails.values()))
    assert tail.pcm.dtype == np.int16 and tail.pcm[0] == 32767


# ---------------------------------------------------------------------------
# Group 4: worker records, receipts and logs for sub-second empties.
# ---------------------------------------------------------------------------


def test_subsecond_recovery_leaves_no_failure_count():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [3.0, 3.4]}])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([current])
    assert worker.counts['failed'] == 0


def test_subsecond_empty_yields_recovery_work_with_the_empty_token():
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=retry)
    results = worker.process_batch([item('a', 4)])
    assert len(results) == 1 and isinstance(results[0], RecoveryWork)
    assert results[0].reason == 'empty_asr' and results[0].padded_retry == 'empty'
    assert results[0].padded_retry_empty is True
    assert worker.counts['failed'] == 1


def test_subsecond_recovery_work_carries_the_measured_vad_speech():
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=retry)
    result = worker.process_batch([item('a', 4)])[0]
    assert result.measured_held_vad_speech_seconds == pytest.approx(0.6)


def test_subsecond_recovery_receipt_binds_input_samples():
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=retry)
    result = worker.process_batch([item('a', 4)])[0]
    receipt = result.worker_vad_receipt
    assert receipt['speech_samples'] == 9600 and receipt['captured_samples'] == 64000


def test_subsecond_recovered_result_carries_speech_accounting():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [3.0, 3.4]}])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    worker.process_batch([current])
    assert saved['s']['speech_seconds'] == pytest.approx(0.6)
    assert saved['s']['audio_seconds'] == pytest.approx(4.0)


def test_retry_prefix_does_not_count_as_first_pass_left_context():
    retry = Mock(return_value=[])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([current])
    assert worker.counts['left_context'] == 0


def test_first_pass_attach_covers_subsecond_units_independent_of_the_retry():
    calls = []

    def model_transcribe(arrays, **_):
        calls.append([len(a) for a in arrays])
        return [SimpleNamespace(text='', timestamp={'word': []}) for _ in arrays]

    provider = ParakeetWords(SimpleNamespace(transcribe=model_transcribe))
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.1, 0.6)],
        retry=provider.recover_empty,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
        config=ProviderConfig(asr_left_context_seconds=2),
    )
    worker.words = provider
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([current])
    # The unit's speech starts at 0.1s <= 0.5: the first pass is already
    # prefixed with the predecessor tail (config-gated); this contract predates
    # the retry gate. The second call is the adapter retry with its synthetic
    # silence margins.
    assert calls[0][0] == int(2.5 * SAMPLE_RATE) + 64000
    # 6.5s of prefixed retry audio + the adapter's 2s+2s synthetic margins.
    assert calls[1][0] == int((2.5 + 4) * SAMPLE_RATE) + 4 * SAMPLE_RATE


def test_mid_utterance_detection_boundary():
    assert starts_in_speech([(START_IN_SPEECH_SECONDS, 1.0)]) is True
    assert starts_in_speech([(START_IN_SPEECH_SECONDS + 0.01, 1.0)]) is False
    assert starts_in_speech([]) is False


def test_healthy_sibling_survives_a_subsecond_empty():
    retry = Mock(return_value=[])
    worker = make_worker(
        vad=lambda s: [(0.2, 0.8)] if s.size == 64000 else [(0, s.size / SAMPLE_RATE)],
        retry=retry,
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
    )
    worker.words.transcribe_batch.side_effect = lambda batch: [
        [{'word': 'hello', 'timestamp': [0.1, 0.2]}] if len(a) == 32000 else [] for a in batch
    ]
    results = worker.process_batch([item('a', 4), item('b', 2)])
    by_id = {result.segment_id: result for result in results}
    assert isinstance(by_id['a'], RecoveryWork)
    assert by_id['b'].outcome == 'success'


def test_subsecond_recovery_and_sibling_empty_in_one_flight():
    retry = Mock(side_effect=[[{'word': 'recovered', 'timestamp': [3.0, 3.4]}], []])
    previous = item('p', 4)
    current = successor(previous)
    other = item('z', 4)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda unit: 'same-device' if unit.segment_id == 's' else None,
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    results = worker.process_batch([current, other])
    by_id = {result.segment_id: result for result in results}
    assert by_id['s'].outcome == 'success'
    assert isinstance(by_id['z'], RecoveryWork)


def test_subsecond_and_full_band_hold_with_the_same_closed_reason():
    retry = Mock(return_value=[])
    worker = make_worker(
        vad=lambda s: [(0.2, 0.8)] if s.size == 64000 else [(0, s.size / SAMPLE_RATE)],
        retry=retry,
        decode=lambda work: np.full(int(work.duration_seconds * SAMPLE_RATE), 0.5, dtype=np.float32),
    )
    results = worker.process_batch([item('a', 4), item('b', 6)])
    assert all(isinstance(result, RecoveryWork) for result in results)
    assert {result.reason for result in results} == {'empty_asr'}
    assert {result.padded_retry for result in results} == {'empty'}


# ---------------------------------------------------------------------------
# Group 5: debris filtering stays measured-speech-gated at 1s.
# ---------------------------------------------------------------------------


def test_subsecond_retry_single_alnum_word_publishes():
    retry = Mock(return_value=[{'word': 'I', 'timestamp': [3.0, 3.2]}])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    assert worker.process_batch([current])[0].outcome == 'success'
    assert [w['word'] for w in saved['s']['words']] == ['I']


def test_full_band_retry_single_alnum_word_is_debris():
    retry = Mock(return_value=[{'word': 'I', 'timestamp': [3.0, 3.2]}])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(1.0, 2.0)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    results = worker.process_batch([current])
    assert isinstance(results[0], RecoveryWork)
    assert results[0].padded_retry == 'empty' and results[0].reason == 'empty_asr'


def test_debris_boundary_is_measured_speech_not_word_count():
    words = [{'word': '.', 'timestamp': [0, 0.2]}]
    assert near_empty_words(words, 0.99) is False
    assert near_empty_words(words, 1.0) is True


def test_two_alnum_words_are_never_debris_at_any_band():
    words = [{'word': 'OK', 'timestamp': [0, 0.2]}]
    assert near_empty_words(words, 0.4) is False
    assert near_empty_words(words, 12.0) is False


def test_multichar_hypothesis_is_never_debris():
    assert near_empty_words([{'word': 'hello', 'timestamp': [0, 0.4]}], 5.0) is False


def test_empty_word_list_trivially_counts_as_debris():
    assert near_empty_words([], 5.0) is True


def test_first_pass_subsecond_single_alnum_hypothesis_publishes():
    words = Mock()
    words.transcribe_batch.side_effect = lambda batch: [[{'word': 'I', 'timestamp': [0.3, 0.5]}] for _ in batch]
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=Mock(return_value=[]), words=words)
    saved = {}
    worker.persist = lambda work, payload: saved.update(payload) or 'result://a'
    result = worker.process_batch([item('a', 4)])[0]
    assert result.outcome == 'success'
    assert saved['words'][0]['word'] == 'I'


def test_first_pass_full_band_punctuation_debris_zeroes_then_retries():
    words = Mock()
    words.transcribe_batch.side_effect = lambda batch: [[{'word': '.', 'timestamp': [1.3, 1.5]}] for _ in batch]
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [3.0, 3.4]}])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(1.0, 2.0)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
        words=words,
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    saved = {}
    worker.persist = lambda work, payload: saved.update({work.segment_id: payload}) or 'result://s'
    assert worker.process_batch([current])[0].outcome == 'success'
    assert retry.call_count == 1


# ---------------------------------------------------------------------------
# Group 6: kill switches and untouched gates.
# ---------------------------------------------------------------------------


def test_safety_net_off_restores_raw_subsecond_retry(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    retry = Mock(return_value=[])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    worker.process_batch([current])
    assert len(retry.call_args.args[0]) == 64000


def test_safety_net_off_disables_the_tail_cache(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=Mock(return_value=[]))
    assert worker.left_context.max_seconds == 0


def test_safety_net_on_bounds_the_tail_cache_at_eight_seconds():
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=Mock(return_value=[]))
    assert worker.left_context.max_seconds == 8


def test_safety_net_default_is_on(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED')
    assert safety_net_enabled()


def test_fenced_gates_follow_their_kill_switches(monkeypatch):
    from config.batch_pipeline import empty_asr_disposition_enabled, empty_asr_recovery_enabled

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'false')
    assert empty_asr_recovery_enabled() is False
    assert empty_asr_disposition_enabled() is False
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    assert empty_asr_recovery_enabled() is True
    assert empty_asr_disposition_enabled() is True


def test_terminal_silence_contract_still_refuses_subsecond_speech():
    assert terminal_empty_allowed([{'start': 0.2, 'end': 0.8}]) is False


def test_terminal_silence_contract_allows_true_silence():
    assert terminal_empty_allowed([]) is True


def test_long_speech_handoff_never_fires_for_subsecond_speech():
    state = {'stt_language': '', 'speech_seconds': 0.6}
    assert long_speech_handoff(state, 'empty_asr') is False


def test_long_speech_handoff_ignores_other_reasons():
    state = {'stt_language': 'zz', 'speech_seconds': 60.0}
    assert long_speech_handoff(state, 'no_owned_words') is False


# ---------------------------------------------------------------------------
# Group 7: scheduler/pump custody contracts for the sub-second quarantine.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subsecond_empty_quarantines_attempt_one_with_closed_reason():
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=retry)
    results = worker.process_batch([item('a', 4)])
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', 4), time.time())
    lease = queue.pull(time.time())[0]
    assert await Pump(queue, worker)._publish(lease, {'a': results[0]}, set())
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['attempt'] == 1
    assert job['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}
    assert job['recovery_state'] == 'held' and not job['merge_pending']


@pytest.mark.asyncio
async def test_subsecond_quarantine_emits_the_held_for_recovery_line(caplog):
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=retry)
    results = worker.process_batch([item('a', 4)])
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', 4), time.time())
    lease = queue.pull(time.time())[0]
    with caplog.at_level('INFO'):
        await Pump(queue, worker)._publish(lease, {'a': results[0]}, set())
    held = next(r.getMessage() for r in caplog.records if 'event=batch_empty_ladder' in r.getMessage())
    assert (
        held == 'event=batch_empty_ladder outcome=held_for_recovery attempt=1 recovery=held '
        'stage=assemble_words worker_reason=empty_asr'
    )
    held_record = next(r for r in caplog.records if 'event=batch_empty_ladder' in r.getMessage())
    assert held_record.levelno == logging.INFO
    assert not [r for r in caplog.records if 'event=batch_quarantined' in r.getMessage()]


@pytest.mark.asyncio
async def test_quarantined_subsecond_job_is_not_released():
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [(0.2, 0.8)], retry=retry)
    results = worker.process_batch([item('a', 4)])
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', 4), time.time())
    lease = queue.pull(time.time())[0]
    await Pump(queue, worker)._publish(lease, {'a': results[0]}, set())
    assert queue.pull(time.time() + 600) == []


@pytest.mark.asyncio
async def test_subsecond_recovered_retry_publishes_a_result():
    retry = Mock(return_value=[{'word': 'recovered', 'timestamp': [3.0, 3.4]}])
    previous = item('p', 4)
    current = successor(previous)
    worker = make_worker(
        vad=lambda _: [(0.2, 0.8)],
        retry=retry,
        stream=lambda _: 'same-device',
        decode=flat_decode(),
    )
    remember_tail(worker, previous, np.full(64000, 0.25, dtype=np.float32), [(2, 4)], 'same-device')
    result = worker.process_batch([current])[0]
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(current, time.time())
    lease = queue.pull(time.time())[0]
    assert await Pump(queue, worker)._publish(lease, {'s': result}, set())
    job = store.rows['jobs', 's']
    assert job['state'] != 'quarantined'


@pytest.mark.asyncio
async def test_full_band_quarantine_shape_is_unchanged():
    retry = Mock(return_value=[])
    worker = make_worker(vad=lambda _: [(1.0, 2.0)], retry=retry)
    results = worker.process_batch([item('a', 4)])
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', 4), time.time())
    lease = queue.pull(time.time())[0]
    await Pump(queue, worker)._publish(lease, {'a': results[0]}, set())
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['attempt'] == 1
    assert job['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}


def test_quarantine_bumps_the_owner_revision_and_clears_the_lease():
    from utils.batch_pipeline.retry_policy import quarantine_job

    owners = {}
    puts = []

    class Tx:
        def get(self, kind, key):
            return owners[key]

        def put(self, kind, key, value):
            puts.append((kind, key))
            owners[key] = value

    job = {'owner_key': 'owner-a', 'attempt': 1, 'duration_seconds': 4.0}
    owners['owner-a'] = {'revision': 7}
    quarantine_job(Tx(), job, 1.0, 'worker_failed')
    assert owners['owner-a']['revision'] == 8
    assert puts == [('owners', 'owner-a')]
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'held'
    assert job['token'] == '' and job['lease_until'] == 0.0 and job['merge_pending'] is False
    assert job['measured_held_vad_speech_seconds'] is None


def test_recovery_work_contract_keeps_the_closed_token_set():
    assert RecoveryWork('a', padded_retry_empty=True).padded_retry == 'empty'
    with pytest.raises(ValueError):
        RecoveryWork('a', padded_retry='identical')
    with pytest.raises(ValueError):
        RecoveryWork('a', padded_retry='recovered', padded_retry_empty=True)


def test_skipped_oversize_and_long_speech_tokens_stay_closed():
    assert RecoveryWork('a', padded_retry='skipped_oversize').padded_retry_empty is False
    assert RecoveryWork('a', padded_retry='skipped_long_speech').padded_retry_empty is False


def test_validation_failure_requires_closed_codes():
    assert ValidationFailureWork('a', 'assemble_words', 'empty_asr').reason == 'empty_asr'
    with pytest.raises(ValueError):
        ValidationFailureWork('a', 'assemble_words', 'mystery')


# ---------------------------------------------------------------------------
# Group 8: padded budget arithmetic.
# ---------------------------------------------------------------------------


def test_padded_retry_seconds_adds_synthetic_edges():
    assert padded_retry_seconds(np.zeros(32000, dtype=np.float32)) == pytest.approx(8.0)
    assert padded_retry_seconds(np.zeros(8 * SAMPLE_RATE, dtype=np.float32)) == pytest.approx(12.0)


def test_padded_retry_fits_the_shared_budget():
    assert padded_retry_fits(np.zeros(32000, dtype=np.float32), 272) is True
    assert padded_retry_fits(np.zeros(117 * SAMPLE_RATE, dtype=np.float32), 272) is False
    assert padded_retry_fits(np.zeros(31 * SAMPLE_RATE, dtype=np.float32), 34) is False


def test_subsecond_unit_retry_always_fits_the_default_budget():
    assert padded_retry_fits(np.zeros(4 * SAMPLE_RATE, dtype=np.float32), 272) is True


def test_prefixed_subsecond_retry_fits_the_default_budget():
    samples = np.zeros(int(2.5 * SAMPLE_RATE) + 4 * SAMPLE_RATE, dtype=np.float32)
    assert padded_retry_fits(samples, 272) is True


# ---------------------------------------------------------------------------
# Group 9: word ownership and clock mapping primitives.
# ---------------------------------------------------------------------------


def test_bounded_words_keep_midpoints_inside_capture():
    words = [{'word': 'hi', 'timestamp': [0.2, 0.8]}]
    assert bounded_window_words(words, 4.0) == words


def test_bounded_words_drop_midpoints_outside_capture():
    # start < duration passes the clock gate; a midpoint at/past the capture is
    # never owned by the unit.
    assert bounded_window_words([{'word': 'ghost', 'timestamp': [3.95, 4.05]}], 4.0) == []


def test_bounded_words_reject_nonfinite_clocks():
    with pytest.raises(BatchValidationError) as raised:
        bounded_window_words([{'word': 'x', 'timestamp': [float('nan'), 1.0]}], 4.0)
    assert raised.value.reason == 'word_clock'


def test_bounded_words_reject_reversed_clocks():
    with pytest.raises(BatchValidationError) as raised:
        bounded_window_words([{'word': 'x', 'timestamp': [1.0, 0.5]}], 4.0)
    assert raised.value.reason == 'word_clock'


def test_bounded_words_drop_wholly_negative_clocks():
    # A clock that ends before the capture begins is a TDT start-state ghost:
    # unowned by the window, never a reason to fail its real transcript.
    assert bounded_window_words([{'word': 'x', 'timestamp': [-3.0, -1.0]}], 4.0) == []


def test_bounded_words_reject_out_of_order_sequences():
    with pytest.raises(BatchValidationError) as raised:
        bounded_window_words([{'word': 'a', 'timestamp': [1.0, 1.5]}, {'word': 'b', 'timestamp': [0.5, 0.8]}], 4.0)
    assert raised.value.reason == 'word_sequence'


def test_bounded_words_reject_blank_tokens():
    with pytest.raises(BatchValidationError) as raised:
        bounded_window_words([{'word': '   ', 'timestamp': [0.5, 0.8]}], 4.0)
    assert raised.value.reason == 'word_sequence'


def test_bounded_words_clamp_edge_straddling_clocks():
    result = bounded_window_words([{'word': 'edge', 'timestamp': [-0.2, 0.3]}], 4.0)
    assert result[0]['timestamp'] == [0.0, 0.3]


def test_validate_words_tolerates_one_frame_of_overshoot():
    words = [{'word': 'edge', 'timestamp': [0.0, 4.005]}]
    assert validate_words(words, 4.0)[0]['timestamp'] == [0.0, 4.005]


def test_validate_words_reject_clocks_past_capture():
    with pytest.raises(BatchValidationError) as raised:
        validate_words([{'word': 'x', 'timestamp': [0.0, 4.2]}], 4.0)
    assert raised.value.reason == 'word_clock'


def test_validate_words_accepts_empty_hypotheses():
    assert validate_words([], 4.0) == []


# ---------------------------------------------------------------------------
# Group 10: VAD geometry primitives the retry depends on.
# ---------------------------------------------------------------------------


def test_vad_speech_spans_merge_adjacent_spans():
    merged = vad_speech_spans([(0.2, 0.5), (0.5, 0.8)], 8 * SAMPLE_RATE)
    assert merged == [{'start': pytest.approx(0.2), 'end': pytest.approx(0.8)}]


def test_vad_speech_spans_round_to_samples():
    merged = vad_speech_spans([(0.0, 0.6001)], 8 * SAMPLE_RATE)
    assert merged[0]['end'] == pytest.approx(9602 / SAMPLE_RATE)


def test_vad_speech_spans_drop_reversed_spans():
    assert vad_speech_spans([(0.5, 0.2)], 8 * SAMPLE_RATE) == []


def test_vad_speech_spans_nan_bounds_never_round_silently():
    with pytest.raises(ValueError):
        vad_speech_spans([(float('nan'), 0.5)], 8 * SAMPLE_RATE)


def test_crop_model_spans_clip_the_end_to_capture():
    assert crop_model_vad_spans([(0.2, 9.0)], 4.0) == [(0.2, 4.0)]


def test_crop_model_spans_reject_wholly_out_of_buffer_spans():
    with pytest.raises(BatchValidationError) as raised:
        crop_model_vad_spans([(4.5, 5.0)], 4.0)
    assert raised.value.reason == 'vad_bounds'


def test_crop_model_spans_reject_nonfinite_bounds():
    with pytest.raises(BatchValidationError) as raised:
        crop_model_vad_spans([(0.0, float('inf'))], 4.0)
    assert raised.value.reason == 'vad_nonfinite'


def test_speech_windows_tile_a_subsecond_unit_once():
    unit = item('a', 4)
    windows = list(speech_windows(unit, np.zeros(4 * SAMPLE_RATE, dtype=np.float32), [(0.2, 0.8)], ProviderConfig()))
    assert len(windows) == 1
    # The core is the padded span (context clamped inside the capture); the
    # window itself spans to the capture end.
    assert windows[0].core_start == pytest.approx(0.0)
    assert windows[0].core_end == pytest.approx(2.8)


def test_speech_windows_pad_span_edges_with_context():
    unit = item('a', 8)
    windows = list(speech_windows(unit, np.zeros(8 * SAMPLE_RATE, dtype=np.float32), [(2.0, 4.0)], ProviderConfig()))
    assert windows[0].start == pytest.approx(0.0)


def test_speech_windows_reject_reversed_spans():
    with pytest.raises(BatchValidationError) as raised:
        list(speech_windows(item('a', 4), np.zeros(4 * SAMPLE_RATE, dtype=np.float32), [(0.8, 0.2)], ProviderConfig()))
    assert raised.value.reason == 'vad_order'


def test_speech_windows_reject_out_of_buffer_spans():
    with pytest.raises(BatchValidationError) as raised:
        list(speech_windows(item('a', 4), np.zeros(4 * SAMPLE_RATE, dtype=np.float32), [(0.0, 4.5)], ProviderConfig()))
    assert raised.value.reason == 'vad_bounds'


# ---------------------------------------------------------------------------
# Group 11: fixtures and safety helpers.
# ---------------------------------------------------------------------------


def test_vad_receipt_binds_speech_and_captured_samples():
    receipt = vad_receipt('audio://a', 64000, 0.6)
    assert receipt['speech_samples'] == 9600 and receipt['captured_samples'] == 64000


def test_bound_vad_receipt_rejects_speech_without_captured_samples():
    from utils.batch_pipeline.contracts import bound_vad_receipt

    job = {'duration_seconds': 4.0, 'audio_uri': 'audio://a'}
    assert bound_vad_receipt(job, vad_receipt('audio://a', 0, 0.6)) is False
    assert bound_vad_receipt(job, vad_receipt('audio://a', 64000, 0.6)) is True
    assert bound_vad_receipt(job, vad_receipt('audio://a', 64000, 0.0)) is True


def test_work_result_round_trip_preserves_the_core():
    result = WorkResult('a', 'audio://r', 'success')
    assert result.matches_persisted(result.to_dict())


def test_failed_work_carries_the_measured_census():
    assert FailedWork('a', 0.6, None).measured_held_vad_speech_seconds == pytest.approx(0.6)


def test_held_work_defaults_to_a_sixty_second_retry():
    assert HeldWork('a').retry_after == 60
    assert HeldWork('a', reason='').reason == ''

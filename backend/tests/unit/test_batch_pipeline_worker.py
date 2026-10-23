from dataclasses import replace
from contextlib import nullcontext
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import io
import logging
import sys
import time
import wave
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from config.batch_pipeline import worker_silence_disposition_enabled
from config.batch_pipeline_providers import ProviderConfig, provider_config
from diarizer import batch_pipeline, batch_pipeline_models
from diarizer.batch_pipeline import (
    BatchValidationError,
    PipelineWorker,
    LiveWords,
    Window,
    crop_model_vad_spans,
    pack_windows,
    speech_windows,
)
from diarizer.batch_pipeline_models import ParakeetWords, PyannoteVAD, decode_pcm16_wav
from utils.batch_pipeline.contracts import WorkItem, Priority, WorkResult, ValidationFailureWork
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.recovery_disposition import result_outcome
from utils.batch_pipeline.worker_silence import inspect_worker_silence
from utils.stt import local_vad as vad
from tests.unit.test_batch_pipeline_scheduler import MemoryStore


@pytest.fixture(autouse=True)
def _full_gpu_stages(monkeypatch):
    # This suite pins the full-stage chain. The ship-on GPU skips have their own
    # contract in test_batch_pipeline_diarization_gate.py.
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')


class Samples:
    def __init__(self, seconds):
        self.size = int(seconds * 16000)

    def __len__(self):
        return self.size

    def __getitem__(self, key):
        return Samples((key.stop - key.start) / 16000)


class Words:
    def __init__(self):
        self.calls = []

    def transcribe_batch(self, samples):
        self.calls.append([len(s) / 16000 for s in samples])
        return [[{'word': 'hello', 'timestamp': [0.1, 0.2]}] for _ in samples]


def item(key='a', duration=2):
    return WorkItem(key, 'owner-' + key, 100, 'encrypted://' + key, duration, Priority.FRESH)


def setup_worker(**kwargs):
    provider, saved, decoded, diarized, failures = Words(), {}, [], [], []

    def decode(work):
        decoded.append(work.segment_id)
        return Samples(work.duration_seconds)

    def persist(work, payload):
        saved[work.segment_id] = payload
        return 'encrypted-result://' + work.segment_id

    def diarize(samples):
        diarized.append(len(samples))
        return {'turns': []}

    settings = dict(
        language_of=lambda item: 'en',  # Synthetic English fixture.
        decode=decode,
        vad=lambda s: [(0, len(s) / 16000)],
        words_providers={'parakeet': provider},
        diarizers={'pyannote': diarize},
        persist=persist,
        on_failure=lambda i, e: failures.append((i.segment_id, e)),
    )
    settings.update(kwargs)
    return PipelineWorker(**settings), provider, saved, decoded, diarized, failures


def test_cross_user_chain_decode_once_sort_restore_and_persist():
    worker, words, saved, decoded, diarized, failures = setup_worker()
    results = worker.process_batch([item('long', 4), item('short', 2)])
    assert words.calls == [[2, 4]]
    assert decoded == ['long', 'short']
    assert len(diarized) == 2
    assert {r.segment_id for r in results} == {'long', 'short'}
    assert saved['short']['words'][0]['word'] == 'hello'
    assert not failures


def test_vad_silence_skips_models_but_persists_result():
    worker, words, saved, _, diarized, _ = setup_worker(vad=lambda s: [])
    assert worker.process_batch([item()])[0].outcome == 'silence'
    assert not words.calls and not diarized
    assert saved['a']['words'] == []
    assert saved['a']['speech_seconds'] == 0
    assert saved['a']['speech_spans'] == []


def test_failure_is_not_silence_and_siblings_survive():
    worker, _, _, _, _, failures = setup_worker(decode=lambda i: Samples(99) if i.segment_id == 'bad' else Samples(2))
    assert [r.segment_id for r in worker.process_batch([item('bad'), item('ok')])] == ['ok']
    assert failures == [('bad', 'ValueError')]


@pytest.mark.parametrize(
    'stage', ['fetch_decode', 'vad_windows', 'asr', 'word_clocks', 'assemble_words', 'diarize', 'persist']
)
def test_item_failures_log_class_and_stage_without_callback_or_private_content(stage, caplog):
    private_marker = 'synthetic-private-content-must-not-be-logged'

    def broken(*args):
        raise ValueError(private_marker)

    class BrokenWords:
        def transcribe_batch(self, samples):
            if stage == 'asr':
                return broken()
            if stage == 'word_clocks':
                # Multiple windows of one item must still emit one failure.
                return [[{'word': private_marker, 'timestamp': [-1, 0]}] for _ in samples]
            return [[] for _ in samples]

    settings = {'on_failure': None}
    if stage == 'fetch_decode':
        settings['decode'] = broken
    elif stage == 'vad_windows':
        settings['vad'] = broken
    elif stage in {'asr', 'word_clocks', 'assemble_words'}:
        settings['words_providers'] = {'parakeet': BrokenWords()}
    elif stage == 'diarize':
        settings['diarizers'] = {'pyannote': broken}
    else:
        settings['persist'] = broken
    worker, *_ = setup_worker(**settings)
    results = worker.process_batch([item(duration=60)])
    expected_reason = {'word_clocks': 'word_clock', 'assemble_words': 'empty_asr'}.get(stage)
    assert results == ([ValidationFailureWork('a', stage, expected_reason)] if expected_reason else [])
    records = [record for record in caplog.records if 'event=batch_worker_failed' in record.getMessage()]
    assert len(records) == worker.counts['failed'] == 1
    reason = {'word_clocks': 'word_clock', 'assemble_words': 'empty_asr'}.get(stage, 'unclassified')
    error_class = 'ValueError' if reason == 'unclassified' else 'BatchValidationError'
    assert (
        records[0]
        .getMessage()
        .startswith(f'event=batch_worker_failed error_class={error_class} stage={stage} segment_id=a reason={reason} ')
    )
    assert all(isinstance(value, (str, int)) for value in records[0].args)
    assert records[0].exc_info is None
    assert private_marker not in caplog.text


def test_raising_failure_logger_cannot_drop_healthy_sibling(monkeypatch, capsys):
    private_marker = 'synthetic-private-worker-error'
    active_exceptions = []

    def decode(work):
        if work.segment_id == 'bad':
            raise ValueError(private_marker)
        return Samples(work.duration_seconds)

    def broken_logger(*args):
        active_exceptions.append(sys.exc_info()[0])
        raise RuntimeError('synthetic-logger-error')

    monkeypatch.setattr(batch_pipeline.logger, 'error', broken_logger)
    worker, *_ = setup_worker(decode=decode, on_failure=None)
    assert [result.segment_id for result in worker.process_batch([item('bad'), item('good')])] == ['good']
    assert worker.counts['failed'] == 1
    assert active_exceptions == [None]
    captured = capsys.readouterr()
    assert private_marker not in captured.out + captured.err


def test_raising_handler_stream_cannot_leak_worker_error_or_drop_sibling(monkeypatch, capsys):
    private_marker = 'synthetic-private-worker-error'

    def decode(work):
        if work.segment_id == 'bad':
            raise ValueError(private_marker)
        return Samples(work.duration_seconds)

    class BrokenStream:
        writes = 0

        def write(self, message):
            self.writes += 1
            raise OSError('synthetic-handler-stream-error')

        def flush(self):
            pass

    stream = BrokenStream()
    isolated_logger = logging.Logger('batch_worker_broken_stream', logging.ERROR)
    isolated_logger.addHandler(logging.StreamHandler(stream))
    monkeypatch.setattr(batch_pipeline, 'logger', isolated_logger)
    monkeypatch.setattr(logging, 'raiseExceptions', True)
    worker, *_ = setup_worker(decode=decode, on_failure=None)
    assert [result.segment_id for result in worker.process_batch([item('bad'), item('good')])] == ['good']
    assert worker.counts['failed'] == stream.writes == 1
    captured = capsys.readouterr()
    assert 'OSError: synthetic-handler-stream-error' in captured.err
    assert private_marker not in captured.out + captured.err


def test_empty_asr_on_vad_speech_stays_failure_with_numeric_shape(caplog):
    class EmptyWords:
        def transcribe_batch(self, samples):
            return [[] for _ in samples]

    worker, _, saved, *_ = setup_worker(
        decode=lambda _: np.zeros(126400, dtype=np.float32),
        words_providers={'parakeet': EmptyWords()},
        on_failure=None,
    )
    assert worker.process_batch([item(duration=7.9)]) == [ValidationFailureWork('a', 'assemble_words', 'empty_asr')]
    assert not saved
    message = next(r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage())
    assert 'stage=assemble_words' in message and 'reason=empty_asr' in message
    assert 'samples=126400 vad_spans=1 windows=1 asr_words=0 owned_words=0' in message


@pytest.mark.parametrize('first_words', [[], [{'word': 'context', 'timestamp': [4.5, 4.8]}]])
def test_empty_unit_retries_full_capture_once_and_preserves_speech_accounting(first_words, caplog):
    class Model:
        def __init__(self):
            self.calls = []

        def transcribe(self, arrays, **kwargs):
            self.calls.append(arrays)
            if len(self.calls) == 1:
                entries = [dict(word=w['word'], start=w['timestamp'][0], end=w['timestamp'][1]) for w in first_words]
            else:
                assert kwargs['batch_size'] == 1
                assert len(arrays[0]) == 14 * 16000
                np.testing.assert_array_equal(arrays[0][32000:-32000], samples)
                assert not arrays[0][:32000].any() and not arrays[0][-32000:].any()
                entries = [{'word': 'recovered', 'start': 8, 'end': 9}]
            return [SimpleNamespace(text='synthetic' if entries else '', timestamp={'word': entries})]

    samples = np.ones(10 * 16000, dtype=np.float32)
    model = Model()
    provider = ParakeetWords(model)
    worker, _, saved, decoded, diarized, failures = setup_worker(
        decode=lambda work: samples,
        vad=lambda s: [(1, 2)],
        words_providers={'parakeet': provider},
        recover_words=provider.recover_empty,
    )
    with caplog.at_level(logging.INFO):
        assert worker.process_batch([item(duration=10)])[0].outcome == 'success'
    assert len(model.calls) == 2 and not failures
    assert saved['a']['words'] == [{'word': 'recovered', 'timestamp': [6, 7]}]
    assert saved['a']['speech_spans'] == [{'start': 1, 'end': 2}]
    assert saved['a']['speech_seconds'] == 1 and saved['a']['audio_seconds'] == 10
    assert diarized == [160000]
    assert 'event=batch_asr_recovery' in caplog.text and 'outcome=recovered' in caplog.text
    event = next(r for r in caplog.records if 'event=batch_asr_recovery' in r.getMessage())
    assert all(isinstance(value, (str, int)) for value in event.args) and event.exc_info is None
    assert 'windows=1 window_min_samples=96000 window_max_samples=96000 speech_samples=16000' in event.getMessage()


def test_recovery_padding_clocks_and_minimum_input():
    class Model:
        def transcribe(self, arrays, **kwargs):
            assert len(arrays) == 1 and arrays[0].dtype == np.float32
            assert len(arrays[0]) == 8 * 16000
            entries = [
                {'word': 'padding', 'start': 0, 'end': 1},
                {'word': 'edge', 'start': 1.8, 'end': 2.4},
                {'word': 'tail', 'start': 3.8, 'end': 4.1},
                {'word': 'padding', 'start': 5, 'end': 6},
            ]
            return [SimpleNamespace(text='synthetic', timestamp={'word': entries})]

    words = ParakeetWords(Model()).recover_empty(np.ones(32000, dtype=np.float32), 272)
    assert [w['word'] for w in words] == ['edge', 'tail']
    assert words[0]['timestamp'] == pytest.approx([0, 0.4])
    assert words[1]['timestamp'] == pytest.approx([1.8, 2])


def test_recovery_never_truncates_audio_to_fit_budget():
    class Model:
        def transcribe(self, *args, **kwargs):
            pytest.fail('oversized recovery must stay held, never transcribe a prefix')

    provider = ParakeetWords(Model())
    assert provider.recover_empty(np.ones(117 * 16000, dtype=np.float32), 272) is None
    assert provider.recover_empty(np.ones(31 * 16000, dtype=np.float32), 34) is None


def test_empty_recovery_remains_failure_and_healthy_sibling_survives(caplog):
    calls = []

    class EmptyWords:
        def transcribe_batch(self, arrays):
            return [[] for _ in arrays]

    def recover(samples, budget):
        calls.append(len(samples))
        return [] if len(samples) == 32000 else [{'word': 'synthetic', 'timestamp': [0, 1]}]

    worker, _, saved, _, diarized, failures = setup_worker(
        words_providers={'parakeet': EmptyWords()}, recover_words=recover
    )
    results = worker.process_batch([item(), item('b', 3)])
    assert ValidationFailureWork('a', 'assemble_words', 'empty_asr') in results
    assert [r.segment_id for r in results if isinstance(r, WorkResult)] == ['b']
    assert calls == [32000, 48000] and set(saved) == {'b'}
    assert failures == [('a', 'BatchValidationError')] and diarized == [48000]
    assert 'reason=empty_asr' in caplog.text


@pytest.mark.parametrize('mode', ['silence', 'nonempty', 'invalid'])
def test_recovery_only_runs_for_valid_empty_speech(mode):
    class Provider:
        def transcribe_batch(self, arrays):
            return [[{'word': 'synthetic', 'timestamp': [-1 if mode == 'invalid' else 0, 1]}] for _ in arrays]

    worker, *_ = setup_worker(
        vad=lambda s: [] if mode == 'silence' else [(0, 2)],
        words_providers={'parakeet': Provider()},
        recover_words=lambda *args: pytest.fail('must not retry silence, successful words or malformed clocks'),
    )
    results = worker.process_batch([item()])
    assert any(isinstance(r, WorkResult) for r in results) == (mode != 'invalid')


def test_recovery_fatal_cuda_quarantines_chain():
    class EmptyWords:
        def transcribe_batch(self, arrays):
            return [[] for _ in arrays]

    def recover(*args):
        raise RuntimeError('CUDA error: illegal memory access')

    worker, *_ = setup_worker(words_providers={'parakeet': EmptyWords()}, recover_words=recover)
    with pytest.raises(RuntimeError, match='fatal CUDA'):
        worker.process_batch([item()])
    with pytest.raises(RuntimeError, match='restart required'):
        worker.process_batch([item('b')])


def test_validation_reason_rejects_free_form_content():
    with pytest.raises(ValueError, match='^invalid batch validation reason$'):
        BatchValidationError('synthetic-private-provider-message')


def test_numeric_diagnostics_preserve_iterable_hypothesis_support():
    class IterableWords:
        def transcribe_batch(self, samples):
            return [(word for word in [{'word': 'synthetic', 'timestamp': [0.1, 0.2]}]) for _ in samples]

    worker, _, saved, *_ = setup_worker(words_providers={'parakeet': IterableWords()})
    assert worker.process_batch([item()])
    assert len(saved['a']['words']) == 1


def test_context_only_hypothesis_is_observable_failure_not_silence(caplog):
    class ContextWords:
        def transcribe_batch(self, samples):
            return [[{'word': 'synthetic', 'timestamp': [4.5, 4.8]}]]

    worker, _, saved, *_ = setup_worker(
        decode=lambda _: np.zeros(160320, dtype=np.float32),
        vad=lambda _: [(1, 2)],
        words_providers={'parakeet': ContextWords()},
        on_failure=None,
    )
    assert worker.process_batch([item(duration=10.02)]) == [
        ValidationFailureWork('a', 'assemble_words', 'no_owned_words')
    ]
    assert not saved
    message = next(r.getMessage() for r in caplog.records if 'event=batch_worker_failed' in r.getMessage())
    assert 'reason=no_owned_words' in message and 'asr_words=1 owned_words=0' in message


def test_fractional_window_rebase_uses_actual_sample_origin():
    class EndWords:
        def transcribe_batch(self, samples):
            duration = len(samples[0]) / 16000
            return [[{'word': 'synthetic', 'timestamp': [duration - 0.1, duration + 0.01]}]]

    samples = np.zeros(126400, dtype=np.float32)
    spans = [(5.123456, 7.88)]
    capture = item(duration=7.9)
    window = next(speech_windows(capture, samples, spans, ProviderConfig()))
    assert window.start == int(1.123456 * 16000) / 16000
    # Rebasing to the unrounded 1.123456 origin exceeds the same validator's
    # permitted end by 0.0000185s. Keep the word using the actual slice origin.
    worker, _, saved, *_ = setup_worker(
        decode=lambda _: samples, vad=lambda _: spans, words_providers={'parakeet': EndWords()}
    )
    assert len(worker.process_batch([capture])) == 1
    assert len(saved['a']['words']) == 1
    assert saved['a']['words'][0]['timestamp'][1] <= 7.91


def test_pyannote_frame_center_beyond_eof_is_cropped_without_losing_in_buffer_speech(monkeypatch):
    monkeypatch.setattr(
        batch_pipeline_models,
        'torch',
        SimpleNamespace(inference_mode=nullcontext, from_numpy=lambda s: SimpleNamespace(unsqueeze=lambda _: s)),
    )
    samples = np.zeros(126400, dtype=np.float32)
    output = SimpleNamespace(get_timeline=lambda: SimpleNamespace(support=lambda: [SimpleNamespace(start=0, end=7.93)]))
    vad = PyannoteVAD(lambda _: output)
    assert vad(samples) == [(0, 7.9)]
    worker, _, saved, *_ = setup_worker(decode=lambda _: samples, vad=vad)
    assert len(worker.process_batch([item(duration=7.9)])) == 1
    assert saved['a']['speech_spans'] == [{'start': 0, 'end': 7.9}]
    assert saved['a']['words']


@pytest.mark.parametrize(
    'span,reason',
    [((0, float('nan')), 'vad_nonfinite'), ((0, 0), 'vad_order'), ((-1, 1), 'vad_order'), ((2, 3), 'vad_bounds')],
)
def test_model_vad_malformed_or_wholly_outside_span_never_becomes_silence(span, reason):
    with pytest.raises(BatchValidationError) as caught:
        crop_model_vad_spans([span], 2)
    assert caught.value.reason == reason


def test_unsorted_overlapping_vad_spans_are_merged_not_failed():
    worker, _, saved, *_ = setup_worker(vad=lambda _: [(1, 2), (0, 1.5)])
    assert worker.process_batch([item()])
    assert saved['a']['speech_spans'] == [{'start': 0, 'end': 2}]


@pytest.mark.parametrize('channels,rate', [(2, 16000), (1, 8000)])
def test_noncanonical_headers_fail_before_vad_or_assembly(channels, rate, caplog):
    body = io.BytesIO()
    with wave.open(body, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b'\0\0' * rate * channels)
    worker, *_ = setup_worker(
        decode=lambda _: decode_pcm16_wav(body.getvalue()),
        vad=lambda _: pytest.fail('header failure must precede VAD'),
        on_failure=None,
    )
    assert worker.process_batch([item(duration=1)]) == []
    assert 'stage=fetch_decode' in caplog.text
    assert 'stage=vad_windows' not in caplog.text and 'stage=assemble_words' not in caplog.text


def test_batch_failure_retries_all_affected_conversations():
    class Broken:
        def transcribe_batch(self, samples):
            return []

    worker, _, saved, _, _, failures = setup_worker(words_providers={'parakeet': Broken()})
    assert worker.process_batch([item('a'), item('b')]) == []
    assert len(failures) == 2 and not saved


def test_padded_budget_and_length_sort():
    config = ProviderConfig(batch_size=2, max_padded_seconds=40)
    windows = [Window(str(n), Samples(n), 0, 0, n) for n in [25, 5, 20, 10]]
    packed = list(pack_windows(windows, config))
    assert [[w.duration for w in b] for b in packed] == [[5, 10], [20], [25]]
    assert all(max(w.duration for w in b) * len(b) <= 40 for b in packed)


def test_forced_boundary_has_context_and_unique_midpoint_ownership():
    config = ProviderConfig(window_seconds=30, context_seconds=2)
    windows = list(speech_windows(item(duration=70), Samples(70), [(0, 70)], config))
    assert [(w.start, w.core_start, w.core_end) for w in windows] == [(0, 0, 30), (28, 30, 60), (58, 60, 70)]
    assert [w.duration for w in windows] == [32, 34, 12]
    assert sum(w.core_start <= 30 < w.core_end for w in windows) == 1


def test_provider_selection_defaults_and_unknown_rejected(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_WORDS_PROVIDER', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_DIARIZER', raising=False)
    assert provider_config().words == 'parakeet'
    assert provider_config().diarizer == 'pyannote'
    monkeypatch.setenv('BATCH_PIPELINE_WORDS_PROVIDER', 'soniox_async')
    with pytest.raises(KeyError):
        setup_worker(config=provider_config())
    with pytest.raises(KeyError):
        setup_worker(config=ProviderConfig(diarizer='nemotron'))


def test_registered_alternative_selected_without_vendor_calls():
    alternate = Words()
    worker, _, _, _, _, _ = setup_worker(config=ProviderConfig(words='future'), words_providers={'future': alternate})
    worker.process_batch([item()])
    assert len(alternate.calls) == 1


def test_single_skip_requires_coverage():
    resolution = SimpleNamespace(coverage=0.9, speaker_ids={'a': 'one'})
    worker, _, saved, _, diarized, _ = setup_worker(single_speaker=lambda *args: resolution)
    worker.process_batch([item()])
    assert not diarized and saved['a']['diarization']['outcome'] == 'skipped_single'
    resolution.coverage = 0.89
    worker.process_batch([item('b')])
    assert len(diarized) == 1


def test_live_reuse_requires_config_lineage_and_quality(monkeypatch):
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'owner-a')
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'true')
    receipt = LiveWords('encrypted://a', 2, [{'word': 'live', 'timestamp': [0, 1]}], True, True)
    worker, words, saved, _, _, _ = setup_worker(config=ProviderConfig(reuse_live=True), live_words=lambda i: receipt)
    worker.process_batch([item()])
    assert not words.calls and saved['a']['words_provider'] == 'live_record'
    receipt = replace(receipt, record_quality=False)
    worker.process_batch([item()])
    assert len(words.calls) == 1
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'false')
    receipt = replace(receipt, record_quality=True)
    worker.process_batch([item()])
    assert len(words.calls) == 2


def test_reuse_default_off_never_reads_lineage():
    worker, words, _, _, _, _ = setup_worker(live_words=lambda i: pytest.fail('off must not read'))
    worker.process_batch([item()])
    assert len(words.calls) == 1


@pytest.mark.parametrize('spans', [[(-1, 1)], [(0, float('nan'))], [(0, 100)]])
def test_invalid_vad_is_failure_not_silence(spans, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    worker, _, _, _, _, failures = setup_worker(vad=lambda s: spans)
    assert worker.process_batch([item()]) == []
    assert failures == [('a', 'BatchValidationError')]


def test_duplicate_and_oversized_pull_rejected():
    worker, *_ = setup_worker()
    with pytest.raises(ValueError):
        worker.process_batch([item(), item()])
    with pytest.raises(ValueError):
        worker.process_batch([item(str(i)) for i in range(33)])


def test_nemo_adapter_arrays_and_word_clocks():
    class Model:
        def transcribe(self, samples, **kwargs):
            assert kwargs['batch_size'] == 2 and kwargs['timestamps']
            return [SimpleNamespace(text='Hi', timestamp={'word': [{'word': 'Hi', 'start': 0, 'end': 1}]})] * 2

    assert len(ParakeetWords(Model()).transcribe_batch([Samples(2), Samples(2)])) == 2


def test_context_cuts_rebase_word_clocks_and_drop_overlap_duplicates():
    class BoundaryWords:
        def transcribe_batch(self, samples):
            # For 60s input: first window is [0,32], second [28,60].
            return [
                (
                    [{'word': 'boundary', 'timestamp': [30.1, 30.3]}]
                    if len(s) == 32 * 16000 and index == 0
                    else [{'word': 'boundary', 'timestamp': [2.1, 2.3]}]
                )
                for index, s in enumerate(samples)
            ]

    worker, _, saved, _, _, failures = setup_worker(words_providers={'parakeet': BoundaryWords()})
    assert len(worker.process_batch([item(duration=60)])) == 1
    assert len(saved['a']['words']) == 1
    assert saved['a']['words'][0]['timestamp'] == [30.1, 30.3]
    assert not failures


def test_model_error_isolated_from_later_batches():
    class SometimesBroken(Words):
        def transcribe_batch(self, samples):
            if len(samples[0]) == 16000:
                raise ValueError('bad audio')
            return super().transcribe_batch(samples)

    worker, _, saved, _, _, failures = setup_worker(
        config=ProviderConfig(batch_size=1), words_providers={'parakeet': SometimesBroken()}
    )
    assert [r.segment_id for r in worker.process_batch([item('bad', 1), item('good', 2)])] == ['good']
    assert failures == [('bad', 'ValueError')] and set(saved) == {'good'}


def test_persistence_failure_never_reports_compute_as_committed():
    worker, _, _, _, _, failures = setup_worker(persist=lambda *args: (_ for _ in ()).throw(OSError()))
    assert worker.process_batch([item()]) == []
    assert failures == [('a', 'OSError')]


def test_canonical_wav_decode_and_truncation():
    import io
    import wave
    from diarizer.batch_pipeline_models import decode_pcm16_wav

    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b'\x00\x40' * 160)
    body = output.getvalue()
    samples = decode_pcm16_wav(body)
    assert len(samples) == 160 and float(samples[0]) == 0.5
    with pytest.raises(ValueError, match='truncated'):
        decode_pcm16_wav(body[:-2])


def test_failure_reporting_callback_cannot_drop_healthy_sibling():
    worker, *_ = setup_worker(
        decode=lambda i: Samples(99) if i.segment_id == 'bad' else Samples(2),
        on_failure=lambda *args: (_ for _ in ()).throw(OSError()),
    )
    assert [r.segment_id for r in worker.process_batch([item('bad'), item('good')])] == ['good']


@pytest.mark.parametrize(
    'error',
    [
        RuntimeError('CUDA error: an illegal memory access was encountered'),
        RuntimeError('CUDA out of memory. Tried to allocate 256 MiB'),
        RuntimeError('CUDA error: out of memory'),
        RuntimeError('CUBLAS_STATUS_ALLOC_FAILED when calling cublasCreate'),
        type('OutOfMemoryError', (RuntimeError,), {})('allocation failed'),
    ],
)
def test_fatal_cuda_fences_whole_worker_without_importing_models(error):
    class Poisoned:
        def transcribe_batch(self, samples):
            raise error

    worker, *_ = setup_worker(words_providers={'parakeet': Poisoned()})
    with pytest.raises(RuntimeError, match='fatal CUDA'):
        worker.process_batch([item()])
    assert worker.counts['failed'] == 0
    with pytest.raises(RuntimeError, match='restart required'):
        worker.process_batch([item('other')])


def test_pool_unit_limits_reject_conversation_on_shared_live_before_decode():
    config = ProviderConfig(pool_kind='shared_live', max_unit_seconds=120, max_padded_seconds=120)
    worker, _, _, decoded, _, _ = setup_worker(config=config)
    with pytest.raises(ValueError, match='dedicated batch'):
        worker.process_batch([item(duration=3600)])
    assert not decoded
    with pytest.raises(ValueError, match='yield between pulls'):
        worker.process_batch([item('a', 100), item('b', 100)])
    assert not decoded
    with pytest.raises(ValueError, match='capture spans'):
        worker.process_batch([item(duration=120)])
    assert worker.process_batch([replace(item(duration=120), unit_kind='capture_span')])
    over, words, _, _, _, failures = setup_worker(config=config, decode=lambda i: Samples(120 + 1 / 16000))
    assert over.process_batch([replace(item(duration=120), unit_kind='capture_span')]) == []
    assert not words.calls and failures == [('a', 'ValueError')]


def test_pool_defaults_and_unsafe_config(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_POOL_KIND', 'shared_live')
    monkeypatch.delenv('BATCH_PIPELINE_UNIT_SECONDS', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PADDED_SECONDS', raising=False)
    config = provider_config()
    assert config.max_unit_seconds == 120 and config.max_padded_seconds == 120
    monkeypatch.setenv('BATCH_PIPELINE_UNIT_SECONDS', '3600')
    with pytest.raises(ValueError):
        provider_config()


def test_speech_seconds_uses_unpadded_vad_union_in_original_samples():
    worker, _, saved, _, _, failures = setup_worker(
        vad=lambda _: [(0.10002, 0.60002), (0.4, 1.10002), (0.30002, 0.50002), (1.8, 2.005)]
    )
    assert worker.process_batch([item()])
    assert saved['a']['speech_spans'] == [{'start': 0.1, 'end': 1.1}, {'start': 1.8, 'end': 2.0}]
    assert saved['a']['speech_seconds'] == pytest.approx(1.2)
    assert saved['a']['audio_seconds'] == 2
    assert not failures


def test_capture_vad_groups_keep_words_and_diarization_on_original_span_clocks():
    from utils.batch_pipeline.contracts import projection_speech_spans
    from utils.batch_pipeline.projection_parts import split_result

    vad_calls = []

    def vad(samples):
        vad_calls.append(len(samples))
        return [(1, 3), (150, 152)]

    class GroupWords:
        def transcribe_batch(self, samples):
            # Context windows are [0,7] and [146,156]. Provider clocks are
            # local to each padded window; emitted clocks must stay original.
            assert [len(sample) / 16000 for sample in samples] == [7, 10]
            return [
                [{'word': 'first', 'timestamp': [1.25, 1.75]}],
                [{'word': 'second', 'timestamp': [4.25, 4.75]}],
            ]

    def diarize(samples):
        assert len(samples) == 180 * 16000
        return {
            'turns': [
                {'start': 1, 'end': 3, 'speaker': 'left'},
                {'start': 150, 'end': 152, 'speaker': 'right'},
            ]
        }

    worker, _, saved, decoded, _, failures = setup_worker(
        vad=vad, words_providers={'parakeet': GroupWords()}, diarizers={'pyannote': diarize}
    )
    capture = replace(item(duration=180), requires_compute_admission=True)
    assert len(worker.process_batch([capture])) == 1
    assert vad_calls == [180 * 16000] and decoded == ['a'] and not failures
    payload = saved['a']
    assert projection_speech_spans(payload, 180) == [{'start': 1.0, 'end': 3.0}, {'start': 150.0, 'end': 152.0}]
    assert payload['speech_seconds'] == 4
    assert [word['timestamp'] for word in payload['words']] == [[1.25, 1.75], [150.25, 150.75]]

    parts = split_result(capture, payload)
    assert len(parts) == 2  # 147 seconds of silence must not join the groups.
    assert [part.capture_at for part, _ in parts] == [101.0, 250.0]
    assert [part.duration_seconds for part, _ in parts] == [2.0, 2.0]
    for index, (_, part_payload) in enumerate(parts):
        assert part_payload['words'] == [{'word': ['first', 'second'][index], 'timestamp': [0.25, 0.75]}]
        assert part_payload['diarization']['turns'] == [{'start': 0.0, 'end': 2.0, 'speaker': ['left', 'right'][index]}]
        assert part_payload['speech_seconds'] == 2.0


@pytest.mark.parametrize('enforce', [False, True])
def test_cap_provenance_is_additive_and_uses_actual_padded_provider_audio(monkeypatch, enforce):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    worker, words, saved, _, _, _ = setup_worker()
    worker.process_batch([item('a', 2)], authorize_dispatch=lambda ids: ids)
    if enforce:
        assert saved['a']['cap_dispatch'] == {
            'omi_funded_accepted_provider_audio_seconds': 2,
            'admission': 'authorized_compute',
        }
    else:
        assert 'cap_dispatch' not in saved['a']
    assert saved['a']['speech_seconds'] == 2
    assert words.calls == [[2]]


@pytest.mark.parametrize('dispatch', [False, True])
def test_worker_rechecks_immediately_before_asr_and_holds_without_failure(monkeypatch, dispatch):
    from utils.batch_pipeline.contracts import HeldWork

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(dispatch).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    worker, words, saved, _, diarized, failures = setup_worker()
    checks = []

    def authorize(ids):
        checks.append(ids)
        return set()

    result = worker.process_batch([item('a', 2)], authorize_dispatch=authorize)
    assert result == [HeldWork('a')]
    assert checks == [{'a'}]
    assert not words.calls and not saved and not diarized and not failures


def test_worker_missing_authority_does_not_spend_at_cap(monkeypatch):
    from utils.batch_pipeline.contracts import HeldWork

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    worker, words, saved, _, _, _ = setup_worker()
    assert worker.process_batch([item('a', 2)]) == [HeldWork('a')]
    assert not words.calls and not saved


@pytest.mark.parametrize('enforce', [False, True])
@pytest.mark.parametrize('recovery_allowed', [False, True])
def test_full_capture_retry_rechecks_cap_and_counts_actual_padding(monkeypatch, enforce, recovery_allowed):
    from utils.batch_pipeline.contracts import HeldWork

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    calls, checks = [], []

    class Model:
        def transcribe(self, arrays, **kwargs):
            calls.append([len(samples) / 16000 for samples in arrays])
            entries = [] if len(calls) == 1 else [{'word': 'recovered', 'start': 2.25, 'end': 2.75}]
            return [SimpleNamespace(text='recovered' if entries else '', timestamp={'word': entries})]

    provider = ParakeetWords(Model())
    worker, _, saved, _, diarized, failures = setup_worker(
        decode=lambda work: np.ones(int(work.duration_seconds * 16000), dtype=np.float32),
        words_providers={'parakeet': provider},
        recover_words=provider.recover_empty,
    )

    def authorize(ids):
        checks.append(ids)
        return ids if len(checks) == 1 or recovery_allowed else set()

    result = worker.process_batch([item('a', 2)], authorize_dispatch=authorize)
    if enforce and not recovery_allowed:
        assert result == [HeldWork('a')]
        assert calls == [[2]]
        assert not saved and not diarized and not failures
    else:
        assert result[0].outcome == 'success'
        assert calls == [[2], [8]]
        assert saved['a']['words'] == [{'word': 'recovered', 'timestamp': [0.25, 0.75]}]
        assert not failures
        if enforce:
            assert saved['a']['cap_dispatch']['omi_funded_accepted_provider_audio_seconds'] == 10
        else:
            assert 'cap_dispatch' not in saved['a']
    assert checks == ([{'a'}, {'a'}] if enforce else [])


@pytest.mark.parametrize('enforce', [False, True])
def test_oversized_recovery_neither_rechecks_nor_counts_unsubmitted_audio(enforce):
    provider = ParakeetWords(SimpleNamespace(transcribe=lambda *a, **kw: pytest.fail('oversized provider request')))
    before, after = Mock(), Mock()
    result = provider.recover_empty(
        np.ones(117 * 16000, dtype=np.float32),
        272,
        **({'before_dispatch': before, 'after_dispatch': after} if enforce else {}),
    )
    assert result is None
    before.assert_not_called()
    after.assert_not_called()


@pytest.mark.parametrize('enforce', [False, True])
def test_oversized_empty_retry_holds_only_when_enforced(monkeypatch, enforce):
    from utils.batch_pipeline.contracts import HeldWork

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    model = Mock()
    model.transcribe.side_effect = lambda arrays, **_: [
        SimpleNamespace(text='', timestamp={'word': []}) for _ in arrays
    ]
    provider = ParakeetWords(model)
    worker, _, saved, _, diarized, failures = setup_worker(
        decode=lambda work: np.ones(int(work.duration_seconds * 16000), dtype=np.float32),
        words_providers={'parakeet': provider},
        recover_words=provider.recover_empty,
    )
    result = worker.process_batch([item('a', 117)], authorize_dispatch=lambda ids: ids)
    assert model.transcribe.call_count == 1  # Initial ASR only; 121s padded retry cannot fit.
    assert not saved and not diarized
    if enforce:
        assert result == [HeldWork('a')]
        assert not failures
    else:
        assert result == [ValidationFailureWork('a', 'assemble_words', 'empty_asr')]
        assert failures == [('a', 'BatchValidationError')]


@pytest.mark.parametrize('enabled', [False, True])
def test_exhausted_padded_empty_asr_hands_off_without_fabricating_silence(monkeypatch, enabled):
    from utils.batch_pipeline.contracts import RecoveryWork

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', str(enabled))

    class EmptyWords:
        def transcribe_batch(self, samples):
            return [[] for _ in samples]

    retry = Mock(return_value=[])
    worker, _, saved, _, diarized, _ = setup_worker(words_providers={'parakeet': EmptyWords()}, recover_words=retry)
    results = worker.process_batch([item()])
    assert results == (
        [RecoveryWork('a', padded_retry_empty=True)]
        if enabled
        else [ValidationFailureWork('a', 'assemble_words', 'empty_asr')]
    )
    retry.assert_called_once()
    assert not saved and not diarized
    assert worker.counts['silence'] == 0


def test_empty_vad_is_the_only_silence_even_with_recovery_enabled(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'true')
    retry = Mock(return_value=[])
    worker, _, saved, _, _, _ = setup_worker(vad=lambda _: [], recover_words=retry)
    assert worker.process_batch([item()])[0].outcome == 'silence'
    retry.assert_not_called()
    assert saved['a']['speech_spans'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,speech', [(True, False), (True, True), (False, False), (False, True)])
async def test_worker_strict_silence_commits_or_preserves_quarantine(monkeypatch, enabled, speech):

    monkeypatch.setenv('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', str(enabled))
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    strict = Mock(return_value=[{'start': 0.25, 'end': 0.5}] if speech else [])
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', strict)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda samples: [[] for _ in samples]
    retry = Mock(return_value=[])
    worker, _, saved, _, diarized, failures = setup_worker(
        decode=lambda work: np.zeros(int(work.duration_seconds * 16000), dtype=np.float32),
        words_providers={'parakeet': provider},
        recover_words=retry,
    )
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    pump = Pump(queue, worker)
    # Drive the real worker -> scheduler -> ordered-merge path, without a GPU
    # or provider. No RecoveryWork may be emitted for confirmed local silence.
    await pump.run_once()
    provider.transcribe_batch.assert_called_once()
    retry.assert_called_once()
    assert strict.call_count == int(enabled)
    if enabled and not speech:
        assert store.rows['jobs', 'a']['state'] == 'committed'
        assert store.rows['results', 'a']['result']['outcome'] == 'silence'
        assert result_outcome(saved['a']) == 'silence'
        assert saved['a']['speech_seconds'] == 0 and saved['a']['speech_spans'] == []
        assert saved['a']['words_provider'] == 'strict_local_vad'
        assert not failures and worker.counts['failed'] == 0
        assert worker.counts['silence'] == 1
    else:
        assert store.rows['jobs', 'a']['state'] == 'quarantined'
        assert ('results', 'a') not in store.rows and not saved
        assert failures == [('a', 'BatchValidationError')]
        assert worker.counts['silence'] == 0
    assert not diarized


@pytest.mark.parametrize('raw', [None, [{'start': 0, 'end': 99}], RuntimeError('unavailable')])
def test_worker_strict_vad_failure_retains_empty_asr(monkeypatch, raw):

    monkeypatch.setenv('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', 'true')
    strict = Mock(**({'side_effect': raw} if isinstance(raw, Exception) else {'return_value': raw}))
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', strict)
    provider = Mock(transcribe_batch=lambda samples: [[] for _ in samples])
    worker, _, saved, _, diarized, failures = setup_worker(
        decode=lambda work: np.zeros(int(work.duration_seconds * 16000), dtype=np.float32),
        words_providers={'parakeet': provider},
        recover_words=lambda *_: [],
    )
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'assemble_words', 'empty_asr')]
    assert failures == [('a', 'BatchValidationError')] and not saved and not diarized


def test_worker_silence_adapter_preserves_exact_pcm_and_shared_evidence(monkeypatch):

    pcm = np.resize(np.array([-32768, -1, 0, 1, 32767], dtype='<i2'), 32000)
    strict = Mock(return_value=[])
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', strict)
    assert inspect_worker_silence(item(), pcm.astype(np.float32) / 32768)['outcome'] == 'silence'
    assert strict.call_args.args[0] == pcm.tobytes()
    for invalid in [np.full(32000, np.nan), np.full(32000, 1.0), np.full(32000, 0.000001)]:
        with pytest.raises(ValueError, match='canonical PCM16'):
            inspect_worker_silence(item(), invalid)
    assert strict.call_count == 1


def test_worker_silence_uses_real_local_silero():

    payload = inspect_worker_silence(item(), np.zeros(32000, dtype=np.float32))
    assert payload['outcome'] == 'silence' and payload['speech_spans'] == []


@pytest.mark.parametrize('recovered', [False, True])
def test_worker_disposition_does_not_replace_positive_asr(monkeypatch, recovered):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', 'true')
    strict = Mock(side_effect=AssertionError('positive ASR must not be disposed'))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', strict)
    provider = Mock()
    # Midpoint is outside core ownership, but initial ASR WAS positive.
    provider.transcribe_batch.return_value = [[{'word': 'heard', 'timestamp': [4.5, 4.8]}]]
    worker, _, saved, _, _, _ = setup_worker(
        decode=lambda _: np.zeros(160320, dtype=np.float32),
        vad=lambda _: [(1, 2)],
        words_providers={'parakeet': provider},
        recover_words=lambda *_: [{'word': 'heard', 'timestamp': [1, 1.1]}] if recovered else [],
    )
    results = worker.process_batch([item(duration=10.02)])
    assert any(isinstance(r, WorkResult) for r in results) is recovered
    if not recovered:
        assert results == [ValidationFailureWork('a', 'assemble_words', 'no_owned_words')]
    assert bool(saved) is recovered
    strict.assert_not_called()


def test_worker_silence_flag_defaults_off(monkeypatch):

    monkeypatch.delenv('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', raising=False)
    assert not worker_silence_disposition_enabled()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'duration,expected_calls,expected_empty,expected_retry,expected_evidence',
    [
        (10, 2, True, 'empty', {'padded_retry': 'empty', 'version': 1}),
        (117, 1, False, 'skipped_oversize', {'padded_retry': 'skipped_oversize', 'version': 1}),
    ],
)
async def test_empty_asr_records_padded_retry_empty_only_when_padded_retry_ran(
    monkeypatch, caplog, duration, expected_calls, expected_empty, expected_retry, expected_evidence
):
    from utils.batch_pipeline.contracts import RecoveryWork

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    model = Mock()
    model.transcribe.side_effect = lambda arrays, **_: [
        SimpleNamespace(text='', timestamp={'word': []}) for _ in arrays
    ]
    provider = ParakeetWords(model)
    worker, _, saved, _, diarized, failures = setup_worker(
        decode=lambda work: np.ones(int(work.duration_seconds * 16000), dtype=np.float32),
        words_providers={'parakeet': provider},
        recover_words=provider.recover_empty,
    )
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a', duration), time.time())
    pump = Pump(queue, worker)
    with caplog.at_level(logging.INFO):
        await pump.run_once()
    assert model.transcribe.call_count == expected_calls
    assert not saved and not diarized
    assert failures == [('a', 'BatchValidationError')]
    assert (
        f'event=batch_asr_recovery segment_id=a reason=empty_asr samples={duration * 16000} owned_words=0 outcome={expected_retry}'
        in caplog.text
    )
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'held'
    assert job.get('worker_empty_evidence') == expected_evidence
    direct = worker.process_batch([item('b', duration)])
    assert direct == [RecoveryWork('b', padded_retry_empty=expected_empty, padded_retry=expected_retry)]


@pytest.mark.parametrize('ladder', [False, True])
def test_mixed_owner_gpu_batch_only_enforces_enrolled_owner(monkeypatch, ladder):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(not ladder).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'uid:owner-a')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'batch')
    worker, words, saved, _, _, failures = setup_worker()
    checks = []

    def authorize(ids):
        checks.append(ids)
        return set()

    result = worker.process_batch([item('a', 2), item('b', 2)], authorize_dispatch=authorize)
    assert checks == [{'a'}]
    assert words.calls == [[2]]
    assert set(saved) == {'b'} and not failures
    assert 'cap_dispatch' not in saved['b']
    assert any(isinstance(row, batch_pipeline.HeldWork) and row.segment_id == 'a' for row in result)


@pytest.mark.parametrize('lanes', ['live', 'sync', ''])
def test_gpu_batch_outside_lane_does_not_require_cap_authority(monkeypatch, lanes):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', lanes)
    worker, words, saved, _, _, failures = setup_worker()
    worker.process_batch([item('a', 2)])
    assert words.calls == [[2]] and set(saved) == {'a'} and not failures

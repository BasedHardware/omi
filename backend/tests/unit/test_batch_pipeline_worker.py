from dataclasses import replace
from types import SimpleNamespace

import pytest

from config.batch_pipeline_providers import ProviderConfig, provider_config
from diarizer.batch_pipeline import PipelineWorker, LiveWords, Window, pack_windows, speech_windows
from diarizer.batch_pipeline_models import ParakeetWords
from utils.batch_pipeline.contracts import WorkItem, Priority


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
def test_invalid_vad_is_failure_not_silence(spans):
    worker, _, _, _, _, failures = setup_worker(vad=lambda s: spans)
    assert worker.process_batch([item()]) == []
    assert failures == [('a', 'ValueError')]


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

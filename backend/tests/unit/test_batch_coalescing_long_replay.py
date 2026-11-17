"""Replay long coalesced units through the real chain with simulation providers.

These qualify packing/contracts/recovery bounds, not GPU quality or peak VRAM.
"""

import pytest

from config.batch_pipeline_providers import ProviderConfig
from tests.unit.test_batch_pipeline_worker import setup_worker, item, _full_gpu_stages  # noqa: F401
from testing.pipeline_sim.stt import SPEECH, SILENCE, EMPTY, WORDS, SimSamples, PlannedWords, vad_spans
from utils.batch_pipeline.contracts import RecoveryWork


@pytest.mark.parametrize('duration', [300, 600])
@pytest.mark.parametrize('kind', [SPEECH, SILENCE])
def test_long_unit_replay_preserves_duration_and_bounded_model_batches(duration, kind):
    words = PlannedWords()
    words.plan['long'] = {'first': WORDS}
    batches = []

    def transcribe(samples):
        seconds = [len(s) / 16000 for s in samples]
        assert len(samples) <= 8 and max(seconds) * len(samples) <= 272
        batches.append(seconds)
        return words.transcribe_batch(samples)

    worker, _, saved, _, diarized, failures = setup_worker(
        config=ProviderConfig(),
        decode=lambda work: SimSamples.for_seconds(work.segment_id, kind, work.duration_seconds),
        vad=vad_spans,
        words_providers={'parakeet': type('Words', (), {'transcribe_batch': staticmethod(transcribe)})()},
    )
    results = worker.process_batch([item('long', duration)])
    assert len(results) == 1 and not failures
    assert saved['long']['audio_seconds'] == duration
    if kind == SPEECH:
        assert sum(map(len, batches)) == duration // 30
        assert diarized == [duration * 16000]
    else:
        assert not batches and not diarized


def test_600_second_empty_asr_replay_does_not_make_oversize_padded_gpu_retry(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'true')
    words = PlannedWords()
    words.plan['long'] = {'first': EMPTY, 'retry': WORDS}
    retries = []
    dispatches = []

    def recover(samples, budget, **kwargs):
        retries.append(len(samples) / 16000)
        before = kwargs.get('before_dispatch', lambda: True)
        kwargs['before_dispatch'] = lambda: dispatches.append('dispatch') or before()
        return words.recover_words(samples, budget, **kwargs)

    worker, _, saved, _, _, _ = setup_worker(
        config=ProviderConfig(),
        decode=lambda work: SimSamples.for_seconds(work.segment_id, SPEECH, work.duration_seconds),
        vad=vad_spans,
        words_providers={'parakeet': words},
        recover_words=recover,
    )
    results = worker.process_batch([item('long', 600)])
    assert not saved  # Real recovery custody, never fabricated transcript success.
    assert len(results) == 1 and isinstance(results[0], RecoveryWork)
    assert retries == [600]
    assert not dispatches  # Provider rejects 600s before admitting a paid GPU retry.

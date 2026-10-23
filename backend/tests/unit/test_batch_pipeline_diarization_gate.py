"""Ship-on batch GPU skips: speech-only diarization and short single-speaker units."""

import numpy as np
import pytest
from prometheus_client import REGISTRY

from diarizer.batch_pipeline import PipelineWorker
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.errors import FatalGpuError
from diarizer import batch_pipeline
from utils.batch_pipeline.diarization_gate import (
    SAMPLE_RATE,
    compact,
    map_back,
    plan_compaction,
    short_single_region,
    speech_regions,
    unassigned_word_count,
)


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', raising=False)


def _decisions(decision):
    return REGISTRY.get_sample_value('omi_batch_pipeline_diarization_decisions_total', {'decision': decision}) or 0.0


def _metric(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


def _np_compact(samples, plan):
    return compact(samples, plan, concatenate=np.concatenate, zeros=lambda n: np.zeros(n, np.float32))


# --- pure gate -----------------------------------------------------------------


def test_regions_union_vad_and_words_including_words_outside_vad():
    regions = speech_regions(
        [{'start': 10, 'end': 12}, {'start': 11.5, 'end': 13}],
        [{'word': 'pad', 'timestamp': [14.0, 14.4]}, {'word': 'in', 'timestamp': [10.5, 10.9]}],
        60,
    )
    assert regions == [(10.0, 13.0), (14.0, 14.4)]


def test_plan_declines_dense_and_empty_units():
    total = 60 * SAMPLE_RATE
    assert plan_compaction([], total) is None
    assert plan_compaction([(0, 55)], total) is None  # >80% kept: diarize full
    assert plan_compaction([(1, 3)], total) is not None


@pytest.mark.parametrize('seed', range(25))
def test_every_evidence_sample_is_retained_and_maps_back_exactly(seed):
    rng = np.random.default_rng(seed)
    duration = float(rng.uniform(60, 900))
    total = int(duration * SAMPLE_RATE)
    spans = []
    for _ in range(int(rng.integers(1, 12))):
        start = float(rng.uniform(0, duration - 0.5))
        spans.append({'start': start, 'end': min(duration, start + float(rng.uniform(0.05, 20)))})
    regions = speech_regions(spans, [], duration)
    plan = plan_compaction(regions, total)
    if plan is None:
        return
    samples = np.arange(total, dtype=np.float32)
    compacted = _np_compact(samples, plan)
    # A whole-compact-clock turn maps back to exactly the retained pieces.
    whole = map_back([{'start': 0, 'end': len(compacted) / SAMPLE_RATE, 'speaker': 'A'}], plan)
    covered = [(t['start'], t['end']) for t in whole]
    for start, end in regions:
        assert any(lo <= start and end <= hi + 1 / SAMPLE_RATE for lo, hi in covered)
    # Retained samples are byte-identical originals at their mapped positions.
    for compact_start, original, count in plan.pieces:
        assert np.array_equal(compacted[compact_start : compact_start + count], samples[original : original + count])


def test_map_back_drops_seams_splits_crossing_turns_and_clips_overhang():
    total = 300 * SAMPLE_RATE
    plan = plan_compaction([(10, 12), (200, 202)], total)
    assert plan is not None and len(plan.pieces) == 2
    (c0, o0, n0), (c1, o1, n1) = plan.pieces
    end = plan.compact_samples / SAMPLE_RATE
    turns = map_back([{'start': 0, 'end': end + 0.4, 'speaker': 'A'}], plan)
    assert [(t['start'], t['end']) for t in turns] == [
        (o0 / SAMPLE_RATE, (o0 + n0) / SAMPLE_RATE),
        (o1 / SAMPLE_RATE, (o1 + n1) / SAMPLE_RATE),
    ]
    seam_only = map_back([{'start': (c0 + n0) / SAMPLE_RATE + 0.01, 'end': c1 / SAMPLE_RATE - 0.01}], plan)
    assert seam_only == []
    with pytest.raises(ValueError):
        map_back([{'start': float('nan'), 'end': 1}], plan)


def test_short_single_region_requires_one_short_contiguous_region():
    assert short_single_region([(5.0, 6.8)])
    assert short_single_region([(5.0, 5.6), (5.9, 6.9)])  # 0.3 s pause is one region
    assert short_single_region([(5.0, 5.5), (6.0, 6.5)])  # exactly 0.5 s pause joins (inclusive)
    assert not short_single_region([(5.0, 5.5), (6.001, 6.5)])  # a longer pause splits
    assert not short_single_region([(5.0, 5.6), (7.0, 7.4)])
    assert not short_single_region([(5.0, 7.5)])
    assert not short_single_region([])


# --- worker integration ----------------------------------------------------------


def _item(key='a', duration=180.0):
    return WorkItem(key, 'owner-' + key, 100, 'encrypted://' + key, duration, Priority.FRESH)


class _Words:
    def __init__(self, clocks):
        self.clocks = list(clocks)
        self.calls = []

    def transcribe_batch(self, samples):
        self.calls.append([len(s) for s in samples])
        return [[{'word': 'w', 'timestamp': list(self.clocks.pop(0))}] for _ in samples]


def _worker(vad_spans, clocks, *, diarize=None):
    saved, diarized = {}, []

    def default_diarize(samples):
        diarized.append(len(samples))
        seconds = len(samples) / SAMPLE_RATE
        return {'turns': [{'start': 0.0, 'end': seconds, 'speaker': 'S1'}], 'overlaps': [], 'backend': 'pyannote'}

    words = _Words(clocks)
    worker = PipelineWorker(
        language_of=lambda item: 'en',
        decode=lambda item: np.full(int(item.duration_seconds * SAMPLE_RATE), 0.01, dtype=np.float32),
        vad=lambda s: list(vad_spans),
        words_providers={'parakeet': words},
        diarizers={'pyannote': diarize or default_diarize},
        persist=lambda item, payload: saved.setdefault(item.segment_id, payload) and 'uri',
    )
    return worker, words, saved, diarized


def test_sparse_unit_diarizes_speech_only_with_identical_words_and_asr(monkeypatch):
    spans = [(10, 14), (150, 156)]
    clocks = [(1.0, 1.5), (3.0, 3.4)]  # local to the 8 s and 10 s ASR windows

    before = _decisions('compacted')
    unit_before = _metric('omi_batch_pipeline_diarization_audio_seconds_total', {'kind': 'unit'})
    worker, words, saved, diarized = _worker(spans, clocks)
    worker.process_batch([_item()])
    compacted = saved['a']
    assert _decisions('compacted') == before + 1
    assert _metric('omi_batch_pipeline_diarization_audio_seconds_total', {'kind': 'unit'}) == unit_before + 180

    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    full_worker, full_words, full_saved, full_diarized = _worker(spans, clocks)
    full_worker.process_batch([_item()])

    # Transcript equivalence: same ASR inputs, same words, same clocks.
    assert words.calls == full_words.calls
    assert compacted['words'] == full_saved['a']['words']
    assert compacted['speech_spans'] == full_saved['a']['speech_spans']
    # GPU work: diarization saw padded speech only, not the 180 s unit.
    assert full_diarized == [180 * SAMPLE_RATE]
    assert diarized[0] < 0.2 * 180 * SAMPLE_RATE
    turns = compacted['diarization']['turns']
    assert all(0 <= t['start'] < t['end'] <= 180 for t in turns)
    # Every word sits inside a mapped turn on the original capture clock.
    for word in compacted['words']:
        mid = sum(word['timestamp']) / 2
        assert any(t['start'] <= mid < t['end'] for t in turns)
    assert compacted['diarization']['speech_compaction']['audio_seconds'] == 180


def test_compaction_never_loses_all_turns_for_words():
    calls = []

    def diarize(samples):
        calls.append(len(samples))
        if len(calls) == 1:
            return {'turns': [], 'overlaps': []}
        return {'turns': [{'start': 0.0, 'end': 180.0, 'speaker': 'S1'}], 'overlaps': []}

    worker, _, saved, _ = _worker([(10, 14), (150, 156)], [(1.0, 1.5), (3.0, 3.4)], diarize=diarize)
    worker.process_batch([_item()])
    assert calls[0] < calls[1] == 180 * SAMPLE_RATE
    assert saved['a']['diarization']['turns'] == [{'start': 0.0, 'end': 180.0, 'speaker': 'S1'}]
    assert 'speech_compaction' not in saved['a']['diarization']


def test_fatal_cuda_in_compacted_diarization_still_fences_the_chain():
    def diarize(samples):
        raise RuntimeError('CUDA out of memory')

    worker, _, _, _ = _worker([(10, 14), (150, 156)], [(1.0, 1.5), (3.0, 3.4)], diarize=diarize)
    with pytest.raises(FatalGpuError):
        worker.process_batch([_item()])


def test_dense_unit_diarizes_full_audio_and_records_kept_over_80pct(monkeypatch):
    fallbacks = []
    monkeypatch.setattr(batch_pipeline, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    before = _decisions('full_kept_over_80pct')
    worker, _, saved, diarized = _worker([(0, 170)], [(1.0, 1.5)] * 6)
    worker.process_batch([_item()])
    assert diarized == [180 * SAMPLE_RATE]
    assert 'speech_compaction' not in saved['a']['diarization']
    assert _decisions('full_kept_over_80pct') == before + 1
    assert fallbacks == [
        {
            'component': 'vad',
            'from_mode': 'batch_speech_only_diarization',
            'to_mode': 'full_unit_diarization',
            'reason': 'kept_over_80pct',
            'outcome': 'recovered',
        }
    ]


def test_compacted_empty_fallback_records_other_reason(monkeypatch):
    fallbacks = []
    monkeypatch.setattr(batch_pipeline, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    calls = []

    def diarize(samples):
        calls.append(len(samples))
        return {'turns': [] if len(calls) == 1 else [{'start': 0.0, 'end': 180.0, 'speaker': 'S1'}]}

    before = _decisions('full_compacted_empty')
    worker, _, _, _ = _worker([(10, 14), (150, 156)], [(1.0, 1.5), (3.0, 3.4)], diarize=diarize)
    worker.process_batch([_item()])
    assert _decisions('full_compacted_empty') == before + 1
    assert [(f['reason'], f['outcome']) for f in fallbacks] == [('other', 'degraded')]


def test_compacted_result_with_unassigned_words_is_counted():
    def diarize(samples):
        # Covers only the first retained piece; the second word is in a gap.
        return {'turns': [{'start': 0.0, 'end': 2.0, 'speaker': 'S1'}], 'overlaps': []}

    units = _metric('omi_batch_pipeline_compacted_unassigned_units_total')
    words = _metric('omi_batch_pipeline_compacted_unassigned_words_total')
    worker, _, saved, _ = _worker([(10, 14), (150, 156)], [(1.0, 1.5), (3.0, 3.4)], diarize=diarize)
    worker.process_batch([_item()])
    assert 'speech_compaction' in saved['a']['diarization']
    assert _metric('omi_batch_pipeline_compacted_unassigned_units_total') == units + 1
    assert _metric('omi_batch_pipeline_compacted_unassigned_words_total') == words + 1


def test_unassigned_word_count_matches_overlap_rule():
    words = [{'word': 'a', 'timestamp': [1.0, 1.2]}, {'word': 'b', 'timestamp': [5.0, 5.2]}]
    assert unassigned_word_count(words, [{'start': 0.0, 'end': 2.0}]) == 1
    assert unassigned_word_count(words, [{'start': 0.0, 'end': 2.0}, {'start': 5.1, 'end': 6.0}]) == 0
    assert unassigned_word_count(words, []) == 2


def test_short_single_skip_is_off_by_default():
    worker, _, saved, diarized = _worker([(40.0, 41.2)], [(4.1, 4.6)])
    worker.process_batch([_item(duration=60)])
    assert len(diarized) == 1
    assert saved['a']['diarization'].get('outcome') != 'skipped_single'


def test_short_single_utterance_skips_diarization_when_enabled(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'true')
    before = _decisions('skipped_short')
    worker, _, saved, diarized = _worker([(40.0, 41.2)], [(4.1, 4.6)])
    worker.process_batch([_item(duration=60)])
    assert diarized == []
    assert saved['a']['diarization'] == {
        'turns': [{'start': 0, 'end': 60.0, 'speaker': 'SPEAKER_00'}],
        'outcome': 'skipped_single',
        'single_evidence': 'short_speech',
    }
    assert _decisions('skipped_short') == before + 1

    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
    worker, _, saved, diarized = _worker([(40.0, 41.2)], [(4.1, 4.6)])
    worker.process_batch([_item(duration=60)])
    assert len(diarized) == 1 and saved['a']['diarization'].get('outcome') != 'skipped_single'


def test_two_separated_short_utterances_are_still_diarized(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'true')
    worker, _, saved, diarized = _worker([(10.0, 11.0), (40.0, 41.0)], [(2.1, 2.5), (2.1, 2.5)])
    worker.process_batch([_item(duration=60)])
    assert len(diarized) == 1
    assert saved['a']['diarization'].get('outcome') != 'skipped_single'


def test_word_in_asr_padding_outside_vad_extends_short_region_beyond_single_skip(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'true')
    # VAD marks 1.0 s, but ASR context found a word 1.5 s after it ends. Words
    # are speech evidence too, so the unit is diarized, not assumed single.
    worker, _, _, diarized = _worker([(40.0, 41.0)], [(6.5, 6.8)])
    worker.process_batch([_item(duration=60)])
    assert len(diarized) == 1


def test_vad_silence_still_skips_asr_and_diarization():
    worker, words, saved, diarized = _worker([], [])
    results = worker.process_batch([_item()])
    assert results[0].outcome == 'silence'
    assert words.calls == [] and diarized == []
    assert saved['a']['diarization'] == {'turns': [], 'outcome': 'silence'}


@pytest.mark.parametrize('value', ['false', 'FALSE', ' false '])
def test_speech_only_kill_switch_parses_false(monkeypatch, value):
    from config.batch_pipeline_gpu_skip import diarize_speech_only_enabled

    assert diarize_speech_only_enabled()
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', value)
    assert not diarize_speech_only_enabled()


@pytest.mark.parametrize('value,enabled', [('true', True), (' TRUE ', True), ('1', False), ('yes', False), ('', False)])
def test_short_single_enables_only_on_explicit_true(monkeypatch, value, enabled):
    from config.batch_pipeline_gpu_skip import short_speech_single_enabled

    assert not short_speech_single_enabled()
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', value)
    assert short_speech_single_enabled() is enabled

"""Left ASR context from a unit's contiguous predecessor in the same capture stream."""

import numpy as np
import pytest

from config.batch_pipeline_providers import ProviderConfig, provider_config
from diarizer.batch_pipeline import PipelineWorker
from diarizer.batch_pipeline_context import LeftContextIndex, capture_stream, select_context, starts_in_speech
from diarizer.batch_pipeline_models import StagedAudio
from utils.batch_pipeline.audio import audio_unit, read_context, with_context
from utils.batch_pipeline.contracts import Priority, WorkItem, WorkResult
from utils.sync.capture import chunk_identity

RATE = 16000
STREAM = 'capture:stream-1'


def item(key, capture_at, seconds, owner='owner-a', generation=1, device='pendant-1', locked=False):
    """A capture span exactly as intake builds it: a per-unit chunk identity."""
    return WorkItem(
        key,
        owner,
        capture_at,
        'encrypted://' + key,
        seconds,
        Priority.FRESH,
        unit_kind='capture_span',
        conversation_id=chunk_identity(owner, 'omi', device, locked, capture_at),
        privacy_generation=generation,
    )


def staged(work, samples, device='pendant-1', locked=False):
    """Intake's frozen staged WAV: PCM16 plus the authenticated intake context."""
    pcm = np.round(samples * 32768).clip(-32768, 32767).astype('<i2').tobytes()
    return with_context(
        audio_unit(work.capture_at, pcm).wav,
        {
            'owner_id': work.owner_id,
            'segment_id': work.segment_id,
            'capture_at': work.capture_at,
            'source': 'omi',
            'should_lock': locked,
            'client_device_id': device,
            'conversation_id': None,
        },
    )


def tone(seconds, level):
    return np.full(int(seconds * RATE), level, dtype=np.float32)


# ---- context selection and index -------------------------------------------------


def test_context_starts_at_the_onset_of_the_speech_run_crossing_the_seam():
    samples = np.zeros(20 * RATE, dtype=np.float32)
    assert select_context(samples, [(2, 5), (15.5, 20)], 8) == (int(15.0 * RATE), 20 * RATE)
    # A run longer than the bound starts at the bound, still mid-run.
    assert select_context(samples, [(1, 20)], 8) == (12 * RATE, 20 * RATE)
    # Predecessor ended in silence: only a short non-speech tail.
    assert select_context(samples, [(2, 5)], 8) == (19 * RATE, 20 * RATE)
    assert select_context(samples, [(2, 5)], 0) is None


def test_index_matches_only_a_contiguous_same_owner_same_generation_predecessor():
    clock = [0.0]
    index = LeftContextIndex(max_seconds=8, max_units=4, ttl_seconds=60, clock=lambda: clock[0])
    index.remember(item('p', 100, 10), tone(10, 0.25), [(5, 10)], STREAM)
    context = index.lookup(item('s', 110.2, 10), 10, STREAM)
    assert context is not None and len(context) == int(5.5 * RATE)
    assert np.allclose(context, 0.25, atol=1 / 32768)
    assert index.lookup(item('s', 112, 10), 10, STREAM) is None  # gap > 1s
    assert index.lookup(item('s', 110, 10, owner='owner-b'), 10, STREAM) is None
    assert index.lookup(item('s', 110, 10), 10, 'capture:stream-2') is None  # another device
    assert index.lookup(item('s', 110, 10), 10, None) is None
    # A unit never takes its own tail as context.
    assert index.lookup(item('p', 100, 10), 10, STREAM) is None
    clock[0] = 61
    assert index.lookup(item('s', 110, 10), 10, STREAM) is None  # expired


def test_a_new_privacy_generation_drops_the_owners_older_tails():
    index = LeftContextIndex(max_seconds=8, max_units=8)
    index.remember(item('p', 100, 10), tone(10, 0.25), [(5, 10)], STREAM)
    assert index.lookup(item('s', 110, 10, generation=2), 10, STREAM) is None
    assert index.lookup(item('s', 110, 10), 10, STREAM) is None  # gone, not merely unmatched


def test_an_overlapping_predecessor_is_trimmed_so_audio_is_never_replayed():
    index = LeftContextIndex(max_seconds=8, max_units=8)
    index.remember(item('p', 100, 10), tone(10, 0.25), [(5, 10)], STREAM)
    context = index.lookup(item('s', 109.6, 10), 10, STREAM)
    assert context is not None and len(context) == int(5.5 * RATE) - int(0.4 * RATE)


def test_index_is_bounded():
    index = LeftContextIndex(max_seconds=8, max_units=2)
    for i in range(3):
        index.remember(item(f'u{i}', 10 * i, 10), tone(10, 0.1), [(9, 10)], STREAM)
    assert index.lookup(item('n', 10, 10), 10, STREAM) is None  # u0 evicted
    assert index.lookup(item('n', 30, 10), 10, STREAM) is not None
    disabled = LeftContextIndex(max_seconds=8, max_units=0)
    disabled.remember(item('u', 0, 10), tone(10, 0.1), [(9, 10)], STREAM)
    assert disabled.lookup(item('n', 10, 10), 10, STREAM) is None


def test_capture_stream_ignores_the_per_unit_chunk_identity():
    first, second = item('p', 100, 10), item('s', 110, 10)
    # Intake's conversation_id differs for every unit of one upload stream...
    assert first.conversation_id != second.conversation_id
    # ...but the stream is source + device + lock from the staged intake context.
    stream = capture_stream(first, read_context(staged(first, tone(1, 0.1))))
    assert stream and stream == capture_stream(second, read_context(staged(second, tone(1, 0.1))))
    other = capture_stream(second, read_context(staged(second, tone(1, 0.1), device='desktop-1')))
    locked = capture_stream(second, read_context(staged(second, tone(1, 0.1), locked=True)))
    assert len({stream, other, locked}) == 3
    assert capture_stream(second, None) is None  # no authenticated context: no stream
    record = WorkItem('r', 'owner-a', 0, 'record://r', 10, Priority.FRESH, conversation_id='conv-1')
    assert capture_stream(record) == 'conversation:conv-1'


def test_only_speech_starting_at_the_first_samples_counts_as_mid_utterance():
    assert starts_in_speech([(0.0, 3.0)]) and starts_in_speech([(4, 5), (0.4, 1)])
    assert not starts_in_speech([(0.8, 3.0)]) and not starts_in_speech([])


def test_knob_is_off_by_default_and_enabled_by_seconds(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_ASR_LEFT_CONTEXT_SECONDS', raising=False)
    assert provider_config().asr_left_context_seconds == 0
    assert ProviderConfig().asr_left_context_seconds == 0
    monkeypatch.setenv('BATCH_PIPELINE_ASR_LEFT_CONTEXT_SECONDS', '8')
    assert provider_config().asr_left_context_seconds == 8
    for invalid in (-1, 31, float('nan')):
        with pytest.raises(ValueError, match='left context'):
            ProviderConfig(asr_left_context_seconds=invalid)


# ---- worker ----------------------------------------------------------------------


class Words:
    """Empty unless the window starts with predecessor audio (level 0.25)."""

    def __init__(self):
        self.calls = []

    def transcribe_batch(self, batch):
        self.calls.append([len(s) / RATE for s in batch])
        result = []
        for samples in batch:
            seconds = len(samples) / RATE
            if samples[0] == pytest.approx(0.25, abs=1e-3) and samples[-1] == pytest.approx(0.5, abs=1e-3):
                # Context word, a seam-straddling word, and a word inside the unit.
                result.append(
                    [
                        {'word': 'before', 'timestamp': [0.5, 1.0]},
                        {'word': 'seam', 'timestamp': [seconds - 10.1, seconds - 9.8]},
                        {'word': 'inside', 'timestamp': [seconds - 5, seconds - 4.5]},
                    ]
                )
            else:
                result.append([])
        return result


def run(units, audio, spans, *, worker=None, ctx=8, flights=None, devices=None):
    saved, failures = {}, []
    words = Words()
    blobs = {u.segment_id: staged(u, audio[u.segment_id], **(devices or {}).get(u.segment_id, {})) for u in units}
    source = StagedAudio(lambda work: blobs[work.segment_id])
    worker = worker or PipelineWorker(
        language_of=lambda item: 'en',
        decode=source.decode,
        stream_of=source.stream,
        vad=lambda samples: spans[int(samples[0] * 100)],
        words_providers={'parakeet': words},
        diarizers={'pyannote': lambda samples: {'turns': []}},
        persist=lambda work, payload: saved.__setitem__(work.segment_id, payload) or 'result://' + work.segment_id,
        config=ProviderConfig(asr_left_context_seconds=ctx),
        on_failure=lambda work, error: failures.append(work.segment_id),
        io_concurrency=1,
    )
    results = []
    for flight in flights or [units]:
        results.extend(worker.process_batch(flight))
    return worker, words, saved, results


# Predecessor (level 0.25, speech to its end) and successor (level 0.5, speech from 0).
AUDIO = {'p': tone(10, 0.25), 's': tone(10, 0.5)}
SPANS = {25: [(6, 10)], 50: [(0, 10)]}


def test_contiguous_predecessor_in_flight_prefixes_the_first_window_and_owns_no_prefix_words():
    units = [item('p', 100, 10), item('s', 110, 10)]
    worker, words, saved, results = run(units, AUDIO, SPANS)
    assert worker.counts['left_context'] == 1
    # The successor's 10s window grew by the predecessor's speech run plus margin (4.5s).
    assert sorted(words.calls[0]) == [pytest.approx(8.0), pytest.approx(14.5)]
    assert {r.segment_id for r in results if isinstance(r, WorkResult)} == {'s'}
    owned = saved['s']['words']
    assert [w['word'] for w in owned] == ['seam', 'inside']
    assert owned[0]['timestamp'][0] == 0.0  # straddling word clamped to the capture
    assert owned[1]['timestamp'] == pytest.approx([5.0, 5.5], abs=1e-6)


def test_cache_carries_context_across_flights():
    units = [item('p', 100, 10), item('s', 110, 10)]
    worker, words, saved, _ = run(units, AUDIO, SPANS, flights=[[units[0]], [units[1]]])
    assert worker.counts['left_context'] == 1 and 's' in saved


@pytest.mark.parametrize(
    'successor,devices',
    [
        (item('s', 115, 10), None),  # not contiguous
        (item('s', 110, 10, owner='owner-b'), None),
        (item('s', 110, 10, generation=2), None),
        (item('s', 110, 10, device='desktop-1'), {'s': {'device': 'desktop-1'}}),  # another device, 0s gap
        (item('s', 110, 10, locked=True), {'s': {'locked': True}}),
    ],
)
def test_no_context_without_a_contiguous_predecessor_in_the_same_stream(successor, devices):
    worker, words, saved, _ = run([item('p', 100, 10), successor], AUDIO, SPANS, devices=devices)
    assert worker.counts['left_context'] == 0 and 's' not in saved


def test_without_a_stream_identity_no_context_attaches():
    units = [item('p', 100, 10), item('s', 110, 10)]
    saved = {}
    worker = PipelineWorker(
        language_of=lambda item: 'en',
        decode=lambda work: AUDIO[work.segment_id],  # no staged intake context
        vad=lambda samples: SPANS[int(samples[0] * 100)],
        words_providers={'parakeet': Words()},
        diarizers={'pyannote': lambda samples: {'turns': []}},
        persist=lambda work, payload: saved.__setitem__(work.segment_id, payload) or 'result://' + work.segment_id,
        config=ProviderConfig(asr_left_context_seconds=8),
        io_concurrency=1,
    )
    worker.process_batch(units)
    assert worker.counts['left_context'] == 0


def test_kill_switch_and_onset_start_take_no_context():
    worker, _, saved, _ = run([item('p', 100, 10), item('s', 110, 10)], AUDIO, SPANS, ctx=0)
    assert worker.counts['left_context'] == 0 and 's' not in saved
    worker, _, _, _ = run([item('p', 100, 10), item('s', 110, 10)], AUDIO, {25: [(6, 10)], 50: [(1.0, 10)]})
    assert worker.counts['left_context'] == 0


def test_prefix_only_words_leave_the_unit_empty_asr():
    class PrefixOnly:
        def transcribe_batch(self, batch):
            return [[{'word': 'before', 'timestamp': [0.5, 1.0]}] for _ in batch]

    saved = {}
    units = [item('p', 100, 10), item('s', 110, 10)]
    source = StagedAudio(lambda work: staged(work, AUDIO[work.segment_id]))
    worker = PipelineWorker(
        language_of=lambda item: 'en',
        decode=source.decode,
        stream_of=source.stream,
        vad=lambda samples: SPANS[int(samples[0] * 100)],
        words_providers={'parakeet': PrefixOnly()},
        diarizers={'pyannote': lambda samples: {'turns': []}},
        persist=lambda work, payload: saved.__setitem__(work.segment_id, payload) or 'result://' + work.segment_id,
        config=ProviderConfig(asr_left_context_seconds=8),
        io_concurrency=1,
    )
    results = worker.process_batch(units)
    assert worker.counts['left_context'] == 1 and 's' not in saved
    failure = next(r for r in results if getattr(r, 'segment_id', None) == 's')
    assert failure.reason == 'empty_asr'

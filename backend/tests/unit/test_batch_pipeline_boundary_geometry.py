"""Boundary-geometry property tests: +-1 sample of the admitted duration.

David, 10-29 (simtests): the EOF VAD wedge (#23926) was a one-sample geometry
error — a span ending at decoded EOF failed the admitted-clock check by
1/16000 s. These tests sweep the exact sample boundaries of every duration
fence on the batch path: VAD spans at EOF, measured-speech tolerances, bound
worker receipts, word-clock clamping, retained-audio manifest slices and the
admitted-duration tolerance of the projection payload contract.

A regression that moves any fence by one sample — in either direction — fails
here before it can wedge a production unit.
"""

import hashlib
import json

import pytest
import numpy as np

from config.batch_pipeline_providers import ProviderConfig
from diarizer.batch_pipeline import BatchValidationError, PipelineWorker, bounded_window_words, validate_words

# build_incoming's function-level imports (pre_recorded pulls the deepgram SDK,
# deterministic_minimum, models.conversation, sync.capture) land in whichever
# test calls it first; import them at collection so the duration-guard call
# phase stays clean.
import models.conversation  # noqa: F401
import utils.conversations.deterministic_minimum  # noqa: F401
import utils.stt.pre_recorded  # noqa: F401
import utils.sync.capture  # noqa: F401
from tests.unit.test_batch_pipeline_owner_chain_projection import SUCCESS_PAYLOAD
from utils.batch_pipeline.audio import audio_unit
from utils.batch_pipeline.contracts import (
    ProjectionBinding,
    Priority,
    WorkItem,
    ValidationFailureWork,
    WorkResult,
    bound_vad_receipt,
    projection_speech_spans,
    vad_receipt,
    validate_measured_vad,
    worker_vad_word_spans,
)
from utils.batch_pipeline.projection import build_incoming
from utils.batch_pipeline.projection_parts import bounded_projection_words
from utils.batch_pipeline.source_audio import MAGIC, materialize

SAMPLE = 1 / 16000
RATE = 16000


# --- VAD spans at EOF (admitted vs decoded clock) --------------------------------


@pytest.mark.parametrize(
    'samples_over,clamped',
    [
        (-1, False),  # one sample inside the admitted duration: untouched
        (0, False),
        (1, True),  # the #23926 wedge: decoded EOF one sample past admission
        (1599, True),
        (1600, True),  # exactly the 0.1 s metadata tolerance
        (1601, True),  # tolerance + one sample rounding allowance: still clamps
    ],
)
def test_eof_span_within_decode_tolerance_is_clamped_at_every_sample(samples_over, clamped):
    duration = 1.0
    end = duration + samples_over * SAMPLE
    payload = {'speech_spans': [{'start': 0.0, 'end': end}], 'speech_seconds': end}
    spans = projection_speech_spans(payload, duration)
    expected_end = duration if clamped else end
    assert spans == [{'start': 0.0, 'end': expected_end}]


@pytest.mark.parametrize('samples_over', [1602, 1603, 3200])
def test_eof_span_beyond_decode_tolerance_is_rejected_at_every_sample(samples_over):
    duration = 1.0
    end = duration + samples_over * SAMPLE
    payload = {'speech_spans': [{'start': 0.0, 'end': end}], 'speech_seconds': end}
    with pytest.raises(ValueError):
        projection_speech_spans(payload, duration)


@pytest.mark.parametrize(
    'start,accepted',
    [(1.0 - SAMPLE, True), (1.0 - 2 * SAMPLE, True), (1.0, False), (1.0 + SAMPLE, False)],
)
def test_eof_span_start_boundary_degenerates_only_at_the_admitted_duration(start, accepted):
    payload = {'speech_spans': [{'start': start, 'end': 1.1}], 'speech_seconds': 1.1 - start}
    if accepted:
        assert projection_speech_spans(payload, 1.0) == [{'start': start, 'end': 1.0}]
    else:
        with pytest.raises(ValueError):
            projection_speech_spans(payload, 1.0)


def test_accounting_fence_tolerates_exactly_one_sample_of_union_disagreement():
    duration = 1.0
    end = duration + SAMPLE
    payload = {'speech_spans': [{'start': 0.0, 'end': end}], 'speech_seconds': end + SAMPLE}
    assert projection_speech_spans(payload, duration) == [{'start': 0.0, 'end': duration}]
    payload['speech_seconds'] = end + 2 * SAMPLE
    with pytest.raises(ValueError, match='accounting'):
        projection_speech_spans(payload, duration)


# --- measured VAD speech tolerances ----------------------------------------------


@pytest.mark.parametrize(
    'seconds,accepted',
    [
        (0.0, True),
        (-SAMPLE, False),
        (2.0, True),
        (2.0 + 1600 * SAMPLE, True),  # exactly the 0.1 s metadata tolerance
        (2.0 + 1601 * SAMPLE, True),  # tolerance + one rounding sample
        (2.0 + 1602 * SAMPLE, False),
    ],
)
def test_measured_vad_boundary_is_the_decode_tolerance_plus_one_sample(seconds, accepted):
    if accepted:
        assert validate_measured_vad(seconds, 2.0) is not None
    else:
        with pytest.raises(ValueError):
            validate_measured_vad(seconds, 2.0)


# --- bound worker receipts --------------------------------------------------------


@pytest.mark.parametrize(
    'captured_samples,valid',
    [
        (16000, True),
        (15999, True),
        (16001, True),
        (16000 - 1600, True),  # 0.1 s under: inside the metadata tolerance
        (16000 + 1599, True),  # 0.0999375 s over: the largest passing overrun
        # The nominal +0.1 s overrun rejects: 17600/16000 - 1.0 is the double
        # 0.10000000000000009, one float ulp past the 0.1 fence. Deterministic
        # production behavior, pinned as-is.
        (16000 + 1600, False),
        (16000 - 1601, False),
        (16000 + 1601, False),
    ],
)
def test_receipt_captured_samples_boundary_is_the_metadata_tolerance(captured_samples, valid):
    job = {'audio_uri': 'gs://synthetic/audio', 'duration_seconds': 1.0}
    receipt = vad_receipt('gs://synthetic/audio', captured_samples, 0.5)
    assert bound_vad_receipt(job, receipt) is valid


@pytest.mark.parametrize('speech_samples,valid', [(-1, False), (0, True), (16000, True), (16001, False)])
def test_receipt_speech_samples_stay_inside_the_capture(speech_samples, valid):
    job = {'audio_uri': 'gs://synthetic/audio', 'duration_seconds': 1.0}
    receipt = vad_receipt('gs://synthetic/audio', 16000, 0.5)
    receipt['speech_samples'] = speech_samples
    assert bound_vad_receipt(job, receipt) is valid


# --- word clocks at EOF ------------------------------------------------------------


def test_word_clocks_clamp_to_the_last_admitted_sample_never_past_it():
    duration = 2.0
    words = [{'word': 'beyond', 'timestamp': [1.0, 5.0]}]
    spans = worker_vad_word_spans(words, duration, 3.0)
    # The 3 s acoustic measure overflows the 2 s capture: the word clock only
    # licenses placement, so the measure fills it and grows into silence.
    assert spans == [{'start': 0.0, 'end': 2.0}]
    assert all(span['end'] <= duration for span in spans)


def test_silence_growth_stops_exactly_at_eof_one_sample_not_beyond():
    duration = 2.0
    words = [{'word': 'a', 'timestamp': [0.0, 1.0]}, {'word': 'b', 'timestamp': [1.5, 1.6]}]
    spans = worker_vad_word_spans(words, duration, 5.0)
    assert spans[-1]['end'] == 2.0
    total = sum(span['end'] - span['start'] for span in spans)
    assert total == 2.0  # min(measured 5 s, captured 2 s): the capture binds


def test_word_clock_one_sample_past_eof_clamps_to_eof_exactly():
    duration = 1.0
    bounded = bounded_projection_words([{'word': 'edge', 'timestamp': [0.5, 1.0 + SAMPLE]}], duration)
    assert bounded[0]['timestamp'] == [0.5, 1.0]


def window_word_result(words):
    class Provider:
        def transcribe_batch(self, samples):
            return [words for _ in samples]

    saved = []

    def persist(item, payload):
        saved.append(payload)
        return 'synthetic:result'

    worker = PipelineWorker(
        config=ProviderConfig(context_seconds=0),
        language_of=lambda _: 'en',
        decode=lambda _: np.ones(8000, dtype=np.float32),
        vad=lambda _: [(0.0, 0.5)],
        words_providers={'parakeet': Provider()},
        diarizers={'pyannote': lambda _: {'turns': []}},
        persist=persist,
    )
    item = WorkItem('synthetic-window', 'synthetic-owner', 0.0, 'synthetic:audio', 0.5, Priority.DEEP)
    return worker.process_batch([item]), saved


def test_subsecond_window_word_past_eof_commits_clamped():
    results, saved = window_word_result([{'word': 'edge', 'timestamp': [0.1, 0.54]}])
    assert len(results) == 1 and isinstance(results[0], WorkResult)
    assert results[0].outcome == 'success'
    assert saved[0]['words'] == [{'word': 'edge', 'timestamp': [0.1, 0.5]}]
    # Other validation surfaces retain their strict bounds.
    with pytest.raises(BatchValidationError, match='word_clock'):
        validate_words([{'word': 'edge', 'timestamp': [0.1, 0.54]}], 0.5)


@pytest.mark.parametrize(
    'clocks', [[-0.2, -0.1], [-0.1, 0.0], [0.5, 0.6], [0.3, 0.2], [0.1, float('nan')], [0.1, float('inf')]]
)
def test_invalid_window_word_clocks_still_fail_at_word_clocks(clocks):
    results, saved = window_word_result([{'word': 'invalid', 'timestamp': clocks}])
    assert results == [ValidationFailureWork('synthetic-window', 'word_clocks', 'word_clock')]
    assert saved == []


def test_bounded_window_owns_midpoints_and_preserves_raw_order():
    words = [
        {'word': 'left-context', 'timestamp': [-0.3, 0.1]},
        {'word': 'left-edge', 'timestamp': [-0.1, 0.2]},
        {'word': 'right-edge', 'timestamp': [0.3, 0.6]},
        {'word': 'right-context', 'timestamp': [0.4, 0.7]},
    ]
    assert bounded_window_words(words, 0.5) == [
        {'word': 'left-edge', 'timestamp': [0, 0.2]},
        {'word': 'right-edge', 'timestamp': [0.3, 0.5]},
    ]
    with pytest.raises(BatchValidationError, match='word_sequence'):
        bounded_window_words(list(reversed(words)), 0.5)


# --- retained-audio manifest slices ------------------------------------------------


def pcm(frames: int) -> bytes:
    return b'\x01\x00' * frames


def manifest_item(capture_at=7.0, duration=1.0):
    return WorkItem(
        'seg', 'sim-owner', capture_at, 'gs://synthetic/audio', duration, Priority.DEEP, conversation_id='conv'
    )


def manifest_body(references, capture_at=7.0):
    return (
        MAGIC
        + json.dumps(
            {
                'owner_id': 'sim-owner',
                'conversation_id': 'conv',
                'capture_at': capture_at,
                'references': references,
                'context': {'provenance': 'synthetic'},
            }
        ).encode()
    )


def reference(start, offset, frames, source):
    return {
        'start_frame': start,
        'offset_frame': offset,
        'frames': frames,
        'pcm_sha256': hashlib.sha256(source).hexdigest(),
    }


def test_manifest_slices_covering_the_capture_exactly_materialize():
    frames = RATE
    first, second = pcm(8000), pcm(8000)
    body = manifest_body([reference(0, 0, 8000, first), reference(8000, 0, 8000, second)])
    wav = materialize(body, manifest_item(), lambda ref: first if ref['start_frame'] == 0 else second)
    assert wav[:4] == b'RIFF'


@pytest.mark.parametrize(
    'references',
    [
        [reference(0, 0, 8001, pcm(8000)), reference(8001, 0, 8000, pcm(8000))],  # one frame past EOF
        [reference(0, 0, 0, pcm(1))],  # zero-frame slice
        [reference(8000, 0, 8000, pcm(8000)), reference(0, 0, 8000, pcm(8000))],  # start regression
    ],
    ids=['one-frame-past-eof', 'zero-frames', 'unordered-start'],
)
def test_manifest_slice_geometry_violations_are_rejected(references):
    sources = {index: pcm(8000) for index in range(len(references))}
    body = manifest_body(references)
    with pytest.raises(ValueError):
        materialize(body, manifest_item(), lambda ref: sources[references.index(ref)])


def test_manifest_pcm_digest_change_is_rejected():
    first = pcm(8000)
    body = manifest_body([reference(0, 0, 8000, first)])
    with pytest.raises(ValueError, match='digest'):
        materialize(body, manifest_item(), lambda ref: pcm(8000)[0:15998] + b'\x02\x00')


# --- admitted-duration tolerance of the projection payload -------------------------


@pytest.mark.parametrize(
    'audio_seconds,accepted',
    [
        (0.9, True),  # nominal -0.1 s: the double 0.09999999999999998 passes
        (0.9 + SAMPLE, True),
        (1.1 - SAMPLE, True),
        # The nominal +0.1 s overruns reject (1.1 - 1.0 is the double
        # 0.10000000000000009, one ulp past the fence), and one sample past
        # the tolerance rejects in both directions. Deterministic, pinned.
        (1.1, False),
        (0.9 - SAMPLE, False),
        (1.1 + SAMPLE, False),
    ],
)
def test_projection_payload_duration_tolerance_is_one_hundred_ms(audio_seconds, accepted):
    """The fence build_incoming/split_result share: +-0.1 s around the admitted
    capture, so a sample-rounded decoded clock always passes and a real
    mismatch by one sample past the tolerance fails."""
    item = WorkItem('seg', 'sim-owner', 0.0, 'gs://synthetic/audio', 1.0, Priority.DEEP)
    payload = {**SUCCESS_PAYLOAD, 'audio_seconds': audio_seconds, 'speech_seconds': min(0.5, audio_seconds)}
    payload['speech_spans'] = [{'start': 0.0, 'end': min(0.5, audio_seconds)}]
    payload['words'] = [{'word': 'Hello.', 'timestamp': [0.0, min(0.5, audio_seconds)]}]
    binding = ProjectionBinding('sim-owner', 'job', 'content', ('seg',))
    if accepted:
        assert build_incoming(item, binding, payload)
    else:
        with pytest.raises(ValueError, match='duration'):
            build_incoming(item, binding, payload)


def test_audio_unit_wav_covers_exactly_the_admitted_frames():
    unit = audio_unit(0.0, pcm(16001))
    assert unit.duration_seconds == pytest.approx(16001 / RATE)
    assert len(unit.wav) > 44  # RIFF header plus the sample-rounded frames

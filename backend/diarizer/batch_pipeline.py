"""Conversation-sized, synchronous GPU chain. Invoke only on the GPU worker lane.

Storage, lineage and model adapters are injected; importing this module does no
IO and loads no models. One instance owns one GPU, with a lock across the entire
chain. Missing results denote retryable failures per the scheduler contract.
"""

from dataclasses import dataclass
from enum import Enum
import math
import logging
import threading
from typing import Any, Callable, Mapping, Sequence

from config.batch_pipeline_providers import ProviderConfig
from config.sync_live_dedupe import sync_live_dedupe_active_for
from utils.batch_pipeline.contracts import WorkItem, WorkResult
from utils.batch_pipeline.errors import FatalGpuError

SAMPLE_RATE = 16000
_GPU_CHAIN_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


class ValidationReason(Enum):
    WORD_SHAPE = 'word_shape'
    WORD_CLOCK = 'word_clock'
    WORD_SEQUENCE = 'word_sequence'
    VAD_NONFINITE = 'vad_nonfinite'
    VAD_ORDER = 'vad_order'
    VAD_BOUNDS = 'vad_bounds'
    EMPTY_ASR = 'empty_asr'
    NO_OWNED_WORDS = 'no_owned_words'


class BatchValidationError(ValueError):
    """A closed reason code, never a provider exception message."""

    def __init__(self, reason: object):
        if not isinstance(reason, ValidationReason):
            raise ValueError('invalid batch validation reason')
        self.reason = reason.value
        super().__init__(reason.value)


def is_fatal_cuda_error(exc):
    # Same fatal states as parakeet.gpu_worker.classify_fatal_cuda_error; keep
    # the model-free chain independent of that service's torch/NeMo imports.
    markers = (
        'worker cuda graph policy violated',
        'cuda out of memory',
        'cuda error: out of memory',
        'cudaerrormemoryallocation',
        'cublas_status_alloc_failed',
        'cublas alloc failed',
        'device-side assert',
        'cudaerrorassert',
        'illegal memory access',
        'cudaerrorillegaladdress',
        'unspecified launch failure',
        'cudaerrorlaunchfailure',
        'capture must end on the same stream it began on',
        'operation not permitted when stream is capturing',
        'cudaerrorstreamcaptureunsupported',
    )
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if (
            any(marker in str(exc).lower() for marker in markers)
            or type(exc).__name__ in {'AcceleratorError', 'OutOfMemoryError'}
            or isinstance(exc, FatalGpuError)
        ):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


@dataclass(frozen=True)
class Window:
    segment_id: str
    samples: Any
    start: float
    core_start: float
    core_end: float

    @property
    def duration(self):
        return len(self.samples) / SAMPLE_RATE


@dataclass(frozen=True)
class LiveWords:
    """Resolver attestation, bound to this immutable audio reference and full span.

    Source overlap alone is insufficient. The resolver must independently verify
    lineage coverage and record quality; current lexical post-STT dedupe cannot
    produce this receipt. No resolver means no pre-STT reuse.
    """

    audio_uri: str
    duration_seconds: float
    words: Sequence[dict]
    full_source_coverage: bool
    record_quality: bool


def validate_words(words, duration):
    result = []
    previous = -1.0
    for word in words:
        try:
            start, end = map(float, word['timestamp'])
        except ValueError:
            raise BatchValidationError(ValidationReason.WORD_SHAPE) from None
        if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start <= end <= duration + 0.01:
            raise BatchValidationError(ValidationReason.WORD_CLOCK)
        if start < previous or not isinstance(word['word'], str) or not word['word'].strip():
            raise BatchValidationError(ValidationReason.WORD_SEQUENCE)
        previous = start
        result.append({**word, 'timestamp': [start, end]})
    return result


def crop_model_vad_spans(spans, duration):
    """Intersect frame-centered model intervals with the real captured buffer.

    Pyannote's loose frame crop may leave the final frame center past EOF.
    Only the end is cropped; malformed or wholly out-of-buffer spans still fail.
    """
    result = []
    for start, end in spans:
        if not all(math.isfinite(v) for v in (start, end)):
            raise BatchValidationError(ValidationReason.VAD_NONFINITE)
        if not 0 <= start < end:
            raise BatchValidationError(ValidationReason.VAD_ORDER)
        if start >= duration:
            raise BatchValidationError(ValidationReason.VAD_BOUNDS)
        result.append((start, min(end, duration)))
    return result


def vad_speech_spans(spans, total_samples):
    """Original capture-relative, sample-rounded VAD union without ASR padding."""
    merged = []
    for start, end in sorted(spans):
        left = max(0, min(total_samples, round(start * SAMPLE_RATE)))
        right = max(left, min(total_samples, round(end * SAMPLE_RATE)))
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        elif right > left:
            merged.append((left, right))
    return [{'start': left / SAMPLE_RATE, 'end': right / SAMPLE_RATE} for left, right in merged]


def speech_windows(item, samples, spans, config):
    """Pad VAD edges and keep context across forced cuts; emit each midpoint once."""
    duration = len(samples) / SAMPLE_RATE
    merged = []
    for start, end in sorted(spans):
        if not all(math.isfinite(v) for v in (start, end)):
            raise BatchValidationError(ValidationReason.VAD_NONFINITE)
        if not 0 <= start < end:
            raise BatchValidationError(ValidationReason.VAD_ORDER)
        if end > duration + 0.01:
            raise BatchValidationError(ValidationReason.VAD_BOUNDS)
        start, end = max(0, start - config.context_seconds), min(duration, end + config.context_seconds)
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for start, end in merged:
        core = start
        while core < end:
            stop = min(end, core + config.window_seconds)
            left = max(0, core - config.context_seconds)
            right = min(duration, stop + config.context_seconds)
            left_sample, right_sample = int(left * SAMPLE_RATE), int(right * SAMPLE_RATE)
            yield Window(
                item.segment_id,
                samples[left_sample:right_sample],
                left_sample / SAMPLE_RATE,
                core,
                stop,
            )
            core = stop


def pack_windows(windows, config):
    """Length buckets across owners, bounded by padded (not summed) audio cost."""
    batch = []
    longest = 0
    for window in sorted(windows, key=lambda w: (w.duration, w.segment_id, w.start)):
        if window.duration > config.max_padded_seconds:
            raise ValueError('window exceeds padded budget')
        if batch and (
            len(batch) >= config.batch_size
            or max(longest, window.duration) * (len(batch) + 1) > config.max_padded_seconds
        ):
            yield batch
            batch, longest = [], 0
        batch.append(window)
        longest = max(longest, window.duration)
    if batch:
        yield batch


class PipelineWorker:
    def __init__(
        self,
        *,
        decode: Callable,
        vad: Callable,
        words_providers: Mapping[str, Any],
        diarizers: Mapping[str, Callable],
        persist: Callable,
        config: ProviderConfig | None = None,
        live_words: Callable | None = None,
        single_speaker: Callable | None = None,
        on_failure: Callable | None = None,
        gpu_lock=None,
    ):
        self.config = config or ProviderConfig()
        # Reject unavailable candidates, never silently select another provider.
        self.words = words_providers[self.config.words]
        self.diarize = diarizers[self.config.diarizer]
        self.decode, self.vad, self.persist = decode, vad, persist
        self.live_words, self.single_speaker = live_words, single_speaker
        self.on_failure = on_failure
        self._lock = gpu_lock if gpu_lock is not None else _GPU_CHAIN_LOCK
        self._unavailable = False
        self.counts = {'items': 0, 'reused_live': 0, 'silence': 0, 'failed': 0}

    def process_batch(self, items: Sequence[WorkItem]) -> Sequence[WorkResult]:
        if len(items) > 32 or len({i.segment_id for i in items}) != len(items):
            raise ValueError('pull must contain at most 32 distinct conversations')
        if any(item.duration_seconds > self.config.max_unit_seconds for item in items):
            raise ValueError('conversation requires a dedicated batch GPU or a smaller admitted unit')
        if self.config.pool_kind == 'shared_live' and sum(i.duration_seconds for i in items) > 120:
            raise ValueError('shared-live pull exceeds 120 audio seconds; yield between pulls')
        if self.config.pool_kind == 'shared_live' and any(i.unit_kind != 'capture_span' for i in items):
            raise ValueError('shared-live requires explicitly admitted capture spans, never conversation units')
        with self._lock:
            if self._unavailable:
                raise FatalGpuError('GPU chain unavailable; restart required')
            results, group, seconds = [], [], 0
            # Bound decoded host memory to two audio-hours (~460 MB float32).
            for item in items:
                if group and seconds + item.duration_seconds > 7200:
                    results.extend(self._process(group))
                    group, seconds = [], 0
                group.append(item)
                seconds += item.duration_seconds
            results.extend(self._process(group))
            return results

    def _process(self, items):
        states, windows, failed, results = {}, [], set(), []
        failure_records = []
        shapes = {item.segment_id: {'samples': -1, 'vad_spans': -1, 'windows': -1, 'asr_words': 0} for item in items}

        def fail(item, exc, stage):
            # Quarantine poisoned CUDA state without importing a second GPU owner.
            if is_fatal_cuda_error(exc):
                self._unavailable = True
                raise FatalGpuError('fatal CUDA error; restart GPU chain') from exc
            if item.segment_id not in failed:
                failed.add(item.segment_id)
                self.counts['failed'] += 1
                reason = exc.reason if isinstance(exc, BatchValidationError) else 'unclassified'
                owned = len(states.get(item.segment_id, {}).get('words', []))
                shape = shapes[item.segment_id]
                failure_records.append(
                    (
                        type(exc).__name__,
                        stage,
                        item.segment_id,
                        reason,
                        shape['samples'],
                        shape['vad_spans'],
                        shape['windows'],
                        shape['asr_words'],
                        owned,
                    )
                )
                if self.on_failure:
                    try:
                        self.on_failure(item, type(exc).__name__)
                    except Exception as callback_error:
                        logger.warning('batch_failure_callback_failed exception_type=%s', type(callback_error).__name__)

        for item in items:
            self.counts['items'] += 1
            stage = 'fetch_decode'
            try:
                samples = self.decode(item)
                shapes[item.segment_id]['samples'] = len(samples)
                duration = len(samples) / SAMPLE_RATE
                if not 0 < duration <= self.config.max_unit_seconds or abs(duration - item.duration_seconds) > 0.1:
                    raise ValueError('decoded duration differs from admitted capture')
                stage = 'vad_windows'
                spans = list(self.vad(samples))
                shapes[item.segment_id]['vad_spans'] = len(spans)
                clips = list(speech_windows(item, samples, spans, self.config))
                shapes[item.segment_id]['windows'] = len(clips)
                speech_spans = vad_speech_spans(spans, len(samples))
                state = {
                    'item': item,
                    'samples': samples,
                    'words': [],
                    'silence': not clips,
                    'reused': False,
                    'speech_spans': speech_spans,
                    'speech_seconds': sum(span['end'] - span['start'] for span in speech_spans),
                }
                states[item.segment_id] = state
                if not clips:
                    self.counts['silence'] += 1
                    continue
                receipt = None
                if self.config.reuse_live and self.live_words:
                    if sync_live_dedupe_active_for(item.owner_id):
                        receipt = self.live_words(item)
                if (
                    receipt is not None
                    and receipt.audio_uri == item.audio_uri
                    and abs(receipt.duration_seconds - duration) <= 0.01
                    and receipt.full_source_coverage
                    and receipt.record_quality
                    and receipt.words
                ):
                    state['words'] = validate_words(receipt.words, duration)
                    state['reused'] = True
                    self.counts['reused_live'] += 1
                else:
                    windows.extend(clips)
            except Exception as exc:
                fail(item, exc, stage)

        for batch in pack_windows(windows, self.config):
            batch = [w for w in batch if w.segment_id not in failed]
            if not batch:
                continue
            try:
                hypotheses = self.words.transcribe_batch([w.samples for w in batch])
                if len(hypotheses) != len(batch):
                    raise ValueError('provider result cardinality mismatch')
            except Exception as exc:
                for window in batch:
                    fail(states[window.segment_id]['item'], exc, 'asr')
                continue
            for window, hypothesis in zip(batch, hypotheses):
                try:
                    checked_words = validate_words(hypothesis, window.duration)
                    shapes[window.segment_id]['asr_words'] += len(checked_words)
                    for word in checked_words:
                        start, end = [t + window.start for t in word['timestamp']]
                        midpoint = (start + end) / 2
                        if window.core_start <= midpoint < window.core_end:
                            states[window.segment_id]['words'].append({**word, 'timestamp': [start, end]})
                except Exception as exc:
                    fail(states[window.segment_id]['item'], exc, 'word_clocks')

        for state in states.values():
            item = state['item']
            if item.segment_id in failed:
                continue
            stage = 'assemble_words'
            try:
                duration = len(state['samples']) / SAMPLE_RATE
                words = validate_words(sorted(state['words'], key=lambda w: w['timestamp'][0]), duration)
                if not state['silence'] and not words:
                    raise BatchValidationError(
                        ValidationReason.NO_OWNED_WORDS
                        if shapes[item.segment_id]['asr_words']
                        else ValidationReason.EMPTY_ASR
                    )
                # The triage adapter must return existing calibrated resolution.
                resolution = (
                    self.single_speaker(item, state['samples'], words) if self.single_speaker and words else None
                )
                single = (
                    resolution is not None
                    and resolution.coverage >= 0.9
                    and len(set(resolution.speaker_ids.values())) == 1
                )
                if state['silence']:
                    diarization = {'turns': [], 'outcome': 'silence'}
                elif single:
                    diarization = {
                        'turns': [{'start': 0, 'end': duration, 'speaker': 'SPEAKER_00'}],
                        'outcome': 'skipped_single',
                    }
                else:
                    stage = 'diarize'
                    diarization = self.diarize(state['samples'])
                payload = {
                    'words': words,
                    'diarization': diarization,
                    'words_provider': 'live_record' if state['reused'] else self.config.words,
                    'diarizer': self.config.diarizer,
                    'audio_seconds': duration,
                    'speech_seconds': state['speech_seconds'],
                    'speech_spans': state['speech_spans'],
                }
                stage = 'persist'
                uri = self.persist(item, payload)
                results.append(WorkResult(item.segment_id, uri, 'silence' if state['silence'] else 'success'))
            except Exception as exc:
                fail(item, exc, stage)
        # Emit only strings/integers after every item exception handler has exited.
        # Handler error printers must not inherit the private worker exception.
        for error_class, failure_stage, segment_id, reason, samples, spans, clips, asr_words, owned in failure_records:
            try:
                logger.error(
                    'event=batch_worker_failed error_class=%s stage=%s segment_id=%s reason=%s '
                    'samples=%d vad_spans=%d windows=%d asr_words=%d owned_words=%d',
                    error_class,
                    failure_stage,
                    segment_id,
                    reason,
                    samples,
                    spans,
                    clips,
                    asr_words,
                    owned,
                )
            except Exception:
                pass  # Observability failure must never discard healthy results.
        return results

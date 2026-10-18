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

from config.stt_cap_dispatch import enabled as cap_dispatch_enabled
from utils.batch_pipeline.worker_silence import inspect_worker_silence
from config.batch_pipeline import (
    empty_asr_recovery_enabled,
    empty_asr_disposition_enabled,
    worker_silence_disposition_enabled,
    worker_validation_disposition_enabled,
)
from utils.observability.stt_cap_dispatch import record_audio
from config.batch_pipeline_providers import ProviderConfig
from config.sync_live_dedupe import sync_live_dedupe_active_for
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import WorkItem, WorkResult, HeldWork, RecoveryWork, ValidationFailureWork
from utils.batch_pipeline.errors import FatalGpuError
from utils.observability.fallback import record_fallback

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


def padded_retry_seconds(samples) -> float:
    left = 2 * SAMPLE_RATE
    right = max(2 * SAMPLE_RATE, 8 * SAMPLE_RATE - len(samples) - left)
    return (len(samples) + left + right) / SAMPLE_RATE


def padded_retry_fits(samples, max_padded_seconds: float) -> bool:
    return padded_retry_seconds(samples) <= min(120, max_padded_seconds)


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
        recover_words: Callable | None = None,
        gpu_lock=None,
    ):
        self.config = config or ProviderConfig()
        # Reject unavailable candidates, never silently select another provider.
        self.words = words_providers[self.config.words]
        self.diarize = diarizers[self.config.diarizer]
        self.decode, self.vad, self.persist = decode, vad, persist
        self.live_words, self.single_speaker = live_words, single_speaker
        self.on_failure = on_failure
        self.recover_words = recover_words
        self._lock = gpu_lock if gpu_lock is not None else _GPU_CHAIN_LOCK
        self._unavailable = False
        self.counts = {'items': 0, 'reused_live': 0, 'silence': 0, 'failed': 0}

    def process_batch(
        self, items: Sequence[WorkItem], *, authorize_dispatch=None
    ) -> Sequence[WorkResult | HeldWork | RecoveryWork | ValidationFailureWork]:
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
                    results.extend(self._process(group, authorize_dispatch=authorize_dispatch))
                    group, seconds = [], 0
                group.append(item)
                seconds += item.duration_seconds
            results.extend(self._process(group, authorize_dispatch=authorize_dispatch))
            return results

    def _process(self, items, *, authorize_dispatch=None):
        states, windows, failed, results = {}, [], set(), []
        failure_records = []
        held = set()
        recovery_records = []
        silence_records = []
        shapes = {item.segment_id: {'samples': -1, 'vad_spans': -1, 'windows': -1, 'asr_words': 0} for item in items}

        def allowed(required):
            try:
                return set(authorize_dispatch(required)) if authorize_dispatch is not None else set()
            except Exception:
                return set()

        def accepted(segment_id, seconds):
            record_audio('sync', 'accepted', self.config.words, seconds)
            state = states[segment_id]
            state['cap_provider_audio_seconds'] = state.get('cap_provider_audio_seconds', 0) + seconds

        def fail(item, exc, stage):
            # Quarantine poisoned CUDA state without importing a second GPU owner.
            if is_fatal_cuda_error(exc):
                self._unavailable = True
                raise FatalGpuError('fatal CUDA error; restart GPU chain') from exc
            if item.segment_id not in failed:
                failed.add(item.segment_id)
                self.counts['failed'] += 1
                reason = exc.reason if isinstance(exc, BatchValidationError) else 'unclassified'
                if reason == 'empty_asr':
                    record_correctness('empty_asr_attempt', source='gpu_worker', seconds=item.duration_seconds)
                if (
                    (
                        reason == 'empty_asr'
                        and empty_asr_recovery_enabled()
                        or reason in {'empty_asr', 'no_owned_words'}
                        and empty_asr_disposition_enabled()
                    )
                    and stage == 'assemble_words'
                    and self.recover_words is not None
                ):
                    state = states.get(item.segment_id, {})
                    results.append(
                        RecoveryWork(
                            item.segment_id,
                            padded_retry_empty=bool(state.get('padded_retry_empty')),
                            padded_retry=state.get('padded_retry'),
                            reason=reason,
                        )
                    )
                elif isinstance(exc, BatchValidationError) and worker_validation_disposition_enabled():
                    # Repeating the same validated GPU failure cannot establish
                    # silence or corrupt audio. End this chain now and retain
                    # custody for the independent privacy-fenced recovery path.
                    results.append(ValidationFailureWork(item.segment_id, stage, reason))
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
                silence = None
                try:
                    spans = list(self.vad(samples))
                except BatchValidationError as error:
                    if error.reason != 'vad_bounds' or not worker_validation_disposition_enabled():
                        raise
                    # A frame may start beyond a very short real buffer (20 ms
                    # in production). Only independent strict VAD can establish
                    # silence; malformed/unavailable evidence stays held.
                    try:
                        silence = inspect_worker_silence(item, samples)
                    except Exception:
                        pass
                    if silence is None:
                        raise
                    spans = []
                shapes[item.segment_id]['vad_spans'] = len(spans)
                clips = list(speech_windows(item, samples, spans, self.config))
                shapes[item.segment_id]['windows'] = len(clips)
                speech_spans = vad_speech_spans(spans, len(samples))
                state = {
                    'item': item,
                    'samples': samples,
                    'words': [],
                    'silence': not clips,
                    'silence_payload': silence,
                    'reused': False,
                    'speech_spans': speech_spans,
                    'speech_seconds': sum(span['end'] - span['start'] for span in speech_spans),
                    'window_min_samples': min((len(w.samples) for w in clips), default=0),
                    'window_max_samples': max((len(w.samples) for w in clips), default=0),
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
            batch = [w for w in batch if w.segment_id not in failed and w.segment_id not in held]
            if cap_dispatch_enabled():
                # Authorization belongs immediately before ASR, after potentially
                # slow decode/VAD and between successive microbatches. Missing
                # policy authority is a hold, never provider permission.
                required = {w.segment_id for w in batch}
                held.update(required - allowed(required))
                batch = [w for w in batch if w.segment_id not in held]
            if not batch:
                continue
            try:
                hypotheses = self.words.transcribe_batch([w.samples for w in batch])
                if cap_dispatch_enabled():
                    for window in batch:
                        accepted(window.segment_id, window.duration)
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
            if item.segment_id in held:
                results.append(HeldWork(item.segment_id))
                continue
            if item.segment_id in failed:
                continue
            stage = 'assemble_words'
            try:
                duration = len(state['samples']) / SAMPLE_RATE
                words = validate_words(sorted(state['words'], key=lambda w: w['timestamp'][0]), duration)
                if not state['silence'] and not words and self.recover_words is not None:
                    # Retry this unit once, independently of the length-bucketed
                    # batch and VAD/core selection. Never combine partial text
                    # with a second hypothesis or publish a fabricated silence.
                    reason = 'no_owned_words' if shapes[item.segment_id]['asr_words'] else 'empty_asr'
                    stage = 'asr_recovery'
                    fits_retry = padded_retry_fits(state['samples'], self.config.max_padded_seconds)
                    if cap_dispatch_enabled():
                        recovered = self.recover_words(
                            state['samples'],
                            self.config.max_padded_seconds,
                            before_dispatch=lambda: item.segment_id in allowed({item.segment_id}),
                            after_dispatch=lambda seconds: accepted(item.segment_id, seconds),
                        )
                        if recovered is None and (
                            fits_retry
                            or not (
                                reason == 'empty_asr'
                                and empty_asr_recovery_enabled()
                                or reason in {'empty_asr', 'no_owned_words'}
                                and empty_asr_disposition_enabled()
                            )
                        ):
                            held.add(item.segment_id)
                            results.append(HeldWork(item.segment_id))
                            continue
                    else:
                        recovered = self.recover_words(state['samples'], self.config.max_padded_seconds)
                    if recovered is None or not fits_retry:
                        words = []
                        state['padded_retry'] = 'skipped_oversize'
                        state['padded_retry_empty'] = False
                        recovery_outcome = 'skipped_oversize'
                    else:
                        words = validate_words(recovered, duration)
                        state['padded_retry'] = 'recovered' if words else 'empty'
                        state['padded_retry_empty'] = not words
                        recovery_outcome = 'recovered' if words else 'empty'
                    recovery_records.append(
                        (
                            item.segment_id,
                            reason,
                            len(state['samples']),
                            len(words),
                            shapes[item.segment_id]['asr_words'],
                            shapes[item.segment_id]['windows'],
                            state['window_min_samples'],
                            state['window_max_samples'],
                            round(state['speech_seconds'] * SAMPLE_RATE),
                            recovery_outcome,
                        )
                    )
                    stage = 'assemble_words'
                silence = state['silence_payload']
                if (
                    not state['silence']
                    and not words
                    and not shapes[item.segment_id]['asr_words']
                    and worker_silence_disposition_enabled()
                ):
                    try:
                        silence = inspect_worker_silence(item, state['samples'])
                    except Exception:
                        # Unavailable/invalid strict VAD is never silence. Keep
                        # the original empty-ASR quarantine and recovery route.
                        silence = None
                    if silence is not None:
                        state['silence'] = True
                        state['speech_spans'], state['speech_seconds'] = [], 0.0
                        self.counts['silence'] += 1
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
                if silence is not None:
                    payload.update(silence)
                if cap_dispatch_enabled():
                    payload['cap_dispatch'] = {
                        'omi_funded_accepted_provider_audio_seconds': state.get('cap_provider_audio_seconds', 0),
                        'admission': 'authorized_compute',
                    }
                stage = 'persist'
                uri = self.persist(item, payload)
                results.append(WorkResult(item.segment_id, uri, 'silence' if state['silence'] else 'success'))
                if silence is not None:
                    silence_records.append(item.segment_id)
            except Exception as exc:
                fail(item, exc, stage)
        # Emit only strings/integers after every item exception handler has exited.
        # Handler error printers must not inherit the private worker exception.
        for (
            segment_id,
            reason,
            samples,
            owned,
            asr_words,
            clips,
            shortest,
            longest,
            speech,
            recovery_outcome,
        ) in recovery_records:
            try:
                record_fallback(
                    component='stt_selection',
                    from_mode='batch',
                    to_mode='batch',
                    reason='other',
                    outcome=(
                        'recovered'
                        if owned
                        else ('degraded' if recovery_outcome == 'skipped_oversize' else 'exhausted')
                    ),
                )
                logger.info(
                    'event=batch_asr_recovery segment_id=%s reason=%s samples=%d owned_words=%d outcome=%s '
                    'asr_words=%d windows=%d window_min_samples=%d window_max_samples=%d speech_samples=%d',
                    segment_id,
                    reason,
                    samples,
                    owned,
                    recovery_outcome,
                    asr_words,
                    clips,
                    shortest,
                    longest,
                    speech,
                )
            except Exception:
                pass  # Metrics/logging cannot invalidate a completed inference.
        for segment_id in silence_records:
            try:
                record_fallback(
                    component='stt_selection', from_mode='batch', to_mode='none', reason='other', outcome='recovered'
                )
                logger.info('event=batch_worker_silence_disposition segment_id=%s outcome=silence', segment_id)
            except Exception:
                pass  # Observability cannot invalidate a persisted result.
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

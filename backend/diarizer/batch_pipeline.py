"""Conversation-sized, synchronous GPU chain. Invoke only on the GPU worker lane.

Storage, lineage and model adapters are injected; importing this module does no
IO and loads no models. One instance owns one GPU, with a lock across the entire
chain. Missing results denote retryable failures per the scheduler contract.
"""

from concurrent.futures import Future, ThreadPoolExecutor, wait as wait_futures
from dataclasses import dataclass
from enum import Enum
import math
import logging
import threading
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from config.batch_pipeline_gpu_skip import diarize_speech_only_enabled, short_speech_single_enabled
from config.prerecorded_language import language_class
from config.stt_cap_dispatch import execution_admission_enabled as cap_dispatch_enabled
from utils.batch_pipeline.worker_silence import inspect_worker_silence
from diarizer.batch_pipeline_context import LeftContextIndex, capture_stream, starts_in_speech
from config.batch_pipeline import (
    LONG_SPEECH_HANDOFF_SECONDS,
    long_speech_handoff_enabled,
    empty_asr_recovery_enabled,
    empty_asr_disposition_enabled,
    worker_io_concurrency,
    worker_silence_disposition_enabled,
    worker_validation_disposition_enabled,
)
from utils.observability.stt_cap_dispatch import record_audio
from config.batch_pipeline_providers import ProviderConfig
from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL
from config.sync_live_dedupe import sync_live_dedupe_active_for
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.contracts import WorkItem, WorkResult, HeldWork, RecoveryWork, ValidationFailureWork
from utils.batch_pipeline.diarization_gate import (
    compact as compact_speech,
    map_back,
    plan_compaction,
    short_single_region,
    speech_regions,
    unassigned_word_count,
)
from utils.batch_pipeline.gpu_skip_metrics import record_compacted_unassigned, record_decision
from utils.batch_pipeline.errors import FatalGpuError
from utils.batch_pipeline.language_metrics import record_route
from utils.observability.fallback import record_fallback

SAMPLE_RATE = 16000
_GPU_CHAIN_LOCK = threading.Lock()
# Audio admitted to fetch/decode ahead of the item currently on the GPU. The
# next item is always admitted; further items only while their summed duration
# stays within this budget (~58 MB PCM16 + ~115 MB float32 in transit).
PREFETCH_AHEAD_SECONDS = 1800
logger = logging.getLogger(__name__)


class ValidationReason(Enum):
    UNSUPPORTED_LANGUAGE = 'unsupported_language'
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


class _DecodePrefetch:
    """Fetch/decode admitted items ahead of the GPU, consumed strictly in order.

    At most ``limit`` items are submitted but not yet consumed, and beyond the
    first such item their summed audio stays within ``ahead_seconds``. Callers
    process one bounded group at a time, so prefetch never crosses into the
    next decoded group. Exceptions surface from ``take`` on the calling thread.
    """

    def __init__(self, executor, decode, items, limit, ahead_seconds):
        self._executor, self._decode, self._items = executor, decode, list(items)
        self._limit, self._ahead_seconds = limit, ahead_seconds
        self._futures: dict[int, Future] = {}
        self._submitted = 0
        self._consumed = 0

    def _fill(self):
        while self._submitted < len(self._items):
            outstanding = self._submitted - self._consumed
            if outstanding >= self._limit:
                return
            ahead = sum(self._items[i].duration_seconds for i in range(self._consumed, self._submitted))
            if outstanding and ahead + self._items[self._submitted].duration_seconds > self._ahead_seconds:
                return
            self._futures[self._submitted] = self._executor.submit(self._decode, self._items[self._submitted])
            self._submitted += 1

    def take(self, index):
        if index != self._consumed:
            raise RuntimeError('prefetch must be consumed in admitted order')
        self._fill()
        future = self._futures.pop(index)
        self._consumed += 1
        # Start the following fetches before blocking: they overlap this
        # item's wait and its VAD on the GPU.
        self._fill()
        return future.result()

    def close(self):
        """Never leave fetches running after the flight; discard their outcomes."""
        pending = list(self._futures.values())
        self._futures.clear()
        for future in pending:
            future.cancel()
        wait_futures(pending)


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


PARAKEET_LANGUAGES = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'}


def long_speech_handoff(state: dict, reason: str) -> bool:
    """Skip the padded Parakeet retry: it cannot recover speech in a language Parakeet lacks.

    Only a zero-word first pass whose intake recorded an STT language that is
    unknown (''), ``multi`` or outside Parakeet's set, with at least
    LONG_SPEECH_HANDOFF_SECONDS of worker VAD speech, and only while the
    quarantine-recovery handoff exists. Units without a recorded intake language
    (older staged audio, record lane) keep the retry.
    """
    language = state.get('stt_language')
    return (
        reason == 'empty_asr'
        and isinstance(language, str)
        and language not in PARAKEET_LANGUAGES
        and state.get('speech_seconds', 0.0) >= LONG_SPEECH_HANDOFF_SECONDS
        and (empty_asr_recovery_enabled() or empty_asr_disposition_enabled())
        and long_speech_handoff_enabled()
    )


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
        io_concurrency: int | None = None,
        flight_models=None,
        stream_of: Callable | None = None,
        language_of: Callable | None = None,
    ):
        self.config = config or ProviderConfig()
        # Reject unavailable candidates, never silently select another provider.
        self.words = words_providers[self.config.words]
        self.diarize = diarizers[self.config.diarizer]
        self.decode, self.vad, self.persist = decode, vad, persist
        self.live_words, self.single_speaker = live_words, single_speaker
        self.on_failure = on_failure
        self.recover_words = recover_words
        # Optional packed pyannote stages (diarizer.batch_pipeline_flight).
        # Absent or failed, every item takes the serial vad/diarize calls.
        self.flight: Any = flight_models if self.config.diarizer == 'pyannote' else None
        self._lock = gpu_lock if gpu_lock is not None else _GPU_CHAIN_LOCK
        self._unavailable = False
        self.counts = {'items': 0, 'reused_live': 0, 'silence': 0, 'failed': 0, 'left_context': 0}
        # Same-owner predecessor tails for units whose speech starts at sample 0.
        # Capture stream of a decoded unit (see batch_pipeline_context.capture_stream).
        # Without it only conversation units have a stream.
        self.stream_of = stream_of or capture_stream
        # Intake's resolved STT language of a decoded unit; None when unrecorded.
        self.language_of = language_of or (lambda item: None)
        self.left_context = LeftContextIndex(
            max_seconds=self.config.asr_left_context_seconds, max_units=self.config.asr_left_context_units
        )
        # Artifact IO only (fetch/decrypt/decode, encrypt/upload). Model calls,
        # CUDA work and the chain lock stay on the calling thread.
        self.io_concurrency = io_concurrency if io_concurrency is not None else worker_io_concurrency()
        if not 1 <= self.io_concurrency <= 32:
            raise ValueError('worker IO concurrency must be in [1, 32]')
        self._io = (
            ThreadPoolExecutor(max_workers=self.io_concurrency, thread_name_prefix='batch-worker-io')
            if self.io_concurrency > 1
            else None
        )

    def _fatal(self, exc):
        self._unavailable = True
        raise FatalGpuError('fatal CUDA error; restart GPU chain') from exc

    def _flight_segment(self, decoded):
        if self.flight is None or not decoded:
            return [None] * len(decoded)
        try:
            features = list(self.flight.segment([samples for _, samples in decoded]))
            if len(features) != len(decoded):
                raise ValueError('flight segmentation cardinality mismatch')
            return features
        except Exception as exc:
            if is_fatal_cuda_error(exc):
                self._fatal(exc)
            logger.warning('event=batch_flight_fallback stage=segmentation exception_type=%s', type(exc).__name__)
            return [None] * len(decoded)

    def _flight_diarize(self, pending):
        # Packed embeddings describe the full unit; speech-only diarization
        # clusters a compacted waveform, so it keeps its own serial call.
        if self.flight is None or not pending or diarize_speech_only_enabled():
            return {}
        try:
            outcomes = list(self.flight.diarize_many([(s['samples'], s.get('flight_features')) for s in pending]))
            if len(outcomes) != len(pending):
                raise ValueError('flight diarization cardinality mismatch')
            return {s['item'].segment_id: outcome for s, outcome in zip(pending, outcomes)}
        except Exception as exc:
            if is_fatal_cuda_error(exc):
                self._fatal(exc)
            logger.warning('event=batch_flight_fallback stage=diarization exception_type=%s', type(exc).__name__)
            return {}

    def _diarize_unit(self, samples, evidence, words):
        """Diarize retained speech only; any doubt diarizes the full unit.

        ``evidence`` is unpadded VAD speech plus every word clock, so no audio
        VAD or ASR marked as speech is ever withheld from the diarizer.
        """
        seconds = len(samples) / SAMPLE_RATE
        if not diarize_speech_only_enabled():
            record_decision('full_flag_off', unit_seconds=seconds, diarized_seconds=seconds)
            return self.diarize(samples)
        if not evidence:
            record_decision('full_no_evidence', unit_seconds=seconds, diarized_seconds=seconds)
            return self.diarize(samples)
        compacted = None
        try:
            plan = plan_compaction(evidence, len(samples))
            compacted = (
                compact_speech(
                    samples, plan, concatenate=np.concatenate, zeros=lambda n: np.zeros(n, dtype=samples.dtype)
                )
                if plan is not None
                else None
            )
        except Exception:
            return self._diarize_full(samples, 'full_compaction_error')
        if plan is None or compacted is None:
            # Dense unit: compaction would remove too little audio to matter.
            return self._diarize_full(samples, 'full_kept_over_80pct')
        output = self.diarize(compacted)
        try:
            turns = map_back(output['turns'], plan)
            mapped = {**output, 'turns': turns}
            if 'overlaps' in output:
                mapped['overlaps'] = map_back(output['overlaps'], plan)
        except (KeyError, TypeError, ValueError):
            return self._diarize_full(samples, 'full_compaction_error')
        if words and not turns:
            # Never let compaction alone remove all speaker evidence for words.
            return self._diarize_full(samples, 'full_compacted_empty')
        diarized = plan.compact_samples / SAMPLE_RATE
        record_decision('compacted', unit_seconds=seconds, diarized_seconds=diarized)
        try:
            record_compacted_unassigned(unassigned_word_count(words, turns))
        except Exception:
            pass  # Observability cannot change the diarization result.
        mapped['speech_compaction'] = {'diarized_seconds': diarized, 'audio_seconds': seconds}
        return mapped

    def _diarize_full(self, samples, decision):
        seconds = len(samples) / SAMPLE_RATE
        record_decision(decision, unit_seconds=seconds, diarized_seconds=seconds)
        try:
            dense = decision == 'full_kept_over_80pct'
            record_fallback(
                component='vad',
                from_mode='batch_speech_only_diarization',
                to_mode='full_unit_diarization',
                reason='kept_over_80pct' if dense else 'other',
                outcome='recovered' if dense else 'degraded',
            )
        except Exception:
            pass  # Observability cannot change the diarization result.
        return self.diarize(samples)

    def _with_left_context(self, state, clips):
        """Prefix the first window with the predecessor's speech-run audio.

        Only a unit whose VAD speech starts at sample 0 qualifies. Window core
        ownership still starts at 0, so prefix words are never emitted.
        """
        item, samples = state['item'], state['samples']
        first = clips[0]
        if (
            self.config.asr_left_context_seconds <= 0
            or first.start != 0
            or not isinstance(samples, np.ndarray)
            or not starts_in_speech(state.get('vad_raw') or [])
        ):
            return clips
        context = self.left_context.lookup(item, len(samples) / SAMPLE_RATE, state.get('stream'))
        if context is None:
            return clips
        room = int((self.config.max_padded_seconds - first.duration) * SAMPLE_RATE)
        if room <= 0:
            return clips
        context = context[-room:]
        self.counts['left_context'] += 1
        prefixed = Window(
            first.segment_id,
            np.concatenate([context.astype(samples.dtype, copy=False), first.samples]),
            -len(context) / SAMPLE_RATE,
            first.core_start,
            first.core_end,
        )
        return [prefixed, *clips[1:]]

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
                if reason == 'empty_asr' and not item.shadow:
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
                elif isinstance(exc, BatchValidationError) and (
                    reason == 'unsupported_language' or worker_validation_disposition_enabled()
                ):
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

        prefetch = (
            _DecodePrefetch(self._io, self.decode, items, self.io_concurrency, PREFETCH_AHEAD_SECONDS)
            if self._io is not None
            else None
        )
        pending_persist = []

        def settle_persist(entry):
            slot, item, future, silent, has_silence = entry
            try:
                uri = future.result()
            except Exception as exc:
                fail(item, exc, 'persist')
                return
            results[slot] = WorkResult(item.segment_id, uri, 'silence' if silent else 'success')
            if has_silence:
                silence_records.append(item.segment_id)

        try:

            def decoded_units():
                for index, item in enumerate(items):
                    self.counts['items'] += 1
                    try:
                        samples = prefetch.take(index) if prefetch is not None else self.decode(item)
                        shapes[item.segment_id]['samples'] = len(samples)
                        duration = len(samples) / SAMPLE_RATE
                        if (
                            not 0 < duration <= self.config.max_unit_seconds
                            or abs(duration - item.duration_seconds) > 0.1
                        ):
                            raise ValueError('decoded duration differs from admitted capture')
                    except Exception as exc:
                        fail(item, exc, 'fetch_decode')
                        continue
                    yield item, samples

            if self.flight is None:
                # Serial: VAD each unit as soon as it is decoded (prefetch overlap).
                units = ((unit, None) for unit in decoded_units())
            else:
                # One packed segmentation pass shared by VAD and diarization; a
                # None feature selects the unchanged serial VAD call for that unit.
                decoded = list(decoded_units())
                units = zip(decoded, self._flight_segment(decoded))
            for (item, samples), features in units:
                stage = 'vad_windows'
                try:
                    duration = len(samples) / SAMPLE_RATE
                    silence = None
                    try:
                        spans = list(
                            self.vad(samples) if features is None else self.flight.vad_spans(samples, features)
                        )
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
                        'flight_features': features,
                    }
                    states[item.segment_id] = state
                    try:
                        state['stream'] = self.stream_of(item)
                    except Exception:
                        state['stream'] = None  # No stream identity: no left context.
                    try:
                        state['stt_language'] = self.language_of(item)
                    except Exception:
                        state['stt_language'] = None
                    if self.config.words == 'parakeet':
                        # A new-admission rollback cannot revoke the quality
                        # boundary for audio already in this worker's custody.
                        blocked = language_class(state['stt_language']) != 'supported'
                        if not item.shadow:
                            record_route(
                                'worker',
                                state['stt_language'],
                                'blocked' if blocked else 'parakeet',
                                segment_id=item.segment_id,
                            )
                        if blocked and clips:
                            # Never ask a fixed-language recognizer to guess an
                            # unknown language, even if it would return words.
                            # Keep encrypted audio for independent recovery; this
                            # is not evidence of an empty recognizer response.
                            raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)
                    if not clips:
                        self.counts['silence'] += 1
                        continue
                    # Every non-silent unit can be a later unit's predecessor.
                    state['vad_raw'] = spans
                    receipt = None
                    if not item.shadow and self.config.reuse_live and self.live_words:
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
                        state['asr_clips'] = clips
                except Exception as exc:
                    fail(item, exc, stage)

            # Predecessors in this flight become visible before any lookup;
            # earlier flights' tails persist in the bounded index.
            for state in states.values():
                if state['item'].segment_id not in failed:
                    self.left_context.remember(
                        state['item'], state['samples'], state.get('vad_raw') or [], state.get('stream')
                    )
            attached = self.counts['left_context']
            for state in states.values():
                clips = state.pop('asr_clips', None)
                if not clips or state['item'].segment_id in failed:
                    continue
                windows.extend(self._with_left_context(state, clips))
            if self.counts['left_context'] > attached:
                logger.info(
                    'event=batch_asr_left_context units=%d attached=%d',
                    len(items),
                    self.counts['left_context'] - attached,
                )

            for batch in pack_windows(windows, self.config):
                batch = [w for w in batch if w.segment_id not in failed and w.segment_id not in held]
                required = {
                    w.segment_id
                    for w in batch
                    if not states[w.segment_id]['item'].shadow
                    and cap_dispatch_enabled(states[w.segment_id]['item'].owner_id, 'batch')
                }
                if required:
                    # Authorization belongs immediately before ASR, after potentially
                    # slow decode/VAD and between successive microbatches. Missing
                    # policy authority is a hold, never provider permission.
                    held.update(required - allowed(required))
                    batch = [w for w in batch if w.segment_id not in held]
                if not batch:
                    continue
                try:
                    hypotheses = self.words.transcribe_batch([w.samples for w in batch])
                    for window in batch:
                        if not states[window.segment_id]['item'].shadow and cap_dispatch_enabled(
                            states[window.segment_id]['item'].owner_id, 'batch'
                        ):
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
                        for word in checked_words:
                            start, end = [t + window.start for t in word['timestamp']]
                            midpoint = (start + end) / 2
                            if midpoint < 0:
                                # Left-context words are the predecessor's; they never
                                # count as this unit's ASR output (empty_asr stays empty_asr).
                                continue
                            shapes[window.segment_id]['asr_words'] += 1
                            if window.core_start <= midpoint < window.core_end:
                                # A left-context window may own a word straddling the seam.
                                states[window.segment_id]['words'].append({**word, 'timestamp': [max(0.0, start), end]})
                    except Exception as exc:
                        fail(states[window.segment_id]['item'], exc, 'word_clocks')

            prepared = []
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
                        if long_speech_handoff(state, reason):
                            # Repadding cannot make Parakeet transcribe a language it
                            # does not have. Hand off to recovery without a retry.
                            words = []
                            state['padded_retry'] = 'skipped_long_speech'
                            state['padded_retry_empty'] = False
                            recovery_records.append(
                                (
                                    item.segment_id,
                                    reason,
                                    len(state['samples']),
                                    0,
                                    shapes[item.segment_id]['asr_words'],
                                    shapes[item.segment_id]['windows'],
                                    state['window_min_samples'],
                                    state['window_max_samples'],
                                    round(state['speech_seconds'] * SAMPLE_RATE),
                                    'skipped_long_speech',
                                )
                            )
                        else:
                            if not item.shadow and cap_dispatch_enabled(item.owner_id, 'batch'):
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
                    evidence = speech_regions(state['speech_spans'], words, duration) if words else []
                    # Default off: one short contiguous utterance takes the
                    # calibrated single label only once a prod-revision paired
                    # run qualifies it (see batch_pipeline_runtime.md).
                    short = not single and short_speech_single_enabled() and short_single_region(evidence)
                    prepared.append((item, state, words, silence, duration, single, evidence, short))
                except Exception as exc:
                    fail(item, exc, stage)

            # Speaker labels never pool across units: packing shares only model
            # forwards. Missing outcomes take the serial diarize call below.
            flight_diarized = self._flight_diarize(
                [
                    state
                    for _, state, _, _, _, single, _, short in prepared
                    if not state['silence'] and not single and not short
                ]
            )
            for item, state, words, silence, duration, single, evidence, short in prepared:
                # Bound in-flight encrypted writes; settle outside any item handler.
                while len(pending_persist) >= self.io_concurrency:
                    settle_persist(pending_persist.pop(0))
                stage = 'assemble_words'
                try:
                    if state['silence']:
                        diarization = {'turns': [], 'outcome': 'silence'}
                    elif single or short:
                        diarization = {
                            'turns': [{'start': 0, 'end': duration, 'speaker': 'SPEAKER_00'}],
                            'outcome': 'skipped_single',
                        }
                        if short:
                            diarization['single_evidence'] = 'short_speech'
                            record_decision('skipped_short', unit_seconds=duration)
                    else:
                        stage = 'diarize'
                        diarization = flight_diarized.get(item.segment_id)
                        if isinstance(diarization, BaseException):
                            raise diarization
                        if diarization is None:
                            diarization = self._diarize_unit(state['samples'], evidence, words)
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
                    if not item.shadow and cap_dispatch_enabled(item.owner_id, 'batch'):
                        payload['cap_dispatch'] = {
                            'omi_funded_accepted_provider_audio_seconds': state.get('cap_provider_audio_seconds', 0),
                            'admission': 'authorized_compute',
                        }
                    stage = 'persist'
                    if self._io is not None:
                        # Encrypt/upload while the GPU diarizes the next item. The
                        # result keeps its admitted position; failures settle below.
                        results.append(None)
                        pending_persist.append(
                            (
                                len(results) - 1,
                                item,
                                self._io.submit(self.persist, item, payload),
                                state['silence'],
                                silence is not None,
                            )
                        )
                        continue
                    uri = self.persist(item, payload)
                    results.append(WorkResult(item.segment_id, uri, 'silence' if state['silence'] else 'success'))
                    if silence is not None:
                        silence_records.append(item.segment_id)
                except Exception as exc:
                    fail(item, exc, stage)
            while pending_persist:
                settle_persist(pending_persist.pop(0))
        finally:
            if prefetch is not None:
                prefetch.close()
            # A fatal error abandons the flight; never leave writes running past it.
            wait_futures([entry[2] for entry in pending_persist])
            pending_persist.clear()
        results[:] = [result for result in results if result is not None]
        shadow_ids = {item.segment_id for item in items if item.shadow}
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
            if segment_id in shadow_ids:
                continue
            try:
                record_fallback(
                    component='stt_selection',
                    from_mode='batch',
                    to_mode='batch',
                    reason='other',
                    outcome=(
                        'recovered'
                        if owned
                        else (
                            'degraded'
                            if recovery_outcome in {'skipped_oversize', 'skipped_long_speech'}
                            else 'exhausted'
                        )
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
            if segment_id in shadow_ids:
                continue
            try:
                record_fallback(
                    component='stt_selection', from_mode='batch', to_mode='none', reason='other', outcome='recovered'
                )
                logger.info('event=batch_worker_silence_disposition segment_id=%s outcome=silence', segment_id)
            except Exception:
                pass  # Observability cannot invalidate a persisted result.
        for error_class, failure_stage, segment_id, reason, samples, spans, clips, asr_words, owned in failure_records:
            try:
                if segment_id in shadow_ids:
                    logger.info('event=batch_shadow_worker_failure stage=%s reason=%s', failure_stage, reason)
                    continue
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

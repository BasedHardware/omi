"""GPU-independent batch protocol. No provider imports or import-time IO."""

from dataclasses import dataclass, field
import hashlib
import math
from typing import Protocol, Sequence


from config.batch_pipeline import Priority
from config.batch_language_recovery import language_guarded, below_silence_threshold
from utils.batch_pipeline.capacity import PoolCapacity as PoolCapacity
from utils.batch_pipeline.errors import validate_worker_failure
from utils.observability.reasons import WorkerValidationReason, WorkOutcome, reason_values

MAX_PROJECTION_PARTS = 128


def projection_speech_spans(payload: dict, duration: float) -> list[dict[str, float]]:
    """Encrypted result contract: original sample-rounded, unpadded VAD union.

    No transcript-derived estimate may substitute for this production evidence.
    ``worker_vad_word_spans`` only positions a bound worker VAD measure at word
    clocks; its total is that acoustic measure, never the ASR duration.
    Parts/receipts stay embedded in the original result document for erasure.
    """
    raw = payload.get('speech_spans')
    if not isinstance(raw, list) or not raw:
        raise ValueError('original VAD speech_spans required')
    spans = []
    previous_end = -1.0
    for span in raw:
        if not isinstance(span, dict):
            raise ValueError('invalid VAD span')
        start, end = span.get('start'), span.get('end')
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not isinstance(end, (int, float))
            or isinstance(end, bool)
        ):
            raise ValueError('numeric VAD span required')
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError('finite VAD span required')
        if not 0 <= start < end <= duration or start < previous_end:
            raise ValueError('ordered nonoverlapping VAD spans required')
        spans.append({'start': float(start), 'end': float(end)})
        previous_end = end
    speech = payload.get('speech_seconds')
    if not isinstance(speech, (int, float)) or isinstance(speech, bool) or not math.isfinite(speech):
        raise ValueError('validated speech_seconds required')
    if abs(sum(span['end'] - span['start'] for span in spans) - speech) > 1 / 16000 + 1e-9:
        raise ValueError('VAD union disagrees with speech accounting')
    return spans


@dataclass(frozen=True)
class WorkItem:
    segment_id: str
    owner_id: str
    capture_at: float
    audio_uri: str
    duration_seconds: float
    priority: Priority
    unit_kind: str = 'conversation'
    conversation_id: str | None = None
    privacy_generation: int | None = None
    requires_compute_admission: bool = False
    shadow: bool = False

    def __post_init__(self):
        if not self.segment_id or len(self.segment_id) > 128 or '/' in self.segment_id:
            raise ValueError('segment_id must be a bounded opaque document ID')
        if not self.owner_id or '/' in self.owner_id or len(self.owner_id.encode()) > 256:
            raise ValueError('owner_id must be bounded')
        if not self.audio_uri or len(self.audio_uri.encode()) > 2048:
            raise ValueError('audio_uri must be a bounded durable reference')
        if not math.isfinite(self.capture_at) or self.capture_at < 0:
            raise ValueError('capture_at must be a UTC epoch timestamp')
        if not math.isfinite(self.duration_seconds) or not 0 < self.duration_seconds <= 7200:
            raise ValueError('audio duration must be in (0, 7200]')
        if self.conversation_id is not None and (
            not self.conversation_id or len(self.conversation_id) > 128 or '/' in self.conversation_id
        ):
            raise ValueError('conversation_id must be a bounded opaque ID')
        if self.privacy_generation is not None and (
            type(self.privacy_generation) is not int or self.privacy_generation < 0
        ):
            raise ValueError('privacy_generation must be a nonnegative integer')
        if type(self.requires_compute_admission) is not bool:
            raise ValueError('requires_compute_admission must be boolean')
        if type(self.shadow) is not bool:
            raise ValueError('shadow must be boolean')
        Priority(self.priority)
        if self.unit_kind not in {'conversation', 'capture_span'}:
            raise ValueError('unit_kind must be conversation or capture_span')


@dataclass(frozen=True)
class LeasedWork:
    item: WorkItem
    token: str
    attempt: int
    lease_until: float


WORK_OUTCOMES = reason_values(WorkOutcome)
EMPTY_WORKER_REASONS = frozenset({WorkerValidationReason.EMPTY_ASR.value, WorkerValidationReason.NO_OWNED_WORDS.value})


def validate_measured_vad(seconds, duration=None):
    """None is unavailable evidence, never a measured zero."""
    if seconds is not None and (
        type(seconds) not in {int, float}
        or not math.isfinite(seconds)
        or seconds < 0
        # Decode/strict audio inspection accept up to 0.1s of metadata rounding.
        # A bound worker receipt additionally caps speech at captured_samples.
        or seconds > min(7200, 7200 if duration is None else duration + 0.1) + 1 / 16000
    ):
        raise ValueError('invalid measured VAD speech seconds')
    return seconds


def held_vad_census(job, seconds=None):
    """Held speech is cumulative evidence: a later lower estimate cannot erase it."""
    duration = job['duration_seconds']
    prior = validate_measured_vad(job.get('measured_held_vad_speech_seconds'), duration)
    measured = validate_measured_vad(seconds, duration)
    known = [value for value in (prior, measured) if value is not None]
    return max(known) if known else None


def held_silence_allowed(job, seconds=None, *, independent=False):
    """Every route respects prior speech; guarded subframes need independent proof."""
    census = held_vad_census(job, seconds)
    if census is None:
        return False
    if independent:
        return below_silence_threshold(census)
    return not language_guarded(job) and census == 0


def held_result_allowed(job, outcome, seconds=None, *, independent=False):
    if outcome == 'silence':
        return held_silence_allowed(job, seconds, independent=independent)
    return outcome != 'no_recoverable_speech' or not language_guarded(job)


def vad_receipt(audio_uri, captured_samples, speech_seconds):
    return {
        'version': 1,
        'state': 'measured',
        'speech_samples': round(speech_seconds * 16000),
        'captured_samples': captured_samples,
        'sample_rate_hz': 16000,
        'input_uri_sha256': hashlib.sha256(audio_uri.encode()).hexdigest(),
    }


def bound_vad_receipt(job, receipt):
    """A measured receipt bound to this job's immutable audio input."""
    expected_keys = {'version', 'state', 'speech_samples', 'captured_samples', 'sample_rate_hz', 'input_uri_sha256'}
    return (
        isinstance(receipt, dict)
        and set(receipt) == expected_keys
        and type(receipt['version']) is int
        and receipt['version'] == 1
        and receipt['state'] == 'measured'
        and type(receipt['sample_rate_hz']) is int
        and receipt['sample_rate_hz'] == 16000
        and type(receipt['speech_samples']) is int
        and type(receipt['captured_samples']) is int
        and receipt['captured_samples'] > 0
        and 0 <= receipt['speech_samples'] <= receipt['captured_samples'] <= 7200 * 16000
        and abs(receipt['captured_samples'] / 16000 - job['duration_seconds']) <= 0.1
        and receipt['input_uri_sha256'] == hashlib.sha256(job['audio_uri'].encode()).hexdigest()
    )


def worker_vad_speech(job):
    """Independent GPU VAD speech (seconds) of at least one full frame, else None."""
    receipt = job.get('worker_vad_receipt')
    if not bound_vad_receipt(job, receipt):
        return None
    seconds = receipt['speech_samples'] / 16000
    return None if below_silence_threshold(seconds) else seconds


def worker_vad_word_spans(words, duration, seconds):
    """Place the worker's acoustic speech measure at validated word clocks.

    Only for strict CPU VAD with no spans under a bound worker VAD receipt. Word
    clocks license placement only: the spans always total the acoustic measure
    (capped at the captured audio), never the ASR word duration, so settlement,
    usage and ramp accounting stay acoustic. Point words carry no voice evidence.
    """
    rate = 16000
    end_sample = math.floor(duration * rate)
    regions = []
    for word in words:
        start, end = (min(end_sample, max(0, round(value * rate))) for value in word['timestamp'])
        if end <= start:
            continue
        if regions and start <= regions[-1][1]:
            regions[-1][1] = max(regions[-1][1], end)
        else:
            regions.append([start, end])
    target = min(round(seconds * rate), end_sample)
    if not regions or target <= 0:
        return []
    placed, remaining = [], target
    for start, end in regions:  # The acoustic measure fills word clocks in order.
        take = min(end - start, remaining)
        if take > 0:
            placed.append([start, start + take])
            remaining -= take
    for index, span in enumerate(placed):  # Then grows forward into following silence.
        limit = placed[index + 1][0] if index + 1 < len(placed) else end_sample
        grow = min(limit - span[1], remaining)
        span[1] += grow
        remaining -= grow
    for index in range(len(placed) - 1, -1, -1):  # Then backward; target <= audio, so it fits.
        limit = placed[index - 1][1] if index else 0
        grow = min(placed[index][0] - limit, remaining)
        placed[index][0] -= grow
        remaining -= grow
    merged = []
    for start, end in placed:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [{'start': start / rate, 'end': end / rate} for start, end in merged]


def attach_held_vad(job, seconds=None, receipt=None, *, receipt_field='worker_vad_receipt'):
    """Validate immutable input binding before a fenced job mutation."""
    measured = validate_measured_vad(seconds, job['duration_seconds'])
    if receipt is not None:
        if (
            not bound_vad_receipt(job, receipt)
            or measured is None
            or abs(receipt['speech_samples'] / 16000 - measured) > 1 / 16000
        ):
            raise ValueError('invalid bound VAD receipt')
        job[receipt_field] = dict(receipt)
    job['measured_held_vad_speech_seconds'] = held_vad_census(job, measured)


@dataclass(frozen=True)
class WorkResult:
    segment_id: str
    result_uri: str
    outcome: str = 'success'

    def __post_init__(self):
        if not self.segment_id or len(self.segment_id) > 128 or '/' in self.segment_id:
            raise ValueError('segment_id must be a bounded opaque document ID')
        if self.outcome not in WORK_OUTCOMES:
            raise ValueError('unsupported batch result outcome')
        if not self.result_uri or len(self.result_uri.encode()) > 2048:
            raise ValueError('result_uri must be a bounded durable encrypted reference')


@dataclass(frozen=True)
class HeldWork:
    segment_id: str
    retry_after: int = 60
    # Bounded machine reason from the dispatch-time admission decision; empty
    # means no policy decision was recorded (unknown holds stay unclassified).
    reason: str = ''


@dataclass(frozen=True)
class FailedWork:
    """Ordinary retryable worker failure, carrying available VAD evidence."""

    segment_id: str
    measured_held_vad_speech_seconds: float | None = None
    worker_vad_receipt: dict | None = None

    def __post_init__(self):
        validate_measured_vad(self.measured_held_vad_speech_seconds)


@dataclass(frozen=True)
class RecoveryWork:
    """Non-success handoff after speech VAD and an exhausted or skipped padded ASR retry."""

    segment_id: str
    padded_retry_empty: bool = False
    padded_retry: str | None = None
    reason: str = 'empty_asr'
    measured_held_vad_speech_seconds: float | None = field(default=None, compare=False)
    worker_vad_receipt: dict | None = field(default=None, compare=False)

    def __post_init__(self):
        validate_measured_vad(self.measured_held_vad_speech_seconds)
        if self.reason not in EMPTY_WORKER_REASONS:
            raise ValueError('closed empty worker reason required')
        if self.padded_retry is None and self.padded_retry_empty:
            object.__setattr__(self, 'padded_retry', 'empty')
        elif self.padded_retry == 'empty' and not self.padded_retry_empty:
            object.__setattr__(self, 'padded_retry_empty', True)
        if self.padded_retry not in {None, 'empty', 'skipped_oversize', 'skipped_long_speech'}:
            raise ValueError('unsupported padded retry evidence')
        if self.padded_retry_empty and self.padded_retry != 'empty':
            raise ValueError('conflicting padded retry evidence')


@dataclass(frozen=True)
class ValidationFailureWork:
    """Terminal for this GPU chain, retained for independent fenced recovery."""

    segment_id: str
    stage: str
    reason: str
    measured_held_vad_speech_seconds: float | None = field(default=None, compare=False)
    worker_vad_receipt: dict | None = field(default=None, compare=False)

    def __post_init__(self):
        validate_measured_vad(self.measured_held_vad_speech_seconds)
        validate_worker_failure({'stage': self.stage, 'reason': self.reason})


class BatchWorker(Protocol):
    def process_batch(
        self, items: Sequence[WorkItem], **kwargs
    ) -> Sequence[WorkResult | HeldWork | FailedWork | RecoveryWork | ValidationFailureWork]: ...


@dataclass(frozen=True)
class ProjectionBinding:
    """Immutable intake metadata; never inferred from a GPU result body.

    Stored as ``jobs[segment_id].projection_binding``. Every sibling names the
    same bounded complete ``segment_ids`` set. Result-log entries additionally
    carry ``previous_segment_id`` (null at the start of an owner log), so
    projection preserves the committed log order under concurrent pumps. Log
    order is capture order except where the bounded merge head wait or a late
    capture appends an earlier capture at the tail (``late_capture``).
    """

    owner_id: str
    job_id: str
    content_id: str
    segment_ids: tuple[str, ...]
    source: str = 'omi'
    client_device_id: str | None = None
    client_platform: str | None = None
    is_locked: bool = False
    private_cloud_sync_enabled: bool = False
    data_protection_level: str = 'enhanced'
    target_conversation_id: str | None = None
    run_token: str | None = None
    run_epoch: int | None = None
    privacy_generation: int = 0
    language: str | None = None
    record_origin: bool = False
    native_record: bool = False

    def __post_init__(self):
        # Firestore caps transaction writes at 500; completion reads all siblings.
        if not self.owner_id or not self.job_id or not self.content_id:
            raise ValueError('projection requires owner, job and content identities')
        if not 1 <= len(self.segment_ids) <= 128 or len(set(self.segment_ids)) != len(self.segment_ids):
            raise ValueError('projection requires 1..128 unique sibling segments')
        for value in (self.owner_id, self.job_id, self.content_id, *self.segment_ids):
            if '/' in value or not value or len(value.encode()) > 256:
                raise ValueError('projection identities must be bounded document IDs')
        if self.data_protection_level not in {'standard', 'enhanced'}:
            raise ValueError('unsupported projection protection level')
        if (self.run_token is None) != (self.run_epoch is None):
            raise ValueError('projection run token and epoch must be paired')
        if self.privacy_generation < 0:
            raise ValueError('invalid privacy generation')


# A runtime and HTTP transports share these timings and dataclass shapes.
HEARTBEAT_SECONDS = 20.0


class WorkerQueue(Protocol):
    def pull(self, now: float, limit: int = 1, *, capacity: PoolCapacity | None = None) -> list[LeasedWork]: ...
    def heartbeat(self, segment_id: str, token: str, now: float) -> bool: ...
    def complete(self, result: WorkResult, token: str, now: float) -> bool: ...
    def fail(self, segment_id: str, token: str, now: float) -> bool: ...
    def recover(self, now: float, limit: int = 100) -> int: ...


# Standard RIFF ancillary chunk, encrypted/authenticated with the audio body.
INTAKE_CONTEXT_CHUNK = b'OMIM'
INTAKE_CONTEXT_VERSION = 1
INTAKE_CONTEXT_LIMIT = 65536

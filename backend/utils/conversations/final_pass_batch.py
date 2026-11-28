"""Batch final pass on each unit's staged PCM and admitted capture clock.

After successful revalidation, retained private recurring profiles may be published.
Only batch-backed positive-duration segments are candidates for relabeling.
"""

import hashlib
import io
import math
import logging
import os
import threading
import time
import wave
from collections import Counter as Counts
from collections.abc import Iterator
from dataclasses import dataclass
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Required, TypedDict
from prometheus_client import Counter
from datetime import datetime, timezone

from config.batch_conversation_speakers import (
    append_conflicting_units_enabled,
    keep_resolved_on_partial_enabled,
    split_mixed_segments_enabled,
    v3_sources_enabled,
    BATCH_CONVERSATION_SCOPE,
    batch_unit_scope,
    final_pass_enabled_for,
    recurring_enabled_for,
)
from database.batch_final_pass import load_reference, ReferenceUnavailable, source_recording_fence
from database import recurring_voices
from utils.observability.recurring_voices import identity_speech
from utils.speakers.recurring_voices import near_misses
from utils.product_telemetry import emit_product_event
from database.batch_pipeline_store import FirestoreStore
from database.redis_db import create_bounded_redis_client
from models.conversation import ConversationSpeakers
from utils.batch_pipeline.contracts import projection_speech_spans
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
from utils.batch_pipeline.projection_parts import split_result, bounded_projection_words
from utils.batch_pipeline.projection_segments import projection_segments
from utils.conversations.final_pass_assignment import assign_words
from utils.conversations.owner_attribution import FINAL_CENTROID_MATCH_SOURCE
from utils.conversations.final_pass_errors import error_details
from utils.conversations import final_pass_split as splitting
from utils.conversations.final_pass_dependencies import transient_cause
from utils.conversations.final_pass_pyannote import run_final_pass, OUTCOMES, OWNER_DELTA
from utils.manual_speaker_assignments import manual_owner_reserved
from utils.observability.fallback import record_fallback
from utils.observability.reasons import BatchFinalPassOutcome, ReasonFamily, reason_label
from utils.stt.conversation_speakers import Identity, significant_capture_speaker_ids
from utils.stt.diarization import HttpDiarizer
from utils.sync.stage import current_stage

logger = logging.getLogger(__name__)

_SLOTS = threading.BoundedSemaphore(1)
# Two hours at a conservative 15 seconds/unit: 20x the producer's 300-second
# target fragmentation. This is an admission limit, not a minimum unit duration.
MAX_AUDIO_SECONDS = 7200
MAX_UNITS = MAX_AUDIO_SECONDS // 15
_RECORD_TERMINAL = ContextVar('batch_final_pass_terminal', default=True)
_IDENTITY_ONLY = ContextVar('batch_final_pass_identity_only', default=False)
UNIT_SKIPS = Counter(
    'omi_transcription_final_pass_unit_skips_total', 'Units omitted by whole-pass shared-unit abstention', ['reason']
)


@contextmanager
def terminal_metrics(enabled):
    token = _RECORD_TERMINAL.set(enabled)
    try:
        yield
    finally:
        _RECORD_TERMINAL.reset(token)


@contextmanager
def identity_only_attempt():
    # Recurring learning stamps the conversation in its own transaction. Keep
    # inference read-only until the retry's identity CAS; normal passes still learn.
    token = _IDENTITY_ONLY.set(True)
    try:
        with terminal_metrics(False):
            yield
    finally:
        _IDENTITY_ONLY.reset(token)


def count_terminal(outcome):
    if _RECORD_TERMINAL.get():
        OUTCOMES.labels(
            lane='batch', outcome=reason_label(ReasonFamily.BATCH_FINAL_PASS, outcome, BatchFinalPassOutcome)
        ).inc()


_RESERVE = """
for i = 1, 2 do
  local spent = tonumber(redis.call('hget', KEYS[i], 'audio_ms') or '0')
  if spent + tonumber(ARGV[1]) > tonumber(ARGV[i+1]) then return 0 end
end
local calls = tonumber(redis.call('hget', KEYS[2], 'calls') or '0')
if calls >= tonumber(ARGV[4]) then return 0 end
for i = 1, 2 do
  redis.call('hincrby', KEYS[i], 'audio_ms', ARGV[1])
  redis.call('expire', KEYS[i], 172800)
end
redis.call('hincrby', KEYS[2], 'calls', 1)
return 1
"""


def _reserve_budget(seconds):
    # Attempts, including retries, are charged before GPU work.
    try:
        limits = [
            float(os.getenv(key, default))
            for key, default in (
                ('BATCH_FINAL_PASS_DAILY_AUDIO_HOURS', '1200'),
                ('BATCH_FINAL_PASS_HOURLY_AUDIO_HOURS', '50'),
            )
        ]
        calls = int(os.getenv('BATCH_FINAL_PASS_HOURLY_REQUESTS', '1000'))
        if any(not math.isfinite(n) or n <= 0 for n in limits) or calls <= 0:
            return False
        now = datetime.now(timezone.utc)
        with create_bounded_redis_client(0.5) as client:
            return (
                client.eval(
                    _RESERVE,
                    2,
                    'batch-final-pass:day:' + now.strftime('%Y%m%d'),
                    'batch-final-pass:hour:' + now.strftime('%Y%m%d%H'),
                    max(1, math.ceil(seconds * 1000)),
                    *(math.floor(n * 3600000) for n in limits),
                    calls,
                )
                == 1
            )
    except Exception:
        return False


class FinalPassResult(TypedDict, total=False):
    outcome: Required[str]
    reason: str
    exception_type: str
    location: str
    failing_unit: str | None
    coverage: dict[str, int]
    coverage_reasons: dict[str, int]
    changed_segments: int
    speaker_count: int
    covered_segments: int
    partial_resolution: str
    split_segments: int
    split_refusals: dict[str, int]


def record_final_pass_failure(outcome: str, **details) -> FinalPassResult:
    if details.get('reason') == 'diarizer_unconfigured':
        from utils.observability.owner_recognition_diagnostics import final_pass_availability

        final_pass_availability('dependency_unavailable')
    count_terminal(outcome)
    logger.info(
        'event=batch_final_pass outcome=%s exception_type=%s reason=%s location=%s',
        outcome,
        details.get('exception_type', ''),
        details.get('reason', ''),
        details.get('location', ''),
    )
    record_fallback(
        component='stt_selection',
        from_mode='batch_final_pass',
        to_mode='legacy_speaker_matching',
        reason=(
            'recovery_budget'
            if outcome in {'failed_read_budget', 'skipped_budget'}
            else 'unavailable' if outcome == 'failed_incomplete_coverage' else 'other'
        ),
        outcome='degraded',
    )

    return FinalPassResult(outcome=outcome, **details)


class IncompleteCoverage(ValueError):
    pass


@dataclass
class UnitFailureContext:
    # Keep diagnostic ownership separate from third-party exception objects.
    unit: str | None = None


@dataclass
class UnitStream:
    origin: float
    capacity: int
    units: Iterator[tuple]
    read_budget: ArtifactReadBudget


APPEND_GAP_BYTES = 32000  # one second of silence before a unit placed after the timeline


def _assemble(stream):
    """One PCM buffer for the diarizer: each unit at its capture clock, words shifted with it.

    A unit whose capture clock overlaps audio already placed with different samples (measured 2026-11-26 on
    owner v3 conversations: a 131 s unit inside a 298 s unit of the same recording, correlation 0 at every lag
    within 0.5 s) cannot sit at that clock. Labels do not need the conversation's timeline: words are
    assigned to turns on the unit's own audio and the result maps back by segment id. So that unit is
    appended after the timeline (one second of silence first) instead of refusing the whole conversation.
    Identical overlaps still share their samples.
    """
    stream.read_budget.timeout(60)
    # Metadata is small and sorted before decoding. Only one decoded unit lives
    # alongside this buffer; it grows only for appended units.
    pcm = bytearray(stream.capacity)
    used, native, words, checks, appended = 0, 0, [], [], 0
    # Appended units go after the whole native timeline (its capacity), so a later unit at its own clock never
    # collides with one placed there.
    append_at = stream.capacity
    for item, audio, local_words, validate in stream.units:
        stream.read_budget.timeout(60)
        position = round((item.capture_at - stream.origin) * 16000) * 2
        overlap = max(0, min(native - position, len(audio)))
        if overlap:
            with memoryview(pcm) as placed, memoryview(audio) as source:
                same = placed[position : position + overlap] == source[:overlap]
            if not same:
                if not append_conflicting_units_enabled():
                    raise IncompleteCoverage('conflicting capture clocks')
                position, overlap = max(append_at, used) + APPEND_GAP_BYTES, 0
                appended += 1
        if position < append_at:
            native = max(native, position + len(audio))
        end = position + len(audio)
        if end > MAX_AUDIO_SECONDS * 32000:
            raise OverflowError('audio timeline too long')
        if end > len(pcm):
            pcm.extend(bytes(end - len(pcm)))
        with memoryview(audio) as source:
            pcm[position + overlap : end] = source[overlap:]
        used = max(used, end)
        for word in local_words:
            word['timestamp'][0] += position / 32000
            word['timestamp'][1] += position / 32000
        words.extend(local_words)
        checks.append(validate)
        del audio, local_words
    if appended:
        logger.info('event=batch_final_pass unit_placement=appended_after_timeline units=%d', appended)
    stream.read_budget.timeout(60)
    return memoryview(pcm)[:used].toreadonly(), words, checks


def receipt_sources(conversation) -> tuple[str, ...]:
    """Recordings a conversations-v3 row was built from: their projection receipts are this row's (empty when
    ``BATCH_FINAL_PASS_V3_SOURCES_ENABLED`` is false)."""
    if not v3_sources_enabled():
        return ()
    return tuple(sorted({str(rid) for rid in (getattr(conversation, 'v3_recording_ids', None) or []) if rid}))


def _epoch(value) -> float:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
    if isinstance(value, (int, float)):
        return float(value)
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()


def _subtract(start: float, end: float, holes) -> list[tuple[float, float]]:
    pieces = [(start, end)]
    for left, right in sorted(holes):
        pieces = [(a, b) for x, y in pieces for a, b in ((x, min(y, left)), (max(x, right), y)) if b > a]
    return pieces


@dataclass(frozen=True)
class SourceScope:
    """A conversations-v3 row's live hold on its source recordings: its claims minus deleted spans (epoch seconds,
    on the stored clock) and a fingerprint of that evidence. Reading it refuses a deleted, locked or unclaiming
    recording; the fingerprint is re-checked after inference so a revoked claim or a new deletion refuses."""

    intervals: tuple[tuple[float, float], ...]
    fingerprint: str


def source_scope(uid, conversation) -> SourceScope | None:
    sources = receipt_sources(conversation)
    if not sources:
        return None
    intervals, evidence = [], []
    for rid in sources:
        recording = source_recording_fence(uid, rid)
        if not recording or recording.get('deleted') or recording.get('is_locked'):
            raise ReferenceUnavailable('skipped_merged')
        claims = [c for c in recording.get('claims') or [] if c.get('conversation_id') == conversation.id]
        if not claims:
            raise ReferenceUnavailable('skipped_merged')
        deleted = [(_epoch(d['start']), _epoch(d['end'])) for d in recording.get('deleted_spans') or []]
        for claim in claims:
            intervals.extend(_subtract(_epoch(claim['start']), _epoch(claim['end']), deleted))
        evidence.append((rid, sorted((_epoch(c['start']), _epoch(c['end'])) for c in claims), sorted(deleted)))
    fingerprint = hashlib.sha256(repr(sorted(evidence)).encode()).hexdigest()
    return SourceScope(tuple(sorted(intervals)), fingerprint)


OWN_SPEECH_PAD_SECONDS = 0.25
OWN_SPEECH_JOIN_SECONDS = 1.0


def own_speech_spans(words) -> list[tuple[float, float]]:
    """Unit-clock stretches around this conversation's own words (``timestamp`` on the unit's audio), joined
    across short pauses and padded. Claim times come from stored segment clocks, which need not match the
    unit's capture clock, so the words, not the claims, say where this conversation's speech is."""
    spans: list[list[float]] = []
    for left, right in sorted((float(w['timestamp'][0]), float(w['timestamp'][1])) for w in words):
        left, right = max(0.0, left - OWN_SPEECH_PAD_SECONDS), right + OWN_SPEECH_PAD_SECONDS
        if spans and left - spans[-1][1] <= OWN_SPEECH_JOIN_SECONDS:
            spans[-1][1] = max(spans[-1][1], right)
        else:
            spans.append([left, right])
    return [(a, b) for a, b in spans]


def masked_pcm(pcm: bytes, spans) -> bytes:
    """``pcm`` with every sample outside ``spans`` (unit seconds) silenced; length and clock unchanged."""
    keep = bytearray(len(pcm))
    for start, end in spans:
        left, right = max(0, round(start * 16000)) * 2, min(len(pcm), round(end * 16000) * 2)
        if right > left:
            keep[left:right] = pcm[left:right]
    return bytes(keep)


def clip_turns(turns, spans) -> list[dict]:
    return [
        {**turn, 'start': max(turn['start'], a), 'end': min(turn['end'], b)}
        for turn in turns
        for a, b in spans
        if min(turn['end'], b) > max(turn['start'], a)
    ]


def read_unit_references(
    store, uid, conversation, units, read_budget, diagnostics, failure_context: UnitFailureContext
):
    references, errors, shared, absent = {}, [], [], []
    for unit in units:
        read_budget.timeout(3)
        try:
            reference = load_reference(
                store, uid, unit, conversation.id, read_budget=read_budget, source_ids=receipt_sources(conversation)
            )
            if reference is None:
                raise IncompleteCoverage('no_job')
            references[unit] = reference
        except Exception as error:
            logger.warning(
                'event=batch_final_pass outcome=unit_unavailable exception_type=%s reason=%s location=%s',
                error_details(error)['exception_type'],
                error_details(error)['reason'],
                error_details(error)['location'],
            )
            if transient_cause(error) is not None or isinstance(error, ArtifactReadLimit):
                failure_context.unit = unit
                raise
            if isinstance(error, ReferenceUnavailable) and error.reason == 'no_job':
                absent.append((unit, error))
                for segment in conversation.transcript_segments:
                    scope = batch_unit_scope(segment)
                    if scope and scope.removeprefix('final:batch:') == unit:
                        diagnostics[segment.id] = 'no_job'
                continue
            errors.append((unit, error))
            if isinstance(error, ReferenceUnavailable) and error.outcome == 'skipped_shared_unit':
                shared.append((unit, error))
    read_budget.timeout(3)
    if shared:
        UNIT_SKIPS.labels(reason='shared_unit').inc(len(shared))
        UNIT_SKIPS.labels(reason='blocked_by_shared_unit').inc(len(units) - len(shared) - len(absent))
        failure_context.unit, error = shared[0]
        raise error
    if errors:
        failure_context.unit, error = errors[0]
        if isinstance(error, (OverflowError, ArtifactReadLimit, IncompleteCoverage, ReferenceUnavailable)):
            raise error
        failure = IncompleteCoverage('unit unavailable')
        raise failure from error
    if not references and absent:
        failure_context.unit, error = absent[0]
        raise error
    return references


def _units(
    uid, conversation, read_budget, *, deadline, diagnostics=None, failure_context: UnitFailureContext | None = None
):
    diagnostics = {} if diagnostics is None else diagnostics
    failure_context = UnitFailureContext() if failure_context is None else failure_context
    units = sorted(
        {scope.removeprefix('final:batch:') for s in conversation.transcript_segments if (scope := batch_unit_scope(s))}
    )
    # Bound candidate lookups, including unproved/no-job scopes, before any IO.
    if len(units) > MAX_UNITS:
        raise OverflowError('unit limit')
    read_budget.timeout(3)
    store = FirestoreStore(f'batch_pipeline_{current_stage()}')
    artifacts = artifacts_for(store)
    references = read_unit_references(store, uid, conversation, units, read_budget, diagnostics, failure_context)
    if sum(max(1, ref[0].duration_seconds) for ref in references.values()) > MAX_AUDIO_SECONDS:
        raise OverflowError('audio too long')
    if not references:
        raise IncompleteCoverage('no units')
    references = dict(sorted(references.items(), key=lambda pair: pair[1][0].capture_at))
    origin = next(iter(references.values()))[0].capture_at
    timeline_end = max(ref[0].capture_at - origin + ref[0].duration_seconds for ref in references.values())
    # Include decode tolerance and capture-clock sample rounding; actual PCM
    # still must fit the strict two-hour timeline in the assembler.
    if timeline_end > MAX_AUDIO_SECONDS + 0.1 + 2 / 16000 + 1e-9:
        raise OverflowError('audio timeline too long')
    # Decoded durations may exceed rounded metadata by 0.1 seconds + one
    # sample. Reserve that tolerance once; expose only actual decoded frames.
    capacity = min(MAX_AUDIO_SECONDS * 32000, math.ceil((timeline_end + 0.1) * 16000 + 1) * 2)
    return UnitStream(
        origin,
        capacity,
        decode_unit_evidence(
            uid, conversation, references, store, artifacts, read_budget, deadline, diagnostics, failure_context
        ),
        read_budget,
    )


def decode_unit_evidence(
    uid,
    conversation,
    references,
    store,
    artifacts,
    read_budget,
    deadline,
    diagnostics,
    failure_context: UnitFailureContext,
    *,
    identity_turns=None,
):
    total_bytes = 0
    owned = source_scope(uid, conversation)
    for unit, reference in references.items():
        read_budget.timeout(60)
        try:
            item, uri, binding, policy = reference
            payload = artifacts.load_result(item, uri, read_budget=read_budget)
            with wave.open(io.BytesIO(artifacts.fetch_audio(item, read_budget=read_budget))) as wav:
                if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) != (1, 16000, 2):
                    raise ValueError('unit_pcm_format')
                pcm = wav.readframes(wav.getnframes())
            if abs(len(pcm) / 32000 - item.duration_seconds) > 0.1 + 1 / 16000 + 1e-9:
                raise ValueError('unit_duration')
            total_bytes += len(pcm)
            if total_bytes > MAX_AUDIO_SECONDS * 32000:
                raise OverflowError('audio too long')
            words = []
            # Record-origin projection does not split by VAD. Older committed
            # results may predate speech_spans; rebuilding their segments needs
            # the words and diarization, not a fresh admission decision.
            if binding.record_origin and 'speech_spans' in payload:
                projection_speech_spans(payload, item.duration_seconds)
            parts = [(item, payload)] if binding.record_origin else split_result(item, payload)
            reconstructed = {}
            local, mapped, output = None, None, None
            for part, output in parts:
                segments = projection_segments(part, binding, output, batch_segment_id=unit, policy=policy)
                reconstructed.update((s.id, s) for s in segments)
                # Projection uses the decoded result clock, which may differ
                # from admitted metadata by the worker's decode tolerance.
                local = bounded_projection_words(output['words'], float(output['audio_seconds']))
                mapped = assign_words(
                    local, [dict(start=s.start, end=s.end, speaker=s.id) for s in segments if s.end > s.start]
                )
                projection_voices = {s.id: s.speaker for s in segments}
                for word in mapped:
                    if word['speaker'] is not None and word['timestamp'][1] > word['timestamp'][0]:
                        words.append(
                            dict(
                                text=word['word'],
                                segment_id=word['speaker'],
                                projection_speaker=(unit, projection_voices[word['speaker']]),
                                timestamp=[t + (part.capture_at - item.capture_at) for t in word['timestamp']],
                            )
                        )
            # Segment indexes can shift across projection versions (point-word
            # splitting and grouping fixes). ID equality alone is insufficient
            # evidence if it now names different text. Never use stored offsets
            # to repair this: merge/split operations rebase those clocks.
            stored = {
                s.id: s
                for s in conversation.transcript_segments
                if (scope := batch_unit_scope(s)) and scope.removeprefix('final:batch:') == unit
            }
            # A segment an earlier pass split is a run of stored pieces (the first keeps the projection id): its
            # words move to the pieces by token position, and the pieces must spell the projection text exactly.
            pieces_of = {}
            for sid, source in reconstructed.items():
                chain = splitting.expand_split(sid, stored)
                if len(chain) < 2:
                    continue
                pieces_of.update((piece.id, sid) for piece in chain)
                mine = [word for word in words if word['segment_id'] == sid]
                owners = (
                    splitting.assign_words_to_pieces(mine, chain)
                    if source.end > source.start and ' '.join(p.text for p in chain).split() == source.text.split()
                    else None
                )
                if owners is None:
                    diagnostics.update((piece.id, 'projection_text_mismatch') for piece in chain)
                    continue
                for word, owner in zip(mine, owners):
                    word['segment_id'] = owner
            placed = {word['segment_id'] for word in words}
            for sid, segment in stored.items():
                if sid in pieces_of:
                    if sid not in diagnostics and sid not in placed:
                        diagnostics[sid] = 'projection_unassigned_words'
                    continue
                source = reconstructed.get(sid)
                reason = (
                    'projection_segment_missing'
                    if source is None
                    else (
                        'projection_text_mismatch'
                        if source.text.split() != segment.text.split()
                        else (
                            'projection_point_words'
                            if source.end <= source.start
                            else 'projection_unassigned_words' if sid not in placed else None
                        )
                    )
                )
                if reason:
                    diagnostics[sid] = reason
            words = [word for word in words if word['segment_id'] not in diagnostics]
            spans: list[tuple[float, float]] = []
            if owned is not None:
                # A source recording's unit also holds sibling conversations' speech and speech the owner
                # deleted: only this conversation's own speech (its own segments' words, on the unit clock)
                # reaches the diarizer and voice evidence.
                words = [word for word in words if word['segment_id'] in stored]
                spans = own_speech_spans(words)
                pcm = masked_pcm(pcm, spans)
            if identity_turns is not None:
                turns = payload['diarization']['turns']
                identity_turns[unit] = clip_turns(turns, spans) if owned is not None else turns

            def validate(unit=unit, reference=reference, owned=owned):
                try:
                    current = source_scope(uid, conversation)
                    return load_reference(
                        store,
                        uid,
                        unit,
                        conversation.id,
                        read_budget=ArtifactReadBudget(deadline, 0, 0),
                        source_ids=receipt_sources(conversation),
                    ) == reference and (current.fingerprint if current else None) == (
                        owned.fingerprint if owned else None
                    )
                except Exception:
                    failure_context.unit = unit
                    raise

            yield item, pcm, words, validate
            # Release the suspended generator's references before fetching the
            # next artifact. The assembler has already retained the word objects.
            del pcm, payload, parts, words, local, mapped, output
        except Exception as error:
            failure_context.unit = unit
            details = error_details(error)
            logger.warning(
                'event=batch_final_pass outcome=unit_unavailable exception_type=%s reason=%s location=%s',
                details['exception_type'],
                details['reason'],
                details['location'],
            )
            if isinstance(error, (OverflowError, ArtifactReadLimit, IncompleteCoverage, ReferenceUnavailable)):
                raise
            failure = IncompleteCoverage('unit unavailable')
            raise failure from error


def _defer(uid, conversation, requeue, outcome: str, **details) -> FinalPassResult:
    try:
        if requeue is None:
            raise RuntimeError('retry_custody_required')
        queued = requeue(uid, conversation.id, conversation.language or 'en')
        if queued is not None and not queued['outcome'].startswith('deferred_'):
            return queued  # A closed obligation cannot reopen or count again.
    except Exception as error:
        record_final_pass_failure('failed_requeue', **error_details(error))
        raise  # Never acknowledge a dependency failure without durable custody.
    record_fallback(
        component='stt_selection',
        from_mode='batch_final_pass',
        to_mode='speaker_final_pass_retry',
        reason='recovery_budget' if outcome == 'deferred_slot_busy' else 'unavailable',
        outcome='degraded',
    )
    logger.info(
        'event=batch_final_pass outcome=%s exception_type=%s reason=%s location=%s',
        outcome,
        details.get('exception_type', ''),
        details.get('reason', 'speaker_final_pass_outbox'),
        details.get('location', ''),
    )
    return FinalPassResult(outcome=outcome, **details)


def run_batch_final_pass(uid, conversation, receipt, *, load_prints, apply, requeue) -> FinalPassResult:
    """One terminal metric per invocation that runs or fails custody, never per segment.

    Non-cohort calls and durable deferrals are outside that contract. A
    deferral records fallback telemetry; its later admitted retry owns the result.
    """
    from utils.observability.owner_recognition_diagnostics import final_pass_availability
    from config.batch_conversation_speakers import has_batch_authority, final_pass_switch_enabled

    if not final_pass_enabled_for(uid, conversation.transcript_segments):
        final_pass_availability(
            'disabled'
            if has_batch_authority(conversation.transcript_segments) and not final_pass_switch_enabled()
            else 'ineligible'
        )
        return {'outcome': 'skipped_ineligible'}
    final_pass_availability('admitted')
    if not _SLOTS.acquire(blocking=False):
        # The processing boundary supplies a dedicated, capped speaker-only
        # obligation. Retry deliveries settle their own existing obligation.
        return _defer(uid, conversation, requeue, 'deferred_slot_busy')
    failure_context = UnitFailureContext()
    try:
        return _run(uid, conversation, receipt, load_prints, apply, failure_context)
    except Exception as error:
        if transient_cause(error) is not None:
            final_pass_availability('dependency_unavailable')
        transient = transient_cause(error)
        if transient is not None:
            return _defer(
                uid,
                conversation,
                requeue,
                'deferred_transient',
                **error_details(transient),
                failing_unit=failure_context.unit,
            )
        outcome = (
            error.outcome
            if isinstance(error, ReferenceUnavailable)
            else (
                'failed_too_long'
                if isinstance(error, OverflowError)
                else (
                    'failed_read_budget'
                    if isinstance(error, ArtifactReadLimit)
                    else 'failed_incomplete_coverage' if isinstance(error, IncompleteCoverage) else 'failed_batch_audio'
                )
            )
        )
        return record_final_pass_failure(
            outcome, **error_details(error.__cause__ or error), failing_unit=failure_context.unit
        )
    finally:
        _SLOTS.release()


def _run(uid, conversation, receipt, load_prints, apply, failure_context: UnitFailureContext) -> FinalPassResult:
    deadline = time.monotonic() + 600
    # Independent byte/time bounds and three artifacts per admitted unit
    # (result, staged audio, retained source). Reference RPCs share the deadline.
    read_budget = ArtifactReadBudget(min(deadline, time.monotonic() + 180), 320 * 1024 * 1024, 3 * MAX_UNITS)
    diagnostics = {}
    stream = _units(
        uid, conversation, read_budget, deadline=deadline, diagnostics=diagnostics, failure_context=failure_context
    )
    pcm, words, checks = _assemble(stream)
    stored = {s.id: s for s in conversation.transcript_segments}
    covered = {s.id for s in conversation.transcript_segments if batch_unit_scope(s) and s.end > s.start}
    words[:] = (w for w in words if w['segment_id'] in covered)
    for word in words:
        segment = stored[word['segment_id']]
        word['speaker'] = (segment.speaker_id_scope, segment.speaker_id)
    missing = covered - {w['segment_id'] for w in words}
    coverage = {'required': len(covered), 'placed': len(covered - missing), 'unplaced': len(missing)}
    coverage_reasons = dict(Counts(diagnostics.get(sid, 'projection_segment_missing') for sid in missing))
    if not words:
        if not covered:
            return record_final_pass_failure(
                'skipped_no_changes', reason='projection_point_words', coverage=coverage, coverage_reasons={}
            )
        reason = next(iter(coverage_reasons), 'projection_unassigned_words')
        return record_final_pass_failure(
            'failed_incomplete_coverage', reason=reason, coverage=coverage, coverage_reasons=coverage_reasons
        )
    updates = {}
    next_id = max((s.speaker_id or 0 for s in conversation.transcript_segments), default=0) + 1
    identities, statuses = {}, {}

    def reserve_attempt(seconds):
        return _reserve_budget(seconds)

    expected = None
    # Units of source recordings: the live-claim bound is checked before inference, not inside the profile
    # publish transaction, so no recurring profile is learned from them.
    if recurring_enabled_for(uid, conversation.transcript_segments) and not receipt_sources(conversation):
        try:
            expected = recurring_voices.checkpoint(uid, conversation.id, receipt=receipt)
        except Exception:
            record_fallback(
                component='stt_selection',
                from_mode='batch_final_pass',
                to_mode='legacy_speaker_matching',
                reason='unavailable',
                outcome='degraded',
            )
    print_options = {'allow_audio_repair': False}
    if expected is not None:
        print_options['require_complete'] = True
    cache = {key: {'embedding': vector} for key, vector in load_prints(uid, **print_options).items()}
    words.sort(key=lambda w: w['timestamp'])
    passed, outcome = run_final_pass(
        pcm,
        words,
        None,
        cache,
        deadline=deadline,
        conversation_id=conversation.id,
        owner_reserved=manual_owner_reserved(receipt),
        lane='batch',
        include_assignments=True,
        diarizer_backend=HttpDiarizer('pyannote', reserve_attempt=reserve_attempt),
        record_outcome=False,
    )
    if passed is None:
        return record_final_pass_failure(
            'skipped_budget' if outcome.get('reason') == 'diarizer_attempt_budget' else 'failed_batch_audio',
            **{key: outcome[key] for key in ('exception_type', 'reason', 'location') if key in outcome},
        )
    if outcome.get('naming_outcome') == 'incompatible_space':
        return record_final_pass_failure('failed_incompatible_space')
    if not all(check() for check in checks) or not final_pass_enabled_for(uid, conversation.transcript_segments):
        return record_final_pass_failure('failed_revoked')
    labels_by_voice = {s.speaker: s for s in passed if s.speaker is not None}
    by_segment = {}
    for word in outcome['assignments']:
        by_segment.setdefault(word['segment_id'], []).append(word)
    original_owner = sum(w['timestamp'][1] - w['timestamp'][0] for w in words if stored[w['segment_id']].is_user)
    final_owner = sum(
        w['timestamp'][1] - w['timestamp'][0]
        for w in outcome['assignments']
        if w['speaker'] is not None and labels_by_voice[w['speaker']].is_user
    )
    OWNER_DELTA.labels(lane='batch').observe(
        abs(final_owner - original_owner) / max(original_owner, final_owner, 0.001)
    )
    voice_ids = {}
    segment_voices = {}
    unassigned = False
    splits, origin, word_piece = {}, {}, {}
    split_refusals = Counts()
    # Never on the identity-only retry: notes may already cite the segment (see final_pass_split).
    can_split = split_mixed_segments_enabled() and not _IDENTITY_ONLY.get()
    split_members = {piece.id for sid in stored for piece in splitting.expand_split(sid, stored)[1:]} | {
        sid for sid in stored if splitting.split_segment_id(sid, 1) in stored
    }

    def assign(segment_id, voice):
        nonlocal next_id
        segment_voices[segment_id] = voice
        if voice not in voice_ids:
            voice_ids[voice] = next_id
            next_id += 1
        label = labels_by_voice[voice]
        new_id = voice_ids[voice]
        updates[segment_id] = new_id
        if label.is_user or label.person_id:
            identities[new_id] = Identity(is_user=label.is_user, person_id=label.person_id)
        statuses[new_id] = label.speaker_identity_status

    for segment_id, segment_words in by_segment.items():
        labels = [word['speaker'] for word in segment_words]
        if None not in labels and len(set(labels)) == 1:
            assign(segment_id, labels[0])
            continue
        runs = splitting.plan_runs(segment_words) if can_split else None
        if runs is None:
            if can_split:
                split_refusals['no_voice' if all(v is None for v in labels) else 'mostly_gap'] += 1
            unassigned = True
            continue
        if len(runs) == 1:  # a gap or a short aside inside one voice's segment: the voice holding the rest
            assign(segment_id, runs[0].voice)
            continue
        reason = (
            'too_many_voices'
            if len(runs) > splitting.MAX_PIECES
            else 'already_split' if segment_id in split_members else splitting.refusal(stored[segment_id], receipt)
        )
        pieces = None if reason else splitting.split_segment(stored[segment_id], segment_words, runs)
        if pieces is None:
            split_refusals[reason or 'text_mismatch'] += 1
            unassigned = True
            continue
        splits[segment_id] = pieces
        for piece, run in zip(pieces, runs):
            origin[piece.id] = segment_id
            assign(piece.id, run.voice)
            for word in segment_words[run.first : run.last + 1]:
                word_piece[id(word)] = piece.id
    # Apply atomically after reference revalidation. Manual segments keep their groups.
    updates = {
        sid: value
        for sid, value in updates.items()
        if (segment := stored.get(origin.get(sid, sid))) is not None and segment.speaker_label_source != 'manual'
    }
    split_details = {'split_segments': len(splits), 'split_refusals': dict(split_refusals)}
    if splits or split_refusals:
        logger.info(
            'event=batch_final_pass_split segments=%d refusals=%s', len(splits), dict(sorted(split_refusals.items()))
        )
    if not updates:
        return record_final_pass_failure(
            'failed_unassigned_words' if unassigned else 'skipped_no_changes', **split_details
        )
    scope = BATCH_CONVERSATION_SCOPE + conversation.id
    complete = len(updates) == len(conversation.transcript_segments) + sum(len(p) - 1 for p in splits.values())

    def applied(plan):
        copy = conversation.model_copy(deep=True)
        if splits:
            copy.transcript_segments = [
                piece.model_copy(deep=True)
                for segment in copy.transcript_segments
                for piece in (splits.get(segment.id) or [segment])
            ]
        apply(
            copy,
            *plan,
            owner_voiceprint_available=bool(cache and 'user' in cache),
            scope=scope,
            match_source=FINAL_CENTROID_MATCH_SOURCE,
        )
        return copy

    candidate, partial_resolution = None, None
    if not complete:
        mapping, partial_resolution = _resolver_voice_mapping(conversation, stored, outcome['assignments'])
        if mapping is not None:
            # One person, one number: updated segments take the resolver's id for the same voice, so they agree
            # with the segments this pass left alone.
            renumber = {voice_ids[voice]: mapping[voice] for voice in voice_ids}
            kept = applied(
                (
                    {sid: mapping[segment_voices[sid]] for sid in updates},
                    {renumber[k]: v for k, v in identities.items()},
                    {renumber[k]: v for k, v in statuses.items()},
                )
            )
            if _consistent_voices(kept):
                candidate, partial_resolution = kept, 'kept'
                updates = {sid: mapping[segment_voices[sid]] for sid in updates}
                voice_ids = {voice: mapping[voice] for voice in voice_ids}
            else:
                partial_resolution = 'inconsistent'
        logger.info('event=batch_final_pass_partial_resolution outcome=%s', partial_resolution)
    if candidate is None:
        candidate = applied((updates, identities, statuses))
    if partial_resolution == 'kept':
        candidate.speaker_resolution = ConversationSpeakers(
            status='resolved',
            version=conversation.speaker_resolution.version,
            participant_speaker_ids=significant_capture_speaker_ids(candidate.transcript_segments),
        )
    else:
        candidate.speaker_resolution = ConversationSpeakers(
            status='resolved' if complete else 'unavailable',
            version=1,
            participant_speaker_ids=(
                significant_capture_speaker_ids(candidate.transcript_segments) if complete else []
            ),
        )
    recurring_labels = {}
    if (
        not missing
        and not unassigned
        and not _IDENTITY_ONLY.get()
        and expected is not None
        and outcome.get('centroids')
    ):
        try:
            eligible = {
                voice: centroid
                for voice, centroid in outcome['centroids'].items()
                if (assigned := [w for w in outcome['assignments'] if w['speaker'] == voice])
                and all(w['segment_id'] in updates for w in assigned)
            }
            recurring_labels = recurring_voices.learn(
                uid,
                conversation,
                eligible,
                {k: v['embedding'] for k, v in cache.items()},
                expected,
                owner_reserved=manual_owner_reserved(receipt),
            )
        except Exception:
            record_fallback(
                component='stt_selection',
                from_mode='batch_final_pass',
                to_mode='legacy_speaker_matching',
                reason='unavailable',
                outcome='degraded',
            )
    # Only a successful transaction may project recurring identity. Manual edits
    # remain authoritative and are excluded from both grouping and learning.
    original_voices = {sid: voice for voice, sid in voice_ids.items()}
    for segment in candidate.transcript_segments:
        if segment.id not in updates:
            continue
        voice = original_voices.get(updates[segment.id])
        label = recurring_labels.get(voice)
        segment.recurring_voice_id = None
        if label is not None:
            pid = label.get('person_id')
            segment.is_user = pid == 'user'
            segment.person_id = pid if pid != 'user' else None
            segment.recurring_voice_id = label.get('recurring_voice_id')
            if segment.recurring_voice_id:
                segment.voice_candidates = near_misses(
                    outcome['centroids'][voice]['embedding'], {k: v['embedding'] for k, v in cache.items()}
                )
            segment.speaker_identity_status = 'user' if segment.is_user else 'not_user' if pid else 'no_match'
    projected = {s.id: s for s in candidate.transcript_segments}
    speech_mix = dict(owner=0.0, person=0.0, recurring=0.0, unnamed=0.0)
    for word in outcome['assignments']:
        segment = projected.get(word_piece.get(id(word), word['segment_id']))
        if segment is not None:
            kind = (
                'owner'
                if segment.is_user
                else 'person' if segment.person_id else 'recurring' if segment.recurring_voice_id else 'unnamed'
            )
            seconds = max(0, word['timestamp'][1] - word['timestamp'][0])
            identity_speech(kind, seconds)
            speech_mix[kind] += seconds
    conversation.transcript_segments = candidate.transcript_segments
    conversation.speaker_resolution = candidate.speaker_resolution
    emit_product_event(
        uid=uid,
        event='Batch Speaker Identity Mix',
        properties={
            **speech_mix,
            'recurring_cohort': 'on' if recurring_enabled_for(uid, conversation.transcript_segments) else 'off',
            'speakers': len(voice_ids),
        },
    )

    if unassigned:
        return record_final_pass_failure(
            'failed_unassigned_words',
            **split_details,
            changed_segments=len(updates),
            speaker_count=len(voice_ids),
            coverage=coverage,
            coverage_reasons=coverage_reasons,
            partial_resolution=partial_resolution,
        )
    if missing:
        return record_final_pass_failure(
            'partial_coverage',
            reason='projection_coverage_partial',
            **split_details,
            coverage=coverage,
            coverage_reasons=coverage_reasons,
            changed_segments=len(updates),
            speaker_count=len(voice_ids),
            partial_resolution=partial_resolution,
        )
    count_terminal('success')
    logger.info('event=batch_final_pass outcome=success')
    result: FinalPassResult = {
        'outcome': 'success',
        'coverage': coverage,
        'coverage_reasons': coverage_reasons,
        'changed_segments': len(updates),
        'speaker_count': len(voice_ids),
        'covered_segments': len(covered),
        'split_segments': len(splits),
        'split_refusals': dict(split_refusals),
    }
    if partial_resolution is not None:
        # Complete coverage with manual or other-lane segments left alone.
        result['partial_resolution'] = partial_resolution
    return result


def _majority(counts: Counts):
    """The key holding more than half of the words, else None."""
    key, top = counts.most_common(1)[0]
    return key if top * 2 > sum(counts.values()) else None


def _resolver_voice_mapping(conversation, stored, assignments) -> tuple[dict | None, str]:
    """Each final-pass voice -> the resolver voice id that holds most of its assigned words, when that is one-to-one.

    Only for a conversation the resolver already resolved: its ids are one voice each across the conversation, and
    a partial pass leaves some of them in place. Manual segments count: the resolver groups them into its voices,
    and only their labels are the person's (they are never updated). Words outside the conversation scope belong to
    no resolver voice. Ambiguous (no clear majority either way), split (two final voices onto one resolver voice)
    and merge (a resolver voice mostly held by a final voice mapped elsewhere) keep today's behaviour.
    """
    if not keep_resolved_on_partial_enabled():
        return None, 'disabled'
    prior = conversation.speaker_resolution
    if prior is None or prior.status != 'resolved':
        return None, 'not_resolved'
    scope = BATCH_CONVERSATION_SCOPE + conversation.id
    by_voice, by_resolver = {}, {}
    for word in assignments:
        voice = word['speaker']
        if voice is None:
            continue
        segment = stored[word['segment_id']]
        resolver = segment.speaker_id if segment.speaker_id_scope == scope else None
        by_voice.setdefault(voice, Counts())[resolver] += 1
        if resolver is not None:
            by_resolver.setdefault(resolver, Counts())[voice] += 1
    mapping = {voice: _majority(counts) for voice, counts in by_voice.items()}
    if not mapping or None in mapping.values():
        return None, 'ambiguous'
    if len(set(mapping.values())) < len(mapping):
        return None, 'split'
    if any(mapping.get(_majority(counts)) != resolver for resolver, counts in by_resolver.items()):
        return None, 'merge'
    return mapping, 'mapped'


def _consistent_voices(conversation) -> bool:
    """Each speaker number denotes one voice: the app numbers voices by ``speaker_id`` alone, so every automatic
    segment holding an id shares its scope and identity. Segments neither pass placed keep the resolver's own
    labels, which it already counted inside its resolved coverage."""
    voices = {}
    for segment in conversation.transcript_segments:
        if segment.speaker_label_source == 'manual':
            continue
        voice = (segment.speaker_id_scope, segment.is_user, segment.person_id)
        if voices.setdefault(segment.speaker_id, voice) != voice:
            return False
    return True

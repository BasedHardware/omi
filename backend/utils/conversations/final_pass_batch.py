"""Batch final pass on each unit's staged PCM and admitted capture clock.

After successful revalidation, retained private recurring profiles may be published.
Only batch-backed positive-duration segments are candidates for relabeling.
"""

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
    BATCH_CONVERSATION_SCOPE,
    batch_unit_scope,
    final_pass_enabled_for,
    recurring_enabled_for,
)
from database.batch_final_pass import load_reference, ReferenceUnavailable
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
from utils.conversations.final_pass_errors import error_details
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


def record_final_pass_failure(outcome: str, **details) -> FinalPassResult:
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


def _assemble(stream):
    stream.read_budget.timeout(60)
    # Metadata is small and sorted before decoding. Only one decoded unit lives
    # alongside this buffer; the returned read-only view never copies it.
    pcm = memoryview(bytearray(stream.capacity))
    used, words, checks = 0, [], []
    for item, audio, local_words, validate in stream.units:
        stream.read_budget.timeout(60)
        position = round((item.capture_at - stream.origin) * 16000) * 2
        end = position + len(audio)
        if end > len(pcm):
            raise OverflowError('audio timeline too long')
        overlap = max(0, min(used - position, len(audio)))
        source = memoryview(audio)
        if overlap and pcm[position : position + overlap] != source[:overlap]:
            raise IncompleteCoverage('conflicting capture clocks')
        pcm[position + overlap : end] = source[overlap:]
        used = max(used, end)
        for word in local_words:
            word['timestamp'][0] += position / 32000
            word['timestamp'][1] += position / 32000
        words.extend(local_words)
        checks.append(validate)
        del source, audio, local_words
    stream.read_budget.timeout(60)
    return pcm[:used].toreadonly(), words, checks


def _references(store, uid, conversation, units, read_budget, diagnostics, failure_context: UnitFailureContext):
    references, errors, shared, absent = {}, [], [], []
    for unit in units:
        read_budget.timeout(3)
        try:
            reference = load_reference(store, uid, unit, conversation.id, read_budget=read_budget)
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
    references = _references(store, uid, conversation, units, read_budget, diagnostics, failure_context)
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
        _decode_units(
            uid, conversation, references, store, artifacts, read_budget, deadline, diagnostics, failure_context
        ),
        read_budget,
    )


def _decode_units(
    uid,
    conversation,
    references,
    store,
    artifacts,
    read_budget,
    deadline,
    diagnostics,
    failure_context: UnitFailureContext,
):
    total_bytes = 0
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
            placed = {word['segment_id'] for word in words}
            for sid, segment in stored.items():
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

            def validate(unit=unit, reference=reference):
                try:
                    return (
                        load_reference(
                            store, uid, unit, conversation.id, read_budget=ArtifactReadBudget(deadline, 0, 0)
                        )
                        == reference
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
    if not final_pass_enabled_for(uid, conversation.transcript_segments):
        return {'outcome': 'skipped_ineligible'}
    if not _SLOTS.acquire(blocking=False):
        # The processing boundary supplies a dedicated, capped speaker-only
        # obligation. Retry deliveries settle their own existing obligation.
        return _defer(uid, conversation, requeue, 'deferred_slot_busy')
    failure_context = UnitFailureContext()
    try:
        return _run(uid, conversation, receipt, load_prints, apply, failure_context)
    except Exception as error:
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
    if recurring_enabled_for(uid, conversation.transcript_segments):
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
        by_segment.setdefault(word['segment_id'], []).append(word['speaker'])
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
    unassigned = False
    for segment_id, labels in by_segment.items():
        if None in labels:
            unassigned = True
            continue
        voices = set(labels)
        if len(voices) != 1:
            unassigned = True
            continue
        voice = voices.pop()
        if voice not in voice_ids:
            voice_ids[voice] = next_id
            next_id += 1
        label = labels_by_voice[voice]
        new_id = voice_ids[voice]
        updates[segment_id] = new_id
        if label.is_user or label.person_id:
            identities[new_id] = Identity(is_user=label.is_user, person_id=label.person_id)
        statuses[new_id] = label.speaker_identity_status
    # Apply atomically after reference revalidation. Manual segments keep their groups.
    updates = {
        sid: value
        for sid, value in updates.items()
        if any(s.id == sid and s.speaker_label_source != 'manual' for s in conversation.transcript_segments)
    }
    if not updates:
        return record_final_pass_failure('failed_unassigned_words' if unassigned else 'skipped_no_changes')
    candidate = conversation.model_copy(deep=True)
    apply(
        candidate,
        updates,
        identities,
        statuses,
        owner_voiceprint_available=bool(cache and 'user' in cache),
        scope=BATCH_CONVERSATION_SCOPE + conversation.id,
    )
    candidate.speaker_resolution = ConversationSpeakers(
        status='resolved' if len(updates) == len(conversation.transcript_segments) else 'unavailable',
        version=1,
        participant_speaker_ids=(
            significant_capture_speaker_ids(candidate.transcript_segments)
            if len(updates) == len(conversation.transcript_segments)
            else []
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
        segment = projected.get(word['segment_id'])
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
            changed_segments=len(updates),
            speaker_count=len(voice_ids),
            coverage=coverage,
            coverage_reasons=coverage_reasons,
        )
    if missing:
        return record_final_pass_failure(
            'partial_coverage',
            reason='projection_coverage_partial',
            coverage=coverage,
            coverage_reasons=coverage_reasons,
            changed_segments=len(updates),
            speaker_count=len(voice_ids),
        )
    count_terminal('success')
    logger.info('event=batch_final_pass outcome=success')
    return {
        'outcome': 'success',
        'coverage': coverage,
        'coverage_reasons': coverage_reasons,
        'changed_segments': len(updates),
        'speaker_count': len(voice_ids),
        'covered_segments': len(covered),
    }

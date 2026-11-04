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
from utils.conversations.final_pass_pyannote import run_final_pass, OUTCOMES, OWNER_DELTA
from utils.manual_speaker_assignments import manual_owner_reserved
from utils.observability.fallback import record_fallback
from utils.observability.reasons import BatchFinalPassOutcome, ReasonFamily, reason_label
from utils.stt.conversation_speakers import Identity, significant_capture_speaker_ids
from utils.stt.diarization import HttpDiarizer
from utils.sync.stage import current_stage

logger = logging.getLogger(__name__)

_SLOTS = threading.BoundedSemaphore(1)
_SLOT_WAIT_SECONDS = 60
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


def _fallback(outcome, **details):
    OUTCOMES.labels(
        lane='batch', outcome=reason_label(ReasonFamily.BATCH_FINAL_PASS, outcome, BatchFinalPassOutcome)
    ).inc()
    logger.info(
        'event=batch_final_pass outcome=%s exception_type=%s reason=%s',
        outcome,
        details.get('exception_type', ''),
        details.get('reason', ''),
    )
    record_fallback(
        component='stt_selection',
        from_mode='batch_final_pass',
        to_mode='legacy_speaker_matching',
        reason=(
            'recovery_budget'
            if outcome in {'failed_read_budget', 'skipped_budget', 'skipped_slot_timeout'}
            else 'unavailable' if outcome == 'failed_incomplete_coverage' else 'other'
        ),
        outcome='degraded',
    )

    return {'outcome': outcome, **details}


class IncompleteCoverage(ValueError):
    pass


def _assemble(units):
    units = sorted(units, key=lambda unit: unit[0].capture_at)
    origin, pcm, words, checks = units[0][0].capture_at, bytearray(), [], []
    for item, audio, local_words, validate in units:
        position = round((item.capture_at - origin) * 16000) * 2
        end = position + len(audio)
        if end > 7200 * 32000:
            raise OverflowError('audio timeline too long')
        # Overlapping staged units must agree; different device captures cannot
        # both claim one conversation timeline. Never replace either silently.
        overlap = max(0, min(len(pcm) - position, len(audio)))
        if overlap and pcm[position : position + overlap] != audio[:overlap]:
            raise IncompleteCoverage('conflicting capture clocks')
        pcm.extend(b'\0' * max(0, position - len(pcm)))
        pcm.extend(audio[overlap:])
        words.extend({**w, 'timestamp': [t + position / 32000 for t in w['timestamp']]} for w in local_words)
        checks.append(validate)
    return bytes(pcm), words, checks


def _units(uid, conversation, read_budget):
    units = sorted(
        {scope.removeprefix('final:batch:') for s in conversation.transcript_segments if (scope := batch_unit_scope(s))}
    )
    if len(units) > 128:
        raise ValueError('unit limit')
    store = FirestoreStore(f'batch_pipeline_{current_stage()}')
    artifacts = artifacts_for(store)
    total_bytes = 0
    for unit in units:
        read_budget.timeout(60)
        try:
            reference = load_reference(store, uid, unit, conversation.id)
            if reference is None:
                raise IncompleteCoverage('unit unavailable')
            item, uri, binding, policy = reference
            payload = artifacts.load_result(item, uri, read_budget=read_budget)
            with wave.open(io.BytesIO(artifacts.fetch_audio(item, read_budget=read_budget))) as wav:
                if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) != (1, 16000, 2):
                    raise ValueError('unit PCM format')
                pcm = wav.readframes(wav.getnframes())
            if abs(len(pcm) / 32000 - item.duration_seconds) > 0.1 + 1 / 16000 + 1e-9:
                raise ValueError('unit duration')
            total_bytes += len(pcm)
            if total_bytes > 7200 * 32000:
                raise OverflowError('audio too long')
            words = []
            # Record-origin projection does not split by VAD. Older committed
            # results may predate speech_spans; rebuilding their segments needs
            # the words and diarization, not a fresh admission decision.
            if binding.record_origin and 'speech_spans' in payload:
                projection_speech_spans(payload, item.duration_seconds)
            parts = [(item, payload)] if binding.record_origin else split_result(item, payload)
            for part, output in parts:
                segments = projection_segments(part, binding, output, batch_segment_id=unit, policy=policy)
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
            yield item, pcm, words, lambda unit=unit, reference=reference: (
                load_reference(store, uid, unit, conversation.id) == reference
            )
        except Exception as error:
            error.failing_unit = unit
            details = error_details(error)
            logger.warning(
                'event=batch_final_pass outcome=unit_unavailable exception_type=%s reason=%s',
                details['exception_type'],
                details['reason'],
            )
            if isinstance(error, (OverflowError, ArtifactReadLimit, IncompleteCoverage, ReferenceUnavailable)):
                raise
            failure = IncompleteCoverage('unit unavailable')
            failure.failing_unit = unit
            raise failure from error


def run_batch_final_pass(uid, conversation, receipt, *, load_prints, apply):
    if not final_pass_enabled_for(uid, conversation.transcript_segments):
        return {'outcome': 'skipped_ineligible'}
    if not _SLOTS.acquire(timeout=_SLOT_WAIT_SECONDS):
        return _fallback('skipped_slot_timeout', reason='slot_wait_timeout')
    try:
        return _run(uid, conversation, receipt, load_prints, apply)
    except Exception as error:
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
        return _fallback(
            outcome, **error_details(error.__cause__ or error), failing_unit=getattr(error, 'failing_unit', None)
        )
    finally:
        _SLOTS.release()


def _run(uid, conversation, receipt, load_prints, apply):
    deadline = time.monotonic() + 600
    # Independent of playback/speaker-reader defaults: up to two hours of PCM
    # plus bounded encrypted results/manifests, 512 objects, 180s for all reads.
    read_budget = ArtifactReadBudget(min(deadline, time.monotonic() + 180), 320 * 1024 * 1024, 512)
    units = list(_units(uid, conversation, read_budget))
    read_budget.timeout(60)
    if not units:
        raise IncompleteCoverage('no units')
    pcm, words, checks = _assemble(units)
    stored = {s.id: s for s in conversation.transcript_segments}
    words = [
        {**w, 'speaker': (stored[w['segment_id']].speaker_id_scope, stored[w['segment_id']].speaker_id)}
        for w in words
        if w['segment_id'] in stored
    ]
    covered = {s.id for s in conversation.transcript_segments if batch_unit_scope(s) and s.end > s.start}
    words = [w for w in words if w['segment_id'] in covered]
    if {w['segment_id'] for w in words} != covered:
        raise IncompleteCoverage('unplaced segments')
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
        return _fallback(
            'skipped_budget' if outcome.get('reason') == 'diarizer_attempt_budget' else 'failed_batch_audio',
            **{key: outcome[key] for key in ('exception_type', 'reason') if key in outcome},
        )
    if outcome.get('naming_outcome') == 'incompatible_space':
        return _fallback('failed_incompatible_space')
    if not all(check() for check in checks) or not final_pass_enabled_for(uid, conversation.transcript_segments):
        return _fallback('failed_revoked')
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
        return _fallback('failed_unassigned_words' if unassigned else 'skipped_no_changes')
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
    if expected is not None and outcome.get('centroids'):
        try:
            eligible = {
                voice: centroid
                for voice, centroid in outcome['centroids'].items()
                if all(w['segment_id'] in updates for w in outcome['assignments'] if w['speaker'] == voice)
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
        return _fallback('failed_unassigned_words', changed_segments=len(updates), speaker_count=len(voice_ids))
    OUTCOMES.labels(lane='batch', outcome='success').inc()
    logger.info('event=batch_final_pass outcome=success')
    return {
        'outcome': 'success',
        'changed_segments': len(updates),
        'speaker_count': len(voice_ids),
        'covered_segments': len(covered),
    }

"""Batch final pass on each unit's staged PCM and admitted capture clock.

No audio, transcript, centroid or enrollment artifact is written by this adapter.
Incomplete conversation coverage leaves every resolver label unchanged.
"""

import io
import math
import logging
import os
import threading
import time
import wave
from datetime import datetime, timezone

from config.batch_conversation_speakers import BATCH_CONVERSATION_SCOPE, final_pass_enabled_for
from database.batch_final_pass import load_reference
from database.batch_pipeline_store import FirestoreStore
from database.redis_db import create_bounded_redis_client
from models.conversation import ConversationSpeakers
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
from utils.batch_pipeline.contracts import projection_speech_spans
from utils.batch_pipeline.projection_parts import split_result, bounded_projection_words
from utils.batch_pipeline.projection_segments import projection_segments
from utils.conversations.final_pass_assignment import assign_words
from utils.conversations.final_pass_pyannote import run_final_pass, OUTCOMES, OWNER_DELTA
from utils.manual_speaker_assignments import manual_owner_reserved
from utils.observability.fallback import record_fallback
from utils.observability.reasons import BatchFinalPassOutcome, ReasonFamily, reason_label
from utils.stt.conversation_speakers import Identity, significant_capture_speaker_ids
from utils.stt.diarization import HttpDiarizer
from utils.sync.stage import current_stage

logger = logging.getLogger(__name__)

_SLOTS = threading.BoundedSemaphore(1)
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


def _fallback(outcome):
    OUTCOMES.labels(
        lane='batch', outcome=reason_label(ReasonFamily.BATCH_FINAL_PASS, outcome, BatchFinalPassOutcome)
    ).inc()
    logger.info('event=batch_final_pass outcome=%s', outcome)
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
    scopes = {
        (s.provider_speaker or {}).get('scope') or s.speaker_id_scope or '' for s in conversation.transcript_segments
    }
    units = sorted(
        s.removeprefix('final:batch:')
        for s in scopes
        if s.startswith('final:batch:') and not s.startswith(BATCH_CONVERSATION_SCOPE)
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
            if abs(len(pcm) / 32000 - item.duration_seconds) > 0.001:
                raise ValueError('unit duration')
            total_bytes += len(pcm)
            if total_bytes > 7200 * 32000:
                raise OverflowError('audio too long')
            words = []
            if binding.record_origin:
                projection_speech_spans(payload, item.duration_seconds)
            parts = [(item, payload)] if binding.record_origin else split_result(item, payload)
            for part, output in parts:
                segments = projection_segments(part, binding, output, batch_segment_id=unit, policy=policy)
                local = bounded_projection_words(output['words'], part.duration_seconds)
                mapped = assign_words(local, [dict(start=s.start, end=s.end, speaker=s.id) for s in segments])
                for word in mapped:
                    if word['speaker'] is not None:
                        words.append(
                            dict(
                                text=word['word'],
                                segment_id=word['speaker'],
                                timestamp=[t + (part.capture_at - item.capture_at) for t in word['timestamp']],
                            )
                        )
            yield item, pcm, words, lambda unit=unit, reference=reference: (
                load_reference(store, uid, unit, conversation.id) == reference
            )
        except (OverflowError, ArtifactReadLimit, IncompleteCoverage):
            raise
        except Exception as error:
            logger.warning('event=batch_final_pass outcome=unit_unavailable exception_type=%s', type(error).__name__)
            raise IncompleteCoverage('unit unavailable') from error


def run_batch_final_pass(uid, conversation, receipt, *, load_prints, apply):
    if not final_pass_enabled_for(uid, conversation.transcript_segments):
        return
    if not _SLOTS.acquire(blocking=False):
        _fallback('skipped_budget')
        return
    try:
        _run(uid, conversation, receipt, load_prints, apply)
    except OverflowError:
        _fallback('failed_too_long')
    except ArtifactReadLimit:
        _fallback('failed_read_budget')
    except IncompleteCoverage:
        _fallback('failed_incomplete_coverage')
    except Exception as error:
        logger.warning('event=batch_final_pass outcome=failed exception_type=%s', type(error).__name__)
        _fallback('failed_batch_audio')
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
    if {w['segment_id'] for w in words} != set(stored):
        raise IncompleteCoverage('unplaced segments')
    updates = {}
    next_id = max((s.speaker_id or 0 for s in conversation.transcript_segments), default=0) + 1
    identities, statuses = {}, {}

    def reserve_attempt(seconds):
        admitted = _reserve_budget(seconds)
        if not admitted:
            _fallback('skipped_budget')
        return admitted

    cache = {key: {'embedding': vector} for key, vector in load_prints(uid, allow_audio_repair=False).items()}
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
    )
    if passed is None:
        return  # Shared runner records its service/timeout fallback.
    if outcome.get('naming_outcome') == 'incompatible_space':
        _fallback('failed_incompatible_space')
        return
    if not all(check() for check in checks) or not final_pass_enabled_for(uid, conversation.transcript_segments):
        _fallback('failed_revoked')
        return
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
    for segment_id, labels in by_segment.items():
        if None in labels:
            _fallback('failed_unassigned_words')
            continue
        voices = set(labels)
        if len(voices) != 1:
            _fallback('failed_unassigned_words')
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
        return
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
    conversation.transcript_segments = candidate.transcript_segments
    conversation.speaker_resolution = candidate.speaker_resolution

"""Sync-on batch final pass. Stable IDs and exact PCM proofs replace stored offsets.

No audio, transcript, centroid or enrollment artifact is written by this adapter.
Unplaceable units retain the resolver's labels, including on partial success.
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
from utils.batch_pipeline.projection_parts import split_result, bounded_projection_words
from utils.batch_pipeline.projection_segments import projection_segments
from utils.conversations.final_pass_assignment import assign_words
from utils.conversations.final_pass_pyannote import run_final_pass, OUTCOMES, OWNER_DELTA
from utils.manual_speaker_assignments import manual_owner_reserved
from utils.observability.fallback import record_fallback
from utils.other.audio_chunks import AudioChunkReadSession, iter_audio_chunk_pcm
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
    OUTCOMES.labels(lane='batch', outcome=outcome).inc()
    record_fallback(
        component='stt_selection',
        from_mode='batch_final_pass',
        to_mode='legacy_speaker_matching',
        reason='other',
        outcome='degraded',
    )


def _store(chunk):
    path = chunk['path']
    return 'sync' if path.endswith(('.opus', '.opus.enc')) else 'raw' if path.startswith('raw-live/') else 'live'


def _assemble(uid, conversation, deadline):
    session = AudioChunkReadSession(uid, conversation.id)
    session.deadline = min(deadline, session.deadline)
    session.max_downloads = 1500
    registered = {round(t, 3) for f in conversation.audio_files for t in f.chunk_timestamps}
    chunks = [c for c in session.chunks if round(c['timestamp'], 3) in registered]
    for store in sorted({_store(c) for c in chunks}):
        origin, pcm, covered = None, bytearray(), []
        for start, data in iter_audio_chunk_pcm(
            uid,
            conversation.id,
            lambda start, _next: round(start, 3) in registered,
            session=session,
            chunk_filter=lambda chunk: _store(chunk) == store,
        ):
            if time.monotonic() >= deadline:
                raise TimeoutError('batch final pass audio deadline')
            if origin is None:
                origin = start
            position = round((start - origin) * 16000) * 2
            trim = max(0, len(pcm) - position)
            data, position = data[trim:], position + trim
            if not data:
                continue
            if position + len(data) > 7200 * 32000:
                raise OverflowError('audio too long')
            pcm.extend(b'\0' * max(0, position - len(pcm)))
            pcm.extend(data)
            covered.append((position, position + len(data)))
        if origin is not None and pcm:
            yield origin, bytes(pcm), covered


def _units(uid, conversation, deadline):
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
        if time.monotonic() >= deadline:
            raise TimeoutError('batch unit deadline')
        try:
            reference = load_reference(store, uid, unit, conversation.id)
            if reference is None:
                _fallback('failed:unit_unavailable')
                continue
            item, uri, binding, policy = reference
            payload = artifacts.load_result(item, uri)
            with wave.open(io.BytesIO(artifacts.fetch_audio(item))) as wav:
                if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) != (1, 16000, 2):
                    raise ValueError('unit PCM format')
                pcm = wav.readframes(wav.getnframes())
            if abs(len(pcm) / 32000 - item.duration_seconds) > 0.001:
                raise ValueError('unit duration')
            total_bytes += len(pcm)
            if total_bytes > 7200 * 32000:
                raise OverflowError('audio too long')
            words = []
            for part, output in split_result(item, payload):
                segments = projection_segments(part, binding, output, batch_segment_id=unit, policy=policy)
                local = bounded_projection_words(output['words'], part.duration_seconds)
                mapped = assign_words(local, [dict(start=s.start, end=s.end, speaker=s.id) for s in segments])
                for word in mapped:
                    if word['speaker'] is not None:
                        words.append(
                            dict(
                                text=word['word'],
                                segment_id=word['speaker'],
                                timestamp=[t + part.capture_at - item.capture_at for t in word['timestamp']],
                            )
                        )
            yield item, pcm, words, lambda unit=unit, reference=reference: (
                load_reference(store, uid, unit, conversation.id) == reference
            )
        except OverflowError:
            raise
        except Exception as error:
            logger.warning('event=batch_final_pass outcome=unit_unavailable exception_type=%s', type(error).__name__)
            _fallback('failed:unit_unavailable')


def run_batch_final_pass(uid, conversation, receipt, *, load_prints, apply):
    if not conversation.private_cloud_sync_enabled or not final_pass_enabled_for(uid, conversation.transcript_segments):
        return
    if not _SLOTS.acquire(blocking=False):
        _fallback('skipped_budget')
        return
    try:
        _run(uid, conversation, receipt, load_prints, apply)
    except OverflowError:
        _fallback('failed:too_long')
    except Exception as error:
        logger.warning('event=batch_final_pass outcome=failed exception_type=%s', type(error).__name__)
        _fallback('failed:batch_audio')
    finally:
        _SLOTS.release()


def _run(uid, conversation, receipt, load_prints, apply):
    deadline = time.monotonic() + 600
    units = list(_units(uid, conversation, deadline))
    if not units:
        _fallback('failed:no_units')
        return
    updates, used_units = {}, set()
    cache = None
    next_id = max((s.speaker_id or 0 for s in conversation.transcript_segments), default=0) + 1
    identities, statuses = {}, {}
    for origin, pcm, covered in _assemble(uid, conversation, deadline):
        words, checks = [], []
        for item, audio, local_words, validate in units:
            if item.segment_id in used_units:
                continue
            position = round((item.capture_at - origin) * 16000) * 2
            end = position + len(audio)
            # Exact decoded PCM equality pins this unit to this store's clock.
            # Require real coverage, so a zero-filled assembly gap cannot prove silence.
            cursor = position
            for left, right in covered:
                if left <= cursor < right:
                    cursor = right
            if position < 0 or cursor < end or pcm[position:end] != audio:
                continue
            words.extend({**w, 'timestamp': [t + position / 32000 for t in w['timestamp']]} for w in local_words)
            checks.append(validate)
            used_units.add(item.segment_id)
        if not words:
            continue
        if not _reserve_budget(len(pcm) / 32000):
            _fallback('skipped_budget')
            return
        if cache is None:
            cache = {key: {'embedding': vector} for key, vector in load_prints(uid, allow_audio_repair=False).items()}
        stored = {s.id: s for s in conversation.transcript_segments}
        words = [
            {**w, 'speaker': (stored[w['segment_id']].speaker_id_scope, stored[w['segment_id']].speaker_id)}
            for w in words
            if w['segment_id'] in stored
        ]
        if not words:
            _fallback('failed:unplaced_unit')
            continue
        words.sort(key=lambda w: w['timestamp'])
        passed, outcome = run_final_pass(
            pcm,
            words,
            None,
            cache,
            deadline=deadline,
            conversation_id=conversation.id,
            owner_reserved=manual_owner_reserved(receipt)
            or any(
                s.is_user and s.id not in {w['segment_id'] for w in words} for s in conversation.transcript_segments
            ),
            lane='batch',
            include_assignments=True,
            diarizer_backend=HttpDiarizer('pyannote'),
        )
        if passed is None:
            return  # Shared runner records its service/timeout fallback.
        if outcome.get('naming_outcome') == 'incompatible_space':
            _fallback('failed:incompatible_space')
            return
        if not all(check() for check in checks) or not final_pass_enabled_for(uid, conversation.transcript_segments):
            _fallback('failed:revoked')
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
                _fallback('failed:unassigned_words')
                continue
            voices = set(labels)
            if len(voices) != 1:
                _fallback('failed:unassigned_words')
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
        break  # One store per conversation; other-store units abstain, avoiding independent owner claims.
    if len(used_units) < len(units):
        _fallback('failed:unplaced_unit')
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

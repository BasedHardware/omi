"""Opt-in, bounded Parakeet final-pass comparison. Never mutates the record.

Admission is deliberately cheap on the finalizer's path. A tracked background
task waits for the pusher's 60-second upload flush, then a dedicated two-worker
pool does storage, transcription and comparison. A restart can lose a shadow
sample; it cannot lose finalization or alter the conversation.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from prometheus_client import Counter, Histogram

from database import conversations as conversations_db
from database._client import db
from database.redis_db import r as redis_client
from models.conversation import Conversation, ConversationSpeakers
from models.transcript_segment import TranscriptSegment
from utils.conversations.factory import deserialize_conversation
from utils.conversations.segment_remap import (
    plan_segment_remap,
    remap_receipt,
    remap_source_ids,
    remap_translations,
)
from utils.conversations.speaker_resolution import apply_speaker_resolution, load_voiceprints_for_resolution
from utils.executors import start_background_task
from utils.other.storage import iter_audio_chunk_pcm
from utils.speaker_tag_prompts.clips import pcm_to_wav, trim_pcm16
from utils.stt.conversation_speakers import resolve_conversation_speakers
from utils.stt.pre_recorded import parakeet_prerecorded_from_bytes, postprocess_words
from utils.stt.speaker_embedding import extract_embedding_from_bytes, speaker_embedding_configured
from utils.sync.pipeline import build_person_embeddings_cache, identify_speakers_for_segments

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='transcription-shadow')
_slots = threading.BoundedSemaphore(2)
_OUTCOMES = {'ok', 'failed', 'timeout', 'partial_audio', 'no_audio', 'skipped_budget'}


class _BudgetExceeded(RuntimeError):
    pass


SHADOW_OUTCOMES = Counter('omi_transcription_shadow_total', 'Bounded final-pass shadow outcomes', ['outcome'])
SHADOW_LATENCY = Histogram('omi_transcription_shadow_latency_seconds', 'Final-pass shadow duration')

_RESERVE_SCRIPT = """
if redis.call('exists', KEYS[2]) == 1 then return 2 end
local spent = tonumber(redis.call('get', KEYS[1]) or '0')
if spent + tonumber(ARGV[1]) > tonumber(ARGV[2]) then return 0 end
redis.call('incrby', KEYS[1], ARGV[1])
redis.call('expire', KEYS[1], 172800)
redis.call('set', KEYS[2], '1', 'EX', 172800)
return 1
"""


def _enabled(uid: str, conversation: Conversation) -> bool:
    if os.getenv('TRANSCRIPTION_SHADOW_KILL_SWITCH', 'false').lower() == 'true':
        return False
    if os.getenv('TRANSCRIPTION_SHADOW_ENABLED', 'false').lower() != 'true':
        return False
    if not conversation.private_cloud_sync_enabled or conversation.discarded or conversation.uses_custom_stt:
        return False
    allowlist = {
        item.strip() for item in os.getenv('TRANSCRIPTION_SHADOW_UID_ALLOWLIST', '').split(',') if item.strip()
    }
    if uid in allowlist:
        return True
    percent = max(0.0, min(100.0, float(os.getenv('TRANSCRIPTION_SHADOW_PERCENT', '0'))))
    bucket = int.from_bytes(hashlib.sha256(uid.encode()).digest()[:4], 'big') / 2**32 * 100
    return bucket < percent


def maybe_start_shadow(uid: str, conversation: Conversation) -> None:
    """Called after lease admission and before canonical processing; never raises."""
    try:
        if not _enabled(uid, conversation):
            return
        if not _slots.acquire(blocking=False):
            SHADOW_OUTCOMES.labels(outcome='skipped_budget').inc()
            return
        try:
            start_background_task(_run_later(uid, conversation.id), name='transcription-shadow')
        except BaseException:
            _slots.release()
            raise
    except Exception as error:
        logger.warning('event=transcription_shadow outcome=admission_failed exception_type=%s', type(error).__name__)


async def _run_later(uid: str, conversation_id: str) -> None:
    try:
        await asyncio.sleep(max(0.0, float(os.getenv('TRANSCRIPTION_SHADOW_UPLOAD_GRACE_SECONDS', '70'))))
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_pool, _run_shadow, uid, conversation_id)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning('event=transcription_shadow outcome=failed exception_type=%s', type(error).__name__)
        SHADOW_OUTCOMES.labels(outcome='failed').inc()
    finally:
        _slots.release()


def _reserve_budget(conversation_id: str, seconds: float) -> str:
    hours = float(os.getenv('TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS', '0'))
    if hours <= 0:
        return 'budget_exhausted'
    requested = max(1, int(seconds * 1000 + 0.999))
    limit = int(hours * 3600 * 1000)
    day = datetime.now(timezone.utc).strftime('%Y%m%d')
    result = redis_client.eval(
        _RESERVE_SCRIPT,
        2,
        f'transcription-shadow:budget:{day}',
        f'transcription-shadow:once:{day}:{conversation_id}',
        requested,
        limit,
    )
    # A duplicate worker never earns a second transcription call or writes to
    # the first worker's result document.
    return {0: 'budget_exhausted', 1: 'reserved', 2: 'duplicate'}[int(result)]


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _word_distance(a: list[str], b: list[str]) -> float | None:
    if not a:
        return 0.0 if not b else None
    if len(a) > 4000 or len(b) > 4000:
        return None
    row = list(range(len(b) + 1))
    for index, word in enumerate(a, 1):
        current = [index]
        for position, other in enumerate(b, 1):
            current.append(min(current[-1] + 1, row[position] + 1, row[position - 1] + (word != other)))
        row = current
    return round(row[-1] / len(a), 4)


def _source_refs(value: Any) -> list[list[str]]:
    refs: list[list[str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'source_segment_ids' and isinstance(child, list):
                refs.append([str(item) for item in child])
            else:
                refs.extend(_source_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_source_refs(child))
    return refs


def _epoch(moment: Any) -> float | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def _make_pass(
    uid: str, conversation: Conversation, *, deadline: float, reserved_seconds: float
) -> tuple[list[TranscriptSegment], dict[str, float]]:
    cache = build_person_embeddings_cache(uid)
    origin: float | None = None
    last_end: float | None = None
    covered = 0.0
    segments: list[TranscriptSegment] = []
    vectors: dict[str, Any] = {}
    chunk_count = 0
    registered = {round(ts, 3) for file in conversation.audio_files for ts in file.chunk_timestamps}
    for chunk_start, pcm in iter_audio_chunk_pcm(
        uid, conversation.id, lambda start, _next: round(start, 3) in registered
    ):
        if time.monotonic() >= deadline:
            raise TimeoutError('shadow deadline')
        if origin is None:
            origin = chunk_start
        assert origin is not None
        audio_origin: float = origin
        # Each blob has its own clock. Remove only duplicate leading samples;
        # playback MP3's dense clock is never used as a transcript clock.
        overlap = max(0.0, (last_end or chunk_start) - chunk_start)
        if overlap:
            pcm = pcm[min(len(pcm), int(overlap * 32000)) :]
            chunk_start += overlap
        if not pcm:
            continue
        if covered + len(pcm) / 32000 > reserved_seconds + 0.01:
            extra = covered + len(pcm) / 32000 - reserved_seconds
            if _reserve_budget(f'{conversation.id}:extra:{chunk_count}', extra) != 'reserved':
                raise _BudgetExceeded('decoded audio exceeds daily budget')
            reserved_seconds += extra
        for offset in range(0, len(pcm), 90 * 32000):
            if time.monotonic() >= deadline:
                raise TimeoutError('shadow deadline')
            part = pcm[offset : offset + 90 * 32000]
            part_start = chunk_start + offset / 32000
            words = parakeet_prerecorded_from_bytes(part, diarize=True, attempts=1, encoding='linear16')
            if isinstance(words, tuple):
                words = words[0]
            slice_segments = postprocess_words(words, 0) if words else []
            first_word = min((float(w['timestamp'][0]) for w in words), default=0.0)
            if slice_segments:
                identify_speakers_for_segments(
                    slice_segments, pcm_to_wav(part), cache, uid, language=conversation.language
                )
            for segment in slice_segments:
                # postprocess_words rebases to the first segment, not the blob.
                segment.start += part_start - audio_origin + first_word
                segment.end += part_start - audio_origin + first_word
                segment.speaker_id_scope = f'sync:shadow:{chunk_count}'
                segments.append(segment)
                if speaker_embedding_configured() and segment.id and segment.end - segment.start >= 1.0:
                    left = max(0.0, segment.start + audio_origin - part_start)
                    right = min(len(part) / 32000, segment.end + audio_origin - part_start, left + 10.0)
                    if right - left >= 1.0:
                        try:
                            clip = trim_pcm16(part, 16000, left, right)
                            vectors[segment.id] = extract_embedding_from_bytes(pcm_to_wav(clip))
                        except Exception:
                            pass  # Identity remains unassigned; compare coverage below.
            chunk_count += 1
        duration = len(pcm) / 32000
        covered += duration
        last_end = chunk_start + duration
    if origin is None or not segments:
        return [], {'coverage': 0.0, 'tail_gap_seconds': 0.0, 'audio_seconds': covered}
    conversation.transcript_segments = segments
    if vectors:
        resolution = resolve_conversation_speakers(
            segments, vectors, manual_speakers={}, voiceprints=load_voiceprints_for_resolution(uid)
        )
        if resolution is not None:
            apply_speaker_resolution(conversation, resolution.speaker_ids, resolution.voice_identities)
            conversation.speaker_resolution = ConversationSpeakers(
                status='resolved' if resolution.coverage >= 0.9 else 'unavailable',
                participant_speaker_ids=resolution.significant_speaker_ids if resolution.coverage >= 0.9 else [],
            )
    finished = _epoch(conversation.finished_at)
    tail = max(0.0, finished - last_end) if finished is not None and last_end is not None else 0.0
    expected = max(covered, (finished - origin) if finished is not None else covered)
    return segments, {
        'coverage': round(min(1.0, covered / expected), 4) if expected > 0 else 0.0,
        'tail_gap_seconds': round(tail, 3),
        'audio_seconds': round(covered, 3),
    }


def _compare(
    conversation: Conversation, passed: list[TranscriptSegment], audio: dict[str, float], receipt: dict
) -> dict:
    old = [s.model_dump() for s in conversation.transcript_segments]
    new = [s.model_dump() for s in passed]
    plan = plan_segment_remap(old, new)
    remap_ok = True
    try:
        remap_receipt(receipt, old, new, plan)
        remap_translations(old, plan)
        for refs in _source_refs(conversation.structured.model_dump()):
            remap_source_ids(refs, plan)
    except ValueError:
        remap_ok = False
    live_words = [word for segment in old for word in _words(str(segment.get('text') or ''))]
    pass_words = [word for segment in new for word in _words(str(segment.get('text') or ''))]
    live_owner = sum(max(0.0, s['end'] - s['start']) for s in old if s.get('is_user'))
    pass_owner = sum(max(0.0, s['end'] - s['start']) for s in new if s.get('is_user'))
    return {
        **audio,
        'word_distance': _word_distance(live_words, pass_words),
        'live_word_count': len(live_words),
        'pass_word_count': len(pass_words),
        'live_owner_seconds': round(live_owner, 3),
        'pass_owner_seconds': round(pass_owner, 3),
        'live_speakers': len({s['speaker_id'] for s in old if s.get('speaker_id') is not None}),
        'pass_speakers': len({s['speaker_id'] for s in new if s.get('speaker_id') is not None}),
        'remap_success_rate': round(plan.success_rate, 4),
        'remap_safe': plan.safe and remap_ok,
        'clock_offset_seconds': plan.offset_seconds,
    }


def _run_shadow(uid: str, conversation_id: str) -> None:
    began = time.monotonic()
    outcome = 'failed'
    result: dict[str, Any] = {}
    record_result = False
    try:
        raw = conversations_db.get_conversation(uid, conversation_id)
        if not raw:
            return
        conversation = deserialize_conversation(raw)
        if not _enabled(uid, conversation):
            return
        record_result = True
        if not conversation.audio_files:
            outcome = 'no_audio'
        else:
            timestamps = [ts for file in conversation.audio_files for ts in file.chunk_timestamps]
            # Legacy Opus byte-size durations can severely undercount decoded
            # PCM. Reserve a full possible tail chunk; any further decoded
            # duration is atomically reserved before the next provider call.
            estimated = max(
                sum(max(0.0, file.duration) for file in conversation.audio_files),
                max(timestamps) - min(timestamps) + 120.0 if timestamps else 0.0,
            )
            reservation = _reserve_budget(conversation_id, estimated)
            if reservation == 'duplicate':
                record_result = False
                return
            if reservation != 'reserved':
                outcome = 'skipped_budget'
            else:
                deadline = began + max(30.0, float(os.getenv('TRANSCRIPTION_SHADOW_TIMEOUT_SECONDS', '600')))
                receipt = conversations_db.get_manual_speaker_receipt(uid, conversation_id)
                live_conversation = conversation.model_copy(deep=True)
                passed, audio = _make_pass(uid, conversation, deadline=deadline, reserved_seconds=estimated)
                if not passed:
                    outcome = 'no_audio'
                    result = audio
                else:
                    result = _compare(live_conversation, passed, audio, receipt)
                    outcome = 'partial_audio' if audio['tail_gap_seconds'] > 5 or audio['coverage'] < 0.95 else 'ok'
    except TimeoutError:
        outcome = 'timeout'
    except _BudgetExceeded:
        outcome = 'skipped_budget'
    except Exception as error:
        logger.warning('event=transcription_shadow outcome=failed exception_type=%s', type(error).__name__)
        outcome = 'failed'
    finally:
        if record_result:
            elapsed = round(time.monotonic() - began, 3)
            result.update(outcome=outcome, latency_seconds=elapsed, measured_at=datetime.now(timezone.utc))
            SHADOW_OUTCOMES.labels(outcome=outcome if outcome in _OUTCOMES else 'failed').inc()
            SHADOW_LATENCY.observe(elapsed)
            # A child of the conversation inherits its deletion lifetime. The
            # parent read in the transaction fences a concurrent parent delete.
            try:
                _store_result(uid, conversation_id, result)
            except Exception as error:
                logger.warning(
                    'event=transcription_shadow outcome=metric_write_failed exception_type=%s', type(error).__name__
                )


def _store_result(uid: str, conversation_id: str, result: dict[str, Any]) -> None:
    parent = db.collection('users').document(uid).collection('conversations').document(conversation_id)
    child = parent.collection('transcription_shadow_results').document('v1')

    @firestore.transactional
    def write_if_current(transaction: Any) -> None:
        snapshot = parent.get(transaction=transaction)
        if not snapshot.exists or (snapshot.to_dict() or {}).get('deleted'):
            return
        transaction.set(child, result)

    write_if_current(db.transaction())

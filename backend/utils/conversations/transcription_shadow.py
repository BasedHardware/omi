"""Opt-in, bounded final-pass comparison and separately gated record promotion.

The default shadow path never mutates the record. A tracked background task
waits for upload flush, then a bounded pool performs storage, transcription and
comparison. Authoritative mode requires a safe remap and current record revision.
A restart can lose a sample; finalization admission remains independent.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os

from config.rollout_cohorts import in_rollout_cohort
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from prometheus_client import Counter, Histogram

from database import conversations as conversations_db
from config.batch_pipeline import RecordOwnerContention
from config.policy import resolve_batch_policy
from utils.manual_speaker_assignments import manual_owner_reserved
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
from utils.conversations.speaker_resolution import apply_speaker_resolution
from utils.executors import start_background_task
from utils.other.audio_chunks import iter_audio_chunk_pcm
from utils.speaker_tag_prompts.clips import pcm_to_wav, trim_pcm16
from utils.stt.conversation_speakers import resolve_conversation_speakers
from utils.stt.local_vad import offline_pcm_speech_segments
from utils.stt.vad_compaction import transcribe_with_speech_compaction
from utils.stt.pre_recorded import parakeet_prerecorded_from_bytes, postprocess_words
from utils.stt.parakeet_request_metrics import parakeet_caller
from utils.stt.speaker_embedding import extract_embedding_from_bytes, speaker_embedding_configured
from utils.sync.speaker_identity import build_person_embeddings_cache, identify_speakers_for_segments

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='transcription-shadow')
_slots = threading.BoundedSemaphore(2)


def _shadow_parakeet(speech_pcm: bytes) -> Any:
    with parakeet_caller('shadow'):
        return parakeet_prerecorded_from_bytes(speech_pcm, diarize=True, attempts=1, encoding='linear16')


_OUTCOMES = {'ok', 'failed', 'timeout', 'partial_audio', 'no_audio', 'skipped_budget'}
_PCM_BYTES_PER_SECOND = 32000
_SILENCE_FRAME_BYTES = 3200  # 100 ms of 16 kHz mono PCM16
_SILENCE_BREAK_FRAMES = 10
_WINDOW_MARGIN_BYTES = 3 * _SILENCE_FRAME_BYTES
_MAX_WINDOW_BYTES = 90 * _PCM_BYTES_PER_SECOND
_FORCED_CONTEXT_BYTES = 10 * _PCM_BYTES_PER_SECOND


class _BudgetExceeded(RuntimeError):
    pass


SHADOW_OUTCOMES = Counter('omi_transcription_shadow_total', 'Bounded final-pass shadow outcomes', ['outcome'])
SHADOW_LATENCY = Histogram('omi_transcription_shadow_latency_seconds', 'Final-pass shadow duration')
SHADOW_WORD_DISTANCE = Histogram(
    'omi_transcription_shadow_word_distance',
    'Word edit distance versus streaming transcript',
    ['outcome'],
    buckets=(0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1, 2, 4),
)
SHADOW_OWNER_DELTA = Histogram(
    'omi_transcription_shadow_owner_delta_ratio',
    'Owner-attributed seconds absolute delta divided by maximum owner seconds',
    ['outcome'],
    buckets=(0, 0.01, 0.05, 0.1, 0.2, 0.5, 1),
)
SHADOW_REMAP_SUCCESS = Histogram(
    'omi_transcription_shadow_remap_success_rate',
    'Fraction of live segments mapped to the shadow pass',
    ['outcome'],
    buckets=(0, 0.25, 0.5, 0.75, 0.9, 0.95, 1),
)
SHADOW_REMAP_SAFE = Counter(
    'omi_transcription_shadow_remap_safe_total',
    'Shadow remap safety verdicts',
    ['outcome', 'safe'],
)

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
    if getattr(conversation, 'record_lane_owner', None) in {'batch_live_v1', 'batch_sync_v1'}:
        return False
    if not conversation.private_cloud_sync_enabled or conversation.discarded or conversation.uses_custom_stt:
        return False
    if in_rollout_cohort(uid, 'transcription-shadow'):
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
        for attempt in range(3):
            try:
                await loop.run_in_executor(_pool, _run_shadow, uid, conversation_id)
                break
            except RecordOwnerContention:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.1 * (attempt + 1))
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning('event=transcription_shadow outcome=failed exception_type=%s', type(error).__name__)
        SHADOW_OUTCOMES.labels(outcome='failed').inc()
    finally:
        _slots.release()


def _reserve_budget(conversation_id: str, seconds: float) -> str:
    hours = float(os.getenv('TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS', '0'))
    requested = max(1, int(seconds * 1000 + 0.999))
    limit = max(0, int(hours * 3600 * 1000))
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


def _audio_windows(pcm: bytes) -> list[tuple[int, int, int]]:
    """Return (start, end, owned_start) byte ranges on the original PCM clock.

    A stored upload batch can contain a few seconds of speech followed by tens
    of seconds of delivered digital silence. Posting that whole batch invites
    TDT to repeat the speech into silence. Silence breaks also give each new
    request an utterance onset. Forced cuts retain ten seconds of context; only
    words extending beyond the previously owned audio are accepted.

    Only *digital* silence is skipped. A low-level recording is never classified
    as silence by an amplitude threshold.
    """
    frames = [
        (offset, any(pcm[offset : offset + _SILENCE_FRAME_BYTES]))
        for offset in range(0, len(pcm), _SILENCE_FRAME_BYTES)
    ]
    active = [index for index, (_, has_signal) in enumerate(frames) if has_signal]
    if not active:
        return []
    runs: list[tuple[int, int]] = []
    first = previous = active[0]
    for index in active[1:]:
        if index - previous > _SILENCE_BREAK_FRAMES:
            runs.append((first, previous))
            first = index
        previous = index
    runs.append((first, previous))

    windows: list[tuple[int, int, int]] = []
    for first, last in runs:
        start = max(0, frames[first][0] - _WINDOW_MARGIN_BYTES)
        end = min(len(pcm), frames[last][0] + _SILENCE_FRAME_BYTES + _WINDOW_MARGIN_BYTES)
        owned = start
        while end - start > _MAX_WINDOW_BYTES:
            cut = start + _MAX_WINDOW_BYTES
            windows.append((start, cut, owned))
            owned = cut
            start = cut - _FORCED_CONTEXT_BYTES
        windows.append((start, end, owned))
    return windows


def _make_pass(
    uid: str,
    conversation: Conversation,
    *,
    deadline: float,
    reserved_seconds: float,
    final_result: dict[str, Any] | None = None,
) -> tuple[list[TranscriptSegment], dict[str, float]]:
    cache = build_person_embeddings_cache(uid)
    final_pcm = bytearray() if final_result is not None else None
    final_words = []
    resolution = None
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
            # The v2 PCM contract trims complete 16-bit samples. Float wall
            # clocks can otherwise truncate an even frame offset to an odd byte.
            trim_bytes = round(overlap * 16000) * 2 if final_result is not None else int(overlap * 32000)
            pcm = pcm[min(len(pcm), trim_bytes) :]
            chunk_start += overlap
        if not pcm:
            continue
        if covered + len(pcm) / 32000 > reserved_seconds + 0.01:
            extra = covered + len(pcm) / 32000 - reserved_seconds
            if _reserve_budget(f'{conversation.id}:extra:{chunk_count}', extra) != 'reserved':
                raise _BudgetExceeded('decoded audio exceeds daily budget')
            reserved_seconds += extra
        if final_pcm is not None:
            position = round((chunk_start - audio_origin) * 16000) * 2
            if position + len(pcm) > 7200 * 32000:
                assert final_result is not None
                final_result['metadata'] = {'outcome': 'failed:too_long'}
                final_pcm = None
            else:
                final_pcm.extend(b'\x00' * max(0, position - len(final_pcm)))
                final_pcm.extend(pcm)
        for offset, end, owned_start in _audio_windows(pcm):
            if time.monotonic() >= deadline:
                raise TimeoutError('shadow deadline')
            part = pcm[offset:end]
            part_start = chunk_start + offset / 32000
            words = transcribe_with_speech_compaction(
                part,
                _shadow_parakeet,
                offline_pcm_speech_segments,
            )
            if isinstance(words, tuple):
                words = words[0]
            # A forced cut re-posts context so TDT can recover the utterance
            # onset. A word spanning the ownership boundary belongs to the
            # later request, which can hear the complete utterance.
            if owned_start > offset:
                words = [w for w in words if offset + float(w['timestamp'][1]) * 32000 > owned_start]
            if final_pcm is not None:
                final_words.extend(
                    {**word, 'timestamp': [float(t) + part_start - audio_origin for t in word['timestamp']]}
                    for word in words
                )
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
            segments,
            vectors,
            manual_speakers={},
            voiceprints={identity: entry['embedding'].reshape(-1) for identity, entry in cache.items()},
        )
        if resolution is not None:
            apply_speaker_resolution(
                conversation,
                resolution.speaker_ids,
                resolution.voice_identities,
                resolution.voice_identity_statuses,
                owner_voiceprint_available=resolution.owner_voiceprint_available,
                contradicted_segment_ids=resolution.contradicted_segment_ids,
            )
            conversation.speaker_resolution = ConversationSpeakers(
                status='resolved' if resolution.coverage >= 0.9 else 'unavailable',
                participant_speaker_ids=resolution.significant_speaker_ids if resolution.coverage >= 0.9 else [],
            )
    finished = _epoch(conversation.finished_at)
    started_origin = _epoch(getattr(conversation, 'started_at', None))
    tail = max(0.0, finished - last_end) if finished is not None and last_end is not None else 0.0
    expected = max(covered, (finished - origin) if finished is not None else covered)
    audio_result = {
        'coverage': round(min(1.0, covered / expected), 4) if expected > 0 else 0.0,
        'tail_gap_seconds': round(tail, 3),
        'audio_seconds': round(covered, 3),
    }
    # Compare with the text-derived remap offset before attributing drift
    # to the live capture clock. No wall timestamps leave this process.
    if started_origin is not None:
        audio_result['audio_origin_offset_seconds'] = round(origin - started_origin, 3)
    if final_result is not None and final_pcm is not None:
        from utils.conversations.final_pass_pyannote import run_final_pass

        passed, metadata = run_final_pass(
            bytes(final_pcm),
            final_words,
            resolution,
            cache,
            deadline=deadline,
            conversation_id=conversation.id,
            segments=segments,
            vectors=vectors,
            owner_reserved=bool(final_result.get('owner_reserved')),
        )
        final_result.update(metadata=metadata, segments=passed)
        final_pcm.clear()
        final_words.clear()
    return segments, audio_result


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
        'audio_timeline_v2': getattr(getattr(conversation, 'audio_timeline', None), 'version', None) == 2,
        'word_distance': _word_distance(live_words, pass_words),
        'live_word_count': len(live_words),
        'pass_word_count': len(pass_words),
        'live_owner_seconds': round(live_owner, 3),
        'pass_owner_seconds': round(pass_owner, 3),
        'live_speakers': len({s['speaker_id'] for s in old if s.get('speaker_id') is not None}),
        'pass_speakers': len({s['speaker_id'] for s in new if s.get('speaker_id') is not None}),
        'remap_success_rate': round(plan.success_rate, 4),
        'remap_ambiguous_count': len(plan.ambiguous),
        'remap_safe': plan.safe and remap_ok,
        'clock_offset_seconds': plan.offset_seconds,
    }


def _record_comparison_metrics(result: dict[str, Any], outcome: str) -> None:
    """Aggregate only bounded scalar comparison measures; no identity labels."""
    if result.get('word_distance') is not None:
        SHADOW_WORD_DISTANCE.labels(outcome=outcome).observe(result['word_distance'])
    owner_denominator = max(result['live_owner_seconds'], result['pass_owner_seconds'], 1.0)
    owner_delta = abs(result['live_owner_seconds'] - result['pass_owner_seconds']) / owner_denominator
    SHADOW_OWNER_DELTA.labels(outcome=outcome).observe(owner_delta)
    SHADOW_REMAP_SUCCESS.labels(outcome=outcome).observe(result['remap_success_rate'])
    SHADOW_REMAP_SAFE.labels(outcome=outcome, safe='true' if result['remap_safe'] else 'false').inc()


def _legacy_final_pass_allowed() -> bool:
    """Blocking (the pass runs on its own executor): new legacy final-pass work only at ``on``."""
    from utils.sync import legacy_dark

    return legacy_dark.legacy_admission_allowed()


def _claim_shadow_owner(uid: str, conversation_id: str, raw: dict, *, policy=None) -> dict | None:
    policy = policy or resolve_batch_policy(uid)
    for _ in range(3):
        owner = raw.get('record_lane_owner')
        if owner in {'batch_live_v1', 'batch_sync_v1'}:
            return None
        if owner == 'legacy_final_pass_v1':
            return raw
        # Once legacy sync is draining/dark no new legacy final-pass owner (and no new
        # final pass) may start: the conversation stays unowned for batch admission to
        # claim (M3 re-review; final_pass_rehome moves the owners that already exist).
        if not _legacy_final_pass_allowed():
            return None
        if not policy.live_admission_enabled:
            return raw
        revision = conversations_db.claim_record_lane_owner(
            uid, conversation_id, 'legacy_final_pass_v1', raw.get('updated_at')
        )
        if revision is not None:
            return {**raw, 'record_lane_owner': 'legacy_final_pass_v1', 'updated_at': revision}
        refreshed = conversations_db.get_conversation(uid, conversation_id)
        if not refreshed:
            return None
        raw = refreshed
    if raw.get('record_lane_owner') in {'batch_live_v1', 'batch_sync_v1'}:
        return None
    if raw.get('record_lane_owner') == 'legacy_final_pass_v1':
        return raw
    raise RecordOwnerContention('shadow owner claim remains contended after three refreshed revisions')


def _run_shadow(uid: str, conversation_id: str) -> None:
    policy = resolve_batch_policy(uid)
    began = time.monotonic()
    outcome = 'failed'
    result: dict[str, Any] = {}
    record_result = False
    try:
        raw = conversations_db.get_conversation(uid, conversation_id)
        if not raw:
            return
        if not _enabled(uid, deserialize_conversation(raw)):
            return
        raw = _claim_shadow_owner(uid, conversation_id, raw, policy=policy)
        if raw is None:
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
                final_result: dict[str, Any] | None = (
                    {'owner_reserved': manual_owner_reserved(receipt)} if policy.final_pass_enabled else None
                )
                kwargs = {'final_result': final_result} if final_result is not None else {}
                passed, audio = _make_pass(uid, conversation, deadline=deadline, reserved_seconds=estimated, **kwargs)
                if not passed:
                    outcome = 'no_audio'
                    result = audio
                else:
                    result = _compare(live_conversation, passed, audio, receipt)
                    outcome = 'partial_audio' if audio['tail_gap_seconds'] > 5 or audio['coverage'] < 0.95 else 'ok'
                    _record_comparison_metrics(result, outcome)
                    if final_result is not None:
                        metadata = final_result.get('metadata', {'outcome': 'failed:no_audio'})
                        candidate = final_result.get('segments')
                        if candidate is not None:
                            metadata['comparison'] = _compare(live_conversation, candidate, audio, receipt)
                            if (
                                outcome == 'ok'
                                and metadata['comparison']['remap_safe']
                                and policy.final_pass_authoritative
                            ):
                                metadata['promoted'] = conversations_db.promote_final_pass_if_current(
                                    uid,
                                    conversation_id,
                                    candidate,
                                    expected_updated_at=raw.get('updated_at'),
                                    clock_offset=metadata['comparison']['clock_offset_seconds'],
                                )
                        _store_result(uid, conversation_id, metadata, version='v2')
    except RecordOwnerContention:
        # Retry ownership before reserving provider budget or doing acoustic
        # work. A metadata race must not silently discard the selected pass.
        raise
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


def _store_result(uid: str, conversation_id: str, result: dict[str, Any], *, version: str = 'v1') -> None:
    parent = db.collection('users').document(uid).collection('conversations').document(conversation_id)
    child = parent.collection('transcription_shadow_results').document(version)
    deletion_marker = db.collection('account_deletions').document(uid)

    @firestore.transactional
    def write_if_current(transaction: Any) -> None:
        # Account deletion persists this marker before its recursive sweep.
        # Reading it in the same transaction fences a child commit after that
        # sweep has passed the conversation, even while the parent still exists.
        if deletion_marker.get(transaction=transaction).exists:
            return
        snapshot = parent.get(transaction=transaction)
        if not snapshot.exists or (snapshot.to_dict() or {}).get('deleted'):
            return
        transaction.set(child, result)

    write_if_current(db.transaction())

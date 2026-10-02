"""Background-only manual person teaching from a complete bounded ASR index.

Stored clocks order candidates but never authorize a cut. Each source is decoded
independently; batch interiors lack continuity evidence and fail closed. No I/O
or provider work runs at import or in the live socket transcription path.
"""

import asyncio
import hashlib
import io
import json
import math
import struct
import time
import uuid
import wave
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from config.speaker_clip_location import text_anchored_clips_enabled
from database import speaker_clip_location as cache
from utils import encryption
from utils.executors import ExecutorSaturatedError, db_executor, run_blocking, speaker_tag_verify_executor
from utils.observability.fallback import record_fallback
from utils.observability.speaker_clip_location import record_location
from utils.other import storage
from utils.speaker_clip_locator import locate_text, tokens
from utils.speaker_learning_policy import TEACHING_MIN_TOTAL_SECONDS, segment_group
from utils.speaker_sample import verify_and_transcribe_sample_in_worker
from utils.stt.pre_recorded import get_prerecorded_service, prerecorded_from_bytes, verification_stt_deadline

SAMPLE_RATE = 16000
MAX_LABEL_SECONDS = 600
MAX_LABEL_DOWNLOADS = 12
MAX_SOURCE_SECONDS = 60
MAX_SOURCE_BYTES = 4_000_000
MAX_SOURCE_COUNT = 128
MAX_INDEX_ENTRIES = 20000
MAX_CLIP_SECONDS = 12
DEADLINE_SECONDS = 35
PROVIDER_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class RelocatedSample:
    pcm: bytes
    transcript: str
    segment_ids: list[str]


def pcm_to_wav(pcm: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(pcm)
    return out.getvalue()


def read_source_pcm(uid: str, chunk: Mapping[str, Any]) -> bytes:
    """One size/generation-fenced download; no retries, gap-fill or batch decode."""
    if chunk.get('is_batch') or not chunk.get('generation'):
        raise ValueError('unsupported source')
    size = chunk.get('size')
    if not isinstance(size, int) or not 0 < size <= MAX_SOURCE_BYTES:
        raise ValueError('unsupported source size')
    path = str(chunk['path'])
    blob = storage.get_private_cloud_sync_bucket().blob(path)
    raw = blob.download_as_bytes(timeout=5, retry=None, if_generation_match=int(chunk['generation']))
    if len(raw) != size or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError('source changed')
    if path.endswith('.enc'):
        raw = encryption.decrypt_audio_file(raw, uid)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError('unsupported decoded source size')
    max_pcm = MAX_SOURCE_SECONDS * SAMPLE_RATE * 2
    if path.endswith(('.opus', '.opus.enc')):
        if len(raw) < 8:
            raise ValueError('invalid opus header')
        packets, pcm_length = struct.unpack_from('<II', raw)
        if packets > MAX_SOURCE_SECONDS * 1000 // storage.OPUS_FRAME_DURATION_MS or pcm_length > max_pcm:
            raise ValueError('unsupported source duration')
        raw = storage.decode_opus_to_pcm(raw, sample_rate=SAMPLE_RATE)
    if not raw or len(raw) % 2 or len(raw) > max_pcm:
        raise ValueError('invalid source duration')
    return raw


def transcribe_source(pcm: bytes, language: str | None, deadline: float) -> list[dict[str, Any]]:
    with verification_stt_deadline(min(deadline, time.monotonic() + PROVIDER_TIMEOUT_SECONDS)):
        result = prerecorded_from_bytes(pcm_to_wav(pcm), SAMPLE_RATE, True, language=language)
    if isinstance(result, tuple):
        result = result[0]
    if len(result) > MAX_INDEX_ENTRIES:
        raise ValueError('source index capacity exceeded')
    return result


def index_key(uid: str, conversation_id: str, chunks: Sequence[Mapping[str, Any]], language: str | None) -> str:
    return hashlib.sha256(
        json.dumps(
            [
                'text-location-1',
                cache.identity(uid, conversation_id),
                language,
                get_prerecorded_service(language),
                [(c['path'], c.get('generation'), c.get('size')) for c in chunks],
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def teaching_utterances(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Join only adjacent, already authorized contributors in one voice scope."""
    runs: list[list[Mapping[str, Any]]] = []
    for segment in sorted(candidates, key=lambda row: float(row.get('start') or 0)):
        if not segment.get('id'):
            continue
        if (
            runs
            and segment_group(segment) == segment_group(runs[-1][-1])
            and segment.get('start') is not None
            and runs[-1][-1].get('end') is not None
            and 0 <= float(segment['start']) - float(runs[-1][-1]['end']) <= 2
        ):
            runs[-1].append(segment)
        else:
            runs.append([segment])
    return [
        {'text': ' '.join(str(s.get('text') or '') for s in run), 'ids': [str(s['id']) for s in run]} for run in runs
    ]


async def relocate_person_sample(
    uid: str,
    conversation_id: str,
    candidates: Sequence[Mapping[str, Any]],
    language: str | None,
) -> RelocatedSample | None:
    """Caller supplies only currently manual-authorized segments after stored failure.

    One 35s coordinator deadline, atomic shared quotas and per-hop timeouts bound
    work. A cancelled leaf may finish its single <=10s provider attempt; it has
    no upload/publication authority. Reservations remain consumed in all cases.
    """
    outcome = 'error'
    lock_token = uuid.uuid4().hex
    locked = False
    deadline = time.monotonic() + DEADLINE_SECONDS
    seconds = 0
    downloads = 0
    try:
        if not text_anchored_clips_enabled():
            outcome = 'disabled'
            return None
        targets = [s for s in teaching_utterances(candidates) if 12 <= len(tokens(str(s.get('text') or ''))) <= 4096]
        if not targets:
            outcome = 'short_or_generic'
            return None
        locked = await run_blocking(db_executor, cache.acquire, uid, conversation_id, lock_token)
        if not locked:
            outcome = 'busy'
            return None
        async with asyncio.timeout(DEADLINE_SECONDS):
            chunks = await run_blocking(
                speaker_tag_verify_executor,
                storage.list_audio_chunks,
                uid,
                conversation_id,
                max_results=MAX_SOURCE_COUNT + 1,
                timeout=5,
                require_complete=True,
            )
            if not chunks:
                outcome = 'incomplete_audio'
                return None
            if len(chunks) > MAX_SOURCE_COUNT:
                outcome = 'budget_exhausted'
                return None
            # A skipped source could contain a competing copy: never claim
            # uniqueness over just the supported portion of a conversation.
            if any(c.get('is_batch') or not c.get('generation') for c in chunks):
                outcome = 'unsupported_source'
                return None
            key = await run_blocking(db_executor, index_key, uid, conversation_id, chunks, language)
            index = await run_blocking(db_executor, cache.read_index, uid, key)
            decoded: dict[int, bytes] = {}
            for number, chunk in enumerate(chunks):
                if str(number) in index:
                    continue
                if (
                    downloads >= MAX_LABEL_DOWNLOADS
                    or seconds + MAX_SOURCE_SECONDS + MAX_CLIP_SECONDS > MAX_LABEL_SECONDS
                ):
                    outcome = 'budget_exhausted'
                    return None
                if not await run_blocking(db_executor, cache.reserve, uid, conversation_id, downloads=1):
                    outcome = 'budget_exhausted'
                    return None
                downloads += 1
                pcm = await run_blocking(speaker_tag_verify_executor, read_source_pcm, uid, chunk)
                duration = len(pcm) / (SAMPLE_RATE * 2)
                charge = math.ceil(duration)
                if seconds + charge + MAX_CLIP_SECONDS > MAX_LABEL_SECONDS or not await run_blocking(
                    db_executor, cache.reserve, uid, conversation_id, seconds=charge
                ):
                    outcome = 'budget_exhausted'
                    return None
                seconds += charge
                words = await run_blocking(speaker_tag_verify_executor, transcribe_source, pcm, language, deadline)
                # Store only provider evidence, encrypted per user, not audio.
                index[str(number)] = {'words': words, 'duration': duration}
                if sum(len(row['words']) for row in index.values()) > MAX_INDEX_ENTRIES:
                    outcome = 'budget_exhausted'
                    return None
                await run_blocking(db_executor, cache.write_index, uid, key, index)
                decoded[number] = pcm
            sources = [(index[str(i)]['words'], index[str(i)]['duration']) for i in range(len(chunks))]
            for segment in targets[:5]:
                location, reason = await run_blocking(
                    speaker_tag_verify_executor,
                    locate_text,
                    str(segment.get('text') or ''),
                    sources,
                    complete=True,
                    deadline=deadline,
                )
                if location is None:
                    outcome = reason
                    continue
                duration = min(MAX_CLIP_SECONDS, location.end - location.start)
                if duration < TEACHING_MIN_TOTAL_SECONDS:
                    outcome = 'verification_rejected'
                    continue
                if seconds + math.ceil(duration) > MAX_LABEL_SECONDS:
                    outcome = 'budget_exhausted'
                    return None
                pcm = decoded.get(location.source)
                if pcm is None:
                    if downloads >= MAX_LABEL_DOWNLOADS or not await run_blocking(
                        db_executor, cache.reserve, uid, conversation_id, downloads=1
                    ):
                        outcome = 'budget_exhausted'
                        return None
                    downloads += 1
                    pcm = await run_blocking(speaker_tag_verify_executor, read_source_pcm, uid, chunks[location.source])
                # Center-crop the matched complete utterance, using only real
                # entry boundaries to locate it. No word timing interpolation.
                start = location.start + (location.end - location.start - duration) / 2
                clip = pcm[round(start * SAMPLE_RATE) * 2 : round((start + duration) * SAMPLE_RATE) * 2]
                if len(clip) < round(TEACHING_MIN_TOTAL_SECONDS * SAMPLE_RATE) * 2:
                    outcome = 'incomplete_audio'
                    continue
                if not await run_blocking(
                    db_executor, cache.reserve, uid, conversation_id, seconds=math.ceil(duration)
                ):
                    outcome = 'budget_exhausted'
                    return None
                seconds += math.ceil(duration)
                transcript, valid, reason = await run_blocking(
                    speaker_tag_verify_executor,
                    verify_and_transcribe_sample_in_worker,
                    pcm_to_wav(clip),
                    SAMPLE_RATE,
                    str(segment.get('text') or ''),
                    language,
                    min(deadline, time.monotonic() + PROVIDER_TIMEOUT_SECONDS),
                )
                if not valid or not transcript:
                    outcome = (
                        'transcription_failed' if reason.startswith('transcription_failed') else 'verification_rejected'
                    )
                    continue
                # Check the complete inventory again before returning evidence.
                current = await run_blocking(
                    speaker_tag_verify_executor,
                    storage.list_audio_chunks,
                    uid,
                    conversation_id,
                    max_results=MAX_SOURCE_COUNT + 1,
                    timeout=5,
                    require_complete=True,
                )
                current_key = await run_blocking(db_executor, index_key, uid, conversation_id, current, language)
                if current_key != key:
                    outcome = 'source_changed'
                    return None
                outcome = 'relocated'
                return RelocatedSample(clip, transcript, segment['ids'])
            return None
    except asyncio.CancelledError:
        outcome = 'timeout'
        raise
    except TimeoutError:
        outcome = 'timeout'
        return None
    except ExecutorSaturatedError:
        outcome = 'busy'
        return None
    except RuntimeError:
        outcome = 'transcription_failed'
        return None
    except ValueError:
        outcome = 'unsupported_source'
        return None
    except Exception:
        outcome = 'cache_unavailable'
        return None
    finally:
        if locked:
            try:
                await run_blocking(db_executor, cache.release, uid, conversation_id, lock_token)
            except Exception:
                pass
        record_location(outcome)
        if outcome != 'disabled':
            record_fallback(
                component='other',
                from_mode='stored_speaker_clip',
                to_mode='text_anchored_clip',
                reason='local_heal' if outcome == 'relocated' else 'policy',
                outcome='recovered' if outcome == 'relocated' else 'exhausted',
            )

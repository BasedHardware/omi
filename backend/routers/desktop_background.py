import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

import database.conversations as conversations_db
import database.users as users_db
from database import redis_db
from models.conversation_enums import ConversationSource, ConversationStatus
from models.transcript_segment import TranscriptSegment
from utils.analytics import record_usage
from utils.chat import resolve_voice_message_language
from utils.conversations.desktop_background import (
    DesktopBackgroundConversationError,
    append_segments_to_in_progress_conversation,
    create_in_progress_desktop_conversation,
    finish_desktop_background_conversation,
)
from utils.executors import db_executor, run_blocking, sync_executor
from utils.fair_use import is_hard_restricted, record_speech_ms
from utils.other import endpoints as auth
from utils.byok import get_byok_key
from utils.speaker_identification import _pcm_to_wav_bytes
from utils.stt.background_speaker_identity import USER_SELF_PERSON_ID, identify_background_speaker_clusters
from utils.stt.provider_service import (
    resolve_prerecorded_provider_for_request,
    transcribe_bytes,
    update_provider_run_identity_metrics,
)
from utils.stt.speaker_embedding import extract_embedding_from_bytes
from utils.stt.providers import STTProviderName, STTWorkload, get_fallback_prerecorded_provider_name
from utils.subscription import has_transcription_credits, is_trial_paywalled
from utils.voice_duration_limiter import compute_pcm_duration_ms

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/desktop", tags=["desktop-background"])

_MAX_PCM_BODY_BYTES = 200_000_000
_SPEAKER_MAP_TTL_SECONDS = 60 * 60 * 24


class BackgroundConversationStartRequest(BaseModel):
    language: Optional[str] = None
    source: Optional[str] = "desktop"


@router.get("/capabilities")
async def desktop_capabilities(uid: str = Depends(auth.get_current_user_uid)):
    background_provider = resolve_prerecorded_provider_for_request(STTWorkload.background)
    assemblyai_key_available = bool(os.getenv('ASSEMBLYAI_API_KEY') or get_byok_key('assemblyai'))
    fallback_provider = get_fallback_prerecorded_provider_name(background_provider, STTWorkload.background)
    fallback_available = fallback_provider == STTProviderName.deepgram
    enabled = background_provider == STTProviderName.assemblyai and (assemblyai_key_available or fallback_available)
    reason = None
    if background_provider != STTProviderName.assemblyai:
        reason = f'provider_{background_provider.value}'
    elif not assemblyai_key_available and fallback_available:
        reason = 'fallback_deepgram_available'
    elif not assemblyai_key_available:
        reason = 'missing_assemblyai_api_key'
    return {
        "background_batch": {
            "enabled": enabled,
            "provider": background_provider.value,
            "fallback_provider": fallback_provider.value if fallback_provider else None,
            "workload": STTWorkload.background.value,
            "reason": reason,
            "sample_rate": 16000,
            "channels": 1,
            "encoding": "linear16",
            "max_chunk_seconds": 15,
        }
    }


@router.post("/background-conversation/start")
async def start_background_conversation(
    body: BackgroundConversationStartRequest,
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    if is_trial_paywalled(uid, x_app_platform or body.source or "desktop"):
        raise HTTPException(status_code=402, detail={'error': 'quota_exceeded', 'plan_type': 'basic'})

    language = resolve_voice_message_language(uid, body.language)
    try:
        source = ConversationSource(body.source or "desktop")
    except ValueError:
        raise HTTPException(status_code=422, detail='Invalid source')

    conversation_id = await run_blocking(
        db_executor,
        create_in_progress_desktop_conversation,
        uid,
        language,
        source,
    )
    return {"conversation_id": conversation_id}


@router.post("/background-conversation/{conversation_id}/finish")
async def finish_background_conversation(
    conversation_id: str,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "desktop:background_conversation_finish")),
):
    try:
        return await run_blocking(
            db_executor,
            finish_desktop_background_conversation,
            uid,
            conversation_id,
        )
    except DesktopBackgroundConversationError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.post("/background-transcribe")
async def background_transcribe(
    request: Request,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "desktop:background_transcribe")),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
):
    if is_trial_paywalled(uid, x_app_platform or "desktop"):
        raise HTTPException(status_code=402, detail={'error': 'quota_exceeded', 'plan_type': 'basic'})
    if await run_blocking(db_executor, is_hard_restricted, uid):
        raise HTTPException(status_code=429, detail='Transcription temporarily restricted')
    if not await run_blocking(db_executor, has_transcription_credits, uid, source="desktop"):
        raise HTTPException(status_code=429, detail='Transcription credits exhausted')

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            content_length_value = int(content_length)
        except ValueError:
            raise HTTPException(status_code=422, detail='content-length must be an integer')
        if content_length_value > _MAX_PCM_BODY_BYTES:
            raise HTTPException(status_code=413, detail=f'Body too large (max {_MAX_PCM_BODY_BYTES} bytes)')

    audio_bytes = await request.body()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail='No audio data provided')
    if len(audio_bytes) > _MAX_PCM_BODY_BYTES:
        del audio_bytes
        raise HTTPException(status_code=413, detail=f'Body too large (max {_MAX_PCM_BODY_BYTES} bytes)')

    try:
        sample_rate = int(request.query_params.get("sample_rate", "16000"))
        channels = int(request.query_params.get("channels", "1"))
    except ValueError:
        del audio_bytes
        raise HTTPException(status_code=422, detail='sample_rate and channels must be integers')

    if sample_rate < 8000 or sample_rate > 48000:
        del audio_bytes
        raise HTTPException(status_code=422, detail='sample_rate must be between 8000 and 48000')
    if channels != 1:
        del audio_bytes
        raise HTTPException(status_code=422, detail='channels must be 1')

    chunk_start_ms_raw = request.query_params.get("chunk_start_ms")
    if chunk_start_ms_raw is None:
        del audio_bytes
        raise HTTPException(status_code=400, detail='chunk_start_ms is required')
    try:
        chunk_start_ms = int(chunk_start_ms_raw)
    except ValueError:
        del audio_bytes
        raise HTTPException(status_code=422, detail='chunk_start_ms must be an integer')
    if chunk_start_ms < 0:
        del audio_bytes
        raise HTTPException(status_code=422, detail='chunk_start_ms must be non-negative')

    conversation_id = request.query_params.get("conversation_id")
    persist = _parse_persist(request.query_params.get("persist"), default=bool(conversation_id))
    if persist:
        if not conversation_id:
            del audio_bytes
            raise HTTPException(status_code=400, detail='conversation_id is required when persist=true')
        await _validate_in_progress_conversation(uid, conversation_id)

    language = resolve_voice_message_language(uid, request.query_params.get("language"))
    keywords = _parse_context_keywords(request.query_params.get("keywords"))
    encoding = request.query_params.get("encoding", "linear16")
    duration_ms = compute_pcm_duration_ms(len(audio_bytes), sample_rate, channels)
    duration_sec = duration_ms / 1000.0

    try:
        audio_for_stt = _pcm_to_wav_bytes(audio_bytes, sample_rate) if encoding == "linear16" else audio_bytes
        response = await run_blocking(
            sync_executor,
            transcribe_bytes,
            audio_for_stt,
            workload=STTWorkload.background,
            uid=uid,
            conversation_id=conversation_id,
            sample_rate=sample_rate,
            diarize=True,
            encoding=None if encoding == "linear16" else encoding,
            channels=channels,
            language=language,
            return_language=language == "multi",
            keywords=keywords,
            raw_audio_seconds=duration_sec,
        )
    except RuntimeError as e:
        logger.error("Desktop background transcription failed: %s", e)
        raise HTTPException(status_code=500, detail=f'Transcription failed: {str(e)}')
    finally:
        del audio_bytes

    segments = response.segments
    speaker_diagnostics = _speaker_diagnostics(segments)
    if conversation_id and segments:
        await _identify_speakers(
            uid=uid,
            conversation_id=conversation_id,
            audio_bytes=audio_for_stt,
            segments=segments,
            provider=response.result.provider if response.result else None,
            model=response.result.model if response.result else None,
            run_id=response.run_id,
        )
    _apply_chunk_offset(segments, chunk_start_ms / 1000.0)
    if conversation_id:
        _apply_speaker_ids(conversation_id, segments)
    speaker_diagnostics.update(_speaker_diagnostics(segments, prefix="mapped_"))

    finished_at = datetime.now(timezone.utc)
    if persist and conversation_id:
        await run_blocking(
            db_executor,
            append_segments_to_in_progress_conversation,
            uid,
            conversation_id,
            segments,
            finished_at,
        )

    await run_blocking(db_executor, record_speech_ms, uid, duration_ms, source='background')
    await run_blocking(db_executor, record_usage, uid, transcription_seconds=duration_sec, speech_seconds=duration_sec)
    provider = response.result.provider if response.result else None
    logger.info(
        "desktop_background_transcribe completed uid=%s conversation_id=%s workload=background provider=%s run_id=%s "
        "chunk_start_ms=%s chunk_duration_ms=%s segments=%s persisted=%s",
        uid,
        conversation_id,
        provider,
        response.run_id,
        chunk_start_ms,
        duration_ms,
        len(segments),
        bool(persist and conversation_id),
    )

    return {
        "segments": [segment.model_dump() for segment in segments],
        "language": response.detected_language or language,
        "provider": provider,
        "run_id": response.run_id,
        "chunk_duration_ms": duration_ms,
        "speaker_diagnostics": speaker_diagnostics,
    }


def _parse_persist(raw: Optional[str], default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no")


def _parse_context_keywords(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    keywords: List[str] = []
    seen = set()
    for item in raw.split(','):
        keyword = item.strip()
        if len(keyword) < 2 or len(keyword) > 80:
            continue
        dedupe_key = keyword.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        keywords.append(keyword)
        if len(keywords) >= 100:
            break
    return keywords


async def _validate_in_progress_conversation(uid: str, conversation_id: str) -> None:
    conversation = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail='conversation_id not found')
    if conversation.get('status') != ConversationStatus.in_progress:
        raise HTTPException(status_code=404, detail='conversation is not in_progress')


def _apply_chunk_offset(segments: List[TranscriptSegment], offset_sec: float) -> None:
    for segment in segments:
        segment.start += offset_sec
        segment.end += offset_sec


async def _identify_speakers(
    uid: str,
    conversation_id: str,
    audio_bytes: bytes,
    segments: List[TranscriptSegment],
    provider: Optional[str],
    model: Optional[str],
    run_id: Optional[str],
) -> None:
    """Apply Omi speaker identity to AssemblyAI background chunk-local segments."""
    try:
        person_embeddings_cache = await run_blocking(db_executor, _build_person_embeddings_cache, uid)
        if not person_embeddings_cache:
            return
        assignments = await run_blocking(
            sync_executor,
            identify_background_speaker_clusters,
            segments,
            audio_bytes,
            person_embeddings_cache,
            extract_embedding_from_bytes,
        )
        identified_count = sum(1 for assignment in assignments.values() if assignment.state in ('identified', 'user'))
        logger.info(
            "Speaker ID (desktop background): cluster assignments=%s identified=%s uid=%s conversation_id=%s",
            len(assignments),
            identified_count,
            uid,
            conversation_id,
        )
        await run_blocking(
            db_executor,
            update_provider_run_identity_metrics,
            run_id,
            provider or 'unknown',
            model or 'unknown',
            STTWorkload.background,
            segments,
        )
    except Exception as e:
        logger.warning(
            "Speaker ID (desktop background): identification failed uid=%s conversation_id=%s: %s",
            uid,
            conversation_id,
            e,
        )


def _build_person_embeddings_cache(uid: str) -> Dict[str, dict]:
    cache: Dict[str, dict] = {}

    embedding_list = users_db.get_user_speaker_embedding(uid)
    if embedding_list:
        user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
        cache[USER_SELF_PERSON_ID] = {'embedding': user_embedding, 'name': 'User'}

    people = users_db.get_people(uid)
    for person in people or []:
        embedding = person.get('speaker_embedding')
        if embedding and person.get('speech_samples'):
            cache[person['id']] = {
                'embedding': np.array(embedding, dtype=np.float32).reshape(1, -1),
                'name': person['name'],
            }

    return cache


def _apply_speaker_ids(conversation_id: str, segments: List[TranscriptSegment]) -> None:
    speaker_map = _load_speaker_map(conversation_id)
    changed = False
    for segment in segments:
        cluster = segment.provider_cluster_id or segment.provider_speaker_label or segment.speaker
        if not cluster:
            continue
        if cluster not in speaker_map:
            speaker_map[cluster] = len(speaker_map)
            changed = True
        speaker_id = speaker_map[cluster]
        segment.speaker_id = speaker_id
        segment.speaker = f"SPEAKER_{speaker_id:02d}"
        if segment.speaker_identity_state == "legacy_ambiguous":
            segment.speaker_identity_state = "unassigned"

    if changed:
        _store_speaker_map(conversation_id, speaker_map)


def _speaker_map_key(conversation_id: str) -> str:
    return f"desktop_batch_speaker_map:{conversation_id}"


def _load_speaker_map(conversation_id: str) -> Dict[str, int]:
    raw = redis_db.r.get(_speaker_map_key(conversation_id))
    if not raw:
        return {}
    try:
        return {str(key): int(value) for key, value in json.loads(raw).items()}
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Invalid desktop batch speaker map for conversation_id=%s", conversation_id)
        return {}


def _store_speaker_map(conversation_id: str, speaker_map: Dict[str, int]) -> None:
    redis_db.r.set(_speaker_map_key(conversation_id), json.dumps(speaker_map), ex=_SPEAKER_MAP_TTL_SECONDS)


def _speaker_diagnostics(segments: List[TranscriptSegment], prefix: str = "") -> Dict[str, object]:
    provider_clusters = sorted(
        {str(segment.provider_cluster_id) for segment in segments if segment.provider_cluster_id is not None}
    )
    provider_labels = sorted(
        {str(segment.provider_speaker_label) for segment in segments if segment.provider_speaker_label is not None}
    )
    mapped_speakers = sorted({int(segment.speaker_id) for segment in segments if segment.speaker_id is not None})
    return {
        f"{prefix}provider_cluster_count": len(provider_clusters),
        f"{prefix}provider_clusters": provider_clusters[:20],
        f"{prefix}provider_speaker_label_count": len(provider_labels),
        f"{prefix}provider_speaker_labels": provider_labels[:20],
        f"{prefix}speaker_id_count": len(mapped_speakers),
        f"{prefix}speaker_ids": mapped_speakers[:20],
    }

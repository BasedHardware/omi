import asyncio
import contextlib
import io
import logging
import os
import shutil
import threading
import time
import uuid as _uuid
import wave
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import httpx

from utils.executors import (
    critical_executor,
    db_executor,
    storage_executor,
    sync_executor,
    run_blocking,
    start_background_task,
)

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Header, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from pydub import AudioSegment

from database import conversations as conversations_db
from database import users as users_db
from database.conversations import get_closest_conversation_to_timestamps, update_conversation_segments
from database.sync_jobs import (
    TERMINAL_STATUSES,
    create_sync_job,
    get_sync_job,
    update_sync_job,
    mark_job_processing,
    mark_job_completed,
    mark_job_failed,
    mark_job_queued_for_retry,
    try_acquire_job_run_lock,
    release_job_run_lock,
    add_processed_segment,
    get_processed_segments,
    try_mark_once,
)
from models.conversation import Conversation, CreateConversation
from models.conversation_enums import ConversationSource
from models.sync_audio import AudioPrecacheResponse, AudioUrlsResponse
from utils.conversations.factory import deserialize_conversation
from models.transcript_segment import TranscriptSegment
from utils.conversations.process_conversation import process_conversation
from utils.analytics import record_usage
from utils.other import endpoints as auth
from utils.other.storage import (
    get_syncing_file_temporal_signed_url,
    delete_syncing_temporal_file,
    schedule_syncing_temporal_file_deletion,
    upload_syncing_temporal_file,
    download_syncing_temporal_file,
    get_playback_artifact_signed_url,
    upload_playback_artifact,
    mark_playback_unavailable,
    upload_audio_chunk,
    precache_conversation_audio,
)

from utils import encryption
from utils.byok import get_byok_keys, set_byok_keys, has_byok_keys
from utils.cloud_tasks import (
    enqueue_sync_job,
    get_sync_tasks_max_attempts,
    is_cloud_tasks_dispatch_enabled,
    verify_cloud_tasks_oidc,
)
from utils.http_client import _get_semaphore
from utils.log_sanitizer import sanitize
from utils.sync import playback as sync_playback
from utils.sync.files import decode_files_to_wav, get_timestamp_from_path, get_wav_duration, retrieve_file_paths
from utils.stt.pre_recorded import postprocess_words, prerecorded
from utils.stt.vad import vad_is_empty
from utils.fair_use import (
    record_speech_ms,
    get_rolling_speech_ms,
    check_soft_caps,
    get_hard_restriction_status,
    trigger_classifier_if_needed,
    is_dg_budget_exhausted,
    get_enforcement_stage,
    record_dg_usage_ms,
    FAIR_USE_ENABLED,
    FAIR_USE_RESTRICT_DAILY_DG_MS,
)
from utils.speaker_assignment import process_speaker_assigned_segments
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.speaker_embedding import (
    extract_embedding_from_bytes,
    compare_embeddings,
    SPEAKER_MATCH_THRESHOLD,
)
from utils.subscription import has_transcription_credits

logger = logging.getLogger(__name__)

# Audio constants
AUDIO_SAMPLE_RATE = 16000

_V1_DEPRECATION_HEADERS = {'Deprecation': 'true', 'Link': '</v2/sync-local-files>; rel="successor-version"'}

router = APIRouter()


class SyncLocalFilesResultResponse(BaseModel):
    new_memories: list[str] = Field(default_factory=list)
    updated_memories: list[str] = Field(default_factory=list)
    failed_segments: int = 0
    total_segments: int = 0
    errors: list[str] = Field(default_factory=list)


class SyncJobStartResponse(BaseModel):
    job_id: str
    status: str
    total_files: int
    total_segments: int
    poll_after_ms: int


class SyncJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_segments: int = 0
    processed_segments: int = 0
    successful_segments: int = 0
    failed_segments: int = 0
    result: SyncLocalFilesResultResponse | None = None
    error: str | None = None


class AudioDownloadPendingResponse(BaseModel):
    status: str
    poll_after_ms: int


def _hard_restriction_headers(retry_after: int | None, base_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = dict(base_headers or {})
    if retry_after is not None:
        headers['Retry-After'] = str(retry_after)
    return headers


@router.post("/v1/sync/audio/{conversation_id}/precache", response_model=AudioPrecacheResponse, tags=['v1'])
def precache_conversation_audio_endpoint(
    conversation_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Warm the audio cache for a conversation.
    Returns immediately - caching happens in background.
    """
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    return sync_playback.precache_audio_files(uid, conversation_id, conversation.get('audio_files', []))


@router.get("/v1/sync/audio/{conversation_id}/urls", response_model=AudioUrlsResponse, tags=['v1'])
def get_audio_signed_urls_endpoint(
    conversation_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Get signed URLs for all audio files in a conversation.
    Synchronously caches the first uncached file for immediate playback.
    Remaining files are cached in background.

    Returns:
        List of audio file info with signed_url (if cached) or status "pending"
    """
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    return sync_playback.get_audio_signed_urls(uid, conversation_id, conversation.get('audio_files', []))


# **********************************************
# ********** AUDIO DOWNLOAD ENDPOINT ***********
# **********************************************


@router.get(
    "/v1/sync/audio/{conversation_id}/{audio_file_id}",
    tags=['v1'],
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Audio stream.",
            "content": {
                "audio/wav": {"schema": {"type": "string", "format": "binary"}},
                "audio/mpeg": {"schema": {"type": "string", "format": "binary"}},
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        202: {
            "description": "Audio artifact is being prepared.",
            "model": AudioDownloadPendingResponse,
        },
        206: {
            "description": "Partial audio stream.",
            "content": {
                "audio/wav": {"schema": {"type": "string", "format": "binary"}},
                "audio/mpeg": {"schema": {"type": "string", "format": "binary"}},
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
            },
        },
    },
)
def download_audio_file_endpoint(
    conversation_id: str,
    audio_file_id: str,
    request: Request,
    format: str = Query(default="wav", regex="^(wav|pcm)$"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Download audio file from private cloud sync in the specified format.
    Merges chunks on-demand.

    Args:
        conversation_id: ID of the conversation
        audio_file_id: ID of the audio file within the conversation
        request: FastAPI Request object (for Range header)
        format: Output format - 'wav' or 'pcm' (raw) (default: wav)
        uid: User ID (from authentication)

    Returns:
        StreamingResponse with the audio file in the requested format.
        Returns 206 Partial Content for Range requests, 200 OK for full file.
    """
    # Verify user owns the conversation
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    # Find the audio file in the conversation
    audio_files = conversation.get('audio_files', [])
    audio_file = None
    for af in audio_files:
        if af.get('id') == audio_file_id:
            audio_file = af
            break

    if not audio_file:
        raise HTTPException(status_code=404, detail="Audio file not found in conversation")

    return sync_playback.download_audio_file_response(uid, conversation_id, audio_file_id, audio_file, request, format)


# **********************************************
# ************ SYNC LOCAL FILES ****************
# **********************************************


# Max length of a single VAD segment / STT transcribe request. Bounds GPU memory on the
# STT worker (~0.5 GiB VRAM per audio minute), which CUDA-OOMs on long continuous audio.
MAX_VAD_SEGMENT_SECONDS = int(os.getenv('SYNC_MAX_VAD_SEGMENT_SECONDS', '300'))


def _merge_and_cap_vad_segments(voice_segments: list) -> list:
    merged = []
    for segment in voice_segments:
        if (
            merged
            and (segment['start'] - merged[-1]['end']) < 120
            and (segment['end'] - merged[-1]['start']) <= MAX_VAD_SEGMENT_SECONDS
        ):
            merged[-1]['end'] = segment['end']
        else:
            merged.append(dict(segment))

    segments = []
    for segment in merged:
        if segment['end'] - segment['start'] <= MAX_VAD_SEGMENT_SECONDS:
            segments.append(segment)
        else:
            chunk_start = segment['start']
            while chunk_start < segment['end']:
                chunk_end = min(chunk_start + MAX_VAD_SEGMENT_SECONDS, segment['end'])
                segments.append({'start': chunk_start, 'end': chunk_end})
                chunk_start = chunk_end
    return segments


def retrieve_vad_segments(path: str, segmented_paths: set, errors: list = None):
    try:
        start_timestamp = get_timestamp_from_path(path)
        voice_segments = vad_is_empty(path, return_segments=True, cache=True)
    except Exception as e:
        error_msg = f"VAD failed for {path}: {str(e)}"
        logger.info(error_msg)
        if errors is not None:
            errors.append(error_msg)
        raise  # Re-raise to ensure thread failure is visible

    segments = _merge_and_cap_vad_segments(voice_segments)
    logger.info(f"{path} {len(segments)}")

    aseg = AudioSegment.from_wav(path)
    path_dir = '/'.join(path.split('/')[:-1])

    try:
        for i, segment in enumerate(segments):
            if (segment['end'] - segment['start']) < 1:
                continue
            segment_timestamp = start_timestamp + segment['start']
            segment_path = f'{path_dir}/{segment_timestamp}.wav'
            segment_aseg = aseg[segment['start'] * 1000 : segment['end'] * 1000]
            segment_aseg.export(segment_path, format='wav')
            segmented_paths.add(segment_path)
            # Explicitly delete segment to free memory immediately
            del segment_aseg
    finally:
        # Explicitly delete main audio to free memory
        del aseg


def _reprocess_conversation_after_update(uid: str, conversation_id: str, language: str):
    """
    Reprocess a conversation after new segments have been added.
    This checks if the conversation should still be discarded and regenerates
    the summary/structured data if it now has sufficient content.
    """
    # Fetch the updated conversation with all segments
    conversation_data = conversations_db.get_conversation(uid, conversation_id)
    if not conversation_data:
        logger.warning(f'Conversation {conversation_id} not found for reprocessing')
        return

    # Convert to Conversation object
    conversation = deserialize_conversation(conversation_data)

    process_conversation(
        uid=uid,
        language_code=language or 'en',
        conversation=conversation,
        force_process=True,
        is_reprocess=True,
    )

    logger.info(f'Successfully reprocessed conversation {conversation_id}')


USER_SELF_PERSON_ID = 'user'
SPEAKER_ID_MIN_AUDIO = 1.0  # Minimum seconds of audio per speaker for embedding extraction


def build_person_embeddings_cache(uid: str) -> Dict[str, dict]:
    """Build a cache of person embeddings for speaker identification.

    Loads the user's own speaker embedding and all people with stored embeddings.
    Returns dict mapping person_id -> {embedding: np.ndarray, name: str}.
    """
    cache: Dict[str, dict] = {}

    # Load user's own speaker embedding
    embedding_list = users_db.get_user_speaker_embedding(uid)
    if embedding_list:
        user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
        cache[USER_SELF_PERSON_ID] = {'embedding': user_embedding, 'name': 'User'}

    # Load all people with speaker embeddings
    people = users_db.get_people(uid)
    for person in people or []:
        emb = person.get('speaker_embedding')
        # Only load embedding if person has speech samples — contacts without
        # samples may have stale embeddings from a pre-v3 model (#6238)
        if emb and person.get('speech_samples'):
            cache[person['id']] = {
                'embedding': np.array(emb, dtype=np.float32).reshape(1, -1),
                'name': person['name'],
            }

    return cache


def _download_audio_bytes(url: str) -> Optional[bytes]:
    """Download audio from a signed URL. Returns WAV bytes or None on failure."""
    try:
        resp = httpx.get(url, timeout=60.0)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logger.warning(f'Speaker ID: failed to download audio: {e}')
        return None


def _extract_speaker_clip_wav(audio_bytes: bytes, start_sec: float, end_sec: float) -> Optional[bytes]:
    """Extract a clip from WAV audio bytes between start_sec and end_sec.

    Returns WAV bytes for the clip, or None if extraction fails or clip is too short.
    """
    try:
        with wave.open(io.BytesIO(audio_bytes), 'rb') as wf:
            framerate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            total_duration = n_frames / framerate

            # Clamp to audio bounds
            start_sec = max(0.0, start_sec)
            end_sec = min(total_duration, end_sec)
            if end_sec - start_sec < SPEAKER_ID_MIN_AUDIO:
                return None

            # Cap extraction at 10 seconds
            if end_sec - start_sec > 10.0:
                center = (start_sec + end_sec) / 2
                start_sec = center - 5.0
                end_sec = center + 5.0
                start_sec = max(0.0, start_sec)
                end_sec = min(total_duration, end_sec)

            start_frame = int(start_sec * framerate)
            end_frame = int(end_sec * framerate)

            wf.setpos(start_frame)
            frames = wf.readframes(end_frame - start_frame)

        # Write clip as WAV
        clip_buf = io.BytesIO()
        with wave.open(clip_buf, 'wb') as out_wf:
            out_wf.setnchannels(n_channels)
            out_wf.setsampwidth(sampwidth)
            out_wf.setframerate(framerate)
            out_wf.writeframes(frames)
        return clip_buf.getvalue()
    except Exception as e:
        logger.warning(f'Speaker ID: failed to extract clip: {e}')
        return None


def identify_speakers_for_segments(
    transcript_segments: List['TranscriptSegment'],
    audio_bytes: Optional[bytes],
    person_embeddings_cache: Dict[str, dict],
    uid: str,
) -> None:
    """Identify speakers in transcript segments using voice embeddings and text detection.

    Modifies segments in-place by assigning person_id and is_user fields.

    Steps:
    1. Voice embedding matching (requires audio_bytes and non-empty cache):
       For each unique speaker_id, find the longest segment (>=1s), extract audio clip,
       get embedding, match against person_embeddings_cache.
    2. Text-based detection ("I am X") runs independently for all unmatched speakers.
    3. Apply assignments via process_speaker_assigned_segments.
    """
    speaker_to_person_map: Dict[int, Tuple[str, str]] = {}
    segment_person_assignment_map: Dict[str, str] = {}

    # Group segments by speaker_id, find best (longest) segment per speaker for embedding
    speaker_segments: Dict[int, List[TranscriptSegment]] = {}
    for seg in transcript_segments:
        sid = seg.speaker_id if seg.speaker_id is not None else 0
        speaker_segments.setdefault(sid, []).append(seg)

    # Voice embedding matching (only when audio and cached embeddings are available)
    # Track matched person_ids so each person is only assigned to one speaker
    # (diarization tells us speakers are distinct — no person can be two speakers).
    matched_person_ids: set = set()

    if audio_bytes and person_embeddings_cache:
        # Sort speakers by best single segment duration (longest first) — this is the clip
        # actually used for embedding, so it determines match quality.
        # Note: matched_person_ids assumes diarization is correct (one person = one speaker).
        # If diarization fragments one person across speaker IDs, only the best match wins.
        sorted_speakers = sorted(
            speaker_segments.items(),
            key=lambda kv: max(s.end - s.start for s in kv[1]),
            reverse=True,
        )

        for speaker_id, segments in sorted_speakers:
            best_seg = max(segments, key=lambda s: s.end - s.start)
            seg_duration = best_seg.end - best_seg.start

            if seg_duration < SPEAKER_ID_MIN_AUDIO:
                continue

            clip_wav = _extract_speaker_clip_wav(audio_bytes, best_seg.start, best_seg.end)
            if not clip_wav:
                continue

            try:
                query_embedding = extract_embedding_from_bytes(clip_wav, "sync_speaker.wav")
            except (ValueError, Exception) as e:
                logger.info(f'Speaker ID: embedding extraction failed for speaker {speaker_id}: {e} uid={uid}')
                continue

            # Compare only against unmatched candidates (each person can be one speaker)
            best_match = None
            best_distance = float('inf')
            for person_id, data in person_embeddings_cache.items():
                if person_id in matched_person_ids:
                    continue
                distance = compare_embeddings(query_embedding, data['embedding'])
                if distance < best_distance:
                    best_distance = distance
                    best_match = (person_id, data['name'])

            if best_match and best_distance < SPEAKER_MATCH_THRESHOLD:
                person_id, person_name = best_match
                speaker_to_person_map[speaker_id] = (person_id, person_name)
                segment_person_assignment_map[best_seg.id] = person_id
                matched_person_ids.add(person_id)
                logger.info(
                    f'Speaker ID (sync): speaker {speaker_id} -> {person_id} '
                    f'(distance={best_distance:.3f}) uid={uid}'
                )

    # Text-based detection runs independently for all unmatched speakers.
    # For speaker_id > 0 (diarized): update both speaker_to_person_map and per-segment map.
    # For speaker_id <= 0 (undiarized): only assign per-segment (avoid mapping all speaker_id=0
    # segments to one person when diarization is inactive).
    for speaker_id, segments in speaker_segments.items():
        if speaker_id in speaker_to_person_map:
            continue
        for seg in segments:
            detected_name = detect_speaker_from_text(seg.text)
            if detected_name:
                person = users_db.get_person_by_name(uid, detected_name)
                if person:
                    # Per-segment assignment always applies
                    segment_person_assignment_map[seg.id] = person['id']
                    # Update speaker map only when diarization is active
                    if speaker_id > 0:
                        speaker_to_person_map[speaker_id] = (person['id'], person['name'])
                    logger.info(
                        f'Speaker ID (sync): text detection speaker {speaker_id} -> '
                        f'{person["id"]} via "{detected_name}" uid={uid}'
                    )
                    if speaker_id > 0:
                        break  # One match per diarized speaker is enough

    # Apply all assignments to segments
    if speaker_to_person_map or segment_person_assignment_map:
        process_speaker_assigned_segments(
            transcript_segments,
            segment_person_assignment_map,
            speaker_to_person_map,
        )


ORDERED_ASSIGNMENT_WAIT_SECONDS = 600


class _OrderedTurnstile:
    """Serializes conversation assignment across parallel segment threads in timestamp order.

    Segments are transcribed concurrently, but each must wait its (chronological) turn
    before looking up / creating a conversation. Without this, timestamp-adjacent chunks
    race get_closest_conversation_to_timestamps() before any of them has persisted a
    conversation, so every chunk becomes its own conversation (#6551, #5747).
    """

    def __init__(self, ordered_keys: List[str]):
        self._pending = deque(ordered_keys)
        self._done = set()
        self._cond = threading.Condition()

    def _advance(self):
        while self._pending and self._pending[0] in self._done:
            self._pending.popleft()

    def wait_turn(self, key: str, timeout: float = ORDERED_ASSIGNMENT_WAIT_SECONDS) -> bool:
        """Block until every earlier key has completed. Returns False on timeout (fail-open)."""
        with self._cond:
            return self._cond.wait_for(
                lambda: self._advance() or not self._pending or self._pending[0] == key, timeout=timeout
            )

    def complete(self, key: str):
        with self._cond:
            self._done.add(key)
            self._advance()
            self._cond.notify_all()


def process_segment(
    path: str,
    uid: str,
    response: dict,
    lock: threading.Lock,
    errors: list,
    source: ConversationSource = ConversationSource.omi,
    is_locked: bool = False,
    transcription_prefs: dict = None,
    person_embeddings_cache: dict = None,
    target_conversation_id: str = None,
    turnstile: Optional[_OrderedTurnstile] = None,
    private_cloud_sync_enabled: bool = False,
    data_protection_level: str = None,
):
    try:
        url = get_syncing_file_temporal_signed_url(path)
        schedule_syncing_temporal_file_deletion(path)

        # Apply user transcription preferences (vocabulary, language, model)
        prefs = transcription_prefs or {}
        user_vocab = [w for w in dict.fromkeys(prefs.get('vocabulary', [])) if w != "Omi"]
        vocabulary = ["Omi"] + user_vocab[:99]
        user_language = prefs.get('language', '') or ''
        single_language_mode = prefs.get('single_language_mode', False)

        req_language = user_language if (single_language_mode and user_language) else 'multi'

        # When single-language mode is active, trust the user's language choice
        # rather than Deepgram's detection (avoids overriding explicit selection).
        use_return_language = not (single_language_mode and user_language)
        words, detected_language = prerecorded(
            url,
            speakers_count=3,
            attempts=0,
            return_language=True,
            language=req_language,
            keywords=vocabulary if vocabulary else None,
        )
        language = user_language if (single_language_mode and user_language) else detected_language
        if not words:
            # DG processed audio successfully but found no speech (silence/noise).
            # Real DG failures now raise RuntimeError and are caught by the except block.
            logger.info(f'No transcript words for segment {path} (silence or noise-only audio)')
            return True
        transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
        if not transcript_segments:
            logger.warning(f'Postprocessing returned empty for segment {path} (words present but no segments)')
            return True

        # Download the segment audio once — used for speaker ID and/or to persist the
        # conversation's audio as a private-cloud chunk (realtime parity, below).
        audio_bytes = _download_audio_bytes(url) if (person_embeddings_cache or private_cloud_sync_enabled) else None
        try:
            identify_speakers_for_segments(
                transcript_segments,
                audio_bytes if person_embeddings_cache else None,
                person_embeddings_cache or {},
                uid,
            )
        except Exception as e:
            logger.warning(f'Speaker ID (sync): identification failed for {path}: {e}')
        finally:
            # Keep audio_bytes for chunk storage when private cloud sync is on; free it now otherwise.
            if audio_bytes is not None and not private_cloud_sync_enabled:
                audio_bytes = None

        # Conversation assignment must happen chronologically across the batch: wait until
        # every earlier-timestamped segment has created/merged its conversation, otherwise
        # the closest-conversation lookup races and adjacent chunks split into separate
        # conversations.
        if turnstile and not turnstile.wait_turn(path):
            logger.warning(f'sync: ordered assignment wait timed out for {path}, proceeding out of order')

        timestamp = get_timestamp_from_path(path)
        segment_end_timestamp = timestamp + transcript_segments[-1].end

        # When a target conversation is specified (auto-sync from live capture),
        # attach segments to it directly instead of searching by timestamp.
        if target_conversation_id:
            closest_memory = conversations_db.get_conversation(uid, target_conversation_id)
            if not closest_memory:
                logger.warning(
                    f'Target conversation {target_conversation_id} not found, falling back to timestamp lookup'
                )
                closest_memory = get_closest_conversation_to_timestamps(uid, timestamp, segment_end_timestamp)
        else:
            closest_memory = get_closest_conversation_to_timestamps(uid, timestamp, segment_end_timestamp)

        if not closest_memory:
            started_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            finished_at = datetime.fromtimestamp(segment_end_timestamp, tz=timezone.utc)
            create_memory = CreateConversation(
                started_at=started_at,
                finished_at=finished_at,
                transcript_segments=transcript_segments,
                source=source,
                is_locked=is_locked,
                private_cloud_sync_enabled=private_cloud_sync_enabled,
            )
            created = process_conversation(uid, language, create_memory)
            with lock:
                response['new_memories'].add(created.id)
            if private_cloud_sync_enabled:
                _store_sync_audio_chunk(uid, created.id, timestamp, audio_bytes, data_protection_level)
        else:

            transcript_segments = [s.model_dump() for s in transcript_segments]

            # assign timestamps to each segment
            for segment in transcript_segments:
                segment['timestamp'] = timestamp + segment['start']
            for segment in closest_memory['transcript_segments']:
                segment['timestamp'] = closest_memory['started_at'].timestamp() + segment['start']

            # Deduplicate: skip new segments whose timestamp range already exists in the conversation
            # (protects against retry after partial failure returning 207)
            existing_timestamps = {
                (round(s['timestamp'], 2), round(s['timestamp'] + (s['end'] - s['start']), 2))
                for s in closest_memory['transcript_segments']
            }
            deduped_segments = []
            for seg in transcript_segments:
                seg_key = (round(seg['timestamp'], 2), round(seg['timestamp'] + (seg['end'] - seg['start']), 2))
                if seg_key not in existing_timestamps:
                    deduped_segments.append(seg)
            if not deduped_segments:
                logger.info(f'All segments already exist in conversation {closest_memory["id"]}, skipping merge')
                with lock:
                    response['updated_memories'].add(closest_memory['id'])
                # No chunk upload here: this segment is a duplicate (retry or overlap with an
                # existing/realtime conversation), so its audio is already represented — uploading
                # again would double the audio in the merge.
                return True

            # merge and sort segments by start timestamp
            segments = closest_memory['transcript_segments'] + deduped_segments
            segments.sort(key=lambda x: x['timestamp'])

            # fix segment.start .end to be relative to the memory
            for i, segment in enumerate(segments):
                duration = segment['end'] - segment['start']
                segment['start'] = segment['timestamp'] - closest_memory['started_at'].timestamp()
                segment['end'] = segment['start'] + duration

            # Calculate new finished_at based on the latest segment
            last_segment_end = segments[-1]['end'] if segments else 0
            new_finished_at = datetime.fromtimestamp(
                closest_memory['started_at'].timestamp() + last_segment_end, tz=timezone.utc
            )

            # Ensure finished_at doesn't go backwards
            if new_finished_at < closest_memory['finished_at']:
                new_finished_at = closest_memory['finished_at']

            # remove timestamp field
            for segment in segments:
                segment.pop('timestamp')

            # save with updated finished_at
            with lock:
                response['updated_memories'].add(closest_memory['id'])
            # Store the chunk before saving segments so "segment present ⇒ chunk present"
            # holds — a retry that dedup-skips this segment won't leave its audio missing.
            # Deterministic chunk path makes the upload overwrite-safe.
            if private_cloud_sync_enabled:
                _store_sync_audio_chunk(uid, closest_memory['id'], timestamp, audio_bytes, data_protection_level)
            update_conversation_segments(uid, closest_memory['id'], segments, finished_at=new_finished_at)

            # Lock existing conversation if credits exhausted
            if is_locked:
                conversations_db.update_conversation(uid, closest_memory['id'], {'is_locked': True})

            # Reprocess if conversation was discarded or if auto-synced WALs added new segments
            if closest_memory.get('discarded', False) or target_conversation_id:
                reason = 'discarded' if closest_memory.get('discarded', False) else 'auto-sync'
                logger.info(f'Conversation {closest_memory["id"]} reprocessing ({reason}) after segment merge')
                _reprocess_conversation_after_update(uid, closest_memory['id'], language)
            else:
                # Summary/structured data is now stale (it predates the merged segments).
                # Record it so the caller reprocesses once per conversation at batch end,
                # instead of once per merged segment.
                with lock:
                    response.setdefault('_merged', {})[closest_memory['id']] = language
        return True
    except Exception as e:
        error_msg = f'Failed to process segment {path}: {e}'
        logger.error(error_msg)
        with lock:
            errors.append(error_msg)
        return False
    finally:
        if turnstile:
            turnstile.complete(path)


def _reprocess_merged_conversations(uid: str, response: dict):
    """Regenerate summary/structured data for conversations that gained segments this batch.

    The merge path in process_segment only appends transcript segments; without this the
    conversation keeps the summary generated from its first chunk only.
    """
    merged = response.pop('_merged', {})
    for conversation_id, language in merged.items():
        try:
            _reprocess_conversation_after_update(uid, conversation_id, language)
        except Exception as e:
            logger.error(f'sync: failed to reprocess merged conversation {conversation_id}: {e}')


def _wav_bytes_to_pcm16_16k(audio_bytes: Optional[bytes]) -> Optional[bytes]:
    """Decode WAV bytes to raw PCM16, 16 kHz mono — the format upload_audio_chunk
    expects (it opus-encodes internally) and the audio merge is hardcoded to."""
    if not audio_bytes:
        return None
    seg = AudioSegment.from_wav(io.BytesIO(audio_bytes))
    seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    return seg.raw_data


def _store_sync_audio_chunk(
    uid: str,
    conversation_id: str,
    timestamp: float,
    audio_bytes: Optional[bytes],
    data_protection_level: Optional[str],
):
    """Persist a sync segment's audio as a private-cloud chunk, identical in format and
    naming to the realtime path (chunks/{uid}/{conversation_id}/{ts}.opus[.enc]), so the
    conversation plays through the existing audio player. Best-effort — audio storage must
    never fail transcription."""
    try:
        pcm = _wav_bytes_to_pcm16_16k(audio_bytes)
        if not pcm:
            return
        upload_audio_chunk(pcm, uid, conversation_id, float(timestamp), data_protection_level)
        del pcm
    except Exception as e:
        logger.warning(f'sync: failed to store audio chunk for {conversation_id}@{timestamp}: {e}')


def _finalize_sync_audio_files(uid: str, response: dict):
    """After all segments are assigned, build audio_files from the uploaded chunks and
    persist them on each conversation — exactly as the realtime flush does — then warm the
    playback artifact. Rebuild+replace is idempotent across retries (create_audio_files_from_chunks
    always rebuilds from the full chunk listing)."""
    conversation_ids = set(response.get('new_memories', set())) | set(response.get('updated_memories', set()))
    for conversation_id in conversation_ids:
        try:
            audio_files = conversations_db.create_audio_files_from_chunks(uid, conversation_id)
            if not audio_files:
                continue
            files_payload = [af.model_dump() for af in audio_files]
            conversations_db.update_conversation(uid, conversation_id, {'audio_files': files_payload})
            precache_conversation_audio(uid, conversation_id, files_payload)
        except Exception as e:
            logger.error(f'sync: failed to finalize audio_files for {conversation_id}: {e}')


def _cleanup_files(file_paths):
    """Helper to clean up temporary files."""
    for path in file_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.error(f"Failed to cleanup file {path}: {e}")


# response_model omitted: deprecated v1 endpoint with mixed dict + JSONResponse returns;
# the v2 typed equivalent (SyncJobStatusResponse) covers the contract.
@router.post("/v1/sync-local-files", deprecated=True)
async def sync_local_files(
    request: Request,
    response: Response,
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.get_current_user_uid),
    conversation_id: str = Query(
        None, description="Target conversation ID to attach audio to (auto-sync from live capture)"
    ),
):
    logger.warning(
        f'sync: deprecated v1 sync-local-files called uid={uid} files={len(files)} '
        f'user_agent={request.headers.get("user-agent", "")}'
    )
    response.headers.update(_V1_DEPRECATION_HEADERS)

    # Pre-check gates (#5854)
    hard_restricted, retry_after = get_hard_restriction_status(uid)
    if hard_restricted:
        raise HTTPException(
            status_code=429,
            detail="Account temporarily restricted due to fair-use policy",
            headers=_hard_restriction_headers(retry_after, _V1_DEPRECATION_HEADERS),
        )

    # Check credits: if exhausted, still process but lock the conversation so user can pay to unlock
    should_lock = not has_transcription_credits(uid)

    # Detect source from filenames
    source = ConversationSource.omi
    for f in files:
        if f.filename and 'limitless' in f.filename.lower():
            source = ConversationSource.limitless
            break

    paths = []
    wav_paths = []
    segmented_paths = set()

    try:
        try:
            paths = retrieve_file_paths(files, uid)
            wav_paths = decode_files_to_wav(paths)
        except HTTPException as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail, headers=_V1_DEPRECATION_HEADERS)

        vad_errors = []

        def _run_vad(path):
            retrieve_vad_segments(path, segmented_paths, vad_errors)

        await asyncio.gather(*[run_blocking(sync_executor, _run_vad, path) for path in wav_paths])

        # Clean up original wav files after VAD segmentation (segments are now in segmented_paths)
        _cleanup_files(wav_paths)
        wav_paths = []  # Clear to avoid double cleanup in finally

        # Check for VAD errors - if any failed, abort to prevent data loss
        if vad_errors:
            error_detail = f"VAD processing failed for {len(vad_errors)} file(s): {'; '.join(vad_errors[:3])}"
            if len(vad_errors) > 3:
                error_detail += f" (and {len(vad_errors) - 3} more)"
            raise HTTPException(status_code=500, detail=error_detail, headers=_V1_DEPRECATION_HEADERS)

        # Fair-use speech tracking from raw VAD segments (#5854)
        # Compute duration from raw segments BEFORE merging (silence gaps not counted)
        total_speech_seconds = sum(get_wav_duration(p) for p in segmented_paths)
        total_speech_ms = int(total_speech_seconds * 1000)
        logger.info(
            f'sync_local_files len(segmented_paths) {len(segmented_paths)} speech_seconds={int(total_speech_seconds)}'
        )

        if FAIR_USE_ENABLED and total_speech_ms > 0:
            record_speech_ms(uid, total_speech_ms, source='sync')
            speech_totals = get_rolling_speech_ms(uid)
            triggered_caps = check_soft_caps(uid, speech_totals=speech_totals)
            if triggered_caps:
                logger.info(f'sync: soft caps triggered for {uid}: {triggered_caps}')
                asyncio.create_task(trigger_classifier_if_needed(uid, triggered_caps))

        is_locked = should_lock

        response = {'updated_memories': set(), 'new_memories': set()}
        segment_errors = []
        segment_lock = threading.Lock()
        total_segments = len(segmented_paths)

        # DG budget gate: throttle cloud STT for restrict-stage users (#6083)
        # Check budget first; only record usage after successful processing.
        dg_budget_blocked = False
        fair_use_restrict_dg = False
        if FAIR_USE_ENABLED:
            try:
                fair_use_stage = get_enforcement_stage(uid)
                if fair_use_stage == 'restrict' and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                    fair_use_restrict_dg = True
                    dg_budget_blocked = is_dg_budget_exhausted(uid)
            except Exception as e:
                logger.error(f'sync: DG budget check error for {uid}: {e}')

        if dg_budget_blocked:
            logger.info(f'sync: DG budget exhausted, skipping {total_segments} segments uid={uid}')
            _cleanup_files(list(segmented_paths))
            return JSONResponse(
                status_code=429,
                headers=_V1_DEPRECATION_HEADERS,
                content={
                    'new_memories': [],
                    'updated_memories': [],
                    'credits_exhausted': should_lock,
                    'dg_budget_exhausted': True,
                    'skipped_segments': total_segments,
                },
            )

        # Fetch user transcription preferences once before spawning threads
        transcription_prefs = await run_blocking(db_executor, users_db.get_user_transcription_preferences, uid)
        private_cloud_sync_enabled = bool(
            await run_blocking(db_executor, users_db.get_user_private_cloud_sync_enabled, uid)
        )
        data_protection_level = (
            await run_blocking(db_executor, users_db.get_data_protection_level, uid)
            if private_cloud_sync_enabled
            else None
        )

        # Build speaker embeddings cache once for all segments (voice + text identification)
        try:
            person_embeddings_cache = await run_blocking(db_executor, build_person_embeddings_cache, uid)
            if person_embeddings_cache:
                logger.info(f'sync: loaded {len(person_embeddings_cache)} person embeddings for speaker ID uid={uid}')
        except Exception as e:
            logger.warning(f'sync: failed to load person embeddings, skipping speaker ID uid={uid}: {e}')
            person_embeddings_cache = {}

        # Chronological order + turnstile: STT runs in parallel, but conversation
        # assignment is serialized oldest-first so adjacent chunks merge instead of
        # racing into separate conversations (#6551, #5747).
        ordered_paths = sorted(segmented_paths, key=get_timestamp_from_path)
        assignment_turnstile = _OrderedTurnstile(ordered_paths)
        await asyncio.gather(
            *[
                run_blocking(
                    sync_executor,
                    process_segment,
                    path,
                    uid,
                    response,
                    segment_lock,
                    segment_errors,
                    source,
                    is_locked,
                    transcription_prefs,
                    person_embeddings_cache,
                    conversation_id,
                    assignment_turnstile,
                    private_cloud_sync_enabled=private_cloud_sync_enabled,
                    data_protection_level=data_protection_level,
                )
                for path in ordered_paths
            ]
        )

        await run_blocking(sync_executor, _reprocess_merged_conversations, uid, response)
        if private_cloud_sync_enabled:
            await run_blocking(sync_executor, _finalize_sync_audio_files, uid, response)

        # Record DG usage after successful processing (not before, to avoid charging on retries)
        if fair_use_restrict_dg:
            try:
                dg_ms = int(total_speech_seconds * 1000)
                if dg_ms > 0:
                    record_dg_usage_ms(uid, dg_ms)
            except Exception as e:
                logger.error(f'sync: DG usage record error for {uid}: {e}')

        # Build JSON-serializable response
        result = {
            'new_memories': sorted(response['new_memories']),
            'updated_memories': sorted(response['updated_memories']),
        }

        failed_segments = len(segment_errors)
        successful_segments = total_segments - failed_segments

        if failed_segments > 0:
            result['failed_segments'] = failed_segments
            result['total_segments'] = total_segments
            result['errors'] = segment_errors[:10]  # Cap error details to avoid huge responses
            logger.error(
                f'sync_local_files partial failure uid={uid} '
                f'success={successful_segments}/{total_segments} errors={segment_errors[:3]}'
            )

        if total_segments > 0 and successful_segments == 0:
            # All segments failed — return 500 (consistent with VAD error behavior)
            raise HTTPException(
                status_code=500,
                detail=f"All {total_segments} segment(s) failed processing: {'; '.join(segment_errors[:3])}",
                headers=_V1_DEPRECATION_HEADERS,
            )

        # Record subscription usage only when at least one segment succeeded
        try:
            usage_seconds = int(total_speech_seconds)
            if usage_seconds > 0:
                record_usage(uid, transcription_seconds=usage_seconds, speech_seconds=usage_seconds)
        except Exception as e:
            logger.error(f'sync: usage record error for {uid}: {e}')

        if failed_segments > 0:
            # Partial failure — return 207 Multi-Status so old clients retry the batch
            return JSONResponse(
                status_code=207,
                headers=_V1_DEPRECATION_HEADERS,
                content=result,
            )

        return result
    finally:
        # Clean up any remaining temporary files
        _cleanup_files(paths)  # .bin files (in case decode_files_to_wav didn't finish)
        _cleanup_files(wav_paths)  # Original wav files (if VAD didn't complete)
        _cleanup_files(segmented_paths)  # Segmented wav files after processing


# ---------------------------------------------------------------------------
# v2 async sync-local-files
# ---------------------------------------------------------------------------
# v1 processes segments synchronously (80-180s for large payloads → 504).
# v2 returns 202 immediately after saving raw files, then runs the full
# pipeline (decode → VAD → fair-use → STT → LLM) in a background thread.
# The app polls GET /v2/sync-local-files/{job_id} until the job reaches
# a terminal status.
# ---------------------------------------------------------------------------


def _retrieve_file_paths_v2(files: List[UploadFile], uid: str, job_id: str):
    """Like retrieve_file_paths but uses a job-specific directory to avoid concurrency conflicts."""
    directory = f'syncing/{uid}/{job_id}/'
    os.makedirs(directory, exist_ok=True)
    paths = []
    for file in files:
        filename = file.filename
        if not filename:
            raise HTTPException(status_code=400, detail='Uploaded file is missing a filename')
        if not filename.endswith('.bin'):
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}")
        if '_' not in filename:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, missing timestamp")
        try:
            timestamp = get_timestamp_from_path(filename)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, invalid timestamp")

        time_val = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if time_val > datetime.now(timezone.utc) or time_val < datetime(2024, 1, 1, tzinfo=timezone.utc):
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, invalid timestamp")

        path = f"{directory}{filename}"
        try:
            with open(path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            paths.append(path)
        except Exception as e:
            if os.path.exists(path):
                os.remove(path)
            raise HTTPException(status_code=500, detail=f"Failed to write file {filename}: {str(e)}")
    return paths


def _get_sync_pipeline_semaphore() -> asyncio.Semaphore:
    """Return a loop-scoped semaphore capping concurrent sync pipelines."""
    return _get_semaphore('sync_pipeline', 16)


async def _run_full_pipeline_background_async(
    job_id: str,
    uid: str,
    raw_paths: list,
    source,
    should_lock: bool,
    job_dir: str,
    target_conversation_id: str = None,
    task_mode: bool = False,
):
    """Async coordinator for the full sync pipeline (decode → VAD → fair-use → STT → LLM).

    Inline dispatch (task_mode=False): runs as a fire-and-forget asyncio task,
    bounded by the per-instance pipeline semaphore; unexpected errors mark the
    job failed (no retry exists).

    Cloud Tasks dispatch (task_mode=True): runs inside the /v2/sync-jobs/run
    request — Cloud Run's containerConcurrency is the concurrency bound, so no
    semaphore; unexpected errors re-raise so the handler can reset the job for
    a queue retry; segments that completed in a prior attempt are skipped via
    the processed-segment ledger.

    All blocking work is offloaded to thread pools via run_blocking(). The
    coordinator itself holds zero thread pool slots — only leaf operations use
    threads, and only for their actual duration.
    """
    concurrency_gate = contextlib.nullcontext() if task_mode else _get_sync_pipeline_semaphore()
    async with concurrency_gate:
        segmented_paths = set()
        wav_paths = []
        stage_timings = {}
        pipeline_start = time.monotonic()
        try:
            await run_blocking(db_executor, mark_job_processing, job_id)

            # --- Phase 1: Decode ---
            await run_blocking(db_executor, update_sync_job, job_id, {'stage': 'decoding'})
            t0 = time.monotonic()
            try:
                wav_paths = await run_blocking(sync_executor, decode_files_to_wav, raw_paths)
            except HTTPException as e:
                await run_blocking(db_executor, mark_job_failed, job_id, f'Decode failed: {e.detail}')
                return
            except Exception as e:
                await run_blocking(db_executor, mark_job_failed, job_id, f'Decode failed: {e}')
                return
            finally:
                await run_blocking(storage_executor, _cleanup_files, raw_paths)
            stage_timings['decode_ms'] = int((time.monotonic() - t0) * 1000)

            if not wav_paths:
                await run_blocking(
                    db_executor,
                    mark_job_completed,
                    job_id,
                    {
                        'new_memories': [],
                        'updated_memories': [],
                        'failed_segments': 0,
                        'total_segments': 0,
                        'errors': [],
                    },
                )
                return

            # --- Phase 2: VAD ---
            await run_blocking(db_executor, update_sync_job, job_id, {'stage': 'vad'})
            t0 = time.monotonic()
            vad_errors = []

            def _run_vad_bg(path):
                try:
                    retrieve_vad_segments(path, segmented_paths, vad_errors)
                except Exception as e:
                    vad_errors.append(f'{path}: {e}')

            vad_tasks = [
                asyncio.wait_for(run_blocking(sync_executor, _run_vad_bg, path), timeout=300) for path in wav_paths
            ]
            vad_results = await asyncio.gather(*vad_tasks, return_exceptions=True)
            for r in vad_results:
                if isinstance(r, asyncio.TimeoutError):
                    vad_errors.append('VAD timed out after 300s')
                elif isinstance(r, Exception):
                    vad_errors.append(f'VAD executor error: {r}')

            stage_timings['vad_ms'] = int((time.monotonic() - t0) * 1000)
            await run_blocking(storage_executor, _cleanup_files, wav_paths)
            wav_paths = []

            if vad_errors:
                error_detail = f'VAD failed for {len(vad_errors)} file(s): {"; ".join(vad_errors[:3])}'
                if len(vad_errors) > 3:
                    error_detail += f' (and {len(vad_errors) - 3} more)'
                await run_blocking(storage_executor, _cleanup_files, list(segmented_paths))
                segmented_paths = set()
                await run_blocking(db_executor, mark_job_failed, job_id, error_detail)
                return

            # --- Phase 3: Speech metrics & fair-use ---
            total_speech_seconds = await run_blocking(
                sync_executor, lambda: sum(get_wav_duration(p) for p in segmented_paths)
            )
            total_speech_ms = int(total_speech_seconds * 1000)
            total_segments = len(segmented_paths)

            await run_blocking(
                db_executor, update_sync_job, job_id, {'total_segments': total_segments, 'stage': 'processing'}
            )

            if total_segments == 0:
                await run_blocking(
                    db_executor,
                    mark_job_completed,
                    job_id,
                    {
                        'new_memories': [],
                        'updated_memories': [],
                        'failed_segments': 0,
                        'total_segments': 0,
                        'errors': [],
                    },
                )
                return

            if FAIR_USE_ENABLED and total_speech_ms > 0:
                # Once-guard: a Cloud Tasks retry must not count the same audio twice
                if await run_blocking(db_executor, try_mark_once, job_id, 'speech_ms'):
                    await run_blocking(db_executor, record_speech_ms, uid, total_speech_ms, source='sync')
                speech_totals = await run_blocking(db_executor, get_rolling_speech_ms, uid)
                triggered_caps = await run_blocking(db_executor, check_soft_caps, uid, speech_totals=speech_totals)
                if triggered_caps:
                    logger.info(f'sync_v2 bg: soft caps triggered for {uid}: {triggered_caps}')
                    try:
                        asyncio.create_task(trigger_classifier_if_needed(uid, triggered_caps))
                    except Exception as e:
                        logger.error(f'sync_v2 bg: classifier scheduling failed for {uid}: {e}')

            # DG budget gate
            fair_use_restrict_dg = False
            if FAIR_USE_ENABLED:
                try:
                    fair_use_stage = await run_blocking(db_executor, get_enforcement_stage, uid)
                    if fair_use_stage == 'restrict' and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                        fair_use_restrict_dg = True
                        if await run_blocking(db_executor, is_dg_budget_exhausted, uid):
                            await run_blocking(storage_executor, _cleanup_files, list(segmented_paths))
                            segmented_paths = set()
                            await run_blocking(
                                db_executor, mark_job_failed, job_id, 'DG budget exhausted — audio retained for retry'
                            )
                            return
                except Exception as e:
                    logger.error(f'sync_v2 bg: DG budget check error for {uid}: {e}')

            is_locked = should_lock

            # --- Phase 4: Fetch prefs & embeddings ---
            transcription_prefs = await run_blocking(db_executor, users_db.get_user_transcription_preferences, uid)
            # Mirror realtime: store conversation audio only when private cloud sync is on.
            private_cloud_sync_enabled = bool(
                await run_blocking(db_executor, users_db.get_user_private_cloud_sync_enabled, uid)
            )
            data_protection_level = (
                await run_blocking(db_executor, users_db.get_data_protection_level, uid)
                if private_cloud_sync_enabled
                else None
            )
            try:
                person_embeddings_cache = await run_blocking(db_executor, build_person_embeddings_cache, uid)
                if person_embeddings_cache:
                    logger.info(f'sync_v2 bg: loaded {len(person_embeddings_cache)} person embeddings uid={uid}')
            except Exception as e:
                logger.warning(f'sync_v2 bg: failed to load person embeddings uid={uid}: {e}')
                person_embeddings_cache = {}

            # --- Phase 5: Process segments (STT + LLM) ---
            await run_blocking(db_executor, update_sync_job, job_id, {'stage': 'stt_llm'})
            t0 = time.monotonic()
            response = {'updated_memories': set(), 'new_memories': set()}
            segment_errors = []
            segment_lock = threading.Lock()

            # Segments that fully landed in a prior Cloud Tasks attempt are skipped
            already_processed = set()
            if task_mode:
                already_processed = await run_blocking(db_executor, get_processed_segments, job_id)
                if already_processed:
                    logger.info(
                        f'sync_v2 bg: job={job_id} skipping {len(already_processed)} '
                        f'segment(s) processed in a prior attempt'
                    )

            # Chronological order + turnstile: STT runs in parallel (per chunk), but
            # conversation assignment is serialized oldest-first so adjacent chunks merge
            # instead of racing into separate conversations (#6551, #5747).
            segment_list = sorted(segmented_paths, key=get_timestamp_from_path)
            assignment_turnstile = _OrderedTurnstile(segment_list)

            def _process_one_segment(path):
                if path in already_processed:
                    # Release the assignment slot — later segments wait on it
                    assignment_turnstile.complete(path)
                    return
                ok = process_segment(
                    path,
                    uid,
                    response,
                    segment_lock,
                    segment_errors,
                    source,
                    is_locked,
                    transcription_prefs,
                    person_embeddings_cache,
                    target_conversation_id,
                    assignment_turnstile,
                    private_cloud_sync_enabled=private_cloud_sync_enabled,
                    data_protection_level=data_protection_level,
                )
                if ok and task_mode:
                    add_processed_segment(job_id, path)

            chunk_size = 5
            for i in range(0, len(segment_list), chunk_size):
                chunk = segment_list[i : i + chunk_size]
                # Later segments in a chunk also wait their assignment turn, so widen
                # their timeout by position to avoid spurious timeouts.
                seg_tasks = [
                    asyncio.wait_for(run_blocking(sync_executor, _process_one_segment, path), timeout=300 + 60 * j)
                    for j, path in enumerate(chunk)
                ]
                seg_results = await asyncio.gather(*seg_tasks, return_exceptions=True)
                for r in seg_results:
                    if isinstance(r, asyncio.TimeoutError):
                        segment_errors.append('Segment timed out after 300s')
                        logger.error(f'sync_v2 bg: segment timed out job={job_id}')
                    elif isinstance(r, Exception):
                        segment_errors.append(f'Segment failed: {sanitize(str(r))}')
                        logger.error(f'sync_v2 bg: segment error: {r}')
                try:
                    await run_blocking(
                        db_executor,
                        update_sync_job,
                        job_id,
                        {'processed_segments': min(i + chunk_size, len(segment_list))},
                    )
                except Exception:
                    pass

            await run_blocking(sync_executor, _reprocess_merged_conversations, uid, response)

            # Persist conversation audio (private-cloud chunks → audio_files) so synced
            # conversations play exactly like realtime ones. Gated on the user's setting.
            if private_cloud_sync_enabled:
                await run_blocking(sync_executor, _finalize_sync_audio_files, uid, response)

            stage_timings['stt_llm_ms'] = int((time.monotonic() - t0) * 1000)

            # Record DG usage after processing
            if fair_use_restrict_dg:
                try:
                    dg_ms = int(total_speech_seconds * 1000)
                    if dg_ms > 0 and await run_blocking(db_executor, try_mark_once, job_id, 'dg_ms'):
                        await run_blocking(db_executor, record_dg_usage_ms, uid, dg_ms)
                except Exception as e:
                    logger.error(f'sync_v2 bg: DG usage record error for {uid}: {e}')

            # Build result
            failed_segments = len(segment_errors)
            successful_segments = total_segments - failed_segments
            result = {
                'new_memories': sorted(response['new_memories']),
                'updated_memories': sorted(response['updated_memories']),
            }
            if failed_segments > 0:
                result['failed_segments'] = failed_segments
                result['total_segments'] = total_segments
                result['errors'] = segment_errors[:10]

            if successful_segments > 0:
                try:
                    usage_seconds = int(total_speech_seconds)
                    if usage_seconds > 0 and await run_blocking(db_executor, try_mark_once, job_id, 'usage'):
                        await run_blocking(
                            db_executor,
                            record_usage,
                            uid,
                            transcription_seconds=usage_seconds,
                            speech_seconds=usage_seconds,
                        )
                except Exception as e:
                    logger.error(f'sync_v2 bg: usage record error for {uid}: {e}')

            stage_timings['total_ms'] = int((time.monotonic() - pipeline_start) * 1000)
            await run_blocking(
                db_executor,
                mark_job_completed,
                job_id,
                {
                    'new_memories': result['new_memories'],
                    'updated_memories': result['updated_memories'],
                    'failed_segments': failed_segments,
                    'total_segments': total_segments,
                    'errors': segment_errors[:10] if segment_errors else [],
                    'stage_timings': stage_timings,
                },
            )

            logger.info(
                f'sync_v2 bg complete job={job_id} uid={uid} '
                f'success={successful_segments}/{total_segments} '
                f'timings={stage_timings}'
            )
        except Exception as e:
            logger.error(f'sync_v2 bg failed job={job_id} uid={uid}: {e}')
            if task_mode:
                # Let the handler decide: queued-reset + Cloud Tasks retry, or
                # final-attempt consume. Marking failed here would be terminal.
                raise
            try:
                await run_blocking(db_executor, mark_job_failed, job_id, str(e))
            except Exception:
                pass
        finally:
            set_byok_keys({})
            await run_blocking(storage_executor, _cleanup_files, list(segmented_paths))
            await run_blocking(storage_executor, _cleanup_files, wav_paths)
            try:
                if job_dir and os.path.isdir(job_dir):
                    await run_blocking(storage_executor, shutil.rmtree, job_dir, True)
            except Exception as e:
                logger.error(f'sync_v2 bg: failed to cleanup job dir {job_dir}: {e}')


def _stage_files_to_gcs(paths: list):
    """Upload raw .bin files to the syncing bucket (blob name = local path)."""
    for p in paths:
        upload_syncing_temporal_file(p)


def _delete_staged_blobs(blob_paths: list):
    for p in blob_paths:
        try:
            delete_syncing_temporal_file(p)
        except Exception as e:
            logger.warning(f'Failed to delete staged blob {p}: {e}')


async def _delete_staged_blobs_async(blob_paths: list):
    await run_blocking(storage_executor, _delete_staged_blobs, blob_paths)


def _download_staged_files(blob_paths: list) -> bool:
    """Download staged blobs back to their local paths. False if any is gone."""
    for p in blob_paths:
        if not download_syncing_temporal_file(p):
            return False
    return True


@router.post("/v2/sync-local-files", status_code=202, response_model=SyncJobStartResponse)
async def sync_local_files_v2(
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.get_current_user_uid),
    conversation_id: str = Query(
        None, description="Target conversation ID to attach audio to (auto-sync from live capture)"
    ),
):
    """
    Async version of sync-local-files. Saves raw files and returns 202
    immediately, then runs the full pipeline (decode → VAD → STT → LLM) as
    an async background task. The app polls GET /v2/sync-local-files/{job_id}.
    """
    # Pre-check gates (same as v1)
    hard_restricted, retry_after = await run_blocking(critical_executor, get_hard_restriction_status, uid)
    if hard_restricted:
        headers = _hard_restriction_headers(retry_after)
        raise HTTPException(
            status_code=429,
            detail="Account temporarily restricted due to fair-use policy",
            headers=headers,
        )

    should_lock = not await run_blocking(critical_executor, has_transcription_credits, uid)

    # Detect source
    source = ConversationSource.omi
    for f in files:
        if f.filename and 'limitless' in f.filename.lower():
            source = ConversationSource.limitless
            break

    # Create job_id early so we have it for the directory
    job_id = str(_uuid.uuid4())
    job_dir = f'syncing/{uid}/{job_id}'

    paths = []

    try:
        # --- Fast path: save raw files only (< 2s typical) ---
        # Use sync_executor, NOT storage_executor — storage is saturated with
        # background pipeline cleanup/GCS work and would queue the 202 response.
        paths = await run_blocking(sync_executor, _retrieve_file_paths_v2, files, uid, job_id)

        # Create Redis job — total_segments=0 until VAD completes in background
        await run_blocking(db_executor, create_sync_job, uid, total_files=len(files), total_segments=0, job_id=job_id)

        # Transfer ownership of raw paths to the background task
        owned_paths = list(paths)
        paths = []  # Prevent finally cleanup of files now owned by bg task

        dispatched = False
        # BYOK keys live only in this request's context and cannot follow a
        # Cloud Task, so BYOK requests always run inline.
        if is_cloud_tasks_dispatch_enabled() and not has_byok_keys():
            try:
                # sync_executor, NOT storage_executor — same reasoning as the
                # file save above (#7372): a saturated storage pool would queue
                # the staging upload and delay the 202.
                await run_blocking(sync_executor, _stage_files_to_gcs, owned_paths)
                await run_blocking(
                    db_executor,
                    enqueue_sync_job,
                    {
                        'schema_version': 1,
                        'job_id': job_id,
                        'uid': uid,
                        'raw_blob_paths': owned_paths,
                        'source': source.value,
                        'should_lock': should_lock,
                        'conversation_id': conversation_id,
                        'enqueued_at': time.time(),
                    },
                )
                dispatched = True
                # The handler instance downloads from GCS; local copies are done
                await run_blocking(sync_executor, _cleanup_files, owned_paths)
                await run_blocking(sync_executor, shutil.rmtree, job_dir, True)
            except Exception as e:
                logger.error(f'sync_v2: Cloud Tasks dispatch failed job={job_id}, falling back inline: {e}')
                start_background_task(_delete_staged_blobs_async(owned_paths), name=f'sync_unstage:{job_id}')

        if not dispatched:
            # Async coordinator: runs on event loop, offloads blocking work to pools.
            # No thread pool slot held for the full pipeline duration (fixes #7361).
            start_background_task(
                _run_full_pipeline_background_async(
                    job_id,
                    uid,
                    owned_paths,
                    source,
                    should_lock,
                    job_dir,
                    conversation_id,
                ),
                name=f'sync_pipeline:{job_id}',
            )

        return JSONResponse(
            status_code=202,
            content={
                'job_id': job_id,
                'status': 'queued',
                'total_files': len(files),
                'total_segments': 0,
                'poll_after_ms': 3000,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'sync_v2 fast-path failed uid={uid}: {e}')
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _cleanup_files(paths)


@router.get("/v2/sync-local-files/{job_id}", response_model=SyncJobStatusResponse, response_model_exclude_none=True)
def get_sync_job_status(job_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Poll for the status of an async sync job."""
    job = get_sync_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found or expired")
    if job['uid'] != uid:
        raise HTTPException(status_code=403, detail="Not authorized to view this sync job")

    # Build response — include result only when terminal
    resp = {
        'job_id': job['job_id'],
        'status': job['status'],
        'total_segments': job.get('total_segments', 0),
        'processed_segments': job.get('processed_segments', 0),
        'successful_segments': job.get('successful_segments', 0),
        'failed_segments': job.get('failed_segments', 0),
    }

    if job['status'] in ('completed', 'partial_failure', 'failed'):
        if job.get('result'):
            resp['result'] = job['result']
        if job.get('error'):
            resp['error'] = job['error']

    return resp


# response_model omitted: include_in_schema=False Cloud Tasks handler; JSONResponse status
# codes (200/409/500) drive the queue protocol, not a typed client-facing body.
@router.post("/v2/sync-jobs/run", include_in_schema=False)
async def run_sync_job(request: Request, task_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    """Cloud Tasks handler: runs one sync job inside the request.

    Auth is the Cloud Tasks OIDC token (verify_cloud_tasks_oidc), not Firebase.
    Response semantics drive the queue: 2xx consumes the task, 409 while the
    run-lock is held retries later, 500 retries with backoff.

    Idempotency: a per-job Redis run-lock serializes concurrent deliveries;
    terminal jobs are acked without re-running; segments completed by a prior
    attempt are skipped via the processed-segment ledger inside the pipeline.
    """
    try:
        payload = await request.json()
        job_id = payload['job_id']
        uid = payload['uid']
        blob_paths = list(payload['raw_blob_paths'])
        source = ConversationSource(payload.get('source') or 'omi')
        should_lock = bool(payload.get('should_lock', False))
        conversation_id = payload.get('conversation_id')
    except Exception as e:
        # A malformed payload will not fix itself on retry — consume it.
        logger.error(f'sync job handler: invalid payload, dropping task: {e}')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

    # Fail-closed lock: Redis errors propagate → 500 → Cloud Tasks retries later.
    lock_token = await run_blocking(db_executor, try_acquire_job_run_lock, job_id)
    if not lock_token:
        logger.warning(f'sync job {job_id}: run-lock held by another attempt, deferring')
        return JSONResponse(status_code=409, content={'status': 'locked'})

    try:
        job = await run_blocking(db_executor, get_sync_job, job_id)
        if not job:
            # Job TTL (24h) expired before dispatch — staged blobs are gone or
            # about to be (1-day lifecycle); the app re-uploads on 404.
            logger.warning(f'sync job {job_id}: job expired before dispatch, dropping task')
            await _delete_staged_blobs_async(blob_paths)
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'job_expired'})

        if job['status'] in TERMINAL_STATUSES:
            # Duplicate delivery, stale-detector-failed job, or a prior attempt
            # that finished. Never re-run terminal jobs — the app may already be
            # re-uploading these files as a new job.
            await _delete_staged_blobs_async(blob_paths)
            return JSONResponse(status_code=200, content={'status': 'acked', 'job_status': job['status']})

        if not await run_blocking(storage_executor, _download_staged_files, blob_paths):
            # Blobs deleted by the bucket's 1-day lifecycle (deep queue backlog).
            await run_blocking(db_executor, mark_job_failed, job_id, 'Staged audio expired before processing')
            await _delete_staged_blobs_async(blob_paths)
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'staged_audio_expired'})

        job_dir = f'syncing/{uid}/{job_id}'
        try:
            await _run_full_pipeline_background_async(
                job_id,
                uid,
                blob_paths,
                source,
                should_lock,
                job_dir,
                conversation_id,
                task_mode=True,
            )
        except Exception as e:
            max_attempts = get_sync_tasks_max_attempts()
            if task_retry_count >= max_attempts - 1:
                logger.error(f'sync job {job_id}: final attempt {task_retry_count + 1} failed, consuming: {e}')
                await run_blocking(db_executor, mark_job_failed, job_id, f'Failed after {max_attempts} attempts: {e}')
                await _delete_staged_blobs_async(blob_paths)
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            # Reset to 'queued' so the stale detector cannot terminally fail the
            # job while the Cloud Tasks retry backoff elapses. Blobs are kept.
            logger.warning(f'sync job {job_id}: attempt {task_retry_count + 1} failed, will retry: {e}')
            await run_blocking(db_executor, mark_job_queued_for_retry, job_id, task_retry_count + 1, str(e))
            return JSONResponse(status_code=500, content={'status': 'retry'})

        # Pipeline returned normally: completed, or it marked the job failed
        # itself (decode/VAD/DG-budget) — terminal either way, staging is done.
        await _delete_staged_blobs_async(blob_paths)
        return JSONResponse(status_code=200, content={'status': 'done'})
    finally:
        await run_blocking(db_executor, release_job_run_lock, job_id, lock_token)


# response_model omitted: include_in_schema=False Cloud Tasks handler; JSONResponse status
# codes (200/409/500) drive the queue protocol, not a typed client-facing body.
@router.post("/v2/audio-merge-jobs/run", include_in_schema=False)
async def run_audio_merge_job(request: Request, task_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    """Cloud Tasks handler: build one playback MP3 artifact inside the request.

    Response semantics drive the queue: 2xx consumes the task, 409 while the
    run-lock is held retries later, 500 retries with backoff. Idempotency:
    named tasks dedupe enqueues, the run-lock serializes duplicate deliveries,
    and an existing artifact is acked without rebuilding.
    """
    try:
        payload = await request.json()
        uid = payload['uid']
        conversation_id = payload['conversation_id']
        audio_file_id = payload['audio_file_id']
        timestamps = list(payload['timestamps'])
    except Exception as e:
        logger.error(f'audio_merge handler: invalid payload, dropping task: {e}')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

    lock_key = f'audio:{conversation_id}:{audio_file_id}'
    lock_token = await run_blocking(db_executor, try_acquire_job_run_lock, lock_key)
    if not lock_token:
        return JSONResponse(status_code=409, content={'status': 'locked'})

    try:
        existing = await run_blocking(
            storage_executor, get_playback_artifact_signed_url, uid, conversation_id, audio_file_id
        )
        if existing:
            return JSONResponse(status_code=200, content={'status': 'exists'})

        try:
            mp3_data = await run_blocking(
                sync_executor, sync_playback.build_playback_artifact, uid, conversation_id, timestamps
            )
        except FileNotFoundError:
            logger.warning(f'audio_merge: chunks missing conv={conversation_id} file={audio_file_id}, dropping')
            # Persist the verdict or /urls reports pending forever and clients
            # poll to exhaustion (named-task tombstones block re-enqueues too)
            await run_blocking(
                storage_executor, mark_playback_unavailable, uid, conversation_id, audio_file_id, 'chunks_missing'
            )
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'chunks_missing'})
        except Exception as e:
            max_attempts = get_sync_tasks_max_attempts()
            if task_retry_count >= max_attempts - 1:
                logger.error(f'audio_merge_failed_final conv={conversation_id} file={audio_file_id}: {e}')
                # Same pending-forever trap as chunks_missing: a consumed task
                # leaves a tombstone that blocks re-enqueue. Mark unavailable so
                # clients stop polling; the 30-day lifecycle grants a retry.
                await run_blocking(
                    storage_executor, mark_playback_unavailable, uid, conversation_id, audio_file_id, 'merge_failed'
                )
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            logger.warning(
                f'audio_merge: attempt {task_retry_count + 1} failed conv={conversation_id} '
                f'file={audio_file_id}, will retry: {e}'
            )
            return JSONResponse(status_code=500, content={'status': 'retry'})

        if not mp3_data:
            logger.warning(f'audio_merge: no audio data conv={conversation_id} file={audio_file_id}, dropping')
            await run_blocking(
                storage_executor, mark_playback_unavailable, uid, conversation_id, audio_file_id, 'empty_audio'
            )
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'empty_audio'})

        await run_blocking(storage_executor, upload_playback_artifact, uid, conversation_id, audio_file_id, mp3_data)
        logger.info(f'audio_merge: built artifact conv={conversation_id} file={audio_file_id} size={len(mp3_data)}')
        return JSONResponse(status_code=200, content={'status': 'done'})
    finally:
        await run_blocking(db_executor, release_job_run_lock, lock_key, lock_token)

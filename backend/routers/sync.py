import asyncio
import contextlib
import io
import logging
import os
import re
import shutil
import struct
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
    postprocess_executor,
    storage_executor,
    sync_executor,
    run_blocking,
    start_background_task,
    submit_with_context,
)

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Header, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from opuslib import Decoder
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
    download_audio_chunks_and_merge,
    get_or_create_merged_audio,
    get_merged_audio_signed_url,
    get_playback_artifact_signed_url,
    download_playback_artifact,
    upload_playback_artifact,
    enqueue_conversation_audio_merge,
    _PRECACHE_FILE_SEM,
)

from utils import encryption
from utils.byok import get_byok_keys, set_byok_keys, has_byok_keys
from utils.cloud_tasks import (
    enqueue_sync_job,
    get_sync_tasks_max_attempts,
    is_audio_merge_dispatch_enabled,
    is_cloud_tasks_dispatch_enabled,
    verify_cloud_tasks_oidc,
)
from utils.http_client import _get_semaphore
from utils.log_sanitizer import sanitize
from utils.stt.pre_recorded import postprocess_words, prerecorded
from utils.stt.vad import vad_is_empty
from utils.fair_use import (
    record_speech_ms,
    get_rolling_speech_ms,
    check_soft_caps,
    is_hard_restricted,
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


# **********************************************
# ******** AUDIO FORMAT CONVERSION *************
# **********************************************


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Convert raw PCM data to WAV format."""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    """
    Parse HTTP Range header and return (start, end) tuple.
    Returns None if the range is invalid.

    Example: "bytes=0-1023" -> (0, 1023)
    """
    if not range_header:
        return None

    try:
        # Parse "bytes=start-end" format
        if not range_header.startswith("bytes="):
            return None

        range_spec = range_header[6:]
        parts = range_spec.split("-")

        if len(parts) != 2:
            return None

        start_str, end_str = parts

        # Handle "bytes=start-" (from start to end of file)
        if start_str and not end_str:
            start = int(start_str)
            end = file_size - 1
        # Handle "bytes=-suffix" (last N bytes)
        elif not start_str and end_str:
            suffix_length = int(end_str)
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        # Handle "bytes=start-end"
        else:
            start = int(start_str)
            end = int(end_str)

        # RFC 7233: start must be valid, end can exceed file size and gets clamped
        if start < 0 or start >= file_size or start > end:
            return None
        end = min(end, file_size - 1)
        return (start, end)
    except (ValueError, IndexError):
        return None


# **********************************************
# ********** AUDIO PRE-CACHING *****************
# **********************************************


def _precache_audio_file(
    uid: str, conversation_id: str, audio_file: dict, fill_gaps: bool = True, caller: str = 'precache_endpoint'
):
    """Pre-cache a single audio file."""
    try:
        audio_file_id = audio_file.get('id')
        timestamps = audio_file.get('chunk_timestamps')
        if not audio_file_id or not timestamps:
            return

        get_or_create_merged_audio(
            uid=uid,
            conversation_id=conversation_id,
            audio_file_id=audio_file_id,
            timestamps=timestamps,
            pcm_to_wav_func=pcm_to_wav,
            fill_gaps=fill_gaps,
            sample_rate=AUDIO_SAMPLE_RATE,
            caller=caller,
        )
    except Exception as e:
        logger.error(f"Error pre-caching audio file {audio_file.get('id')}: {e}")


@router.post("/v1/sync/audio/{conversation_id}/precache", tags=['v1'])
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

    audio_files = conversation.get('audio_files', [])
    if not audio_files:
        return {"status": "no_audio", "message": "No audio files in conversation"}

    if is_audio_merge_dispatch_enabled():
        enqueue_conversation_audio_merge(uid, conversation_id, audio_files, caller='precache_endpoint')
        return {"status": "started", "audio_file_count": len(audio_files)}

    # Start background parallel pre-caching with bounded concurrency (#7387)
    def _precache_all_parallel():
        logger.info(f"Pre-caching all {len(audio_files)} audio files for conversation {conversation_id} (parallel)")
        futures = []
        for af in audio_files:
            _PRECACHE_FILE_SEM.acquire()
            try:
                f = submit_with_context(
                    storage_executor, _precache_audio_file, uid, conversation_id, af, caller='precache_endpoint'
                )
                f.add_done_callback(lambda _: _PRECACHE_FILE_SEM.release())
                futures.append(f)
            except Exception:
                _PRECACHE_FILE_SEM.release()
                raise
        for future in futures:
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error in parallel precache: {e}")
        logger.info(f"Completed pre-cache for conversation {conversation_id}")

    submit_with_context(postprocess_executor, _precache_all_parallel)

    return {"status": "started", "audio_file_count": len(audio_files)}


AUDIO_URLS_POLL_AFTER_MS = 3000


def _get_audio_urls_via_artifacts(uid: str, conversation_id: str, audio_files: list) -> dict:
    """Artifact-backed /urls: a pure metadata read that never merges in-request.

    Cached = a playback MP3 artifact (or legacy unexpired WAV cache) exists.
    Everything else is reported pending and enqueued as an audio-merge task
    (named-task deduped); the app polls until cached.
    """
    result = []
    to_enqueue = []
    for af in audio_files:
        audio_file_id = af.get('id')
        if not audio_file_id:
            continue

        signed_url = get_playback_artifact_signed_url(uid, conversation_id, audio_file_id)
        content_type = 'audio/mpeg' if signed_url else None
        if not signed_url:
            signed_url = get_merged_audio_signed_url(uid, conversation_id, audio_file_id)
            content_type = 'audio/wav' if signed_url else None

        if signed_url:
            result.append(
                {
                    "id": audio_file_id,
                    "status": "cached",
                    "signed_url": signed_url,
                    "content_type": content_type,
                    "duration": af.get('duration', 0),
                }
            )
        else:
            result.append(
                {
                    "id": audio_file_id,
                    "status": "pending",
                    "signed_url": None,
                    "duration": af.get('duration', 0),
                }
            )
            to_enqueue.append(af)

    if to_enqueue:
        enqueue_conversation_audio_merge(uid, conversation_id, to_enqueue, caller='sync_urls')

    return {
        "audio_files": result,
        "poll_after_ms": AUDIO_URLS_POLL_AFTER_MS if to_enqueue else None,
    }


@router.get("/v1/sync/audio/{conversation_id}/urls", tags=['v1'])
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

    audio_files = conversation.get('audio_files', [])
    if not audio_files:
        return {"audio_files": []}

    if is_audio_merge_dispatch_enabled():
        return _get_audio_urls_via_artifacts(uid, conversation_id, audio_files)

    result = []
    uncached_files = []
    first_uncached_handled = False

    for af in audio_files:
        audio_file_id = af.get('id')
        if not audio_file_id:
            continue

        signed_url = get_merged_audio_signed_url(uid, conversation_id, audio_file_id)

        if signed_url:
            result.append(
                {
                    "id": audio_file_id,
                    "status": "cached",
                    "signed_url": signed_url,
                    "duration": af.get('duration', 0),
                }
            )
        else:
            # First uncached file: cache synchronously for immediate playback
            if not first_uncached_handled:
                first_uncached_handled = True
                _precache_audio_file(uid, conversation_id, af, caller='sync_urls_first')
                # Get signed URL after caching
                signed_url = get_merged_audio_signed_url(uid, conversation_id, audio_file_id)
                if signed_url:
                    result.append(
                        {
                            "id": audio_file_id,
                            "status": "cached",
                            "signed_url": signed_url,
                            "duration": af.get('duration', 0),
                        }
                    )
                else:
                    # Cache failed, return pending
                    result.append(
                        {
                            "id": audio_file_id,
                            "status": "pending",
                            "signed_url": None,
                            "duration": af.get('duration', 0),
                        }
                    )
            else:
                result.append(
                    {
                        "id": audio_file_id,
                        "status": "pending",
                        "signed_url": None,
                        "duration": af.get('duration', 0),
                    }
                )
                uncached_files.append(af)

    # Cache remaining files in background
    if uncached_files:

        def _cache_uncached_parallel():
            futures = []
            for af in uncached_files:
                _PRECACHE_FILE_SEM.acquire()
                try:
                    f = submit_with_context(
                        storage_executor, _precache_audio_file, uid, conversation_id, af, caller='sync_urls_bg'
                    )
                    f.add_done_callback(lambda _: _PRECACHE_FILE_SEM.release())
                    futures.append(f)
                except Exception:
                    _PRECACHE_FILE_SEM.release()
                    raise
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error in parallel cache: {e}")

        submit_with_context(postprocess_executor, _cache_uncached_parallel)

    return {"audio_files": result}


# **********************************************
# ********** AUDIO DOWNLOAD ENDPOINT ***********
# **********************************************


@router.get("/v1/sync/audio/{conversation_id}/{audio_file_id}", tags=['v1'])
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

    # Get audio data - use cache if available, otherwise merge and cache
    try:
        if not audio_file.get('chunk_timestamps'):
            raise HTTPException(status_code=500, detail="Audio file has no chunk timestamps")

        if format == "wav" and is_audio_merge_dispatch_enabled():
            # Artifact-backed mode: serve only prebuilt audio, never merge
            # in-request. On miss, enqueue the merge task and tell the client
            # to poll /urls (old app versions hit this path uncached and get
            # a fast 202 instead of the inline merge that used to time out).
            audio_data = download_playback_artifact(uid, conversation_id, audio_file_id)
            if audio_data is not None:
                content_type = "audio/mpeg"
                extension = "mp3"
            else:
                legacy_url = get_merged_audio_signed_url(uid, conversation_id, audio_file_id)
                if legacy_url:
                    audio_data, _ = get_or_create_merged_audio(
                        uid=uid,
                        conversation_id=conversation_id,
                        audio_file_id=audio_file_id,
                        timestamps=audio_file['chunk_timestamps'],
                        pcm_to_wav_func=pcm_to_wav,
                        fill_gaps=True,
                        sample_rate=AUDIO_SAMPLE_RATE,
                        caller='sync_download_legacy_cache',
                    )
                    content_type = "audio/wav"
                    extension = "wav"
                else:
                    enqueue_conversation_audio_merge(uid, conversation_id, [audio_file], caller='sync_download')
                    return JSONResponse(
                        status_code=202,
                        content={"status": "pending", "poll_after_ms": AUDIO_URLS_POLL_AFTER_MS},
                    )
        elif format == "wav":
            audio_data, was_cached = get_or_create_merged_audio(
                uid=uid,
                conversation_id=conversation_id,
                audio_file_id=audio_file_id,
                timestamps=audio_file['chunk_timestamps'],
                pcm_to_wav_func=pcm_to_wav,
                fill_gaps=True,
                sample_rate=AUDIO_SAMPLE_RATE,
                caller='sync_download',
            )
            content_type = "audio/wav"
            extension = "wav"
        else:
            audio_data = download_audio_chunks_and_merge(
                uid, conversation_id, audio_file['chunk_timestamps'], fill_gaps=True, sample_rate=AUDIO_SAMPLE_RATE
            )
            content_type = "application/octet-stream"
            extension = "pcm"
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio chunks not found in storage")
    except Exception as e:
        logger.error(f"Error downloading audio file: {e}")
        raise HTTPException(status_code=500, detail="Failed to download audio file")

    # Create descriptive filename
    filename = f"conversation_{conversation_id}_audio_{audio_file_id}.{extension}"
    file_size = len(audio_data)

    base_headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=3600",
    }

    range_header = request.headers.get("Range")

    if range_header:
        # Parse the range request
        range_tuple = parse_range_header(range_header, file_size)

        if range_tuple is None:
            return Response(
                status_code=416,
                headers={
                    "Content-Range": f"bytes */{file_size}",
                    **base_headers,
                },
            )

        start, end = range_tuple
        content_length = end - start + 1

        # Return partial content
        return StreamingResponse(
            io.BytesIO(audio_data[start : end + 1]),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Length": str(content_length),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                **base_headers,
            },
        )

    return StreamingResponse(
        io.BytesIO(audio_data),
        status_code=200,
        media_type=content_type,
        headers={
            "Content-Length": str(file_size),
            **base_headers,
        },
    )


# **********************************************
# ************ SYNC LOCAL FILES ****************
# **********************************************


def decode_opus_file_to_wav(opus_file_path, wav_file_path, sample_rate=16000, channels=1, frame_size: int = 160):
    """Decode an Opus file with length-prefixed frames to WAV format.

    Writes directly to WAV file to avoid accumulating all PCM data in memory.
    """
    if not os.path.exists(opus_file_path):
        logger.warning(f"File not found: {sanitize(opus_file_path)}")
        return False

    decoder = Decoder(sample_rate, channels)
    frame_count = 0

    try:
        with open(opus_file_path, 'rb') as f, wave.open(wav_file_path, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)  # 16-bit audio
            wav_file.setframerate(sample_rate)

            while True:
                length_bytes = f.read(4)
                if not length_bytes:
                    logger.info("End of file reached.")
                    break
                if len(length_bytes) < 4:
                    logger.info("Incomplete length prefix at the end of the file.")
                    break

                frame_length = struct.unpack('<I', length_bytes)[0]
                opus_data = f.read(frame_length)
                if len(opus_data) < frame_length:
                    logger.error(f"Unexpected end of file at frame {frame_count}.")
                    break
                try:
                    pcm_frame = decoder.decode(opus_data, frame_size=frame_size)
                    wav_file.writeframes(pcm_frame)  # Write directly to file
                    frame_count += 1
                except Exception as e:
                    logger.error(f"Error decoding frame {frame_count}: {e}")
                    # Skip this frame instead of breaking the entire decode loop
                    continue

        if frame_count > 0:
            logger.info(f"Decoded audio saved to {sanitize(wav_file_path)}")
            return True
        else:
            logger.info("No PCM data was decoded.")
            # Clean up empty/invalid wav file
            if os.path.exists(wav_file_path):
                os.remove(wav_file_path)
            return False
    except Exception as e:
        logger.error(f"Error during decode: {e}")
        # Clean up on error
        if os.path.exists(wav_file_path):
            os.remove(wav_file_path)
        return False


def get_timestamp_from_path(path: str):
    timestamp = int(path.split('/')[-1].split('_')[-1].split('.')[0])
    if timestamp > 1e10:
        return int(timestamp / 1000)
    return timestamp


def retrieve_file_paths(files: List[UploadFile], uid: str):
    directory = f'syncing/{uid}/'
    os.makedirs(directory, exist_ok=True)
    paths = []
    for file in files:
        filename = file.filename
        # Validate the file is .bin and contains a _$timestamp.bin, if not, 400 bad request
        if not filename.endswith('.bin'):
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}")
        if '_' not in filename:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, missing timestamp")
        try:
            timestamp = get_timestamp_from_path(filename)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, invalid timestamp")

        time = datetime.fromtimestamp(timestamp)
        if time > datetime.now() or time < datetime(2024, 1, 1):
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


def get_wav_duration(wav_path: str) -> float:
    """Get WAV file duration without loading entire file into memory."""
    try:
        with wave.open(wav_path, 'rb') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return frames / float(rate)
    except Exception as e:
        logger.error(f"Error reading WAV duration: {e}")
        return 0.0


def decode_pcm_file_to_wav(pcm_file_path, wav_file_path, sample_rate=16000, channels=1, sample_width=2):
    """Decode a length-prefixed PCM .bin file to WAV.

    The file format is: [4-byte uint32 frame_length][frame_bytes] repeated.
    Each frame contains raw PCM samples (no encoding).
    sample_width: 2 for pcm16, 1 for pcm8.
    """
    try:
        pcm_data = bytearray()
        with open(pcm_file_path, 'rb') as f:
            while True:
                length_bytes = f.read(4)
                if not length_bytes or len(length_bytes) < 4:
                    break
                frame_length = struct.unpack('<I', length_bytes)[0]
                if frame_length == 0 or frame_length > 65536:
                    logger.warning(f"PCM decode: suspicious frame length {frame_length}, skipping rest")
                    break
                frame_data = f.read(frame_length)
                if len(frame_data) < frame_length:
                    break
                pcm_data.extend(frame_data)

        if not pcm_data:
            logger.info(f"PCM decode: no data in {pcm_file_path}")
            return False

        wav_data = pcm_to_wav(bytes(pcm_data), sample_rate=sample_rate, channels=channels, sample_width=sample_width)
        with open(wav_file_path, 'wb') as f:
            f.write(wav_data)
        return True
    except Exception as e:
        logger.error(f"PCM decode failed for {pcm_file_path}: {e}")
        return False


def _is_pcm_codec(filename: str) -> bool:
    """Check if the filename indicates a PCM codec (pcm8 or pcm16)."""
    return '_pcm16_' in filename or '_pcm8_' in filename


def decode_files_to_wav(files_path: List[str]):
    wav_files = []
    for path in files_path:
        wav_path = path.replace('.bin', '.wav')
        filename = os.path.basename(path)
        frame_size = 160  # Default frame size
        match = re.search(r'_fs(\d+)', filename)
        if match:
            try:
                frame_size = int(match.group(1))
                logger.info(f"Found frame size {frame_size} in filename: {filename}")
            except ValueError:
                logger.error(f"Invalid frame size format in filename: {filename}, using default {frame_size}")

        # Detect codec from filename: PCM files need different decoding than Opus
        if _is_pcm_codec(filename):
            # Parse sample rate from filename: audio_{device}_{codec}_{sampleRate}_{channel}_...
            sample_rate_match = re.search(r'_pcm(?:8|16)_(\d+)_', filename)
            sample_rate = (
                int(sample_rate_match.group(1)) if sample_rate_match else (16000 if '_pcm16_' in filename else 8000)
            )
            sample_width = 1 if '_pcm8_' in filename else 2
            success = decode_pcm_file_to_wav(path, wav_path, sample_rate=sample_rate, sample_width=sample_width)
        else:
            success = decode_opus_file_to_wav(path, wav_path, frame_size=frame_size)

        if not success:
            # Clean up .bin file even on decode failure
            if os.path.exists(path):
                os.remove(path)
            continue

        # Always remove .bin file after decode attempt
        if os.path.exists(path):
            os.remove(path)

        # Check duration without loading entire file into memory
        duration = get_wav_duration(wav_path)
        if duration == 0:
            # Invalid WAV file
            if os.path.exists(wav_path):
                os.remove(wav_path)
            raise HTTPException(status_code=400, detail=f"Invalid file format {path}")

        if duration < 1:
            os.remove(wav_path)
            continue
        wav_files.append(wav_path)
    return wav_files


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

    segments = []
    # should we merge more aggressively, to avoid too many small segments? ~ not for now
    # Pros -> lesser segments, faster, less concurrency
    # Cons -> less accuracy.

    # edge case, multiple small segments that map towards the same memory .-.
    # so ... let's merge them if distance < 120 seconds
    # a better option would be to keep here 1s, and merge them like that after transcribing
    # but FAL has 10 RPS limit, **let's merge it here for simplicity for now**

    for i, segment in enumerate(voice_segments):
        if segments and (segment['start'] - segments[-1]['end']) < 120:
            segments[-1]['end'] = segment['end']
        else:
            segments.append(segment)

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

        # Speaker identification: voice embedding matching + text-based detection
        audio_bytes = _download_audio_bytes(url) if person_embeddings_cache else None
        try:
            identify_speakers_for_segments(transcript_segments, audio_bytes, person_embeddings_cache or {}, uid)
        except Exception as e:
            logger.warning(f'Speaker ID (sync): identification failed for {path}: {e}')
        finally:
            if audio_bytes:
                del audio_bytes

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
            )
            created = process_conversation(uid, language, create_memory)
            with lock:
                response['new_memories'].add(created.id)
        else:

            transcript_segments = [s.dict() for s in transcript_segments]

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


def _cleanup_files(file_paths):
    """Helper to clean up temporary files."""
    for path in file_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.error(f"Failed to cleanup file {path}: {e}")


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
    if is_hard_restricted(uid):
        raise HTTPException(
            status_code=429,
            detail="Account temporarily restricted due to fair-use policy",
            headers=_V1_DEPRECATION_HEADERS,
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
                )
                for path in ordered_paths
            ]
        )

        await run_blocking(sync_executor, _reprocess_merged_conversations, uid, response)

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
        if not filename.endswith('.bin'):
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}")
        if '_' not in filename:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, missing timestamp")
        try:
            timestamp = get_timestamp_from_path(filename)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, invalid timestamp")

        time_val = datetime.fromtimestamp(timestamp)
        if time_val > datetime.now() or time_val < datetime(2024, 1, 1):
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


@router.post("/v2/sync-local-files")
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
    if await run_blocking(critical_executor, is_hard_restricted, uid):
        raise HTTPException(status_code=429, detail="Account temporarily restricted due to fair-use policy")

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


@router.get("/v2/sync-local-files/{job_id}")
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


def _build_playback_artifact(uid: str, conversation_id: str, timestamps: list) -> bytes:
    """Merge chunks (download → decrypt → decode → gap-fill) and encode MP3 ~48kbps mono."""
    pcm_data = download_audio_chunks_and_merge(
        uid, conversation_id, timestamps, fill_gaps=True, sample_rate=AUDIO_SAMPLE_RATE
    )
    if not pcm_data:
        return b''
    segment = AudioSegment(data=pcm_data, sample_width=2, frame_rate=AUDIO_SAMPLE_RATE, channels=1)
    del pcm_data
    buf = io.BytesIO()
    segment.export(buf, format='mp3', bitrate='48k')
    return buf.getvalue()


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
            mp3_data = await run_blocking(sync_executor, _build_playback_artifact, uid, conversation_id, timestamps)
        except FileNotFoundError:
            logger.warning(f'audio_merge: chunks missing conv={conversation_id} file={audio_file_id}, dropping')
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'chunks_missing'})
        except Exception as e:
            max_attempts = get_sync_tasks_max_attempts()
            if task_retry_count >= max_attempts - 1:
                logger.error(f'audio_merge_failed_final conv={conversation_id} file={audio_file_id}: {e}')
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            logger.warning(
                f'audio_merge: attempt {task_retry_count + 1} failed conv={conversation_id} '
                f'file={audio_file_id}, will retry: {e}'
            )
            return JSONResponse(status_code=500, content={'status': 'retry'})

        if not mp3_data:
            logger.warning(f'audio_merge: no audio data conv={conversation_id} file={audio_file_id}, dropping')
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'empty_audio'})

        await run_blocking(storage_executor, upload_playback_artifact, uid, conversation_id, audio_file_id, mp3_data)
        logger.info(f'audio_merge: built artifact conv={conversation_id} file={audio_file_id} size={len(mp3_data)}')
        return JSONResponse(status_code=200, content={'status': 'done'})
    finally:
        await run_blocking(db_executor, release_job_run_lock, lock_key, lock_token)

import asyncio
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
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import httpx

from utils.executors import critical_executor, storage_executor

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Header, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from opuslib import Decoder
from pydub import AudioSegment

from database import conversations as conversations_db
from database import users as users_db
from database.conversations import get_closest_conversation_to_timestamps, update_conversation_segments
from database.sync_jobs import (
    create_sync_job,
    get_sync_job,
    update_sync_job,
    mark_job_processing,
    mark_job_completed,
    mark_job_failed,
)
from models.conversation import Conversation, CreateConversation
from models.conversation_enums import ConversationSource
from utils.conversations.factory import deserialize_conversation
from models.transcript_segment import TranscriptSegment
from utils.conversations.process_conversation import process_conversation
from utils.other import endpoints as auth
from utils.other.storage import (
    get_syncing_file_temporal_signed_url,
    delete_syncing_temporal_file,
    download_audio_chunks_and_merge,
    get_or_create_merged_audio,
    get_merged_audio_signed_url,
)

from utils import encryption
from utils.log_sanitizer import sanitize
from utils.stt.pre_recorded import deepgram_prerecorded, get_deepgram_model_for_language, postprocess_words
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


def _precache_audio_file(uid: str, conversation_id: str, audio_file: dict, fill_gaps: bool = True):
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
        )
        logger.info(f"Pre-cached audio file: {audio_file_id}")
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

    # Start background parallel pre-caching for all audio files using storage_executor
    def _precache_all_parallel():
        logger.info(f"Pre-caching all {len(audio_files)} audio files for conversation {conversation_id} (parallel)")
        futures = [storage_executor.submit(_precache_audio_file, uid, conversation_id, af) for af in audio_files]
        for future in futures:
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error in parallel precache: {e}")
        logger.info(f"Completed pre-cache for conversation {conversation_id}")

    critical_executor.submit(_precache_all_parallel)

    return {"status": "started", "audio_file_count": len(audio_files)}


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
                _precache_audio_file(uid, conversation_id, af)
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
            futures = [storage_executor.submit(_precache_audio_file, uid, conversation_id, af) for af in uncached_files]
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error in parallel cache: {e}")

        critical_executor.submit(_cache_uncached_parallel)

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

        if format == "wav":
            audio_data, was_cached = get_or_create_merged_audio(
                uid=uid,
                conversation_id=conversation_id,
                audio_file_id=audio_file_id,
                timestamps=audio_file['chunk_timestamps'],
                pcm_to_wav_func=pcm_to_wav,
                fill_gaps=True,
                sample_rate=AUDIO_SAMPLE_RATE,
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
                    break

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
):
    try:
        url = get_syncing_file_temporal_signed_url(path)

        def delete_file():
            time.sleep(480)
            delete_syncing_temporal_file(path)

        storage_executor.submit(delete_file)

        # Apply user transcription preferences (vocabulary, language, model)
        prefs = transcription_prefs or {}
        user_vocab = [w for w in dict.fromkeys(prefs.get('vocabulary', [])) if w != "Omi"]
        vocabulary = ["Omi"] + user_vocab[:99]
        user_language = prefs.get('language', '') or ''
        single_language_mode = prefs.get('single_language_mode', False)

        if single_language_mode and user_language:
            dg_language, dg_model = get_deepgram_model_for_language(user_language)
        else:
            dg_language, dg_model = get_deepgram_model_for_language('multi')

        # When single-language mode is active, trust the user's language choice
        # rather than Deepgram's detection (avoids overriding explicit selection).
        use_return_language = not (single_language_mode and user_language)
        words, detected_language = deepgram_prerecorded(
            url,
            speakers_count=3,
            attempts=0,
            return_language=True,
            language=dg_language,
            model=dg_model,
            keywords=vocabulary if vocabulary else None,
        )
        language = user_language if (single_language_mode and user_language) else detected_language
        if not words:
            # DG processed audio successfully but found no speech (silence/noise).
            # Real DG failures now raise RuntimeError and are caught by the except block.
            logger.info(f'No transcript words for segment {path} (silence or noise-only audio)')
            return
        transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
        if not transcript_segments:
            logger.warning(f'Postprocessing returned empty for segment {path} (words present but no segments)')
            return

        # Speaker identification: voice embedding matching + text-based detection
        audio_bytes = _download_audio_bytes(url) if person_embeddings_cache else None
        try:
            identify_speakers_for_segments(transcript_segments, audio_bytes, person_embeddings_cache or {}, uid)
        except Exception as e:
            logger.warning(f'Speaker ID (sync): identification failed for {path}: {e}')
        finally:
            if audio_bytes:
                del audio_bytes

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
                return

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
    except Exception as e:
        error_msg = f'Failed to process segment {path}: {e}'
        logger.error(error_msg)
        with lock:
            errors.append(error_msg)


def _cleanup_files(file_paths):
    """Helper to clean up temporary files."""
    for path in file_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.error(f"Failed to cleanup file {path}: {e}")


@router.post("/v1/sync-local-files")
async def sync_local_files(
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.get_current_user_uid),
    conversation_id: str = Query(
        None, description="Target conversation ID to attach audio to (auto-sync from live capture)"
    ),
):
    # Pre-check gates (#5854)
    if is_hard_restricted(uid):
        raise HTTPException(status_code=429, detail="Account temporarily restricted due to fair-use policy")

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
        paths = retrieve_file_paths(files, uid)
        wav_paths = decode_files_to_wav(paths)

        vad_errors = []

        def _run_vad(path):
            retrieve_vad_segments(path, segmented_paths, vad_errors)

        loop = asyncio.get_running_loop()
        await asyncio.gather(*[loop.run_in_executor(critical_executor, _run_vad, path) for path in wav_paths])

        # Clean up original wav files after VAD segmentation (segments are now in segmented_paths)
        _cleanup_files(wav_paths)
        wav_paths = []  # Clear to avoid double cleanup in finally

        # Check for VAD errors - if any failed, abort to prevent data loss
        if vad_errors:
            error_detail = f"VAD processing failed for {len(vad_errors)} file(s): {'; '.join(vad_errors[:3])}"
            if len(vad_errors) > 3:
                error_detail += f" (and {len(vad_errors) - 3} more)"
            raise HTTPException(status_code=500, detail=error_detail)

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
                content={
                    'new_memories': [],
                    'updated_memories': [],
                    'credits_exhausted': should_lock,
                    'dg_budget_exhausted': True,
                    'skipped_segments': total_segments,
                },
            )

        # Fetch user transcription preferences once before spawning threads
        transcription_prefs = users_db.get_user_transcription_preferences(uid)

        # Build speaker embeddings cache once for all segments (voice + text identification)
        try:
            person_embeddings_cache = build_person_embeddings_cache(uid)
            if person_embeddings_cache:
                logger.info(f'sync: loaded {len(person_embeddings_cache)} person embeddings for speaker ID uid={uid}')
        except Exception as e:
            logger.warning(f'sync: failed to load person embeddings, skipping speaker ID uid={uid}: {e}')
            person_embeddings_cache = {}

        await asyncio.gather(
            *[
                loop.run_in_executor(
                    critical_executor,
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
                )
                for path in segmented_paths
            ]
        )

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
            )

        if failed_segments > 0:
            # Partial failure — return 207 Multi-Status so old clients retry the batch
            return JSONResponse(status_code=207, content=result)

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
# v2 does the fast path (decode, VAD) inline, then hands off STT+LLM to a
# background thread. The app polls GET /v2/sync-local-files/{job_id} until
# the job reaches a terminal status.
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


def _process_segments_background(
    job_id: str,
    uid: str,
    segmented_paths: list,
    source,
    is_locked: bool,
    fair_use_restrict_dg: bool,
    total_speech_seconds: float,
    job_dir: str,
    transcription_prefs: Optional[dict] = None,
    person_embeddings_cache: Optional[Dict[str, dict]] = None,
    target_conversation_id: str = None,
):
    """Background worker: runs segment processing and updates Redis job status."""
    try:
        mark_job_processing(job_id)

        response = {'updated_memories': set(), 'new_memories': set()}
        segment_errors = []
        segment_lock = threading.Lock()
        total_segments = len(segmented_paths)

        def _process_one_segment(path):
            process_segment(
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
            )

        # Process in chunks of 5, with heartbeat after each chunk
        chunk_size = 5
        segment_list = list(segmented_paths)
        for i in range(0, len(segment_list), chunk_size):
            chunk = segment_list[i : i + chunk_size]
            futures = [critical_executor.submit(_process_one_segment, path) for path in chunk]
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error processing segment: {e}")
            # Heartbeat: refresh updated_at so stale detection doesn't kill active jobs
            try:
                update_sync_job(job_id, {'processed_segments': min(i + chunk_size, len(segment_list))})
            except Exception:
                pass  # Non-fatal: stale detection is a safety net, not a hard gate

        # Record DG usage after processing (not before, to avoid charging on retries)
        if fair_use_restrict_dg:
            try:
                dg_ms = int(total_speech_seconds * 1000)
                if dg_ms > 0:
                    record_dg_usage_ms(uid, dg_ms)
            except Exception as e:
                logger.error(f'sync_v2: DG usage record error for {uid}: {e}')

        # Build result matching v1 response shape
        failed_segments = len(segment_errors)
        result = {
            'new_memories': sorted(response['new_memories']),
            'updated_memories': sorted(response['updated_memories']),
        }
        if failed_segments > 0:
            result['failed_segments'] = failed_segments
            result['total_segments'] = total_segments
            result['errors'] = segment_errors[:10]

        mark_job_completed(
            job_id,
            {
                'new_memories': result['new_memories'],
                'updated_memories': result['updated_memories'],
                'failed_segments': failed_segments,
                'total_segments': total_segments,
                'errors': segment_errors[:10] if segment_errors else [],
            },
        )

        logger.info(
            f'sync_v2 background complete job={job_id} uid={uid} '
            f'success={total_segments - failed_segments}/{total_segments}'
        )
    except Exception as e:
        logger.error(f'sync_v2 background failed job={job_id} uid={uid}: {e}')
        try:
            mark_job_failed(job_id, str(e))
        except Exception:
            pass
    finally:
        # Clean up segmented wav files
        _cleanup_files(list(segmented_paths))
        # Clean up job directory
        try:
            if job_dir and os.path.isdir(job_dir):
                shutil.rmtree(job_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f'sync_v2: failed to cleanup job dir {job_dir}: {e}')


@router.post("/v2/sync-local-files")
async def sync_local_files_v2(
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.get_current_user_uid),
    conversation_id: str = Query(
        None, description="Target conversation ID to attach audio to (auto-sync from live capture)"
    ),
):
    """
    Async version of sync-local-files. Does fast-path work (decode, VAD) inline,
    then starts background processing and returns 202 with a job_id for polling.
    """
    # Pre-check gates (same as v1)
    if is_hard_restricted(uid):
        raise HTTPException(status_code=429, detail="Account temporarily restricted due to fair-use policy")

    should_lock = not has_transcription_credits(uid)

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
    wav_paths = []
    segmented_paths = set()

    try:
        # --- Fast path (inline, <5s typically) ---
        paths = _retrieve_file_paths_v2(files, uid, job_id)
        wav_paths = decode_files_to_wav(paths)

        vad_errors = []

        def _run_vad_v2(path):
            retrieve_vad_segments(path, segmented_paths, vad_errors)

        loop_v2 = asyncio.get_running_loop()
        await asyncio.gather(*[loop_v2.run_in_executor(critical_executor, _run_vad_v2, path) for path in wav_paths])

        _cleanup_files(wav_paths)
        wav_paths = []

        if vad_errors:
            error_detail = f"VAD processing failed for {len(vad_errors)} file(s): {'; '.join(vad_errors[:3])}"
            if len(vad_errors) > 3:
                error_detail += f" (and {len(vad_errors) - 3} more)"
            raise HTTPException(status_code=500, detail=error_detail)

        # Fair-use speech tracking
        total_speech_seconds = sum(get_wav_duration(p) for p in segmented_paths)
        total_speech_ms = int(total_speech_seconds * 1000)

        if FAIR_USE_ENABLED and total_speech_ms > 0:
            record_speech_ms(uid, total_speech_ms, source='sync')
            speech_totals = get_rolling_speech_ms(uid)
            triggered_caps = check_soft_caps(uid, speech_totals=speech_totals)
            if triggered_caps:
                logger.info(f'sync_v2: soft caps triggered for {uid}: {triggered_caps}')
                asyncio.create_task(trigger_classifier_if_needed(uid, triggered_caps))

        # DG budget gate
        fair_use_restrict_dg = False
        if FAIR_USE_ENABLED:
            try:
                fair_use_stage = get_enforcement_stage(uid)
                if fair_use_stage == 'restrict' and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                    fair_use_restrict_dg = True
                    if is_dg_budget_exhausted(uid):
                        _cleanup_files(list(segmented_paths))
                        return JSONResponse(
                            status_code=429,
                            content={
                                'dg_budget_exhausted': True,
                                'skipped_segments': len(segmented_paths),
                            },
                        )
            except Exception as e:
                logger.error(f'sync_v2: DG budget check error for {uid}: {e}')

        total_segments = len(segmented_paths)

        if total_segments == 0:
            # Nothing to process — return completed immediately
            return JSONResponse(
                status_code=200,
                content={
                    'new_memories': [],
                    'updated_memories': [],
                },
            )

        # --- Create Redis job and start background thread ---
        job = create_sync_job(uid, total_files=len(files), total_segments=total_segments, job_id=job_id)

        # Fetch user transcription preferences once before spawning background thread
        transcription_prefs = users_db.get_user_transcription_preferences(uid)

        # Build speaker embeddings cache once for all segments (voice + text identification)
        try:
            person_embeddings_cache = build_person_embeddings_cache(uid)
            if person_embeddings_cache:
                logger.info(
                    f'sync_v2: loaded {len(person_embeddings_cache)} person embeddings for speaker ID uid={uid}'
                )
        except Exception as e:
            logger.warning(f'sync_v2: failed to load person embeddings, skipping speaker ID uid={uid}: {e}')
            person_embeddings_cache = {}

        # Transfer ownership of segmented_paths to the background thread
        owned_paths = list(segmented_paths)
        segmented_paths = set()  # Prevent finally cleanup of files now owned by bg thread

        # Run in default executor (not critical_executor) because _process_segments_background
        # is a coordinator that submits child tasks to critical_executor — nesting both
        # in the same pool causes deadlock under concurrent load.
        loop_v2.run_in_executor(
            None,
            _process_segments_background,
            job_id,
            uid,
            owned_paths,
            source,
            should_lock,
            fair_use_restrict_dg,
            total_speech_seconds,
            job_dir,
            transcription_prefs,
            person_embeddings_cache,
            conversation_id,
        )

        return JSONResponse(
            status_code=202,
            content={
                'job_id': job_id,
                'status': 'queued',
                'total_files': len(files),
                'total_segments': total_segments,
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
        _cleanup_files(wav_paths)
        _cleanup_files(list(segmented_paths))


@router.get("/v2/sync-local-files/{job_id}")
async def get_sync_job_status(job_id: str, uid: str = Depends(auth.get_current_user_uid)):
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

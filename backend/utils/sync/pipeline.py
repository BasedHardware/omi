"""Sync local-files pipeline: decode → VAD → fair-use → STT → conversation merge.

Extracted from routers/sync.py so the router stays thin and utils never imports routers.
"""

# pyright: reportPrivateUsage=false, reportUnusedFunction=false, reportUnusedVariable=false, reportUnnecessaryComparison=false, reportAssignmentType=false, reportIndexIssue=false, reportArgumentType=false

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
import shutil
import threading
import time
import wave
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx
import numpy as np
from fastapi import HTTPException, UploadFile
from pydub import AudioSegment

from database import conversations as conversations_db
from database import users as users_db
from database.conversations import get_closest_conversation_to_timestamps, update_conversation_segments
from database.sync_jobs import (
    add_processed_segment,
    get_processed_segments,
    mark_job_completed,
    mark_job_failed,
    mark_job_processing,
    try_mark_once,
    update_sync_job,
)
from models.conversation import CreateConversation
from models.conversation_enums import ConversationSource
from models.transcript_segment import TranscriptSegment
from utils.analytics import record_usage
from utils.byok import get_byok_keys, set_byok_keys, set_byok_uid
from utils.conversations.factory import deserialize_conversation
from utils.conversations.process_conversation import process_conversation
from utils.executors import db_executor, run_blocking, storage_executor, sync_executor
from utils.fair_use import (
    FAIR_USE_ENABLED,
    FAIR_USE_RESTRICT_DAILY_DG_MS,
    check_soft_caps,
    get_enforcement_stage,
    get_rolling_speech_ms,
    is_dg_budget_exhausted,
    record_dg_usage_ms,
    record_speech_ms,
    trigger_classifier_if_needed,
)
from utils.http_client import _get_semaphore
from utils.log_sanitizer import sanitize
from utils.other.storage import (
    delete_syncing_temporal_file,
    download_syncing_temporal_file,
    get_syncing_file_temporal_signed_url,
    precache_conversation_audio,
    schedule_syncing_temporal_file_deletion,
    upload_audio_chunk,
    upload_syncing_temporal_file,
)
from utils.speaker_assignment import process_speaker_assigned_segments
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.pre_recorded import postprocess_words, prerecorded
from utils.stt.speaker_embedding import (
    SPEAKER_MATCH_THRESHOLD,
    compare_embeddings,
    extract_embedding_from_bytes,
)
from utils.stt.vad import vad_is_empty
from utils.sync.files import decode_files_to_wav, get_timestamp_from_path, get_wav_duration

logger = logging.getLogger(__name__)

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
        set_byok_uid(uid if get_byok_keys() else None)
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
            set_byok_uid(None)
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

import asyncio
import io
import re
import wave
from typing import List, Optional, Dict, Tuple
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import av
import numpy as np

from database import conversations as conversations_db
from database import users as users_db
from utils.other.storage import (
    download_audio_chunks_and_merge,
    upload_person_speech_sample_from_bytes,
)
from utils.speaker_sample import verify_and_transcribe_sample
from utils.speaker_sample_migration import maybe_migrate_person_samples
from utils.stt.speaker_embedding import extract_embedding_from_bytes
from utils.speaker_identification_hybrid import detect_speaker_hybrid, _detect_from_regex

logger = logging.getLogger(__name__)

# Constants for speaker sample extraction
SPEAKER_SAMPLE_MIN_SEGMENT_DURATION = 10.0
SPEAKER_SAMPLE_WINDOW_HALF = SPEAKER_SAMPLE_MIN_SEGMENT_DURATION / 2

# Shared executor for sync-to-async bridging to avoid overhead
_executor = ThreadPoolExecutor(max_workers=4)

def _pcm_to_wav_bytes(pcm_data: bytes, sample_rate: int) -> bytes:
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return wav_buffer.getvalue()

def _trim_pcm_audio(pcm_data: bytes, sample_rate: int, start_sec: float, end_sec: float) -> bytes:
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    wav_buffer.seek(0)

    trimmed_samples = []
    with av.open(wav_buffer, mode='r') as container:
        stream = container.streams.audio[0]
        for frame in container.decode(stream):
            if frame.pts is None: continue
            frame_time = float(frame.pts * stream.time_base)
            frame_duration = frame.samples / sample_rate
            frame_end_time = frame_time + frame_duration
            if frame_end_time <= start_sec: continue
            if frame_time >= end_sec: break
            arr = frame.to_ndarray()
            if arr.ndim == 2: arr = arr[0]
            frame_start_sample = 0
            frame_end_sample = len(arr)
            if frame_time < start_sec:
                frame_start_sample = int((start_sec - frame_time) * sample_rate)
            if frame_end_time > end_sec:
                frame_end_sample = frame_start_sample + int((end_sec - max(frame_time, start_sec)) * sample_rate)
            if frame_start_sample < frame_end_sample:
                trimmed_samples.append(arr[frame_start_sample:frame_end_sample])

    if not trimmed_samples: return b''
    return np.concatenate(trimmed_samples).astype(np.int16).tobytes()

async def detect_speaker_from_text_async(text: str, language: str = 'en') -> Optional[str]:
    """
    Detect speaker name from text using the Hybrid Identification Engine (Async).
    Now fully delegates to the hybrid engine in speaker_identification_hybrid.
    """
    return await detect_speaker_hybrid(text, language)

def detect_speaker_from_text(text: str, language: str = 'en') -> Optional[str]:
    """
    Synchronous wrapper for detect_speaker_from_text_async.
    Used for legacy compatibility in threads and tests.
    Optimized to handle event loop bridging correctly.
    """
    # Try Stage 1 (Regex) sync first for performance and to avoid event loop overhead
    name = _detect_from_regex(text, language)
    if name:
        return name
    
    # Try full hybrid (LLM/NER stage) if regex failed
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
            
        if loop and loop.is_running():
            # Already in a loop - bridging to a new loop in a background thread
            # to avoid blocking the main event loop while waiting for LLM
            def _run_in_new_loop():
                new_loop = asyncio.new_event_loop()
                try:
                    return new_loop.run_until_complete(detect_speaker_hybrid(text, language))
                finally:
                    new_loop.close()
            return _executor.submit(_run_in_new_loop).result()
        
        # In a plain thread (e.g. background script) without a running loop
        return asyncio.run(detect_speaker_hybrid(text, language))
    except Exception as e:
        logger.debug(f"Hybrid speaker ID fallback failed: {e}")
        return None

async def extract_speaker_samples(
    uid: str, person_id: str, conversation_id: str, segment_ids: List[str], sample_rate: int = 16000,
):
    try:
        person = users_db.get_person(uid, person_id)
        if person:
            person = await maybe_migrate_person_samples(uid, person)

        sample_count = users_db.get_person_speech_samples_count(uid, person_id)
        if sample_count >= 1:
            logger.warning(f"Person {person_id} already has {sample_count} samples, skipping {uid} {conversation_id}")
            return

        conversation = conversations_db.get_conversation(uid, conversation_id)
        if not conversation: return

        started_at = conversation.get('started_at')
        if not started_at: return
        started_at_ts = started_at.timestamp() if hasattr(started_at, 'timestamp') else float(started_at)

        conv_segments = conversation.get('transcript_segments', [])
        segment_map = {s.get('id'): s for s in conv_segments if s.get('id')}
        audio_files = conversation.get('audio_files', [])
        if not audio_files: return

        all_timestamps = []
        for af in audio_files:
            timestamps = af.get('chunk_timestamps', [])
            all_timestamps.extend(timestamps)

        if not all_timestamps: return
        chunks = [{'timestamp': ts} for ts in sorted(set(all_timestamps))]
        samples_added = 0
        max_samples_to_add = 1 - sample_count
        ordered_segments = [s for s in conv_segments if s.get('id')]
        segment_index_map = {s.get('id'): i for i, s in enumerate(ordered_segments)}

        for seg_id in segment_ids:
            if samples_added >= max_samples_to_add: break
            seg = segment_map.get(seg_id)
            if not seg: continue

            segment_start = seg.get('start')
            segment_end = seg.get('end')
            if segment_start is None or segment_end is None: continue
            seg_duration = segment_end - segment_start
            speaker_id = seg.get('speaker_id')

            if seg_duration < SPEAKER_SAMPLE_MIN_SEGMENT_DURATION and speaker_id is not None:
                seg_idx = segment_index_map.get(seg_id)
                if seg_idx is not None:
                    i = seg_idx - 1
                    while i >= 0:
                        prev_seg = ordered_segments[i]
                        if prev_seg.get('speaker_id') != speaker_id: break
                        prev_start = prev_seg.get('start')
                        if prev_start is not None:
                            segment_start = min(segment_start, prev_start)
                            seg_duration = segment_end - segment_start
                        if seg_duration >= SPEAKER_SAMPLE_MIN_SEGMENT_DURATION: break
                        i -= 1

            if seg_duration < SPEAKER_SAMPLE_MIN_SEGMENT_DURATION: continue

            seg_center = (segment_start + segment_end) / 2
            sample_start = max(segment_start, seg_center - SPEAKER_SAMPLE_WINDOW_HALF)
            sample_end = min(segment_end, seg_center + SPEAKER_SAMPLE_WINDOW_HALF)
            abs_start = started_at_ts + sample_start
            abs_end = started_at_ts + sample_end
            sorted_chunks = sorted(chunks, key=lambda c: c['timestamp'])
            first_idx = 0
            for i, chunk in enumerate(sorted_chunks):
                if chunk['timestamp'] <= abs_start: first_idx = i
                else: break
            relevant_timestamps = []
            for chunk in sorted_chunks[first_idx:]:
                if chunk['timestamp'] <= abs_end: relevant_timestamps.append(chunk['timestamp'])
                else: break

            if not relevant_timestamps: continue
            merged = await asyncio.to_thread(download_audio_chunks_and_merge, uid, conversation_id, relevant_timestamps, fill_gaps=True, sample_rate=sample_rate)
            buffer_start = min(relevant_timestamps)
            trim_start = abs_start - buffer_start
            trim_end = abs_end - buffer_start
            sample_audio = _trim_pcm_audio(merged, sample_rate, trim_start, trim_end)

            min_sample_bytes = int(sample_rate * 8.0 * 2)
            if len(sample_audio) < min_sample_bytes: continue

            expected_text = seg.get('text', '')
            wav_bytes = _pcm_to_wav_bytes(sample_audio, sample_rate)
            transcript, is_valid, reason = await verify_and_transcribe_sample(wav_bytes, sample_rate, expected_text)
            if not is_valid: continue

            path = await asyncio.to_thread(upload_person_speech_sample_from_bytes, sample_audio, uid, person_id, sample_rate)
            success = users_db.add_person_speech_sample(uid, person_id, path, transcript=transcript)
            if success:
                samples_added += 1
                try:
                    embedding = await asyncio.to_thread(extract_embedding_from_bytes, wav_bytes, "sample.wav")
                    embedding_list = embedding.flatten().tolist()
                    users_db.set_person_speaker_embedding(uid, person_id, embedding_list)
                except Exception: pass
            else: break
    except Exception as e:
        logger.error(f"Error extracting speaker samples: {e}")

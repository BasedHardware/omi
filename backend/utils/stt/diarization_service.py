"""
Diarization Refinement Service

Orchestrates the async refinement of speaker diarization using Pyannote.
Integrates with Modal for GPU processing and handles status tracking.

Flow:
1. Conversation completes with Deepgram diarization
2. Backend calls trigger_diarization_refinement()
3. Modal function processes audio with Pyannote on GPU
4. Results update the conversation transcript
"""

import asyncio
import logging
import os
from enum import Enum
from typing import List, Optional

from utils.other.storage import get_conversation_recording_signed_url
import database.conversations as conversations_db

logger = logging.getLogger(__name__)


class DiarizationStatus(str, Enum):
    """Status of diarization refinement for a conversation."""

    NOT_STARTED = "not_started"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # No audio available or too short


async def trigger_diarization_refinement(
    uid: str,
    conversation_id: str,
    transcript_segments: List[dict],
    num_speakers: Optional[int] = None,
    force: bool = False,
) -> DiarizationStatus:
    """
    Trigger async diarization refinement for a conversation.

    This is called after Deepgram transcription completes. It:
    1. Checks if audio is available
    2. Spawns Modal function for Pyannote processing
    3. Returns immediately (non-blocking)
    4. Modal will call back when complete

    Args:
        uid: User ID
        conversation_id: Conversation/memory ID
        transcript_segments: Deepgram transcript segments
        num_speakers: Optional speaker count hint
        force: Force refinement even if already processed

    Returns:
        DiarizationStatus indicating if refinement was triggered
    """
    try:
        # Check if we have audio for this conversation
        audio_url = await asyncio.to_thread(get_conversation_recording_signed_url, uid, conversation_id)
        if not audio_url:
            logger.info(f"[{conversation_id}] No audio recording available, skipping diarization refinement")
            return DiarizationStatus.SKIPPED

        # Extract words from transcript segments for Pyannote
        words = _extract_words_from_segments(transcript_segments)
        if not words:
            logger.info(f"[{conversation_id}] No words in transcript, skipping diarization refinement")
            return DiarizationStatus.SKIPPED

        # Detect number of speakers if not provided
        if num_speakers is None:
            speakers = set()
            for seg in transcript_segments:
                if seg.get('speaker'):
                    speakers.add(seg['speaker'])
            num_speakers = len(speakers) if speakers else None

        # Prepare Deepgram result for Modal
        dg_result = {"words": words, "num_speakers": num_speakers}

        # Spawn Modal function (non-blocking)
        logger.info(f"[{conversation_id}] Triggering Pyannote refinement (speakers: {num_speakers})")

        # Import Modal client
        try:
            from modal import Function

            refine_fn = Function.lookup("pyannote-diarization", "refine_diarization")

            # Spawn async - returns immediately
            refine_fn.spawn(
                recording_id=conversation_id, audio_url=audio_url, dg_result=dg_result, num_speakers=num_speakers
            )

            return DiarizationStatus.PENDING

        except Exception as modal_error:
            logger.error(f"[{conversation_id}] Failed to spawn Modal function: {modal_error}")
            # Fall back to sync processing if Modal unavailable
            return await _fallback_local_refinement(uid, conversation_id, audio_url, dg_result, num_speakers)

    except Exception as e:
        logger.error(f"[{conversation_id}] Error triggering diarization refinement: {e}")
        return DiarizationStatus.FAILED


def process_diarization_result(uid: str, recording_id: str, result: dict) -> bool:
    """
    Process the result from Modal diarization function.

    Called via webhook or polling when Modal completes.

    Args:
        uid: User ID
        recording_id: Conversation ID
        result: Modal function result with refined words

    Returns:
        True if successfully updated, False otherwise
    """
    try:
        if result.get("status") != "success":
            logger.error(f"[{recording_id}] Diarization failed: {result.get('error')}")
            return False

        refined_words = result.get("words", [])
        if not refined_words:
            logger.warning(f"[{recording_id}] No refined words returned")
            return False

        # Convert words back to transcript segments
        segments = _words_to_transcript_segments(refined_words)

        # Update conversation in database
        conversations_db.update_conversation(
            uid=uid,
            conversation_id=recording_id,
            update_data={'transcript_segments': segments, 'diarization_refined': True},
        )

        logger.info(f"[{recording_id}] Diarization refinement complete, updated {len(segments)} segments")
        return True

    except Exception as e:
        logger.error(f"[{recording_id}] Error processing diarization result: {e}")
        return False


def _extract_words_from_segments(segments: List[dict]) -> List[dict]:
    """
    Extract word-level data from transcript segments.

    Segments may be sentence-level, so we need to handle both cases.
    """
    words = []

    for seg in segments:
        # Check if segment has word-level data
        if 'words' in seg and isinstance(seg['words'], list):
            for word in seg['words']:
                words.append(
                    {
                        'start': word.get('start', seg.get('start', 0)),
                        'end': word.get('end', seg.get('end', 0)),
                        'text': word.get('text', word.get('word', '')),
                        'speaker': seg.get('speaker', 'SPEAKER_0'),
                    }
                )
        else:
            # Segment-level only - treat whole segment as one unit
            words.append(
                {
                    'start': seg.get('start', 0),
                    'end': seg.get('end', 0),
                    'text': seg.get('text', ''),
                    'speaker': seg.get('speaker', 'SPEAKER_0'),
                }
            )

    return words


def _words_to_transcript_segments(words: List[dict]) -> List[dict]:
    """
    Convert word-level data back to transcript segments.

    Groups consecutive words by speaker into segments.
    """
    if not words:
        return []

    segments = []
    current_segment = {
        'speaker': words[0].get('speaker', 'SPEAKER_0'),
        'start': words[0]['start'],
        'end': words[0]['end'],
        'text': words[0].get('text', ''),
        'is_user': False,
        'person_id': None,
    }

    for word in words[1:]:
        word_speaker = word.get('speaker', 'SPEAKER_0')

        if word_speaker == current_segment['speaker']:
            # Same speaker - extend segment
            current_segment['end'] = word['end']
            current_segment['text'] += ' ' + word.get('text', '')
        else:
            # Speaker change - save current and start new
            current_segment['text'] = current_segment['text'].strip()
            segments.append(current_segment)

            current_segment = {
                'speaker': word_speaker,
                'start': word['start'],
                'end': word['end'],
                'text': word.get('text', ''),
                'is_user': False,
                'person_id': None,
            }

    # Don't forget last segment
    current_segment['text'] = current_segment['text'].strip()
    segments.append(current_segment)

    return segments


async def _fallback_local_refinement(
    uid: str, conversation_id: str, audio_url: str, dg_result: dict, num_speakers: Optional[int]
) -> DiarizationStatus:
    """
    Fallback to local/cloud Pyannote if Modal is unavailable.

    Uses pyannote.ai cloud API or local processing.
    All blocking I/O is wrapped in asyncio.to_thread to avoid blocking the event loop.
    """
    try:
        from utils.stt.pyannote_diarization import pyannote_diarize_cloud, merge_with_transcript

        # Try cloud API first
        api_key = os.environ.get('PYANNOTE_API_KEY')
        if api_key:
            logger.info(f"[{conversation_id}] Falling back to Pyannote cloud API")

            # Download audio to temp file (blocking I/O - run in thread)
            import tempfile
            import requests

            def _download_and_save():
                response = requests.get(audio_url, timeout=300)
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(response.content)
                    return f.name

            audio_path = await asyncio.to_thread(_download_and_save)

            try:
                # Cloud API call is blocking - run in thread
                segments = await asyncio.to_thread(
                    pyannote_diarize_cloud,
                    audio_path,
                    api_key,
                    None,  # webhook_url
                    2.0,  # poll_interval
                    300.0,  # timeout
                    num_speakers,
                )

                if segments:
                    refined_words = merge_with_transcript(words=dg_result['words'], diarization_segments=segments)

                    # Update conversation (sync function, run in thread)
                    await asyncio.to_thread(
                        process_diarization_result, uid, conversation_id, {"status": "success", "words": refined_words}
                    )

                    return DiarizationStatus.COMPLETED

            finally:
                if os.path.exists(audio_path):
                    os.remove(audio_path)

        logger.warning(f"[{conversation_id}] No fallback available, keeping Deepgram diarization")
        return DiarizationStatus.SKIPPED

    except Exception as e:
        logger.error(f"[{conversation_id}] Fallback refinement failed: {e}")
        return DiarizationStatus.FAILED


# Sync wrapper for non-async contexts
def trigger_diarization_refinement_sync(
    uid: str,
    conversation_id: str,
    transcript_segments: List[dict],
    num_speakers: Optional[int] = None,
    force: bool = False,
) -> DiarizationStatus:
    """Synchronous wrapper for trigger_diarization_refinement."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(
        trigger_diarization_refinement(uid, conversation_id, transcript_segments, num_speakers, force)
    )

"""Orphaned WAV retranscription pipeline (client upload path removed).

Historically reached via ``POST /v1/memories/{id}/post-processing`` and a Flutter
``memoryPostProcessing`` upload. That router was commented out (2024-09) and
deleted (2025-05); no ``backend/routers`` caller remains. Short uploads were an
app-side buffer bug (``createWavFile(removeLastNSeconds=120)`` on quiet-timer
memory creation), not backend truncation — see module ARCHITECTURE.md.

Keep the transcript-relative duration guard if this util is ever rewired.
"""

import asyncio
import os
import time
from typing import List

from utils.executors import storage_executor

from pydub import AudioSegment

import database.conversations as conversations_db
from database.users import get_user_store_recording_permission
from models.conversation import Conversation
from models.conversation_enums import PostProcessingStatus
from utils.conversations.factory import deserialize_conversation
from utils.conversations import lifecycle as lifecycle_service
from models.transcript_segment import TranscriptSegment
from utils.conversations.process_conversation import process_conversation, process_user_emotion
from utils.other.storage import upload_postprocessing_audio, delete_postprocessing_audio, upload_conversation_recording
from utils.stt.pre_recorded import postprocess_words, prerecorded
from utils.stt.speech_profile import get_speech_profile_matching_predictions
from utils.stt.vad import vad_is_empty
import logging

logger = logging.getLogger(__name__)

_MINIMUM_AUDIO_FLOOR_SECONDS = 10.0
_TRANSCRIPT_DURATION_PADDING_SECONDS = 10.0


def _transcript_span_seconds(transcript_segments: List[TranscriptSegment]) -> float:
    """Wall-clock span covered by segment timestamps (extrema, not list order)."""
    if not transcript_segments:
        return 0.0
    starts = [segment.start for segment in transcript_segments]
    ends = [segment.end for segment in transcript_segments]
    return max(ends) - min(starts)


def _minimum_audio_duration(transcript_segments: List[TranscriptSegment]) -> float:
    if not transcript_segments:
        return _MINIMUM_AUDIO_FLOOR_SECONDS
    transcript_duration = _transcript_span_seconds(transcript_segments)
    return max(_MINIMUM_AUDIO_FLOOR_SECONDS, transcript_duration - _TRANSCRIPT_DURATION_PADDING_SECONDS)


# TODO: this pipeline vs groq+pyannote diarization 3.1, probably the latter is better.
# TODO: should consider storing non beautified segments, and beautify on read?
def postprocess_conversation(
    conversation_id: str, file_path: str, uid: str, emotional_feedback: bool, streaming_model: str
):
    conversation_data = _get_conversation_by_id(uid, conversation_id)
    if not conversation_data:
        return 404, "Conversation not found"

    conversation = deserialize_conversation(conversation_data)
    if conversation.discarded:
        logger.info('postprocess_conversation: Conversation is discarded')
        return 400, "Conversation is discarded"

    if (
        conversation.postprocessing is not None
        and conversation.postprocessing.status != PostProcessingStatus.not_started
    ):
        logger.info(
            f'postprocess_conversation: Conversation can\'t be post-processed again {conversation.postprocessing.status}'
        )
        return 400, "Conversation can't be post-processed again"

    aseg = AudioSegment.from_wav(file_path)
    min_required = _minimum_audio_duration(conversation.transcript_segments)

    if aseg.duration_seconds < min_required:
        # Historical root cause: mobile CaptureProvider built the upload with
        # createWavFile(removeLastNSeconds=quietSecondsForMemoryCreation=120), so
        # quiet-timer creations uploaded a truncated WAV while transcript segments
        # still spanned the full session. Client + router for this path are gone;
        # keep rejecting short files if the util is ever rewired.
        fail_reason = (
            f'Audio duration is too short, seems wrong '
            f'(audio_s={aseg.duration_seconds:.2f} min_required_s={min_required:.2f}).'
        )
        logger.info('postprocess_conversation: %s', fail_reason)
        conversations_db.set_postprocessing_status(
            uid, conversation.id, PostProcessingStatus.canceled, fail_reason=fail_reason
        )
        return 500, "Audio duration is too short, seems wrong."

    conversations_db.set_postprocessing_status(uid, conversation.id, PostProcessingStatus.in_progress)

    try:
        logger.info(f'previous to vad_is_empty (segments duration): {conversation.transcript_segments[-1].end}')
        vad_segments = vad_is_empty(file_path, return_segments=True)
        if vad_segments:
            start = vad_segments[0]['start']
            end = vad_segments[-1]['end']
            logger.info(f'vad_is_empty file result segments: {start} {end}')
            aseg = AudioSegment.from_wav(file_path)
            aseg = aseg[max(0, (start - 1) * 1000) : min((end + 1) * 1000, aseg.duration_seconds * 1000)]
            aseg.export(file_path, format="wav")
    except Exception as e:
        logger.error(e)

    try:
        aseg = AudioSegment.from_wav(file_path)
        signed_url = upload_postprocessing_audio(file_path)
        storage_executor.submit(_delete_postprocessing_audio, file_path)

        if aseg.frame_rate == 16000 and get_user_store_recording_permission(uid):
            upload_conversation_recording(file_path, uid, conversation_id)

        speakers_count = len(set([segment.speaker for segment in conversation.transcript_segments]))
        words = prerecorded(signed_url, speakers_count=speakers_count)
        prerecorded_segments = postprocess_words(words, aseg.duration_seconds)

        # if new transcript is 90% shorter than the original, cancel post-processing, smth wrong with audio or STT provider
        count = len(''.join([segment.text.strip() for segment in conversation.transcript_segments]))
        new_count = len(''.join([segment.text.strip() for segment in prerecorded_segments]))
        logger.info(f'Prev characters count: {count} New characters count: {new_count}')

        prerecorded_failed = not prerecorded_segments or new_count < (count * 0.85)

        if prerecorded_failed:
            _handle_segment_embedding_matching(uid, file_path, conversation.transcript_segments, aseg)
        else:
            _handle_segment_embedding_matching(uid, file_path, prerecorded_segments, aseg)

        # Store both models results.
        conversations_db.store_model_segments_result(
            uid, conversation.id, streaming_model, conversation.transcript_segments
        )
        conversations_db.store_model_segments_result(uid, conversation.id, 'prerecorded', prerecorded_segments)

        if not prerecorded_failed:
            conversation.transcript_segments = prerecorded_segments

        lifecycle_service.persist_processed_conversation(
            uid, conversation.model_dump()
        )  # Store transcript segments at least if smth fails later
        if prerecorded_failed:
            fail_reason = (
                'STT empty segments'
                if not prerecorded_segments
                else f'STT transcript too short ({new_count} vs {count})'
            )
            conversations_db.set_postprocessing_status(
                uid, conversation.id, PostProcessingStatus.failed, fail_reason=fail_reason
            )
            # conversation.postprocessing = MemoryPostProcessing(
            # TODO: consider doing process_conversation, if any segment still matched to user or people
            return 200, conversation

        # Reprocess conversation with improved transcription
        result: Conversation = process_conversation(uid, conversation.language, conversation, force_process=True)

        # Process users emotion, async
        if emotional_feedback:
            asyncio.run(_process_user_emotion(uid, conversation.language, conversation, [signed_url]))
    except Exception as e:
        logger.error(e)
        conversations_db.set_postprocessing_status(
            uid, conversation.id, PostProcessingStatus.failed, fail_reason=str(e)
        )
        return 500, str(e)

    conversations_db.set_postprocessing_status(uid, conversation.id, PostProcessingStatus.completed)
    # result.postprocessing = MemoryPostProcessing(

    return 200, result


def _get_conversation_by_id(uid: str, conversation_id: str) -> dict:
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation is None:
        return None
    return conversation


def _delete_postprocessing_audio(file_path):
    time.sleep(300)  # 5 min
    delete_postprocessing_audio(file_path)
    os.remove(file_path)


async def _process_user_emotion(uid: str, language_code: str, conversation: Conversation, urls: [str]):
    if not any(segment.is_user for segment in conversation.transcript_segments):
        logger.warning(f"_process_user_emotion skipped for {conversation.id}")
        return

    process_user_emotion(uid, language_code, conversation, urls)


def _handle_segment_embedding_matching(uid: str, file_path: str, segments: List[TranscriptSegment], aseg: AudioSegment):
    if aseg.frame_rate == 16000:
        matches = get_speech_profile_matching_predictions(uid, file_path, [s.model_dump() for s in segments])
        for i, segment in enumerate(segments):
            segment.is_user = matches[i]['is_user']
            segment.person_id = matches[i].get('person_id')

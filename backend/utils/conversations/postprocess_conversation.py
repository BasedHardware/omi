import asyncio
import os
import threading
import time

from pydub import AudioSegment

import database.conversations as conversations_db
from database.users import get_user_store_recording_permission
from models.conversation import *
from utils.conversations.process_conversation import process_conversation, process_user_emotion
from utils.other.storage import upload_postprocessing_audio, delete_postprocessing_audio, upload_conversation_recording
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing
from utils.stt.speech_profile import get_speech_profile_matching_predictions
from utils.stt.vad import vad_is_empty


# TODO: this pipeline vs groq+pyannote diarization 3.1, probably the latter is better.
# TODO: should consider storing non beautified segments, and beautify on read?
def postprocess_conversation(
    conversation_id: str, file_path: str, uid: str, emotional_feedback: bool, streaming_model: str
):
    conversation_data = _get_conversation_by_id(uid, conversation_id)
    if not conversation_data:
        return 404, "Conversation not found"

    conversation = Conversation(**conversation_data)
    if conversation.discarded:
        print('postprocess_conversation: Conversation is discarded')
        return 400, "Conversation is discarded"

    if (
        conversation.postprocessing is not None
        and conversation.postprocessing.status != PostProcessingStatus.not_started
    ):
        print(
            f'postprocess_conversation: Conversation can\'t be post-processed again {conversation.postprocessing.status}'
        )
        return 400, "Conversation can't be post-processed again"

    aseg = AudioSegment.from_wav(file_path)
    if (
        aseg.duration_seconds < 10
    ):  # TODO: validate duration more accurately, segment.last.end - segment.first.start - 10
        # TODO: fix app, sometimes audio uploaded is wrong, is too short.
        print('postprocess_conversation: Audio duration is too short, seems wrong.')
        conversations_db.set_postprocessing_status(uid, conversation.id, PostProcessingStatus.canceled)
        return 500, "Audio duration is too short, seems wrong."

    conversations_db.set_postprocessing_status(uid, conversation.id, PostProcessingStatus.in_progress)

    try:
        print('previous to vad_is_empty (segments duration):', conversation.transcript_segments[-1].end)
        vad_segments = vad_is_empty(file_path, return_segments=True)
        if vad_segments:
            start = vad_segments[0]['start']
            end = vad_segments[-1]['end']
            print('vad_is_empty file result segments:', start, end)
            aseg = AudioSegment.from_wav(file_path)
            aseg = aseg[max(0, (start - 1) * 1000) : min((end + 1) * 1000, aseg.duration_seconds * 1000)]
            aseg.export(file_path, format="wav")
    except Exception as e:
        print(e)

    try:
        aseg = AudioSegment.from_wav(file_path)
        signed_url = upload_postprocessing_audio(file_path)
        threading.Thread(target=_delete_postprocessing_audio, args=(file_path,)).start()

        if aseg.frame_rate == 16000 and get_user_store_recording_permission(uid):
            upload_conversation_recording(file_path, uid, conversation_id)

        speakers_count = len(set([segment.speaker for segment in conversation.transcript_segments]))
        words = fal_whisperx(signed_url, speakers_count)
        fal_segments = fal_postprocessing(words, aseg.duration_seconds)

        # if new transcript is 90% shorter than the original, cancel post-processing, smth wrong with audio or FAL
        count = len(''.join([segment.text.strip() for segment in conversation.transcript_segments]))
        new_count = len(''.join([segment.text.strip() for segment in fal_segments]))
        print('Prev characters count:', count, 'New characters count:', new_count)

        fal_failed = not fal_segments or new_count < (count * 0.85)

        if fal_failed:
            _handle_segment_embedding_matching(uid, file_path, conversation.transcript_segments, aseg)
        else:
            _handle_segment_embedding_matching(uid, file_path, fal_segments, aseg)

        # Store both models results.
        conversations_db.store_model_segments_result(
            uid, conversation.id, streaming_model, conversation.transcript_segments
        )
        conversations_db.store_model_segments_result(uid, conversation.id, 'fal_whisperx', fal_segments)

        if not fal_failed:
            conversation.transcript_segments = fal_segments

        conversations_db.upsert_conversation(
            uid, conversation.dict()
        )  # Store transcript segments at least if smth fails later
        if fal_failed:
            # TODO: FAL fails too much and is fucking expensive. Remove it.
            fail_reason = (
                'FAL empty segments' if not fal_segments else f'FAL transcript too short ({new_count} vs {count})'
            )
            conversations_db.set_postprocessing_status(
                uid, conversation.id, PostProcessingStatus.failed, fail_reason=fail_reason
            )
            # conversation.postprocessing = MemoryPostProcessing(
            #     status=PostProcessingStatus.failed, model=PostProcessingModel.fal_whisperx)
            # TODO: consider doing process_conversation, if any segment still matched to user or people
            return 200, conversation

        # Reprocess conversation with improved transcription
        result: Conversation = process_conversation(uid, conversation.language, conversation, force_process=True)

        # Process users emotion, async
        if emotional_feedback:
            asyncio.run(_process_user_emotion(uid, conversation.language, conversation, [signed_url]))
    except Exception as e:
        print(e)
        conversations_db.set_postprocessing_status(
            uid, conversation.id, PostProcessingStatus.failed, fail_reason=str(e)
        )
        return 500, str(e)

    conversations_db.set_postprocessing_status(uid, conversation.id, PostProcessingStatus.completed)
    # result.postprocessing = MemoryPostProcessing(
    #     status=PostProcessingStatus.completed, model=PostProcessingModel.fal_whisperx)

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
        print(f"_process_user_emotion skipped for {conversation.id}")
        return

    process_user_emotion(uid, language_code, conversation, urls)


def _handle_segment_embedding_matching(uid: str, file_path: str, segments: List[TranscriptSegment], aseg: AudioSegment):
    if aseg.frame_rate == 16000:
        matches = get_speech_profile_matching_predictions(uid, file_path, [s.dict() for s in segments])
        for i, segment in enumerate(segments):
            segment.is_user = matches[i]['is_user']
            segment.person_id = matches[i].get('person_id')

import asyncio
import os
import threading
import time

from pydub import AudioSegment

import database.memories as memories_db
from database.users import get_user_store_recording_permission
from models.memory import *
from utils.memories.process_memory import process_memory, process_user_emotion
from utils.other.storage import upload_postprocessing_audio, \
    delete_postprocessing_audio, upload_memory_recording
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing
from utils.stt.speech_profile import get_speech_profile_matching_predictions
from utils.stt.vad import vad_is_empty


# TODO: this pipeline vs groq+pyannote diarization 3.1, probably the latter is better.
# TODO: should consider storing non beautified segments, and beautify on read?
def postprocess_memory(memory_id: str, file_path: str, uid: str, emotional_feedback: bool, streaming_model: str):
    memory_data = _get_memory_by_id(uid, memory_id)
    if not memory_data:
        return 404, "Memory not found"

    memory = Memory(**memory_data)
    if memory.discarded:
        print('postprocess_memory: Memory is discarded')
        return 400, "Memory is discarded"

    if memory.postprocessing is not None and memory.postprocessing.status != PostProcessingStatus.not_started:
        print(f'postprocess_memory: Memory can\'t be post-processed again {memory.postprocessing.status}')
        return 400, "Memory can't be post-processed again"

    aseg = AudioSegment.from_wav(file_path)
    if aseg.duration_seconds < 10:  # TODO: validate duration more accurately, segment.last.end - segment.first.start - 10
        # TODO: fix app, sometimes audio uploaded is wrong, is too short.
        print('postprocess_memory: Audio duration is too short, seems wrong.')
        memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.canceled)
        return 500, "Audio duration is too short, seems wrong."

    memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.in_progress)

    try:
        print('previous to vad_is_empty (segments duration):', memory.transcript_segments[-1].end)
        vad_segments = vad_is_empty(file_path, return_segments=True)
        if vad_segments:
            start = vad_segments[0]['start']
            end = vad_segments[-1]['end']
            print('vad_is_empty file result segments:', start, end)
            aseg = AudioSegment.from_wav(file_path)
            aseg = aseg[max(0, (start - 1) * 1000):min((end + 1) * 1000, aseg.duration_seconds * 1000)]
            aseg.export(file_path, format="wav")
    except Exception as e:
        print(e)

    try:
        aseg = AudioSegment.from_wav(file_path)
        signed_url = upload_postprocessing_audio(file_path)
        threading.Thread(target=_delete_postprocessing_audio, args=(file_path,)).start()

        if aseg.frame_rate == 16000 and get_user_store_recording_permission(uid):
            upload_memory_recording(file_path, uid, memory_id)

        speakers_count = len(set([segment.speaker for segment in memory.transcript_segments]))
        words = fal_whisperx(signed_url, speakers_count)
        fal_segments = fal_postprocessing(words, aseg.duration_seconds)

        # if new transcript is 90% shorter than the original, cancel post-processing, smth wrong with audio or FAL
        count = len(''.join([segment.text.strip() for segment in memory.transcript_segments]))
        new_count = len(''.join([segment.text.strip() for segment in fal_segments]))
        print('Prev characters count:', count, 'New characters count:', new_count)

        fal_failed = not fal_segments or new_count < (count * 0.85)

        if fal_failed:
            _handle_segment_embedding_matching(uid, file_path, memory.transcript_segments, aseg)
        else:
            _handle_segment_embedding_matching(uid, file_path, fal_segments, aseg)

        # Store both models results.
        memories_db.store_model_segments_result(uid, memory.id, streaming_model, memory.transcript_segments)
        memories_db.store_model_segments_result(uid, memory.id, 'fal_whisperx', fal_segments)

        if not fal_failed:
            memory.transcript_segments = fal_segments

        memories_db.upsert_memory(uid, memory.dict())  # Store transcript segments at least if smth fails later
        if fal_failed:
            # TODO: FAL fails too much and is fucking expensive. Remove it.
            fail_reason = 'FAL empty segments' if not fal_segments else f'FAL transcript too short ({new_count} vs {count})'
            memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.failed, fail_reason=fail_reason)
            memory.postprocessing = MemoryPostProcessing(
                status=PostProcessingStatus.failed, model=PostProcessingModel.fal_whisperx)
            # TODO: consider doing process_memory, if any segment still matched to user or people
            return 200, memory

        # Reprocess memory with improved transcription
        result: Memory = process_memory(uid, memory.language, memory, force_process=True)

        # Process users emotion, async
        if emotional_feedback:
            asyncio.run(_process_user_emotion(uid, memory.language, memory, [signed_url]))
    except Exception as e:
        print(e)
        memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.failed, fail_reason=str(e))
        return 500, str(e)

    memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.completed)
    result.postprocessing = MemoryPostProcessing(
        status=PostProcessingStatus.completed, model=PostProcessingModel.fal_whisperx)

    return 200, result


def _get_memory_by_id(uid: str, memory_id: str) -> dict:
    memory = memories_db.get_memory(uid, memory_id)
    if memory is None or memory.get('deleted', False):
        return None
    return memory


def _delete_postprocessing_audio(file_path):
    time.sleep(300)  # 5 min
    delete_postprocessing_audio(file_path)
    os.remove(file_path)


async def _process_user_emotion(uid: str, language_code: str, memory: Memory, urls: [str]):
    if not any(segment.is_user for segment in memory.transcript_segments):
        print(f"_process_user_emotion skipped for {memory.id}")
        return

    process_user_emotion(uid, language_code, memory, urls)


def _handle_segment_embedding_matching(uid: str, file_path: str, segments: List[TranscriptSegment], aseg: AudioSegment):
    if aseg.frame_rate == 16000:
        matches = get_speech_profile_matching_predictions(uid, file_path, [s.dict() for s in segments])
        for i, segment in enumerate(segments):
            segment.is_user = matches[i]['is_user']
            segment.person_id = matches[i].get('person_id')

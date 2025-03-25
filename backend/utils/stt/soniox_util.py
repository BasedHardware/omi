# import json
# import os
# import subprocess
# import time
#
# import websockets
# from pydub import AudioSegment
# from soniox.speech_service import SpeechClient
# from soniox.transcribe_file import transcribe_file_short, transcribe_file_async
# from starlette.websockets import WebSocket
#
# from utils.endpoints import timeit
#
#
#

#
# def add_speaker(uid: str):
#     result = subprocess.run(['python', '-m', 'soniox.manage_speakers', '--add_speaker', '--speaker_name', uid])
#     completed = result.returncode == 0
#     print('add_speaker successful:', completed)
#     return completed
#
#
# def get_speaker_audios(uid: str):
#     result = subprocess.run(['python', '-m', 'soniox.manage_speakers', '--list_audio', '--speaker_name', uid],
#                             capture_output=True)
#     audios = str(result.stdout).split('\\n')[1:-1]
#     return audios
#
#
# def remove_speaker_audio(uid: str, audio_name: str = 'joined_output'):
#     result = subprocess.run(
#         ['python', '-m', 'soniox.manage_speakers', '--remove_audio', '--speaker_name', uid, '--audio_name', audio_name])
#     completed = result.returncode == 0
#     print('remove_speaker_audio successful:', completed)
#     return completed
#
#
# def remove_speaker(uid: str):
#     result = subprocess.run(['python', '-m', 'soniox.manage_speakers', '--remove_speaker', '--speaker_name', uid])
#     completed = result.returncode == 0
#     print('remove_speaker successful:', completed)
#     return completed
#
#
# def remove_training_sample(uid: str, audio_name: str):
#     result = subprocess.run(
#         ['python', '-m', 'soniox.manage_speakers', '--remove_audio', '--speaker_name', uid, '--audio_name', audio_name]
#     )
#     completed = result.returncode == 0
#     print('remove_training_sample success:', completed)
#     return completed
#
#
import json
import subprocess

from database.redis_db import get_user_has_soniox_speech_profile, set_user_has_soniox_speech_profile
from utils.other.endpoints import timeit
from utils.other.storage import get_profile_audio_if_exists


#
#
# # TRANSCRIPTION
#
# def _add_segment(transcript, word, speaker_num_to_name):
#     transcript.append({
#         'speaker': word.speaker,
#         'start': word.start_ms,
#         'confidence': [word.confidence],
#         'text': word.text,
#         'is_user': speaker_num_to_name.get(word.speaker) is not None,
#         # 'duration': word.duration_ms,
#         'end': word.start_ms + word.duration_ms
#     })
#
#
# def _get_transcript_from_result(result):
#     speaker_num_to_name = {entry.speaker: entry.name for entry in result.speakers}
#     # print(speaker_num_to_name)
#
#     transcript = []
#     for word in result.words:
#         if not transcript:
#             _add_segment(transcript, word, speaker_num_to_name)
#         else:
#             last = transcript[-1]
#             if last['speaker'] == word.speaker:
#                 last['text'] += f'{word.text}'
#                 last['end'] = word.start_ms + word.duration_ms
#                 last['confidence'].append(word.confidence)
#             else:
#                 _add_segment(transcript, word, speaker_num_to_name)
#
#     for segment in transcript:
#         segment['speaker'] = f'SPEAKER_{segment["speaker"]}'
#         segment['start'] = round(segment['start'] / 1000, 2)
#         segment['end'] = round(segment['end'] / 1000, 2)
#         segment['confidence'] = round(sum(segment['confidence']) / len(segment['confidence']), 2)
#         segment['text'] = segment['text'].strip()
#     return transcript
#
#
# def short_transcript(file_path: str, language: str, uid: str, has_speech_profile: bool, sample_rate=8000):
#     is_english = language == 'en'
#     with SpeechClient() as client:
#         return transcribe_file_short(
#             file_path,
#             client,
#             model=f"{language}_v2",
#             enable_global_speaker_diarization=is_english,  # True
#             sample_rate_hertz=sample_rate,
#             num_audio_channels=1,
#             enable_speaker_identification=has_speech_profile and is_english,
#             cand_speaker_names=[uid] if has_speech_profile and is_english else None,
#         )
#
#
# @timeit
# def longer_transcript(file_path: str, language: str, uid: str, uid_profile_exists: bool, sample_rate=8000):
#     is_english = language == 'en'
#     with SpeechClient() as client:
#         file_name = file_path.split('/')[-1]
#         file_id = transcribe_file_async(
#             file_path,
#             client,
#             reference_name=file_name,
#             model=f"{language}_v2",
#             enable_global_speaker_diarization=is_english,  # True
#             num_audio_channels=1,
#             enable_speaker_identification=uid_profile_exists and is_english,
#             cand_speaker_names=[uid] if uid_profile_exists and is_english else None,
#         )
#         print(f"File ID: {file_id}")
#
#         waiting = 0
#         while True:
#             if waiting > 60:
#                 print("Timeout while waiting for transcription.")
#                 raise TimeoutError("Timeout while waiting for transcription.")
#             status = client.GetTranscribeAsyncStatus(file_id)
#             # print(f"Status: {status.status}")
#             if status.status in ("COMPLETED", "FAILED"):
#                 break
#             time.sleep(2.0)
#             waiting += 2
#
#         if status.status == "COMPLETED":
#             print("Calling GetTranscribeAsyncResult")
#             result = client.GetTranscribeAsyncResult(file_id)
#         else:
#             raise Exception(f"Transcription failed with error: {status.error_message}")
#
#         print("Calling DeleteTranscribeAsyncFile.")
#         client.DeleteTranscribeAsyncFile(file_id)
#         return result
#
#
# def transcribe_file_soniox(uid: str, file_path: str, sample_rate=8000, language: str = 'en'):
#     if language not in ['en']:  # , 'es', 'ko', 'zh', 'fr', 'it', 'pt', 'de' ~ no diarization
#         raise ValueError(f'Language {language} not supported')
#     # has_speech_profile = uid_has_speech_profile(uid)
#     has_speech_profile = False
#     aseg = AudioSegment.from_wav(file_path)
#     if aseg.duration_seconds <= 60:
#         result = short_transcript(file_path, language, uid, has_speech_profile, sample_rate=sample_rate)
#     else:
#         result = longer_transcript(file_path, language, uid, has_speech_profile, sample_rate=sample_rate)
#     return _get_transcript_from_result(result)
#
#

def set_json_speech_profiles(result):
    data = (result.stdout.decode('utf-8').replace('Listing speakers and audios.\n  ', '')
            .replace('\n', '').replace('\'', '"').strip())
    parsed_json = {}
    for part in data.split('}'):
        if not part.strip():
            continue
        part = part.strip() + ' }'
        parsed_part = json.loads(part)
        if 'name' not in parsed_part:
            continue  # means is an audio name
        parsed_json[parsed_part['name']] = parsed_part
    print(parsed_json)
    # for uid in parsed_json.keys():
    #     set_user_has_speech_profile(uid)
    return list(parsed_json.keys())


def _script():
    result = subprocess.run(['python', '-m', 'soniox.manage_speakers', '--list'], capture_output=True)
    uids = set_json_speech_profiles(result)
    print(uids)


# _script()


def _train_user_speech_profile(uid: str):
    output_path = get_profile_audio_if_exists(uid, download=True)
    if not output_path:
        return False
    try:
        result = subprocess.run(
            [
                'python', '-m', 'soniox.manage_speakers', '--add_audio', '--speaker_name', uid, '--audio_name',
                'joined_output', '--audio_fn', output_path
            ],
            capture_output=True
        )
        completed = result.returncode == 0
        print('_train_user_speech_profile:', completed)
        return completed
    except Exception as e:
        print(f'Error in _train_user_speech_profile: {e}')
        return False


def _create_user_speech_profile(uid: str):
    try:
        result = subprocess.run(
            ['python', '-m', 'soniox.manage_speakers', '--add_speaker', '--speaker_name', uid], capture_output=True
        )
        completed = result.returncode == 0
        print('_create_user_speech_profile successful:', completed, result.stdout)
        return completed
    except Exception as e:
        print(f'_create_user_speech_profile failed: {e}')
        return False


def _remove_user_speech_profile(uid: str):
    try:
        result = subprocess.run(['python', '-m', 'soniox.manage_speakers', '--remove_speaker', '--speaker_name', uid])
        completed = result.returncode == 0
        print('_remove_user_speech_profile successful:', completed)
        return completed
    except Exception as e:
        print(f'_remove_user_speech_profile failed: {e}')
        return False

@timeit
def create_user_speech_profile(uid: str):
    if get_user_has_soniox_speech_profile(uid):
        return True
    _remove_user_speech_profile(uid)
    _create_user_speech_profile(uid)

    try:
        result = _train_user_speech_profile(uid)
        if result:
            set_user_has_soniox_speech_profile(uid)
        return result
    except Exception as e:
        print(f'Error in create_speaker_profile: {e}')
        return False

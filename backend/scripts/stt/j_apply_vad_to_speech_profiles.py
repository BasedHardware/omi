import os
import threading
# noinspection PyUnresolvedReferences
from typing import List

from dotenv import load_dotenv
from pydub import AudioSegment

from utils.stt.vad import apply_vad_for_speech_profile

load_dotenv('../../.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

from database._client import get_users_uid
from utils.other.storage import get_profile_audio_if_exists, upload_profile_audio


def execute():
    os.makedirs('_temp', exist_ok=True)
    uids = get_users_uid()
    print('execute for', len(uids))

    def single(uid):
        file_path = get_profile_audio_if_exists(uid)
        if not file_path:
            return
        apply_vad_for_speech_profile(file_path)
        aseg = AudioSegment.from_wav(file_path)
        if aseg.duration_seconds < 5 or aseg.duration_seconds > 120:
            print('Invalid duration for', uid)
            return
        upload_profile_audio(file_path, uid)

    threads = []
    for i, uid in enumerate(uids):
        threads.append(threading.Thread(target=single, args=(uid,)))

    count = 20
    chunks = [threads[i:i + count] for i in range(0, len(threads), count)]
    for i, chunk in enumerate(chunks):
        [thread.start() for thread in chunk]
        [thread.join() for thread in chunk]
        print('Chunk', i + 1, 'completed')

import os
import threading

from fastapi import APIRouter, UploadFile
from pydub import AudioSegment

from utils.storage import retrieve_all_samples, upload_sample_storage
from utils.stt.soniox_util import create_speaker_profile, uid_has_speech_profile

router = APIRouter()


# TODO: issues with this
# - user sends sample a, if the user sends sample b, before a process finished completely 2 things could happen
#   - remove_speaker_audio(uid) is triggered before the previous sample created the profile, which cause an exception
#   - os.remove(f"{path}/{file}") happens after request b, downloaded all samples again, which would result in 0 samples list dir
# NOTE: this only happens when the user has already more than 5 samples, and tries to do the profile again.

def _create_profile(uid: str):
    path = retrieve_all_samples(uid)
    create_speaker_profile(uid, path)
    for file in os.listdir(path):
        os.remove(f"{path}/{file}")


@router.post('/samples/upload')
def upload_sample(file: UploadFile, uid: str):
    print('upload_sample')
    path = f"_temp/{uid}"
    os.makedirs(path, exist_ok=True)
    file_path = f"{path}/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
        aseg = AudioSegment.from_wav(file_path)
        print(f'Uploading sample audio {aseg.duration_seconds} secs and {aseg.frame_rate / 1000} khz')
        uploaded_url, count = upload_sample_storage(file_path, uid)
        print('upload_sample ~ file uploaded')
        if count >= 5:
            threading.Thread(target=_create_profile, args=(uid,)).start()
    # os.remove(file_path)
    return {"url": uploaded_url}


@router.get('/samples')
def my_samples(uid: str):
    print('my_samples')
    samples_dir = retrieve_all_samples(uid)
    samples = set(os.listdir(samples_dir))
    phrases = [
        "I scream, you scream, we all scream for ice cream.",
        "Pack my box with five dozen liquor jugs.",
        "The five boxing wizards jump quickly and quietly.",
        "Bright blue birds fly above the green grassy hills.",
        "Fred's friends fried Fritos for Friday's food festival.",
        "How much wood would a woodchuck chuck if a woodchuck could chuck wood?",
    ]
    data = []
    for phrase in phrases:
        pid = phrase.replace(' ', '-').replace(',', '').replace('.', '').replace('\'', '').lower()
        data.append({'id': pid, 'phrase': phrase, 'uploaded': f"{pid}.wav" in samples})

    for file in os.listdir(samples_dir):
        os.remove(f"{samples_dir}/{file}")
    return data


@router.get('/profile')
async def has_profile(uid: str):
    return {'has_profile': uid_has_speech_profile(uid)}


@router.get('/v1/speech-profile', tags=['v1'])
async def has_speech_profile(uid: str):
    return {'has_profile': uid_has_speech_profile(uid)}

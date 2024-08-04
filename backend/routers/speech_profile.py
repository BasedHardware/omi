import os

from fastapi import APIRouter, UploadFile, Depends
from pydub import AudioSegment

from utils import auth
from utils.storage import retrieve_all_samples, upload_sample_storage
from utils.stt.soniox_util import create_speaker_profile

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


def _endpoint1(file, uid):
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
        # if count >= 5: # no soniox, let's do only deepgram for now.
        #     threading.Thread(target=_create_profile, args=(uid,)).start()
    # os.remove(file_path)
    return {"url": uploaded_url}


@router.post('/samples/upload')
def upload_sample(file: UploadFile, uid: str):
    return _endpoint1(file, uid)


def _endpoint2(uid: str):
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


def _has_speech_profile(uid: str):
    data = _endpoint2(uid)
    return sum([1 for d in data if d['uploaded']]) >= 5


@router.get('/samples')
def my_samples(uid: str):
    return _endpoint2(uid)


@router.get('/v1/speech-profile', tags=['v1'])
def has_speech_profile(uid: str):
    return {'has_profile': _has_speech_profile(uid)}


# ********************
# * Latest endpoints *
# ********************
@router.post('/v1/speech-profile/samples', tags=['v1'])
def upload_sample(file: UploadFile, uid: str = Depends(auth.get_current_user_uid)):
    return _endpoint1(file, uid)


@router.get('/v1/speech-profile/samples', tags=['v1'])
def my_samples(uid: str = Depends(auth.get_current_user_uid)):
    return _endpoint2(uid)


@router.get('/v2/speech-profile', tags=['v1'])
def has_speech_profile(uid: str = Depends(auth.get_current_user_uid)):
    print('has_speech_profile', uid, _has_speech_profile(uid))
    return {'has_profile': _has_speech_profile(uid)}

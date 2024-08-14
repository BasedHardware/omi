import os

from fastapi import APIRouter, UploadFile, Depends

from utils import auth
from utils.storage import retrieve_all_samples, upload_sample_storage, upload_profile_audio, get_speech_profile

router = APIRouter()


def _endpoint1(file, uid):
    print('upload_sample')
    path = f"_temp/{uid}"
    os.makedirs(path, exist_ok=True)
    file_path = f"{path}/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
        uploaded_url, count = upload_sample_storage(file_path, uid)
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

    # for file in os.listdir(samples_dir):
    #     os.remove(f"{samples_dir}/{file}")
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
    return {'has_profile': _has_speech_profile(uid)}


# **********************
# * Latest endpoints 2 *
# **********************


@router.get('/v3/speech-profile', tags=['v1'])
def has_speech_profile(uid: str = Depends(auth.get_current_user_uid)):
    return {'has_profile': get_speech_profile(uid) is not None}


@router.post('/v3/upload', tags=['v1'])
def upload_profile(file: UploadFile, uid: str = Depends(auth.get_current_user_uid)):
    os.makedirs(f'_temp/{uid}', exist_ok=True)
    file_path = f"_temp/{uid}/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())

    return {"url": upload_profile_audio(file_path, uid)}

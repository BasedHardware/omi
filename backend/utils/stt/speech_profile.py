import json
import os
from typing import List

import requests
from pydub import AudioSegment

from utils.other.storage import get_profile_audio_if_exists, get_additional_profile_recordings, get_user_people_ids, \
    get_user_person_speech_samples


def get_speech_profile_matching_predictions(uid: str, audio_file_path: str, segments: List) -> List[dict]:
    print('get_speech_profile_matching_predictions')
    files = [
        ('audio_file', (os.path.basename(audio_file_path), open(audio_file_path, 'rb'), 'audio/wav')),
    ]
    response = requests.post(
        os.getenv('HOSTED_SPEECH_PROFILE_API_URL') + f'?uid={uid}',
        data={'segments': json.dumps(segments)},
        files=files
    )
    default = [{'is_user': False, 'person_id': None}] * len(segments)

    if response.status_code != 200:
        print('get_speech_profile_matching_predictions', response.text)
        return default
    try:
        result = response.json()
        print('get_speech_profile_matching_predictions', result)
        if isinstance(result[0], bool):
            return [{'is_user': r, 'person_id': None} for r in result]

        return result
    except Exception as e:
        print('get_speech_profile_matching_predictions', str(e))
        return default


def get_speech_profile_expanded(uid: str):
    main = get_profile_audio_if_exists(uid, download=True)
    if not main:
        return None
    parts = get_additional_profile_recordings(uid, download=True)
    aseg = AudioSegment.from_wav(main)
    for part in parts:
        aseg += AudioSegment.from_wav(part)
    path = f'_temp/{uid}_complete_speech_profile.wav'
    aseg.export(path, format='wav')
    return path


def get_people_with_speech_samples(uid: str):
    people_ids = get_user_people_ids(uid)
    people = []
    for pid in people_ids:
        file_paths = get_user_person_speech_samples(uid, pid, download=True)
        aseg = AudioSegment.empty()
        for path in file_paths:
            aseg += AudioSegment.from_wav(path)
        path = f'_temp/{uid}_{pid}_complete_speech_profile.wav'
        aseg.export(path, format='wav')
        people.append({'id': pid, 'path': path})
    return people

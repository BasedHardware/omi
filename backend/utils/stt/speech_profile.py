import json
import os
from typing import List

import requests
from pydub import AudioSegment

from utils.other.storage import get_profile_audio_if_exists, get_additional_profile_recordings


def get_speech_profile_matching_predictions(audio_file_path: str, profile_path: str, segments: List) -> List[bool]:
    print('get_speech_profile_matching_predictions')
    files = [
        ('audio_file', (os.path.basename(audio_file_path), open(audio_file_path, 'rb'), 'audio/wav')),
        ('profile_path', (os.path.basename(profile_path), open(profile_path, 'rb'), 'audio/wav'))
    ]
    response = requests.post(
        os.getenv('HOSTED_SPEECH_PROFILE_API_URL'),
        data={'segments': json.dumps(segments)},
        files=files
    )
    if response.status_code != 200:
        print('get_speech_profile_matching_predictions', response.text)
        return [False] * len(segments)
    try:
        result = response.json()
        print('get_speech_profile_matching_predictions', result)
        return result
    except Exception as e:
        print('get_speech_profile_matching_predictions', str(e))
        return [False] * len(segments)


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

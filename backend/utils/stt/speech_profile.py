import json
import os
from typing import List

import requests


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
    try:
        result = response.json()
        print('get_speech_profile_matching_predictions', result)
        return result
    except Exception as e:
        print('get_speech_profile_matching_predictions', str(e))
        return [False] * len(segments)

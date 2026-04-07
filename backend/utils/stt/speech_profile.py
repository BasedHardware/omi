import asyncio
import json
import logging
import os
from typing import List

import requests
from pydub import AudioSegment

from utils.executors import storage_executor
from utils.http_client import get_stt_client
from utils.log_sanitizer import sanitize
from utils.other.storage import (
    get_profile_audio_if_exists,
    get_additional_profile_recordings,
    get_user_people_ids,
    get_user_person_speech_samples,
)

logger = logging.getLogger(__name__)


def get_speech_profile_matching_predictions(uid: str, audio_file_path: str, segments: List) -> List[dict]:
    logger.info('get_speech_profile_matching_predictions')
    files = [
        ('audio_file', (os.path.basename(audio_file_path), open(audio_file_path, 'rb'), 'audio/wav')),
    ]
    response = requests.post(
        os.getenv('HOSTED_SPEECH_PROFILE_API_URL') + f'?uid={uid}', data={'segments': json.dumps(segments)}, files=files
    )
    default = [{'is_user': False, 'person_id': None}] * len(segments)

    if response.status_code != 200:
        logger.info(f'get_speech_profile_matching_predictions {sanitize(response.text)}')
        return default
    try:
        result = response.json()
        logger.info(f'get_speech_profile_matching_predictions {sanitize(result)}')
        if isinstance(result[0], bool):
            return [{'is_user': r, 'person_id': None} for r in result]

        return result
    except Exception as e:
        logger.info(f'get_speech_profile_matching_predictions {str(e)}')
        return default


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


async def async_get_speech_profile_matching_predictions(uid: str, audio_file_path: str, segments: List) -> List[dict]:
    """Async version of get_speech_profile_matching_predictions using httpx.AsyncClient."""
    logger.info('async_get_speech_profile_matching_predictions')
    loop = asyncio.get_running_loop()
    file_data = await loop.run_in_executor(storage_executor, _read_file, audio_file_path)

    files = {'audio_file': (os.path.basename(audio_file_path), file_data, 'audio/wav')}
    default = [{'is_user': False, 'person_id': None}] * len(segments)

    try:
        client = get_stt_client()
        response = await client.post(
            os.getenv('HOSTED_SPEECH_PROFILE_API_URL') + f'?uid={uid}',
            data={'segments': json.dumps(segments)},
            files=files,
        )
    except Exception as e:
        logger.error(f'async_get_speech_profile_matching_predictions HTTP error: {e}')
        return default

    if response.status_code != 200:
        logger.info(f'async_get_speech_profile_matching_predictions {sanitize(response.text)}')
        return default
    try:
        result = response.json()
        logger.info(f'async_get_speech_profile_matching_predictions {sanitize(result)}')
        if isinstance(result[0], bool):
            return [{'is_user': r, 'person_id': None} for r in result]
        return result
    except Exception as e:
        logger.info(f'async_get_speech_profile_matching_predictions {str(e)}')
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

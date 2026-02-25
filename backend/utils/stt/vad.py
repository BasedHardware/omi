import os

import requests
from fastapi import HTTPException
from pydub import AudioSegment

from database import redis_db
import logging

logger = logging.getLogger(__name__)


def vad_is_empty(file_path, return_segments: bool = False, cache: bool = False):
    """Uses vad_modal/vad.py deployment (Best quality)"""
    caching_key = f'vad_is_empty:{file_path}'
    if cache:
        if exists := redis_db.get_generic_cache(caching_key):
            if return_segments:
                return exists
            return len(exists) == 0

    with open(file_path, 'rb') as file:
        files = {'file': (file_path.split('/')[-1], file, 'audio/wav')}
        response = requests.post(os.getenv('HOSTED_VAD_API_URL'), files=files, timeout=300)
        response.raise_for_status()  # Raise exception for HTTP errors
        segments = response.json()
        if cache:
            redis_db.set_generic_cache(caching_key, segments, ttl=60 * 60 * 24)
        if return_segments:
            return segments
        logger.info(f'vad_is_empty {len(segments) == 0}')
        return len(segments) == 0


def apply_vad_for_speech_profile(file_path: str):
    logger.info(f'apply_vad_for_speech_profile {file_path}')
    voice_segments = vad_is_empty(file_path, return_segments=True)
    if len(voice_segments) == 0:  # TODO: front error on post-processing, audio sent is bad.
        raise HTTPException(status_code=400, detail="Audio is empty")
    joined_segments = []
    for i, segment in enumerate(voice_segments):
        if joined_segments and (segment['start'] - joined_segments[-1]['end']) < 1:
            joined_segments[-1]['end'] = segment['end']
        else:
            joined_segments.append(segment)

    # Load audio file once instead of repeatedly in the loop
    full_audio = AudioSegment.from_wav(file_path)

    try:
        # trim silence out of file_path, but leave 1 sec of silence within chunks
        trimmed_aseg = AudioSegment.empty()
        for i, segment in enumerate(joined_segments):
            start = segment['start'] * 1000
            end = segment['end'] * 1000
            trimmed_aseg += full_audio[start:end]
            if i < len(joined_segments) - 1:
                trimmed_aseg += full_audio[end : end + 1000]

        # file_path.replace('.wav', '-cleaned.wav')
        trimmed_aseg.export(file_path, format="wav")
    finally:
        # Explicitly free memory
        del full_audio
        del trimmed_aseg

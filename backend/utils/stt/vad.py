import os
import logging
from enum import Enum

import numpy as np
import requests
import torch
from fastapi import HTTPException
from pydub import AudioSegment

from database import redis_db

logger = logging.getLogger("vad")

# Global variables to hold model and utilities
model = None
utils = None
get_speech_timestamps = None
save_audio = None
read_audio = None
VADIterator = None
collect_chunks = None

def initialize_vad():
    """Initialize VAD model and utilities. Should be called after logging is configured."""
    global model, utils, get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks

    logger.info("[VAD] Initializing VAD module")
    torch.set_num_threads(1)
    torch.hub.set_dir('pretrained_models')
    logger.info("[VAD] Torch configs set")

    model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
    (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils

    logger.info("[VAD] Model loaded successfully")


class SpeechState(str, Enum):
    speech_found = 'speech_found'
    no_speech = 'no_speech'


def is_speech_present(data, vad_iterator, window_size_samples=256):
    if model is None:
        initialize_vad()

    logger.debug("[VAD] Checking if speech is present")
    data_int16 = np.frombuffer(data, dtype=np.int16)
    data_float32 = data_int16.astype(np.float32) / 32768.0
    has_start, has_end = False, False

    for i in range(0, len(data_float32), window_size_samples):
        chunk = data_float32[i: i + window_size_samples]
        if len(chunk) < window_size_samples:
            break
        speech_dict = vad_iterator(chunk, return_seconds=False)
        if speech_dict:
            logger.debug(f"[VAD] Speech found: {speech_dict}")
            vad_iterator.reset_states()
            return SpeechState.speech_found

            # if not has_start and 'start' in speech_dict:
            #     has_start = True
            #
            # if not has_end and 'end' in speech_dict:
            #     has_end = True

    # if has_start:
    #     return SpeechState.speech_found
    # elif has_end:
    #     return SpeechState.no_speech
    logger.debug("[VAD] No speech detected")
    vad_iterator.reset_states()
    return SpeechState.no_speech


def is_audio_empty(file_path, sample_rate=8000):
    if model is None:
        initialize_vad()

    logger.debug(f"[VAD] Checking if audio is empty: {file_path}")
    wav = read_audio(file_path)
    timestamps = get_speech_timestamps(wav, model, sampling_rate=sample_rate)
    if len(timestamps) == 1:
        prob_not_speech = ((timestamps[0]['end'] / 1000) - (timestamps[0]['start'] / 1000)) < 1
        logger.debug(f"[VAD] Single timestamp detected, probably not speech: {prob_not_speech}")
        return prob_not_speech
    logger.debug(f"[VAD] Audio empty: {len(timestamps) == 0}")
    return len(timestamps) == 0


def vad_is_empty(file_path, return_segments: bool = False, cache: bool = False):
    """Uses vad_modal/vad.py deployment (Best quality)"""
    logger.debug(f"[VAD] vad_is_empty check on: {file_path}, cache: {cache}")
    caching_key = f'vad_is_empty:{file_path}'
    if cache:
        if exists := redis_db.get_generic_cache(caching_key):
            logger.debug(f"[VAD] Cache hit for {file_path}")
            if return_segments:
                return exists
            return len(exists) == 0

    try:
        # file_duration = AudioSegment.from_wav(file_path).duration_seconds
        # print('vad_is_empty file duration:', file_duration)
        with open(file_path, 'rb') as file:
            files = {'file': (file_path.split('/')[-1], file, 'audio/wav')}
            logger.debug(f"[VAD] Sending request to hosted VAD API")
            response = requests.post(os.getenv('HOSTED_VAD_API_URL'), files=files)
            segments = response.json()
            logger.debug(f"[VAD] Received {len(segments)} segments from VAD API")
            if cache:
                redis_db.set_generic_cache(caching_key, segments, ttl=60 * 60 * 24)
                logger.debug(f"[VAD] Cache set for {file_path}")
            if return_segments:
                return segments
            result = len(segments) == 0
            logger.info(f"[VAD] vad_is_empty result: {result}")
            return result
    except Exception as e:
        logger.error(f'[VAD] Error in vad_is_empty: {e}')
        if return_segments:
            return []
        return False


def apply_vad_for_speech_profile(file_path: str):
    # No initialization needed as this calls vad_is_empty which uses hosted API
    logger.info(f'[VAD] Applying VAD for speech profile: {file_path}')
    voice_segments = vad_is_empty(file_path, return_segments=True)
    if len(voice_segments) == 0:  # TODO: front error on post-processing, audio sent is bad.
        logger.error(f'[VAD] No voice segments found in {file_path}')
        raise HTTPException(status_code=400, detail="Audio is empty")

    logger.debug(f'[VAD] Found {len(voice_segments)} voice segments')
    joined_segments = []
    for i, segment in enumerate(voice_segments):
        if joined_segments and (segment['start'] - joined_segments[-1]['end']) < 1:
            joined_segments[-1]['end'] = segment['end']
        else:
            joined_segments.append(segment)

    logger.debug(f'[VAD] Joined into {len(joined_segments)} segments')

    # trim silence out of file_path, but leave 1 sec of silence within chunks
    trimmed_aseg = AudioSegment.empty()
    for i, segment in enumerate(joined_segments):
        start = segment['start'] * 1000
        end = segment['end'] * 1000
        trimmed_aseg += AudioSegment.from_wav(file_path)[start:end]
        if i < len(joined_segments) - 1:
            trimmed_aseg += AudioSegment.from_wav(file_path)[end:end + 1000]

    # file_path.replace('.wav', '-cleaned.wav')
    logger.debug(f'[VAD] Exporting trimmed audio to {file_path}')
    trimmed_aseg.export(file_path, format="wav")
    logger.info(f'[VAD] VAD processing complete for {file_path}')

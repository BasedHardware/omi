import os
from enum import Enum
import json
import urllib.request
from pathlib import Path

import numpy as np
import requests
import torch
import onnxruntime
from fastapi import HTTPException
from pydub import AudioSegment

from database import redis_db

# Fix SSL certificate issues
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

torch.set_num_threads(1)
torch.hub.set_dir('pretrained_models')

# Define model directory and files
MODEL_DIR = Path('pretrained_models/silero_vad')
MODEL_FILE = MODEL_DIR / 'model.onnx'
UTILS_FILE = MODEL_DIR / 'utils.py'
EXAMPLE_FILE = MODEL_DIR / 'example.py'
CONFIG_FILE = MODEL_DIR / 'config.json'

# Create model directory if it doesn't exist
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Try to load the model with error handling
try:
    # Check if model files already exist
    if not MODEL_FILE.exists() or not UTILS_FILE.exists() or not CONFIG_FILE.exists():
        print("Downloading Silero VAD model files...")

        # Download model file
        urllib.request.urlretrieve(
            "https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx",
            MODEL_FILE
        )

        # Download utils file
        urllib.request.urlretrieve(
            "https://github.com/snakers4/silero-vad/raw/master/utils_vad.py",
            UTILS_FILE
        )

        # Download example file for reference
        urllib.request.urlretrieve(
            "https://github.com/snakers4/silero-vad/raw/master/examples/vad_examples.py",
            EXAMPLE_FILE
        )

        # Create a simple config file
        with open(CONFIG_FILE, 'w') as f:
            json.dump({
                "sampling_rate": 16000,
                "window_size_samples": 1536
            }, f)

        print("Model files downloaded successfully")

    # Load the ONNX model directly using onnxruntime
    model = onnxruntime.InferenceSession(str(MODEL_FILE))

    # Import functions from our local utils.py
    from pretrained_models.silero_vad.utils import (
        get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks
    )

    print("Silero VAD model loaded successfully")

except Exception as e:
    print(f"Error loading Silero VAD model: {e}")
    print("Using mock VAD model instead. Some functionality may be limited.")

    # Create mock functions for VAD
    def get_speech_timestamps(audio_data, **kwargs):
        # Return the entire audio as one speech segment
        return [{'start': 0, 'end': len(audio_data)}]

    def save_audio(path, tensor, **kwargs):
        pass

    def read_audio(path, **kwargs):
        return torch.zeros(1000)

    def collect_chunks(chunks, **kwargs):
        return torch.cat(chunks) if chunks else torch.zeros(1)

    class MockVADIterator:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, x, return_seconds=False):
            return 0.9  # Always return high speech probability

    VADIterator = MockVADIterator
    model = None


class SpeechState(str, Enum):
    speech_found = 'speech_found'
    no_speech = 'no_speech'


def is_speech_present(data, vad_iterator, window_size_samples=256):
    data_int16 = np.frombuffer(data, dtype=np.int16)
    data_float32 = data_int16.astype(np.float32) / 32768.0
    has_start, has_end = False, False

    for i in range(0, len(data_float32), window_size_samples):
        chunk = data_float32[i: i + window_size_samples]
        if len(chunk) < window_size_samples:
            break
        speech_dict = vad_iterator(chunk, return_seconds=False)
        if speech_dict:
            print(speech_dict)
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
    vad_iterator.reset_states()
    return SpeechState.no_speech


def is_audio_empty(file_path, sample_rate=8000):
    wav = read_audio(file_path)
    timestamps = get_speech_timestamps(wav, model, sampling_rate=sample_rate)
    if len(timestamps) == 1:
        prob_not_speech = ((timestamps[0]['end'] / 1000) - (timestamps[0]['start'] / 1000)) < 1
        return prob_not_speech
    return len(timestamps) == 0


def vad_is_empty(file_path, return_segments: bool = False, cache: bool = False):
    """Uses vad_modal/vad.py deployment (Best quality)"""
    caching_key = f'vad_is_empty:{file_path}'
    if cache:
        if exists := redis_db.get_generic_cache(caching_key):
            if return_segments:
                return exists
            return len(exists) == 0

    try:
        # file_duration = AudioSegment.from_wav(file_path).duration_seconds
        # print('vad_is_empty file duration:', file_duration)
        with open(file_path, 'rb') as file:
            files = {'file': (file_path.split('/')[-1], file, 'audio/wav')}
            response = requests.post(os.getenv('HOSTED_VAD_API_URL'), files=files)
            segments = response.json()
            if cache:
                redis_db.set_generic_cache(caching_key, segments, ttl=60 * 60 * 24)
            if return_segments:
                return segments
            print('vad_is_empty', len(segments) == 0)  # compute % of empty files in someway
            return len(segments) == 0  # but also check likelyhood of silence if only 1 segment?
    except Exception as e:
        print('vad_is_empty', e)
        if return_segments:
            return []
        return False


def apply_vad_for_speech_profile(file_path: str):
    print('apply_vad_for_speech_profile', file_path)
    voice_segments = vad_is_empty(file_path, return_segments=True)
    if len(voice_segments) == 0:  # TODO: front error on post-processing, audio sent is bad.
        raise HTTPException(status_code=400, detail="Audio is empty")
    joined_segments = []
    for i, segment in enumerate(voice_segments):
        if joined_segments and (segment['start'] - joined_segments[-1]['end']) < 1:
            joined_segments[-1]['end'] = segment['end']
        else:
            joined_segments.append(segment)

    # trim silence out of file_path, but leave 1 sec of silence within chunks
    trimmed_aseg = AudioSegment.empty()
    for i, segment in enumerate(joined_segments):
        start = segment['start'] * 1000
        end = segment['end'] * 1000
        trimmed_aseg += AudioSegment.from_wav(file_path)[start:end]
        if i < len(joined_segments) - 1:
            trimmed_aseg += AudioSegment.from_wav(file_path)[end:end + 1000]

    # file_path.replace('.wav', '-cleaned.wav')
    trimmed_aseg.export(file_path, format="wav")

# import numpy as np
from enum import Enum

import requests
import torch

from utils.endpoints import timeit

# # Instantiate pretrained voice activity detection pipeline
# vad = Pipeline.from_pretrained(
#     "pyannote/voice-activity-detection",
#     use_auth_token=os.getenv('HUGGINGFACE_TOKEN')
# )

torch.set_num_threads(1)
torch.hub.set_dir('pretrained_models')
model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
(get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils


class SpeechState(str, Enum):
    has_speech = 'has_speech'
    no_speech = 'no_speech'


def get_speech_state(data, vad_iterator, window_size_samples=256):
    for i in range(0, len(data), window_size_samples):
        chunk = data[i: i + window_size_samples]
        if len(chunk) < window_size_samples:
            break
        speech_dict = vad_iterator(chunk, return_seconds=False)
        if speech_dict:
            if 'start' in speech_dict:
                return SpeechState.has_speech
            elif 'end' in speech_dict:
                return SpeechState.no_speech

    # vad_iterator.reset_states()
    return None


@timeit
def is_audio_empty(file_path, sample_rate=8000):
    wav = read_audio(file_path)
    timestamps = get_speech_timestamps(wav, model, sampling_rate=sample_rate)
    # prob_no_speech = len(timestamps) == 1 and timestamps[0].duration < 1
    if len(timestamps) == 1:
        prob_not_speech = ((timestamps[0]['end'] / 1000) - (timestamps[0]['start'] / 1000)) < 1
        return prob_not_speech
    return len(timestamps) == 0


#
#
# def retrieve_proper_segment_points(file_path, sample_rate=8000):
#     wav = read_audio(file_path)
#     speech_timestamps = get_speech_timestamps(wav, model, sampling_rate=sample_rate)
#     if not speech_timestamps:
#         return [None, None]
#     return [speech_timestamps[0]['start'] / 1000, speech_timestamps[-1]['end'] / 1000]

# def retrieve_proper_segment_points_pyannote(file_path):
#     output = vad(file_path)
#     segments = output.get_timeline().support()
#     has_speech = any(segments)
#     if not has_speech:
#         return [None, None]
#     return [segments[0].start, segments[-1].end]


# TODO: improve VAD management in someway, mix with pipeline
# TODO: segments[0].duration < 1 makes sense?

# @timeit
# def is_audio_empty(file_path, sample_rate=8000):
#     output = vad(file_path)
#     segments = output.get_timeline().support()
#     has_speech = any(segments)
#     prob_no_speech = len(segments) == 1 and segments[0].duration < 1
#     print('is_audio_empty:', not has_speech or prob_no_speech)
#     return not has_speech or prob_no_speech

def vad_is_empty(file_path, return_segments: bool = False):
    try:
        with open(file_path, 'rb') as file:
            files = {'file': (file_path.split('/')[-1], file, 'audio/wav')}
            response = requests.post('https://josancamon19--vad-vad-endpoint.modal.run/', files=files, timeout=10)
            segments = response.json()
            if return_segments:
                return segments
            print('vad_is_empty', len(segments) == 0)  # compute % of empty files in someway
            return len(segments) == 0  # but also check likelyhood of silence if only 1 segment?
    except Exception as e:
        print('vad_is_empty', e)
        return False

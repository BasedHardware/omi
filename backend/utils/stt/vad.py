import os

import requests
import torch
from fastapi import HTTPException
from pydub import AudioSegment

from utils.other.endpoints import timeit

torch.set_num_threads(1)
torch.hub.set_dir('pretrained_models')
model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
(get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils


def is_speech_present(data, vad_iterator, window_size_samples=256):
    for i in range(0, len(data), window_size_samples):
        chunk = data[i: i + window_size_samples]
        if len(chunk) < window_size_samples:
            break
        speech_dict = vad_iterator(chunk, return_seconds=False)
        # TODO: should have like a buffer of start? or some way to not keep it, it ends appear first
        #   maybe like, if `end` was last, then return end? TEST THIS

        if speech_dict:
            # print(speech_dict)
            return True
    return False


@timeit
def is_audio_empty(file_path, sample_rate=8000):
    wav = read_audio(file_path)
    timestamps = get_speech_timestamps(wav, model, sampling_rate=sample_rate)
    if len(timestamps) == 1:
        prob_not_speech = ((timestamps[0]['end'] / 1000) - (timestamps[0]['start'] / 1000)) < 1
        return prob_not_speech
    return len(timestamps) == 0


def vad_is_empty(file_path, return_segments: bool = False):
    """Uses vad_modal/vad.py deployment (Best quality)"""
    try:
        with open(file_path, 'rb') as file:
            files = {'file': (file_path.split('/')[-1], file, 'audio/wav')}
            response = requests.post(os.getenv('HOSTED_VAD_API_URL'), files=files)
            segments = response.json()
            if return_segments:
                return segments
            print('vad_is_empty', len(segments) == 0)  # compute % of empty files in someway
            return len(segments) == 0  # but also check likelyhood of silence if only 1 segment?
    except Exception as e:
        print('vad_is_empty', e)
        return False


def apply_vad_for_speech_profile(file_path: str):
    voice_segments = vad_is_empty(file_path, return_segments=True)
    if len(voice_segments) == 0:
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

import numpy as np
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

vad_iterator = VADIterator(model, sampling_rate=8000)  # threshold=0.9
window_size_samples = 256  # 8000


def is_speech_present(data):
    for i in range(0, len(data), window_size_samples):
        chunk = data[i: i + window_size_samples]
        if len(chunk) < window_size_samples:
            break
        speech_dict = vad_iterator(chunk, return_seconds=False)
        if speech_dict:
            # print(speech_dict)
            return True
    return False


def voice_in_bytes(data):
    # Convert audio bytes to a numpy array
    audio_array = np.frombuffer(data, dtype=np.int16)

    # Normalize audio to range [-1, 1]
    audio_tensor = torch.from_numpy(audio_array).float() / 32768.0

    # Ensure the audio is in the correct shape (batch_size, num_channels, num_samples)
    audio_tensor = audio_tensor.unsqueeze(0).unsqueeze(0)

    # Pass the audio tensor to the VAD model
    speech_timestamps = get_speech_timestamps(audio_tensor, model)

    # Check if there's voice in the audio
    if speech_timestamps:
        print("Voice detected in the audio.")
    else:
        print("No voice detected in the audio.")


#
#
# def speech_probabilities(file_path):
#     SAMPLING_RATE = 8000
#     vad_iterator = VADIterator(model, sampling_rate=SAMPLING_RATE)
#     wav = read_audio(file_path, sampling_rate=SAMPLING_RATE)
#     speech_probs = []
#     window_size_samples = 512 if SAMPLING_RATE == 16000 else 256
#     for i in range(0, len(wav), window_size_samples):
#         chunk = wav[i: i + window_size_samples]
#         if len(chunk) < window_size_samples:
#             break
#         speech_prob = model(chunk, SAMPLING_RATE).item()
#         speech_probs.append(speech_prob)
#     vad_iterator.reset_states()  # reset model states after each audio
#     print(speech_probs[:10])  # first 10 chunks predicts
#
#
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

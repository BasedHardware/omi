import json
import os
from collections import defaultdict
from typing import List, Optional

import modal.gpu
import torch
from fastapi import File, UploadFile, Form
from modal import App, web_endpoint, Secret, Image
from pydantic import BaseModel
from pydub import AudioSegment
from speechbrain.inference.speaker import SpeakerRecognition

from utils.stt.speech_profile import get_speech_profile_expanded, get_people_with_speech_samples


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class ResponseItem(BaseModel):
    is_user: bool
    person_id: Optional[str] = None


device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = SpeakerRecognition.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="pretrained_models/spkrec-ecapa-voxceleb",
    run_opts={"device": device},
)


def sample_same_speaker_as_segment(sample_audio: str, segment: str) -> float:
    try:
        score, prediction = model.verify_files(sample_audio, segment)
        if bool(prediction[0]):
            return float(score[0])
        return 0
    except Exception as e:
        print(e)
        return 0


def classify_segments(
        audio_file_path: str, profile_path: str, people: List[dict], segments: List[TranscriptSegment]
):
    matches = [{'is_user': False, 'person_id': None}] * len(segments)
    if not profile_path:
        return matches

    # TODO: do per segment cleaning later. 1 by 1, maybe running pyannote VAD here (gpu), or using silero
    # cleaning start, end doesn't do anything, cause segments are already pointing that

    print('Duration:', AudioSegment.from_wav(audio_file_path).duration_seconds)

    file_name = os.path.basename(audio_file_path)
    for i, segment in enumerate(segments):

        duration = segment.end - segment.start
        by_chunk_matches = defaultdict(float)

        for j in range(0, int(duration), 30):
            start = segment.start + j
            end = min(segment.end, start + 30)

            temporal_file = f"_temp/{file_name}_{start}_{end}.wav"
            AudioSegment.from_wav(audio_file_path)[start * 1000:end * 1000].export(temporal_file, format="wav")

            by_chunk_matches['user'] += sample_same_speaker_as_segment(temporal_file, profile_path)
            for person in people:
                by_chunk_matches[person['id']] += sample_same_speaker_as_segment(temporal_file, person['path'])

            os.remove(temporal_file)

        if not by_chunk_matches:
            continue
        print(by_chunk_matches)
        max_match = max(by_chunk_matches, key=by_chunk_matches.get)
        matches[i] = {'is_user': max_match == 'user', 'person_id': None if max_match == 'user' else max_match}

    return matches


app = App(name='speech_profile')
image = (
    Image.debian_slim()
    .apt_install('ffmpeg')
    .pip_install("torch")
    .pip_install("torchaudio")
    .pip_install("torchvision")
    .pip_install("speechbrain")
    .pip_install("pydub")
    .pip_install("requests")
    .pip_install("google-cloud-storage")
    .pip_install("redis")
)

os.makedirs('_temp', exist_ok=True)


@app.function(
    image=image,
    keep_warm=1,
    memory=(1024, 2048),
    allow_concurrent_inputs=2,
    cpu=4,
    gpu=modal.gpu.T4(count=1),
    secrets=[Secret.from_name('huggingface-token'), Secret.from_name('envs'), Secret.from_name("gcp-credentials")],
)
@web_endpoint(method='POST')
def endpoint(uid: str, audio_file: UploadFile = File(...), segments: str = Form(...)) -> List[ResponseItem]:
    """
    This endpoint obtains the user (speech profile + samples) + all user people speech samples
    and every segment from the transcript from the stt model, and classifies each segment to a person or to the user.

    :return: List of ResponseItem with is_user and person_id.
    """
    profile_path = get_speech_profile_expanded(uid)
    default = [{'is_user': False}] * len(json.loads(segments))

    if not profile_path:
        return default

    with open(audio_file.filename, 'wb') as f:
        f.write(audio_file.file.read())

    segments_data = json.loads(segments)
    transcript_segments = [TranscriptSegment(**segment) for segment in segments_data]

    # people = get_people_with_speech_samples(uid)
    people = []
    try:
        result = classify_segments(audio_file.filename, profile_path, people, transcript_segments)
        print(result)
        return result
    except:
        return default
    finally:
        os.remove(profile_path)
        os.remove(audio_file.filename)

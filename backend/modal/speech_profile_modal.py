import json
import os
from typing import List

import modal.gpu
import torch
from fastapi import File, UploadFile, Form
from modal import App, web_endpoint, Secret, Image
from pydantic import BaseModel
from pydub import AudioSegment
from speechbrain.inference.speaker import SpeakerRecognition


class TranscriptSegment(BaseModel):
    start: float
    end: float


device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = SpeakerRecognition.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="pretrained_models/spkrec-ecapa-voxceleb",
    run_opts={"device": device},
)


def sample_same_speaker_as_segment(sample_audio: str, segment: str) -> bool:
    try:
        score, prediction = model.verify_files(sample_audio, segment)
        print(score, prediction)
        # return bool(score[0] > 0.6)
        return bool(prediction[0])
    except Exception as e:
        print(e)
        return False


def classify_segments(audio_file: str, transcript_segments: List[TranscriptSegment], profile_path: str):
    print('classify_segments')
    matches = [False] * len(transcript_segments)
    if not profile_path:
        return matches

    for i, segment in enumerate(transcript_segments):
        file_name = os.path.basename(audio_file)
        temporal_file = f"_temp/{file_name}_{segment.start}_{segment.end}.wav"
        AudioSegment.from_wav(audio_file)[segment.start * 1000:segment.end * 1000].export(temporal_file, format="wav")

        is_user = sample_same_speaker_as_segment(temporal_file, profile_path)
        print('Matches', is_user, temporal_file)
        matches[i] = is_user

        os.remove(temporal_file)
    return matches


app = App(name='speech_profile')
image = (
    Image.debian_slim()
    .apt_install('ffmpeg')
    .pip_install("torch")
    .pip_install("torchaudio")
    .pip_install("speechbrain")
    .pip_install("pydub")
)

os.makedirs('_temp', exist_ok=True)


@app.function(
    image=image,
    keep_warm=1,
    memory=(1024, 2048),
    allow_concurrent_inputs=2,
    cpu=4,
    gpu=modal.gpu.T4(count=1),
    secrets=[Secret.from_name('huggingface-token')],
)
@web_endpoint(method='POST')
def endpoint(
        profile_path: UploadFile = File(...), audio_file: UploadFile = File(...), segments: str = Form(...)
) -> List[bool]:

    with open(profile_path.filename, 'wb') as f:
        f.write(profile_path.file.read())

    with open(audio_file.filename, 'wb') as f:
        f.write(audio_file.file.read())

    segments_data = json.loads(segments)
    transcript_segments = [TranscriptSegment(**segment) for segment in segments_data]

    try:
        result = classify_segments(audio_file.filename, transcript_segments, profile_path.filename)
        return result
    finally:
        # Clean up temporary files
        os.remove(profile_path.filename)
        os.remove(audio_file.filename)

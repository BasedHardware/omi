"""Local stand-in for the hosted speaker-embedding service (backend/diarizer, `/v2/embedding`).

Only the voiceprint the speech profile needs: the public wespeaker-voxceleb-resnet34-LM model,
the same one production's v2 endpoint uses. Started by dev-up-real.sh when ~/.venvs/omi-embedding
exists; the backend reaches it through HOSTED_SPEAKER_EMBEDDING_API_URL.
"""

import io
from typing import List

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, File, UploadFile
from pyannote.audio import Inference, Model

app = FastAPI()
model = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM")
inference = Inference(model, window="whole")


@app.post("/v2/embedding")
def embedding_v2(file: UploadFile = File(...)) -> List[float]:
    samples, rate = sf.read(io.BytesIO(file.file.read()), dtype="float32", always_2d=True)
    waveform = torch.from_numpy(np.ascontiguousarray(samples.T))
    return inference({"waveform": waveform, "sample_rate": rate}).tolist()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

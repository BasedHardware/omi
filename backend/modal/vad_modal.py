import os
import uuid

import torch
from fastapi import UploadFile
from modal import App, web_endpoint, Secret, Image
from pyannote.audio import Pipeline

# Instantiate pretrained voice activity detection pipeline
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
vad = Pipeline.from_pretrained(
    "pyannote/voice-activity-detection",
    use_auth_token=os.getenv('HUGGINGFACE_TOKEN')
).to(device)

app = App(name='vad')
image = (
    Image.debian_slim()
    .pip_install("pyannote.audio")
    .pip_install("torch")
    .pip_install("torchaudio")
)

os.makedirs('_temp', exist_ok=True)


@app.function(
    image=image,
    keep_warm=0,
    memory=(1024, 2048),
    cpu=4,
    secrets=[Secret.from_name('huggingface-token')],
)
@web_endpoint(method='POST')
def endpoint(file: UploadFile):
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    output = vad(file_path)
    segments = output.get_timeline().support()
    os.remove(file_path)
    data = []
    for segment in segments:
        data.append({
            'start': segment.start,
            'end': segment.end,
            'duration': segment.duration,
        })
    return data

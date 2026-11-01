import os
import uuid
from typing import Any, Dict, List

import torch  # type: ignore[reportMissingImports]  # torch not installed in dev venv
from fastapi import UploadFile
from pyannote.audio import Pipeline  # type: ignore[reportMissingImports]  # pyannote.audio not installed in dev venv

# Instantiate pretrained voice activity detection pipeline.
# torch 2.6+ defaults torch.load to weights_only=True. The trusted
# pyannote/voice-activity-detection checkpoint pickles a Lightning
# ModelCheckpoint, and that default raises UnpicklingError. Prod models:00377ac
# loaded this same checkpoint with the older default. The parakeet embedding
# loader uses the same trusted-checkpoint override.
device: Any = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # type: ignore[reportUnknownMemberType]  # torch untyped
_orig_torch_load: Any = torch.load


def _load_trusted_vad_checkpoint(*args: Any, **kwargs: Any) -> Any:
    return _orig_torch_load(*args, **{**kwargs, "weights_only": False})


torch.load = _load_trusted_vad_checkpoint  # type: ignore[method-assign]
vad: Any = None
try:
    vad = Pipeline.from_pretrained(  # type: ignore[reportUnknownMemberType]  # pyannote untyped
        "pyannote/voice-activity-detection", use_auth_token=os.getenv('HUGGINGFACE_TOKEN')
    ).to(device)
finally:
    torch.load = _orig_torch_load  # type: ignore[method-assign]

os.makedirs('_temp', exist_ok=True)


def vad_endpoint(file: UploadFile) -> List[Dict[str, float]]:
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    output: Any = vad(file_path)
    segments: Any = output.get_timeline().support()
    os.remove(file_path)
    data: List[Dict[str, float]] = []
    for segment in segments:
        seg: Any = segment
        data.append(
            {
                'start': float(seg.start),
                'end': float(seg.end),
                'duration': float(seg.duration),
            }
        )
    return data

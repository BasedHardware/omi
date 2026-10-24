"""Import-safe shared model factory; construct/download only on explicit calls."""

import os
from functools import lru_cache
from typing import Any

try:
    import torch  # type: ignore[reportMissingImports]  # Optional GPU dependency
    from pyannote.audio import Model, Inference  # type: ignore[reportMissingImports]  # Optional GPU dependency
except ImportError:
    torch = None
    Model = None
    Inference = None


@lru_cache(maxsize=2)
def get_embedding_inference(version: int, device_name: str | None = None) -> Any:
    if torch is None or Model is None or Inference is None:
        raise RuntimeError('local embedding requires torch and pyannote')
    device: Any = torch.device(
        device_name if device_name is not None else "cuda" if torch.cuda.is_available() else "cpu"
    )
    if version == 2:
        model = Model.from_pretrained(
            "pyannote/wespeaker-voxceleb-resnet34-LM",
            revision="837717ddb9ff5507820346191109dc79c958d614",
            token=os.getenv('HUGGINGFACE_TOKEN'),
        )
    else:
        model = Model.from_pretrained("pyannote/embedding", token=os.getenv('HUGGINGFACE_TOKEN'))
    inference = Inference(model, window="whole")
    inference.to(device)
    return inference

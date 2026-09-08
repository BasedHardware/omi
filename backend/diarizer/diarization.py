import os
import uuid
from typing import Any, Dict, List

import torch  # type: ignore[reportMissingImports]  # torch not installed in dev venv
from fastapi import UploadFile
from pyannote.audio import Pipeline  # type: ignore[reportMissingImports]  # pyannote.audio not installed in dev venv

# Instantiate pretrained speaker diarization pipeline
device: Any = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # type: ignore[reportUnknownMemberType]  # torch untyped
diarization_pipeline: Any = Pipeline.from_pretrained(  # type: ignore[reportUnknownMemberType]  # pyannote untyped
    "pyannote/speaker-diarization-community-1", token=os.getenv('HUGGINGFACE_TOKEN')
).to(device)

os.makedirs('_temp', exist_ok=True)


def diarization_endpoint(file: UploadFile) -> List[Dict[str, Any]]:
    """
    Perform speaker diarization on an audio file.

    Args:
        file: Audio file (wav, mp3, etc.)

    Returns:
        List of diarization segments with speaker labels, start time, end time
    """
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"

    try:
        # Save uploaded file
        with open(file_path, 'wb') as f:
            f.write(file.file.read())

        # Run diarization
        output: Any = diarization_pipeline(file_path)

        # Extract segments
        data: List[Dict[str, Any]] = []
        for turn, speaker in output.speaker_diarization:
            turn_any: Any = turn
            speaker_any: Any = speaker
            data.append(
                {
                    'speaker': speaker_any,
                    'start': float(turn_any.start),
                    'end': float(turn_any.end),
                    'duration': float(turn_any.end) - float(turn_any.start),
                }
            )

        return data

    finally:
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)

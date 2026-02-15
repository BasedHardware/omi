import os
import shutil
import uuid
import wave

import torch
import torchaudio
from fastapi import HTTPException, UploadFile
from pyannote.audio import Model, Inference

# Minimum audio duration (seconds) for speaker embedding extraction.
# Audio shorter than this crashes wespeaker fbank (see issue #4572).
MIN_EMBEDDING_AUDIO_DURATION = float(os.getenv("MIN_EMBEDDING_AUDIO_DURATION", "0.5"))


def _get_audio_duration_from_file(file_path: str) -> float:
    """Get duration in seconds from an audio file on disk. Returns 0.0 on failure.
    Tries stdlib wave first (header-only, fast) then falls back to torchaudio.info()
    for non-WAV formats (mp3, flac, ogg, etc.)."""
    try:
        with wave.open(file_path, "rb") as wf:
            framerate = wf.getframerate()
            if framerate <= 0:
                return 0.0
            return wf.getnframes() / framerate
    except (wave.Error, EOFError, OSError):
        pass
    try:
        info = torchaudio.info(file_path)
        if info.sample_rate <= 0:
            return 0.0
        return info.num_frames / info.sample_rate
    except Exception:
        return 0.0


def _validate_audio_duration(file_path: str):
    """Validate audio duration is above the minimum threshold. Raises HTTPException if too short."""
    duration = _get_audio_duration_from_file(file_path)
    if duration < MIN_EMBEDDING_AUDIO_DURATION:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "audio_too_short",
                "min_duration": MIN_EMBEDDING_AUDIO_DURATION,
                "actual_duration": round(duration, 3),
            },
        )


# Instantiate pretrained speaker embedding model
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
embedding_model = Model.from_pretrained("pyannote/embedding", token=os.getenv('HUGGINGFACE_TOKEN'))
embedding_inference = Inference(embedding_model, window="whole")
embedding_inference.to(device)

# Instantiate wespeaker-voxceleb-resnet34-LM model for v2
embedding_model_v2 = Model.from_pretrained(
    "pyannote/wespeaker-voxceleb-resnet34-LM", token=os.getenv('HUGGINGFACE_TOKEN')
)
embedding_inference_v2 = Inference(embedding_model_v2, window="whole")
embedding_inference_v2.to(device)

os.makedirs('_temp', exist_ok=True)


def embedding_endpoint(file: UploadFile):
    """
    Extract speaker embedding from an audio file.

    Args:
        file: Audio file (wav, mp3, etc.)

    Returns:
        Dictionary containing the embedding vector and metadata
    """
    upload_id = str(uuid.uuid4())
    # Sanitize filename to prevent path traversal
    filename = os.path.basename(file.filename)
    file_path = f"_temp/{upload_id}_{filename}"

    try:
        # Save uploaded file in chunks to avoid high memory usage
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)

        # Validate audio duration before inference (issue #4572)
        _validate_audio_duration(file_path)

        # Extract embedding
        embedding = embedding_inference(file_path)

        # Convert numpy array to list for JSON serialization
        return embedding.tolist()

    finally:
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)


def embedding_endpoint_v2(file: UploadFile):
    """
    Extract speaker embedding from an audio file using wespeaker-voxceleb-resnet34-LM model.

    Args:
        file: Audio file (wav, mp3, etc.)

    Returns:
        Dictionary containing the embedding vector and metadata
    """
    upload_id = str(uuid.uuid4())
    # Sanitize filename to prevent path traversal
    filename = os.path.basename(file.filename)
    file_path = f"_temp/{upload_id}_{filename}"

    try:
        # Save uploaded file in chunks to avoid high memory usage
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)

        # Validate audio duration before inference (issue #4572)
        _validate_audio_duration(file_path)

        # Extract embedding using v2 model
        embedding = embedding_inference_v2(file_path)

        # Convert numpy array to list for JSON serialization
        return embedding.tolist()

    finally:
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)

import os
import shutil
import uuid
import wave
from typing import Any, Dict, List, cast

import torch  # type: ignore[reportMissingImports]  # torch not installed in dev venv
import torchaudio  # type: ignore[reportMissingImports]  # torchaudio not installed in dev venv
from fastapi import HTTPException, UploadFile
from pyannote.audio import Model, Inference  # type: ignore[reportMissingImports]  # pyannote.audio not installed in dev venv

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
        info = cast(Any, torchaudio.info(file_path))  # type: ignore[reportUnknownMemberType]  # torchaudio untyped
        if info.sample_rate <= 0:
            return 0.0
        return info.num_frames / info.sample_rate
    except Exception:
        return 0.0


def _validate_audio_duration(file_path: str) -> None:
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
device: Any = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # type: ignore[reportUnknownMemberType]  # torch untyped
embedding_model: Any = Model.from_pretrained("pyannote/embedding", token=os.getenv('HUGGINGFACE_TOKEN'))  # type: ignore[reportUnknownMemberType]  # pyannote untyped
embedding_inference: Any = Inference(embedding_model, window="whole")  # type: ignore[reportUnknownMemberType]  # pyannote untyped
embedding_inference.to(device)  # type: ignore[reportUnknownMemberType]  # pyannote untyped

# Instantiate wespeaker-voxceleb-resnet34-LM model for v2
embedding_model_v2: Any = Model.from_pretrained(  # type: ignore[reportUnknownMemberType]  # pyannote untyped
    "pyannote/wespeaker-voxceleb-resnet34-LM", token=os.getenv('HUGGINGFACE_TOKEN')
)
embedding_inference_v2: Any = Inference(embedding_model_v2, window="whole")  # type: ignore[reportUnknownMemberType]  # pyannote untyped
embedding_inference_v2.to(device)  # type: ignore[reportUnknownMemberType]  # pyannote untyped

os.makedirs('_temp', exist_ok=True)


def _load_audio_for_inference(file_path: str) -> Dict[str, Any]:
    """Load audio into memory to avoid pyannote's TorchCodec file decoder path."""
    waveform, sample_rate = cast(Any, torchaudio.load(file_path))  # type: ignore[reportUnknownMemberType]  # torchaudio untyped
    return {"waveform": waveform, "sample_rate": sample_rate}


def embedding_endpoint(file: UploadFile) -> List[float]:
    """
    Extract speaker embedding from an audio file.

    Args:
        file: Audio file (wav, mp3, etc.)

    Returns:
        Dictionary containing the embedding vector and metadata
    """
    upload_id = str(uuid.uuid4())
    # Sanitize filename to prevent path traversal
    filename = os.path.basename(cast(str, file.filename))
    file_path = f"_temp/{upload_id}_{filename}"

    try:
        # Save uploaded file in chunks to avoid high memory usage
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)

        # Validate audio duration before inference (issue #4572)
        _validate_audio_duration(file_path)

        # Preload waveform to avoid pyannote's TorchCodec file decoder path.
        embedding: Any = embedding_inference(_load_audio_for_inference(file_path))

        # Convert numpy array to list for JSON serialization
        return embedding.tolist()

    finally:
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)


def embedding_endpoint_v2(file: UploadFile) -> List[float]:
    """
    Extract speaker embedding from an audio file using wespeaker-voxceleb-resnet34-LM model.

    Args:
        file: Audio file (wav, mp3, etc.)

    Returns:
        Dictionary containing the embedding vector and metadata
    """
    upload_id = str(uuid.uuid4())
    # Sanitize filename to prevent path traversal
    filename = os.path.basename(cast(str, file.filename))
    file_path = f"_temp/{upload_id}_{filename}"

    try:
        # Save uploaded file in chunks to avoid high memory usage
        with open(file_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)

        # Validate audio duration before inference (issue #4572)
        _validate_audio_duration(file_path)

        # Preload waveform to avoid pyannote's TorchCodec file decoder path.
        embedding: Any = embedding_inference_v2(_load_audio_for_inference(file_path))

        # Convert numpy array to list for JSON serialization
        return embedding.tolist()

    finally:
        # Clean up temporary file
        if os.path.exists(file_path):
            os.remove(file_path)

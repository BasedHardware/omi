import io
import logging
import os
import struct
import wave
from typing import Any, List, Mapping, Optional, Tuple

import numpy as np
import httpx
from scipy.spatial.distance import cdist

from utils.executors import storage_executor, run_blocking
from utils.http_client import get_stt_client

logger = logging.getLogger(__name__)

# Cosine distance threshold for speaker matching
# Based on VoxCeleb 1 test set EER of 2.8%
SPEAKER_MATCH_THRESHOLD = 0.45

SPEAKER_MATCH_MARGIN = float(os.getenv("SPEAKER_MATCH_MARGIN", "0.05"))

# Distance a candidate must beat when no runner-up is close enough to compare
# it against.
#
# The margin needs two candidates to say anything. Against a single enrolled
# person the runner-up is infinitely far away, the margin test cannot fail, and
# SPEAKER_MATCH_THRESHOLD decides alone. That threshold is the equal error rate
# point, where a false accept and a false reject are equally likely -- but here
# they cost very different things. Rejecting costs an unnamed speaker; accepting
# writes one person's voice into another person's enrolment, and every later
# match inherits the mistake.
#
# So the lone-candidate case is held to a stricter distance than the roster
# case. This wants calibrating per embedding model, like the threshold above.
SPEAKER_MATCH_SOLE_THRESHOLD = float(os.getenv("SPEAKER_MATCH_SOLE_THRESHOLD", "0.35"))

# Minimum audio duration (seconds) for speaker embedding extraction.
# Audio shorter than this crashes pyannote wespeaker fbank (see issue #4572).
MIN_EMBEDDING_AUDIO_DURATION = float(os.getenv("MIN_EMBEDDING_AUDIO_DURATION", "0.5"))


def _get_wav_duration(audio_data: bytes) -> float:
    """Get duration in seconds from WAV bytes. Returns 0.0 on parse failure."""
    try:
        with wave.open(io.BytesIO(audio_data), "rb") as wf:
            framerate = wf.getframerate()
            if framerate <= 0:
                return 0.0
            return wf.getnframes() / framerate
    except (wave.Error, EOFError, struct.error):
        return 0.0


def _get_api_url() -> str:
    """Get the speaker embedding API URL from environment."""
    url = os.getenv('HOSTED_SPEAKER_EMBEDDING_API_URL')
    if not url:
        raise ValueError("HOSTED_SPEAKER_EMBEDDING_API_URL environment variable not set")
    return url


def extract_embedding(audio_path: str) -> np.ndarray[Any, Any]:
    """
    Extract speaker embedding from an audio file using hosted API.

    Args:
        audio_path: Path to audio file (wav format recommended)

    Returns:
        numpy array of shape (1, D) where D is embedding dimension
    """
    api_url = _get_api_url()

    with open(audio_path, 'rb') as f:
        files = {'file': (os.path.basename(audio_path), f, 'audio/wav')}
        response = httpx.post(f"{api_url}/v2/embedding", files=files, timeout=300.0)
        response.raise_for_status()

    result = response.json()

    # Handle both formats: direct array or {"embedding": [...]}
    if isinstance(result, list):
        embedding = np.array(result, dtype=np.float32)
    else:
        embedding = np.array(result['embedding'], dtype=np.float32)

    # Ensure shape is (1, D)
    if embedding.ndim == 1:
        embedding = embedding.reshape(1, -1)

    return embedding


def extract_embedding_from_bytes(audio_data: bytes, filename: str = "audio.wav") -> np.ndarray[Any, Any]:
    """
    Extract speaker embedding from audio bytes using hosted API.

    Args:
        audio_data: Raw audio bytes (wav format)
        filename: Filename to use in the request

    Returns:
        numpy array of shape (1, D) where D is embedding dimension

    Raises:
        ValueError: If audio is too short for speaker embedding
    """
    duration = _get_wav_duration(audio_data)
    if duration < MIN_EMBEDDING_AUDIO_DURATION:
        raise ValueError(f"Audio too short for speaker embedding: {duration:.3f}s < {MIN_EMBEDDING_AUDIO_DURATION}s")

    api_url = _get_api_url()

    files = {'file': (filename, audio_data, 'audio/wav')}
    response = httpx.post(f"{api_url}/v2/embedding", files=files, timeout=300.0)
    response.raise_for_status()

    result = response.json()

    # Handle both formats: direct array or {"embedding": [...]}
    if isinstance(result, list):
        embedding = np.array(result, dtype=np.float32)
    else:
        embedding = np.array(result['embedding'], dtype=np.float32)

    # Ensure shape is (1, D)
    if embedding.ndim == 1:
        embedding = embedding.reshape(1, -1)

    return embedding


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


async def async_extract_embedding(audio_path: str) -> np.ndarray[Any, Any]:
    """Async version of extract_embedding using httpx.AsyncClient."""
    api_url = _get_api_url()
    client = get_stt_client()

    file_data = await run_blocking(storage_executor, _read_file, audio_path)

    files = {'file': (os.path.basename(audio_path), file_data, 'audio/wav')}
    try:
        response = await client.post(f"{api_url}/v2/embedding", files=files)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"async_extract_embedding failed for {audio_path}: {e}")
        raise

    result = response.json()
    if isinstance(result, list):
        embedding = np.array(result, dtype=np.float32)
    else:
        embedding = np.array(result['embedding'], dtype=np.float32)

    if embedding.ndim == 1:
        embedding = embedding.reshape(1, -1)
    return embedding


async def async_extract_embedding_from_bytes(audio_data: bytes, filename: str = "audio.wav") -> np.ndarray[Any, Any]:
    """Async version of extract_embedding_from_bytes using httpx.AsyncClient."""
    duration = _get_wav_duration(audio_data)
    if duration < MIN_EMBEDDING_AUDIO_DURATION:
        raise ValueError(f"Audio too short for speaker embedding: {duration:.3f}s < {MIN_EMBEDDING_AUDIO_DURATION}s")

    api_url = _get_api_url()
    client = get_stt_client()

    files = {'file': (filename, audio_data, 'audio/wav')}
    try:
        response = await client.post(f"{api_url}/v2/embedding", files=files)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"async_extract_embedding_from_bytes failed: {e}")
        raise

    result = response.json()
    if isinstance(result, list):
        embedding = np.array(result, dtype=np.float32)
    else:
        embedding = np.array(result['embedding'], dtype=np.float32)

    if embedding.ndim == 1:
        embedding = embedding.reshape(1, -1)
    return embedding


def compare_embeddings(embedding1: np.ndarray[Any, Any], embedding2: np.ndarray[Any, Any]) -> float:
    """
    Compare two speaker embeddings using cosine distance.

    Args:
        embedding1: First embedding array (1, D)
        embedding2: Second embedding array (1, D)

    Returns:
        Cosine distance (0.0 = identical, 2.0 = opposite)
        Lower values indicate more similar speakers.
        Returns 2.0 (max distance) if embeddings have different dimensions.
    """
    if embedding1.shape[1] != embedding2.shape[1]:
        return 2.0
    distance = cdist(embedding1, embedding2, metric="cosine")[0, 0]
    return float(distance)


def is_same_speaker(
    embedding1: np.ndarray[Any, Any], embedding2: np.ndarray[Any, Any], threshold: float = SPEAKER_MATCH_THRESHOLD
) -> Tuple[bool, float]:
    """
    Determine if two embeddings belong to the same speaker.

    Args:
        embedding1: First embedding array
        embedding2: Second embedding array
        threshold: Cosine distance threshold for matching

    Returns:
        Tuple of (is_match, distance)
    """
    distance = compare_embeddings(embedding1, embedding2)
    return distance < threshold, distance


def embedding_to_bytes(embedding: np.ndarray[Any, Any]) -> bytes:
    """
    Serialize embedding to bytes for storage.

    Args:
        embedding: numpy array embedding

    Returns:
        Bytes representation of the embedding
    """
    return embedding.astype(np.float32).tobytes()


def bytes_to_embedding(data: bytes, dim: int = 512) -> np.ndarray[Any, Any]:
    """
    Deserialize embedding from bytes.

    Args:
        data: Bytes representation of embedding
        dim: Embedding dimension (default 512 for pyannote/embedding)

    Returns:
        numpy array of shape (1, D)
    """
    embedding = np.frombuffer(data, dtype=np.float32)
    return embedding.reshape(1, -1)


def find_best_match(
    query_embedding: np.ndarray[Any, Any],
    candidate_embeddings: List[np.ndarray[Any, Any]],
    threshold: float = SPEAKER_MATCH_THRESHOLD,
) -> Optional[Tuple[int, float]]:
    """
    Find the best matching speaker from a list of candidates.

    Args:
        query_embedding: Embedding to match
        candidate_embeddings: List of candidate embeddings
        threshold: Maximum distance for a valid match

    Returns:
        Tuple of (best_index, distance) or None if no match found
    """
    if not candidate_embeddings:
        return None

    best_idx = -1
    best_distance = float('inf')

    for idx, candidate in enumerate(candidate_embeddings):
        distance = compare_embeddings(query_embedding, candidate)
        if distance < best_distance:
            best_distance = distance
            best_idx = idx

    if best_distance < threshold:
        return best_idx, best_distance

    return None


def select_best_match(
    query_embedding: np.ndarray[Any, Any],
    candidates: Mapping[str, np.ndarray[Any, Any]],
    threshold: float = SPEAKER_MATCH_THRESHOLD,
    margin: float = SPEAKER_MATCH_MARGIN,
    sole_threshold: float = SPEAKER_MATCH_SOLE_THRESHOLD,
) -> Tuple[Optional[str], float, bool]:
    """
    Pick the matching candidate only when it is unambiguously the closest.

    As the roster grows the runner-up creeps inside the threshold too, and
    whichever of two similar voices happens to score marginally lower wins. That
    silently attributes one person's speech to another. Requiring the winner to
    beat the runner-up by `margin` turns those near-ties into no-match, which
    surfaces as an unlabelled speaker instead of a confidently wrong name
    (issue #5565).

    A bare threshold is not enough for the other end of that range either. With
    nobody else enrolled there is no runner-up, so the margin cannot speak and
    the threshold decides by itself -- at the equal error rate point, which
    accepts a false match as readily as it rejects a true one. Those are not
    equally priced here, so a lone candidate is held to `sole_threshold`.

    Args:
        query_embedding: Embedding to match
        candidates: Mapping of candidate key to embedding
        threshold: Maximum distance for a valid match
        margin: Minimum distance the runner-up must trail the winner by
        sole_threshold: Maximum distance when no runner-up is inside `threshold`

    Returns:
        Tuple of (key or None, best distance, ambiguous). `ambiguous` is True
        when a candidate was inside the threshold but failed the margin test,
        so callers can distinguish "nobody matched" from "too close to call".
    """
    best_key: Optional[str] = None
    best_distance = float('inf')
    runner_up_distance = float('inf')

    for key, candidate in candidates.items():
        distance = compare_embeddings(query_embedding, candidate)
        if distance < best_distance:
            best_key, runner_up_distance, best_distance = key, best_distance, distance
        elif distance < runner_up_distance:
            runner_up_distance = distance

    if best_key is None or best_distance >= threshold:
        return None, best_distance, False

    if runner_up_distance >= threshold:
        if best_distance >= sole_threshold:
            return None, best_distance, False
        return best_key, best_distance, False

    if runner_up_distance - best_distance < margin:
        return None, best_distance, True

    return best_key, best_distance, False

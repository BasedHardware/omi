import os
from typing import Optional, Tuple

import numpy as np
import requests
from scipy.spatial.distance import cdist

# Cosine distance threshold for speaker matching
# Based on VoxCeleb 1 test set EER of 2.8%
SPEAKER_MATCH_THRESHOLD = 0.45


def _get_api_url() -> str:
    """Get the speaker embedding API URL from environment."""
    url = os.getenv('HOSTED_SPEAKER_EMBEDDING_API_URL')
    if not url:
        raise ValueError("HOSTED_SPEAKER_EMBEDDING_API_URL environment variable not set")
    return url


def extract_embedding(audio_path: str) -> np.ndarray:
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
        response = requests.post(f"{api_url}/v1/embedding", files=files, timeout=300)
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


def extract_embedding_from_bytes(audio_data: bytes, filename: str = "audio.wav") -> np.ndarray:
    """
    Extract speaker embedding from audio bytes using hosted API.

    Args:
        audio_data: Raw audio bytes (wav format)
        filename: Filename to use in the request

    Returns:
        numpy array of shape (1, D) where D is embedding dimension
    """
    api_url = _get_api_url()

    files = {'file': (filename, audio_data, 'audio/wav')}
    response = requests.post(f"{api_url}/v1/embedding", files=files, timeout=300)
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


def compare_embeddings(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """
    Compare two speaker embeddings using cosine distance.

    Args:
        embedding1: First embedding array (1, D)
        embedding2: Second embedding array (1, D)

    Returns:
        Cosine distance (0.0 = identical, 2.0 = opposite)
        Lower values indicate more similar speakers
    """
    distance = cdist(embedding1, embedding2, metric="cosine")[0, 0]
    return float(distance)


def is_same_speaker(
    embedding1: np.ndarray, embedding2: np.ndarray, threshold: float = SPEAKER_MATCH_THRESHOLD
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


def embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """
    Serialize embedding to bytes for storage.

    Args:
        embedding: numpy array embedding

    Returns:
        Bytes representation of the embedding
    """
    return embedding.astype(np.float32).tobytes()


def bytes_to_embedding(data: bytes, dim: int = 512) -> np.ndarray:
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
    query_embedding: np.ndarray, candidate_embeddings: list[np.ndarray], threshold: float = SPEAKER_MATCH_THRESHOLD
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

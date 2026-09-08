import os
from typing import Callable, Sequence

import numpy as np

# Enrollment verification is a separate backend operation fixed at 0.45. These
# defaults are for short, noisy in-session/batch centroid clustering only.
SPEAKER_CLUSTERING_THRESHOLD = float(os.getenv("PARAKEET_SPEAKER_CLUSTERING_THRESHOLD", "0.60"))
SPEAKER_CLUSTERING_MAX_SPEAKERS = max(1, int(os.getenv("PARAKEET_SPEAKER_CLUSTERING_MAX_SPEAKERS", "8")))


def cosine_distance(a: object, b: object) -> float:
    a_vec = np.asarray(a, dtype=np.float32).reshape(-1)
    b_vec = np.asarray(b, dtype=np.float32).reshape(-1)
    denom = float(np.linalg.norm(a_vec) * np.linalg.norm(b_vec))
    if denom <= 0.0:
        return 1.0
    distance = 1.0 - float(np.dot(a_vec, b_vec) / denom)
    return max(0.0, min(2.0, distance))


def select_speaker_cluster(
    embedding: object,
    centroids: Sequence[object],
    distance: Callable[[object, object], float] = cosine_distance,
    *,
    threshold: float = SPEAKER_CLUSTERING_THRESHOLD,
    max_speakers: int = SPEAKER_CLUSTERING_MAX_SPEAKERS,
) -> tuple[int, bool, float, bool]:
    """Choose a cluster, merging to the nearest once the configured cap is full.

    Mirrors utils/stt/speaker_clustering.py (this image cannot import it); the
    tests pin the two copies to the same behavior. The fourth value is True when
    the merge was forced by the cap rather than earned by the threshold, so
    callers can log it and keep the miss out of the centroid running mean.
    """
    if not centroids:
        return 0, True, float("inf"), False

    best_index = 0
    best_distance = float("inf")
    for index, centroid in enumerate(centroids):
        candidate_distance = distance(embedding, centroid)
        if candidate_distance < best_distance:
            best_index = index
            best_distance = candidate_distance

    if best_distance < threshold:
        return best_index, False, best_distance, False
    if len(centroids) < max(1, max_speakers):
        return len(centroids), True, best_distance, False
    return best_index, False, best_distance, True

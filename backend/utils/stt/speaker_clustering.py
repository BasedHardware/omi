"""Policy shared by backend-side speaker-embedding clustering paths."""

from __future__ import annotations

import os
from typing import Any, Callable, Sequence

# Enrollment verification compares a clip to a long-lived, taught voiceprint at
# SPEAKER_MATCH_THRESHOLD=0.45. Online clustering compares short capture clips to
# noisy in-session centroids, so it deliberately has a separate, more permissive
# operating point. This changes clustering only; enrollment verification stays at 0.45.
SPEAKER_CLUSTERING_THRESHOLD = float(os.getenv('SPEAKER_CLUSTERING_THRESHOLD', '0.60'))

# Eight active speakers preserves ordinary group conversations while making a
# pathological run of noisy embeddings finite. Once full, the nearest centroid
# absorbs the clip even when it misses the threshold; audio/text is never dropped.
SPEAKER_CLUSTERING_MAX_SPEAKERS = max(1, int(os.getenv('SPEAKER_CLUSTERING_MAX_SPEAKERS', '8')))


def select_speaker_cluster(
    embedding: Any,
    centroids: Sequence[Any],
    distance: Callable[[Any, Any], float],
    *,
    threshold: float = SPEAKER_CLUSTERING_THRESHOLD,
    max_speakers: int = SPEAKER_CLUSTERING_MAX_SPEAKERS,
) -> tuple[int, bool, float, bool]:
    """Return ``(index, create_new, distance, capped)`` for bounded greedy clustering.

    A miss creates a centroid only while capacity remains. At capacity, the
    nearest existing centroid wins regardless of the threshold — ``capped`` is
    then True so callers can report the forced merge (it is a degraded,
    misattribution-prone outcome, not a match) and keep the miss out of the
    centroid's running mean. Audio/text is never dropped and no overflow ID is
    invented.
    """
    if not centroids:
        return 0, True, float('inf'), False

    best_index = 0
    best_distance = float('inf')
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

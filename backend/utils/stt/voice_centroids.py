"""Bounded clean-speech evidence and Omi v2 voice centroid pooling.

Pure selection/pooling: no model ownership, gallery access or network calls.
Community-1's own embedding space is not the Omi enrollment space below.
"""

import math

import numpy as np

EMBEDDING_MODEL = 'pyannote/wespeaker-voxceleb-resnet34-LM'
EMBEDDING_REVISION = '837717ddb9ff5507820346191109dc79c958d614'
EMBEDDING_SPACE = EMBEDDING_MODEL + ':v2'
COMMUNITY_MODEL_REVISION = '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee'
MAX_CLIPS = 3
MAX_CLIP_SECONDS = 10.0
MIN_CLIP_SECONDS = 0.5


def select_evidence(turns, overlaps=(), *, duration_seconds=None):
    """Return at most three <=10s non-overlapping clean clips per voice.

    Keep the established longest-first final-pass policy, with simultaneous
    speech removed before selection. Crop clocks remain unit-relative.
    """
    selected = {}
    for turn in turns:
        speaker = turn['speaker']
        left, right = float(turn['start']), float(turn['end'])
        if not math.isfinite(left) or not math.isfinite(right):
            continue
        left = max(0.0, left)
        if duration_seconds is not None:
            right = min(right, duration_seconds)
        cuts = [(left, right)] if right > left else []
        for region in overlaps:
            start, end = float(region['start']), float(region['end'])
            if not math.isfinite(start) or not math.isfinite(end) or end <= start:
                continue
            cuts = [(a, b) for l, r in cuts for a, b in ((l, min(r, start)), (max(l, end), r)) if b > a]
        selected.setdefault(speaker, []).extend((l, r) for l, r in cuts if r - l >= MIN_CLIP_SECONDS)
    return {
        speaker: [
            (l, min(r, l + MAX_CLIP_SECONDS))
            for l, r in sorted(clips, key=lambda x: x[1] - x[0], reverse=True)[:MAX_CLIPS]
        ]
        for speaker, clips in sorted(selected.items())
        if clips
    }


def pool_centroids(vectors):
    """Normalize and duration-weight valid clip vectors; missing evidence abstains."""
    valid, seconds, dimension = [], 0.0, None
    for vector, duration in vectors:
        vector = np.asarray(vector, dtype=np.float64).reshape(-1)
        if not math.isfinite(duration) or duration <= 0 or vector.size == 0 or not np.isfinite(vector).all():
            continue
        norm = float(np.linalg.norm(vector))
        if norm <= 0 or not math.isfinite(norm) or dimension is not None and vector.size != dimension:
            continue
        dimension = vector.size
        valid.append((vector / norm, duration))
        seconds += duration
    if not valid:
        return None
    centroid = np.asarray(sum(vector * duration for vector, duration in valid) / seconds)
    norm = float(np.linalg.norm(centroid))
    if norm <= 0 or not math.isfinite(norm) or not np.isfinite(centroid).all():
        return None
    return {'embedding': (centroid / norm).tolist(), 'evidence_seconds': seconds}

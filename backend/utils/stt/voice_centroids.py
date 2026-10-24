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
    result = {}
    for speaker, clips in sorted(selected.items()):
        # Never count the same PCM twice if a provider repeats an interval.
        merged = []
        for left, right in sorted(clips):
            if merged and left < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
            else:
                merged.append((left, right))
        ranked = sorted(merged, key=lambda x: x[1] - x[0], reverse=True)
        chosen, tails = [], []
        # Preserve longest-first, diverse-turn selection, then spend otherwise
        # unused slots on disjoint clean PCM from a long continuous turn.
        for left, right in ranked[:MAX_CLIPS]:
            end = min(right, left + MAX_CLIP_SECONDS)
            chosen.append((left, end))
            if right - end >= MIN_CLIP_SECONDS:
                tails.append((end, right))
        while len(chosen) < MAX_CLIPS and tails:
            left, right = max(tails, key=lambda x: x[1] - x[0])
            tails.remove((left, right))
            end = min(right, left + MAX_CLIP_SECONDS)
            chosen.append((left, end))
            if right - end >= MIN_CLIP_SECONDS:
                tails.append((end, right))
        if chosen:
            result[speaker] = chosen
    return result


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

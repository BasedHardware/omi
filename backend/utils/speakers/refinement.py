"""Bounded v2 refinement of the one speaker evidence record; no IO or text storage."""

import heapq
from math import isfinite
from statistics import median

import numpy as np

from models.speaker_evidence import OWNER, SpeakerCandidate
from utils.speakers import policy


def unit(vector):
    if vector is None:
        return None
    try:
        array = np.asarray(vector, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    norm = np.linalg.norm(array)
    return array / norm if array.size and np.isfinite(array).all() and np.isfinite(norm) and norm > 0 else None


def identities(cluster):
    return {c.person_id for c in cluster.candidates if c.source == 'manual' or c.label_eligible}


def merge_surplus(clusters, centroids, hint, *, channel_ids=()):
    """Closest-first centroid linkage, never exceeding the policy distance.

    Confident identities are transitive cannot-links. Missing or incompatible
    embedding spaces abstain. The target is a hint, never a forced merge.
    """
    if hint is None or len(clusters) <= hint * policy.SURPLUS_RATIO:
        return clusters, centroids, False
    if len(clusters) > 256:
        return clusters, centroids, True
    active = {i: c.model_copy(deep=True) for i, c in enumerate(clusters)}
    vectors = {i: unit(centroids.get(c.id)) for i, c in active.items()}
    # Keep original identity constraints even if a merged candidate abstains.
    constraints = {i: identities(c) for i, c in active.items()}
    channel_ids = set(channel_ids)
    channels = {i: {sid in channel_ids for sid in c.segment_ids} for i, c in active.items()}
    heap = []

    def offer(a, b):
        va, vb = vectors[a], vectors[b]
        if va is None or vb is None or va.shape != vb.shape:
            return
        if len(constraints[a] | constraints[b]) > 1:
            return
        if channel_ids and len(channels[a] | channels[b]) > 1:
            return
        distance = float(1 - np.dot(va, vb))
        if policy.SURPLUS_MERGE.accepts(distance):
            heapq.heappush(heap, (distance, a, b))

    for a in active:
        for b in range(a + 1, len(active)):
            offer(a, b)
    fresh = len(active)
    while heap and len(active) > hint:
        _, a, b = heapq.heappop(heap)
        if a not in active or b not in active:
            continue
        a_vector, b_vector = vectors[a], vectors[b]
        if a_vector is None or b_vector is None:
            continue
        left, right = active.pop(a), active.pop(b)
        weight = max(left.speech_seconds, 0.001)
        other = max(right.speech_seconds, 0.001)
        vectors[fresh] = unit(a_vector * weight + b_vector * other)
        constraints[fresh] = constraints[a] | constraints[b]
        channels[fresh] = channels[a] | channels[b]
        by_key = {(c.person_id, c.source): c for c in left.candidates}
        right_keys = {(c.person_id, c.source): c for c in right.candidates}
        for key, candidate in by_key.items():
            match = right_keys.get(key)
            candidate.label_eligible &= bool(match and match.label_eligible)
            if candidate.source == 'manual' and match is not None:
                # Preserve every explicit excerpt; an older unscoped receipt
                # remains unknown rather than becoming a narrower known scope.
                candidate.segment_ids = (
                    sorted(set(candidate.segment_ids) | set(match.segment_ids))
                    if candidate.segment_ids is not None and match.segment_ids is not None
                    else None
                )
        for key, candidate in right_keys.items():
            if key not in by_key:
                candidate.label_eligible = False
                by_key[key] = candidate
        left.candidates = sorted(by_key.values(), key=lambda c: (-c.probability, c.source, c.person_id))
        left.segment_ids.extend(right.segment_ids)
        left.speech_seconds += right.speech_seconds
        active[fresh] = left
        for i in list(active):
            if i != fresh:
                offer(i, fresh)
        fresh += 1
    return (
        list(active.values()),
        {c.id: vectors[i] for i, c in active.items() if vectors[i] is not None},
        len(active) > hint,
    )


def anchor_owner(clusters, *, channel_ids=(), energies=None, near_field_allowed=False):
    """Channel attribution outranks voice; energy needs repeated strong separation."""
    channel_ids = set(channel_ids)
    energies = energies or {}
    anchored = [c for c in clusters if set(c.segment_ids) <= channel_ids and not identities(c) - {OWNER}]
    method = 'channel'
    if not anchored:
        anchored = [c for c in clusters if any(p.person_id == OWNER and p.label_eligible for p in c.candidates)]
        method = 'voiceprint'
    if not anchored and near_field_allowed and len(clusters) >= 2:
        scored = []
        for cluster in clusters:
            clips = [energies[sid] for sid in cluster.segment_ids if sid in energies and isfinite(energies[sid])]
            # Every competing voice needs measured audio, otherwise loudness
            # ranking could simply be a missing-sample artifact.
            if len(clips) < policy.NEAR_FIELD_MIN_CLIPS or cluster.speech_seconds < policy.MIN_EVIDENCE_SECONDS:
                return 'none'
            scored.append((median(clips), cluster))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        if scored[0][0] >= policy.NEAR_FIELD_MIN_DBFS and scored[0][0] - scored[1][0] >= policy.NEAR_FIELD_GAP_DB:
            winner = scored[0][1]
            if not identities(winner) - {OWNER}:
                anchored, method = [winner], 'near_field'
    if not anchored:
        return 'none'
    for cluster in anchored:
        if method in ('channel', 'near_field') and not identities(cluster) - {OWNER}:
            cluster.candidates = [c for c in cluster.candidates if c.person_id != OWNER or c.source == 'manual']
            cluster.candidates.append(
                SpeakerCandidate(
                    person_id=OWNER,
                    probability=1 if method == 'channel' else 0.95,
                    band='confident',
                    source=method,
                    label_eligible=True,
                )
            )
            cluster.candidates.sort(key=lambda c: (-c.probability, c.source, c.person_id))
    return method


def pcm_energy(pcm):
    samples = np.frombuffer(pcm, dtype='<i2').astype(float) / 32768
    rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0
    return float(20 * np.log10(rms)) if rms > 0 else float('-inf')

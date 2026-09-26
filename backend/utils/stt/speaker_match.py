"""Decision policy for matching a voice clip against enrolled voiceprints.

Kept free of network and scipy imports so the listen socket, the sync pipeline and
their tests can share one implementation of "is this the enrolled speaker?" without
pulling in the embedding client. Distances are cosine distances as produced by
`utils.stt.speaker_embedding.compare_embeddings`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np

# Cosine distance operating point for enrolled-voiceprint verification only.
#
# Measured offline on real enrollments (2026-09-07, scripts/speaker_id_bench): the
# same user's audio from a different session sits at a median distance of 0.40-0.53
# from their stored voiceprint, while other users sit at 0.93. The former 0.45
# (taken from a clean-studio VoxCeleb figure) rejected 40-70% of cross-session
# owner audio at a 0.0% false-accept rate; 0.65 rejects 14-22% at <1% false-accept
# against random users. Same-session audio matches at either value, which is why
# the old constant looked fine in demos. In-session clustering has its own policy in
# speaker_clustering.py and must not silently retune this boundary.
SPEAKER_MATCH_THRESHOLD = 0.65

# A match must also beat the runner-up voiceprint by at least this much. Raising the
# threshold alone would confuse the owner with a taught person in a minority of
# households (owner-vs-own-person distances were measured as low as 0.43); the
# margin keeps "the nearest is clearly nearest" as a second condition.
SPEAKER_MATCH_MARGIN = 0.10

# Live sessions decide on a speaker once this much clip audio has been embedded for
# them (a single long clip, or a few short ones averaged). Two-second clips alone
# had a 17% equal-error rate in the bench against 10% at five seconds.
SPEAKER_MATCH_MIN_EVIDENCE_SECONDS = 5.0

# How many recent clips per diarized speaker feed the running centroid.
SPEAKER_MATCH_MAX_CLIPS = 3


@dataclass(frozen=True)
class SpeakerMatchDecision:
    """Outcome of comparing one query voiceprint against enrolled candidates.

    `person_id` is set only on an accept. `best_id` and both distances are populated
    whenever at least one candidate existed, so callers can log the near-misses that
    a bare boolean would hide.
    """

    person_id: Optional[str]
    best_id: Optional[str]
    best_distance: float
    runner_up_distance: float

    @property
    def accepted(self) -> bool:
        return self.person_id is not None


def select_speaker_match(
    distances: Mapping[str, float],
    *,
    threshold: float = SPEAKER_MATCH_THRESHOLD,
    margin: float = SPEAKER_MATCH_MARGIN,
) -> SpeakerMatchDecision:
    """Pick the enrolled speaker a query belongs to, or nobody.

    Accepts the nearest candidate when its distance is strictly below `threshold`
    and, if there is a runner-up, the runner-up is at least `margin` farther away.
    NaN distances (zero-norm embeddings) never match. Ties keep insertion order.
    """
    best_id: Optional[str] = None
    best = float('inf')
    runner_up = float('inf')
    for candidate_id, distance in distances.items():
        if distance != distance:  # NaN
            continue
        if distance < best:
            best_id, runner_up, best = candidate_id, best, distance
        elif distance < runner_up:
            runner_up = distance
    accepted = best_id is not None and best < threshold and (runner_up - best) >= margin
    return SpeakerMatchDecision(
        person_id=best_id if accepted else None,
        best_id=best_id,
        best_distance=best,
        runner_up_distance=runner_up,
    )


def mean_embedding(embeddings: Sequence[np.ndarray[Any, Any]]) -> np.ndarray[Any, Any]:
    """Length-normalised centroid of (1, D) embeddings, returned as (1, D).

    Averaging a few short clips of one diarized speaker before comparing beat both
    single-clip and majority-vote decisions in the offline bench; the mean is
    renormalised so cosine distance to it behaves like distance to one clip.
    """
    stacked = np.concatenate([np.asarray(e, dtype=np.float32).reshape(1, -1) for e in embeddings], axis=0)
    centroid = stacked.mean(axis=0, keepdims=True)
    norm = float(np.linalg.norm(centroid))
    return centroid / norm if norm > 0 else centroid

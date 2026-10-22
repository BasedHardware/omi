"""One versioned speaker policy; distances are cosine distances, never similarities.

The table is an operating-point calibration, not an empirical posterior fit. Its
anchors preserve existing accept boundaries. Retuning requires a new version and
held-out calibration data; callers must not turn a roster prior into a voice label.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Literal
import os

POLICY_VERSION = 'wespeaker-operating-points-v1'


@dataclass(frozen=True)
class OperatingPoint:
    distance: float
    inclusive: bool = False

    def accepts(self, distance: float) -> bool:
        return isfinite(distance) and (distance <= self.distance if self.inclusive else distance < self.distance)


LIVE = OperatingPoint(0.65)
FINALIZE = OperatingPoint(float(os.getenv('CONVERSATION_SPEAKER_VOICE_MATCH_THRESHOLD', '0.50')))
CONTINUITY = OperatingPoint(0.35)
CROSS_SCOPE_CLUSTER = OperatingPoint(0.60)
CROSS_EPOCH = FINALIZE  # historically shares the finalize env override
ONLINE_CLUSTER = OperatingPoint(float(os.getenv('SPEAKER_CLUSTERING_THRESHOLD', '0.60')))
PARAKEET_CLUSTER = OperatingPoint(float(os.getenv('PARAKEET_SPEAKER_CLUSTERING_THRESHOLD', '0.60')))
BATCH_CLUSTER = OperatingPoint(0.55, inclusive=True)
CONVERSATION_CLUSTER = OperatingPoint(float(os.getenv('CONVERSATION_SPEAKER_AHC_THRESHOLD', '0.70')), inclusive=True)
ABSORB = OperatingPoint(float(os.getenv('CONVERSATION_SPEAKER_ABSORB_DISTANCE', '0.60')))
OWNER_NEAR_MISS_DISTANCE = 0.70
MATCH_MARGIN = 0.10
MIN_EVIDENCE_SECONDS = 5.0
MAX_CLIPS = 3
SIMILARITY_FLOOR = 0.30
ROSTER_PRIOR = 0.10
CALIBRATION = (
    (0.0, 1.0),
    (0.35, 0.98),
    (0.40, 0.95),
    (0.50, 0.90),
    (0.55, 0.85),
    (0.60, 0.80),
    (0.65, 0.75),
    (0.70, 0.65),
    (0.85, 0.30),
    (1.0, 0.05),
    (2.0, 0.0),
)


def probability(distance: float) -> float:
    if not isfinite(distance):
        return 0.0
    if distance <= CALIBRATION[0][0]:
        return CALIBRATION[0][1]
    for (a, pa), (b, pb) in zip(CALIBRATION, CALIBRATION[1:]):
        if distance <= b:
            return pa + (pb - pa) * (distance - a) / (b - a)
    return 0.0


def band(value: float) -> Literal['confident', 'likely', 'unknown']:
    # Strictness agrees with the old finalize/live accept boundaries.
    return (
        'confident'
        if value > probability(FINALIZE.distance)
        else 'likely' if value > probability(LIVE.distance) else 'unknown'
    )

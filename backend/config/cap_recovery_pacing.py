"""Always-on recovery capacity settings, read at the dispatch boundary."""

import math
import os
from dataclasses import dataclass

# One minute of credits, not an hour of backlog dumped at startup. Ordinary
# VAD pieces are capped below this envelope. Oversized legacy plans fail closed.
BURST_SECONDS = 60
UNAVAILABLE_RETRY_SECONDS = 60


@dataclass(frozen=True)
class Limits:
    audio_per_second: float
    holds_per_second: float


def limits() -> Limits:
    audio = float(os.getenv('CAP_HOLD_RECOVERY_AUDIO_HOURS_PER_HOUR', '60'))
    holds = float(os.getenv('CAP_HOLD_RECOVERY_HOLDS_PER_HOUR', '12000')) / 3600
    if not all(math.isfinite(value) and value > 0 for value in (audio, holds)):
        raise ValueError('invalid recovery pacing capacity')
    return Limits(audio, holds)

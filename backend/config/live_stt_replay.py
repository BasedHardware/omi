"""Typed per-target live replay delivery limits; safe defaults need no env."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplayLimits:
    """Endpoint-scoped pacing bounds for failover prefix and live-tail delivery.

    ``rate`` is the audio-time multiple the endpoint accepts (1.0 = real time).
    A slower endpoint retains proportionally less replay audio inside the same
    wall budget; anything it cannot keep up with fails over rather than
    promising delivery past the hard residence bound.
    """

    rate: float = 1.0
    max_frame_bytes: int = 16 * 1024
    queue_packets: int = 2
    queue_wait_seconds: float = 2.0


DEFAULT_REPLAY_LIMITS = ReplayLimits()

_FIELDS = frozenset(ReplayLimits.__dataclass_fields__)


def parse_replay_limits(value: Any) -> ReplayLimits:
    """Validate an optional registry ``replay`` mapping; unknown fields reject."""
    if value is None:
        return DEFAULT_REPLAY_LIMITS
    if not isinstance(value, dict):
        raise ValueError('live STT replay limits must be a mapping')
    if set(value) - _FIELDS:
        raise ValueError('unknown live STT replay limit fields')
    rate = value.get('rate', DEFAULT_REPLAY_LIMITS.rate)
    if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 < rate <= 1.0:
        raise ValueError('live STT replay rate must be in (0, 1]')
    frame = value.get('max_frame_bytes', DEFAULT_REPLAY_LIMITS.max_frame_bytes)
    if type(frame) is not int or not 2 <= frame <= 16384 or frame % 2:
        raise ValueError('live STT replay frame must be an even byte count in [2, 16384]')
    packets = value.get('queue_packets', DEFAULT_REPLAY_LIMITS.queue_packets)
    if type(packets) is not int or not 1 <= packets <= 2:
        raise ValueError('live STT replay queue depth must be in [1, 2]')
    wait = value.get('queue_wait_seconds', DEFAULT_REPLAY_LIMITS.queue_wait_seconds)
    if type(wait) not in (int, float) or not math.isfinite(wait) or not 0 < wait <= 2.0:
        raise ValueError('live STT replay queue wait must be in (0, 2]')
    return ReplayLimits(
        rate=float(rate),
        max_frame_bytes=frame,
        queue_packets=packets,
        queue_wait_seconds=float(wait),
    )

"""Typed per-target live replay delivery limits; safe defaults need no env."""

from __future__ import annotations

from config.refactor_switches import default_on as rollout_default_on

import math
import os
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

NONWINDOW_REPLAY_SETTLE_ENV = 'LISTEN_NONWINDOW_REPLAY_SETTLE_ENABLED'


def nonwindow_replay_settle_enabled() -> bool:
    """Kill switch, default on: a non-window replacement leg whose provider has
    nothing pending settles horizon-aged quiet capture instead of failing over."""
    return rollout_default_on(
        NONWINDOW_REPLAY_SETTLE_ENV,
        os.getenv(NONWINDOW_REPLAY_SETTLE_ENV, 'true').strip().lower() not in {'false', '0', 'off'},
    )


SESSION_LOCAL_EXCLUSION_RELEASE_ENV = 'LISTEN_SESSION_LOCAL_EXCLUSION_RELEASE_ENABLED'
NONWINDOW_EMITTED_TEXT_ACCOUNTING_ENV = 'LISTEN_NONWINDOW_EMITTED_TEXT_ACCOUNTING_ENABLED'


def _default_on(name: str) -> bool:
    return rollout_default_on(name, os.getenv(name, 'true').strip().lower() not in {'false', '0', 'off'})


def session_local_exclusion_release_enabled() -> bool:
    """Kill switch, default on: a provider that left the session only for a
    session-local replay overflow becomes selectable again once a successor
    is adopted, instead of staying excluded for the rest of the session."""
    return _default_on(SESSION_LOCAL_EXCLUSION_RELEASE_ENV)


def nonwindow_emitted_text_accounting_enabled() -> bool:
    """Kill switch, default on: final Soniox text, placed or not, accounts
    tracked speech sends older than the settle grace."""
    return _default_on(NONWINDOW_EMITTED_TEXT_ACCOUNTING_ENV)


REPLAY_PREFIX_MARGIN_ENV = 'LISTEN_REPLAY_PREFIX_MARGIN_SECONDS'
DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS = 1.0
MAX_REPLAY_PREFIX_MARGIN_SECONDS = 10.0


def replay_prefix_margin_seconds() -> float:
    """Audio seconds held back from the replay prefix so paced delivery at the
    endpoint rate finishes inside the prefix wall with slack. ``0`` restores
    the exact-wall prefix (kill switch); unparsable or out-of-range values use
    the default."""
    raw = os.getenv(REPLAY_PREFIX_MARGIN_ENV, '').strip()
    if not raw:
        return DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS
    try:
        margin = float(raw)
    except ValueError:
        return DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS
    if not math.isfinite(margin) or not 0.0 <= margin <= MAX_REPLAY_PREFIX_MARGIN_SECONDS:
        return DEFAULT_REPLAY_PREFIX_MARGIN_SECONDS
    return margin


LIVE_TAIL_CATCHUP_RATE_ENV = 'LISTEN_LIVE_TAIL_CATCHUP_RATE'
DEFAULT_LIVE_TAIL_CATCHUP_RATE = 1.5
MAX_LIVE_TAIL_CATCHUP_RATE = 4.0


def live_tail_catchup_rate() -> float:
    """Multiple of the endpoint's sustained rate at which the live tail pump
    drains a held backlog. ``1`` keeps the tail at the sustained rate, so a
    backlog is permanent until input pauses (kill switch); unparsable or
    out-of-range values use the default. Per-family ceilings apply on top."""
    raw = os.getenv(LIVE_TAIL_CATCHUP_RATE_ENV, '').strip()
    if not raw:
        return DEFAULT_LIVE_TAIL_CATCHUP_RATE
    try:
        rate = float(raw)
    except ValueError:
        return DEFAULT_LIVE_TAIL_CATCHUP_RATE
    if not math.isfinite(rate) or not 1.0 <= rate <= MAX_LIVE_TAIL_CATCHUP_RATE:
        return DEFAULT_LIVE_TAIL_CATCHUP_RATE
    return rate


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

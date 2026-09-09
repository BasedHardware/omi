"""How much of the shared voice allowance one request spends.

Deliberately dependency-free — no Redis, no `av`, no environment. The rate a
surface is charged at is a product decision, and keeping it here lets the
router, the limiter, and their tests read the same policy without standing up
the infrastructure the limiter needs to enforce it.

Who may spend the allowance, and how much of it is left, stays in
``utils.voice_duration_limiter``.
"""

from __future__ import annotations

from enum import Enum
from math import ceil
from typing import Final, Mapping, Optional


class VoiceBudgetSurface(str, Enum):
    """What a request spent its audio on, for metering purposes only.

    The allowance is one pool shared by every voice-message endpoint. The
    surface never changes who may spend it — only the rate.
    """

    PTT = 'ptt'
    VOICE_TYPING = 'voice_typing'


# Dictation is metered at a tenth of the audio it sends. It replaces typing, so
# a user runs it in minutes-long stretches across a working day where a spoken
# question lasts seconds; charged alike, voice typing alone would spend the
# whole two-hour allowance and leave a user none of it for anything else. The
# provider cost this defers is the cheapest on the platform — the typing surface
# is served by the self-hosted Parakeet deployment first (see
# ``config.stt_provider_policy``), not by a per-minute vendor.
#
# This is a cost guard, not an authorization boundary: the surface is whatever
# the client declares, and the ceilings that do exist to stop abuse (the
# per-request body cap, MAX_SESSION_DURATION_S, and fair_use's daily audio
# ceiling) are all unaffected by it.
BUDGET_DIVISOR_BY_SURFACE: Final[Mapping[VoiceBudgetSurface, int]] = {
    VoiceBudgetSurface.PTT: 1,
    VoiceBudgetSurface.VOICE_TYPING: 10,
}


def resolve_budget_surface(raw: Optional[str]) -> VoiceBudgetSurface:
    """Read a client-declared surface, defaulting to the undiscounted rate."""
    try:
        return VoiceBudgetSurface((raw or '').strip().lower())
    except ValueError:
        return VoiceBudgetSurface.PTT


def budget_cost_ms(duration_ms: int, surface: VoiceBudgetSurface = VoiceBudgetSurface.PTT) -> int:
    """What ``duration_ms`` of audio on ``surface`` costs from the allowance.

    A probe (``0``) stays free, and audio carrying any duration always costs at
    least a millisecond: rounding real turns down to nothing would make the
    budget unenforceable one short turn at a time.
    """
    divisor = BUDGET_DIVISOR_BY_SURFACE.get(surface, 1)
    if duration_ms <= 0 or divisor <= 1:
        return duration_ms
    return max(1, ceil(duration_ms / divisor))

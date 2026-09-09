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
# whole two-hour allowance and leave a user none of it for anything else.
#
# This is a cost guard, not an authorization boundary: the surface is whatever
# the client declares, and any client can declare it. Be precise about what
# still bounds a request once it does, because on the voice-message endpoints
# it is less than the names elsewhere in the codebase suggest:
#
# - The per-request body cap (``_MAX_PCM_BODY_BYTES``, 200 MB — roughly 104
#   minutes of 16 kHz mono) is the only per-request ceiling. It is unaffected.
# - ``MAX_SESSION_DURATION_S`` bounds a *streaming* PTT session's reservation.
#   On the batch route it is only the worst case charged when a file's duration
#   cannot be read; it rejects nothing, so it does not bound this discount.
# - ``fair_use``'s daily audio ceiling meters the listen and sync speech
#   pipelines. It is never consulted here.
#
# So the rolling 24 h ``DAILY_BUDGET_MS`` is effectively the only daily ceiling
# on this endpoint, and dividing what a request spends against it raises the
# audio one account can push through in a day by the same factor — from ~2 h to
# ~20 h at the divisor below. That is the intended product trade (dictation is
# served by the self-hosted Parakeet deployment first — see
# ``config.stt_provider_policy`` — not by a per-minute vendor), but it is the
# cost this rate is really buying, and it should be re-priced deliberately.
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

"""Session-scoped live recovery episode state; exactly one per ListenReceiver.

The controller is the single authority on recovery lifecycle and dial
accounting. A provider death opens one wall-clock episode; every real
dial, the paced prefix replay, and the recovery proof must complete
inside it. Proof is the first nonempty successor transcript, or — for an
adopted but silent successor — RECOVERY_HEALTHY_CONNECTED_SECONDS of
connected dwell observed after adoption. Socket acceptance alone never
clears the deadline. A successor dying before proof shares the episode;
one dying after release opens a fresh episode, bounded per session by
MAX_RECOVERY_EPISODES.
Target identities are kept in memory only — never endpoint or user labels.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from enum import Enum
from typing import Any, Callable

from starlette.websockets import WebSocketState

from utils.stt.live_metrics import RECOVERY_ATTEMPTS, provider_family
from config.live_stt_registry import MAX_REGISTRY_TARGETS

# One recovery episode per provider death.
RECOVERY_EPISODE_SECONDS = 60.0
# Each actual dial gets at most this much of the remaining episode.
RECOVERY_DIAL_SECONDS = 5.0
# An adopted, connected successor proves recovery after this healthy dwell,
# even when the provider stays silent and emits no transcript.
RECOVERY_HEALTHY_CONNECTED_SECONDS = 5.0
# max 16 registry targets plus the possible four legacy protocol identities.
MAX_RECOVERY_TARGETS = MAX_REGISTRY_TARGETS + 4
# Bounded recovery work per session: each fresh episode deadline counts once.
MAX_RECOVERY_EPISODES = 20
clock = time.monotonic


def _now() -> float:
    return clock()


# The receiver publishes its controller while constructing provider sockets so
# the chain/connect seams can reserve target identity at the real attempt.
current_recovery: ContextVar['LiveRecoveryController | None'] = ContextVar('stt_current_recovery', default=None)


class RecoveryState(str, Enum):
    serving = 'serving'
    provider_died = 'provider_died'
    recovering = 'recovering'
    replaying = 'replaying'
    recovered = 'recovered'
    exhausted = 'exhausted'
    client_leaving = 'client_leaving'


class LiveRecoveryController:
    def __init__(self, host: Any, clock: Callable[[], float] | None = None) -> None:
        self.host = host
        # Late binding keeps the test fixture's virtual clock in effect even
        # when the controller was constructed before monkeypatching ran.
        self._clock = clock if clock is not None else _now
        self.state = RecoveryState.serving
        self._deadline: float | None = None
        self._adopted = False
        self._leaving = False
        self.attempted_targets: set[str] = set()
        self.dial_attempts = 0
        self._reentry_grants: set[str] = set()
        self._reentry_used: set[str] = set()
        self._cheap_reentry_granted = False
        self._cheap_reentry_used = False
        # The dial that killed the leg, normalized for bounded metric labels.
        self.source_family: str | None = None
        # Proof binding: text and adoption count only for the current
        # candidate; a retired candidate's late callbacks never release.
        self._candidate: Any = None
        self._candidate_text = False
        self._adopted_at: float | None = None
        self.episode_count = 0

    # -- client departure latch (monotonic; a flap cannot resurrect) --------

    def mark_client_leaving(self) -> None:
        self._leaving = True
        if self.state is not RecoveryState.exhausted:
            self.state = RecoveryState.client_leaving

    def _latch_leaving(self) -> bool:
        self._leaving = True
        if self.state is not RecoveryState.exhausted:
            self.state = RecoveryState.client_leaving
        return True

    def client_has_left(self) -> bool:
        """Latch departure on explicit owner evidence only — never socket flags."""
        if self._leaving:
            return True
        state = getattr(self.host, 'state', None)
        if getattr(state, 'active', None) is False:
            return self._latch_leaving()
        shutdown = getattr(state, 'shutdown_event', None)
        if shutdown is not None and shutdown.is_set() is True:
            return self._latch_leaving()
        client = getattr(getattr(self.host, 'request', None), 'websocket', None)
        if (
            getattr(client, 'client_state', None) == WebSocketState.DISCONNECTED
            or getattr(client, 'application_state', None) == WebSocketState.DISCONNECTED
        ):
            return self._latch_leaving()
        return False

    # -- episode ------------------------------------------------------------

    def begin(self, source_socket: Any = None, family: str | None = None) -> None:
        """A provider death opens (or continues) one bounded recovery episode."""
        if self.state in (RecoveryState.exhausted, RecoveryState.client_leaving):
            return
        # A successor that dies before its episode released shares the same
        # deadline; adopted + nonempty text, or the healthy connected dwell,
        # clears it. Each fresh deadline counts against the episode cap.
        if self._deadline is None:
            if self.episode_count >= MAX_RECOVERY_EPISODES:
                self.exhaust()
                return
            self._deadline = self._clock() + RECOVERY_EPISODE_SECONDS
            self.episode_count += 1
        if family is not None:
            self.source_family = family
        # A new death invalidates the previous candidate's adoption/text proof.
        self._candidate = None
        self._candidate_text = False
        self._adopted = False
        self._adopted_at = None
        self.state = RecoveryState.provider_died

    def set_candidate(self, token: Any) -> None:
        """Bind proof to this candidate before its replay prefix starts."""
        if self.state in (RecoveryState.exhausted, RecoveryState.client_leaving):
            return
        self._candidate = token
        self._candidate_text = False
        self._adopted = False
        self._adopted_at = None

    def replaying(self) -> None:
        if self.state not in (RecoveryState.exhausted, RecoveryState.client_leaving):
            self.state = RecoveryState.replaying

    def _release(self) -> None:
        if self.state in (RecoveryState.exhausted, RecoveryState.client_leaving):
            return
        if self.client_has_left():
            return
        if self._adopted and self._candidate_text:
            self._deadline = None
            self.state = RecoveryState.recovered

    def adopted(self, token: Any = None) -> None:
        """Frozen prefix written and leg adopted; the deadline still waits on
        this candidate's text, or on RECOVERY_HEALTHY_CONNECTED_SECONDS of
        connected healthy dwell observed through note_healthy_connection."""
        if self.state in (RecoveryState.exhausted, RecoveryState.client_leaving):
            return
        if self._candidate is not None and token is not None and token is not self._candidate:
            return
        if self._adopted_at is None:
            self._adopted_at = self._clock()
        self._adopted = True
        self._release()

    def note_transcript(self, nonempty: bool = True, candidate: Any = None) -> None:
        """Nonempty text binds to the current candidate only. An unattributed
        or retired-candidate callback — even from the same family — never
        releases the episode."""
        if not nonempty or candidate is None or candidate is not self._candidate:
            return
        self._candidate_text = True
        self._release()

    def note_healthy_connection(self, candidate: Any = None) -> None:
        """The owner observed the current candidate's socket alive.

        An adopted successor that stays connected for the healthy dwell
        satisfies the episode's lifecycle proof: the deadline releases to
        ``recovered`` without transcript text. It is lifecycle proof only —
        not transcript or availability evidence — so it never synthesizes
        ``note_transcript``, emits no provider-health observation, and never
        settles a pending leg outcome; those still need real emitted text
        (or the owner's own terminal settlement). No dwell is credited
        before adoption, and a stale candidate's health never releases.
        """
        if self.state in (RecoveryState.exhausted, RecoveryState.client_leaving):
            return
        if self._deadline is None or self._adopted_at is None:
            return
        if candidate is None or candidate is not self._candidate or not self._adopted:
            return
        if self.client_has_left():
            return
        if self._clock() - self._adopted_at < RECOVERY_HEALTHY_CONNECTED_SECONDS:
            return
        self._deadline = None
        self.state = RecoveryState.recovered

    def exhaust(self) -> None:
        if not self.client_has_left():
            self.state = RecoveryState.exhausted

    @property
    def exhausted(self) -> bool:
        return self.state is RecoveryState.exhausted

    # -- wall budget ---------------------------------------------------------

    def now(self) -> float:
        return self._clock()

    @property
    def deadline(self) -> float | None:
        return self._deadline

    def remaining(self) -> float | None:
        if self._deadline is None:
            return None
        return self._deadline - self._clock()

    def episode_expired(self) -> bool:
        remaining = self.remaining()
        return remaining is not None and remaining <= 0

    def dial_budget(self) -> float:
        """Per-dial bound: the smaller of the fixed dial cap and episode left."""
        remaining = self.remaining()
        if remaining is None:
            return RECOVERY_DIAL_SECONDS
        return min(RECOVERY_DIAL_SECONDS, max(0.0, remaining))

    # -- attempt accounting ---------------------------------------------------

    def grant_soniox_reentry(self, identity: str) -> bool:
        """Grant at most one repeat dial per session (Soniox rescue/reconnect).
        Granting the same still-unused identity is idempotent; a different
        identity, or any grant once a repeat has been consumed, is refused.
        Granting never resets the episode deadline."""
        if self._reentry_used:
            return False
        if self._reentry_grants and identity not in self._reentry_grants:
            return False
        self._reentry_grants.add(identity)
        return True

    def grant_cheap_reentry(self, identity: str) -> bool:
        """One lease-expiry failback, independent of transient Soniox rescue."""
        if self._cheap_reentry_granted or identity != 'parakeet-window':
            return False
        self._cheap_reentry_granted = True
        return True

    def _cheap_reentry_available(self, identity: str) -> bool:
        return identity == 'parakeet-window' and self._cheap_reentry_granted and not self._cheap_reentry_used

    def mark_attempted(self, identity: str) -> None:
        """Record a real dial whose reservation happened outside the seam
        (e.g. a test harness socket factory that bypasses the chain)."""
        if identity not in self.attempted_targets:
            self.attempted_targets.add(identity)
            self.dial_attempts += 1

    def _blocked(self) -> bool:
        return self._leaving or self.state is RecoveryState.exhausted or self.episode_expired()

    def admission_open(self) -> bool:
        """Whether any further dial is possible: budget left or a granted,
        unused transient re-entry remains."""
        if self._blocked():
            return False
        if len(self.attempted_targets) < MAX_RECOVERY_TARGETS:
            return True
        return bool(self._reentry_grants - self._reentry_used) or self._cheap_reentry_available('parakeet-window')

    def can_attempt(self, identity: str) -> bool:
        if self._blocked():
            return False
        if identity in self.attempted_targets:
            return (
                identity in self._reentry_grants and identity not in self._reentry_used
            ) or self._cheap_reentry_available(identity)
        return len(self.attempted_targets) < MAX_RECOVERY_TARGETS

    def reserve(self, identity: str, successor: str | None = None) -> bool:
        """Count a real connection once, just before it is dialed. A target's
        second dial is refused except one granted transient re-entry or the
        single bounded no-text lease failback to Parakeet."""
        if self._blocked():
            return False
        if identity in self.attempted_targets:
            if self._cheap_reentry_available(identity):
                self._cheap_reentry_used = True
            elif identity in self._reentry_grants and identity not in self._reentry_used:
                self._reentry_used.add(identity)
            else:
                return False
        else:
            if len(self.attempted_targets) >= MAX_RECOVERY_TARGETS:
                return False
            self.attempted_targets.add(identity)
        self.dial_attempts += 1
        if self._deadline is not None and self.state is RecoveryState.provider_died:
            self.state = RecoveryState.recovering
        # Metric only for actual recovery dials — the initial connect runs
        # before any episode exists; selector probes/capacity skips never
        # reach this seam.
        if self._deadline is not None:
            RECOVERY_ATTEMPTS.labels(
                source=provider_family(self.source_family), successor=provider_family(successor or identity)
            ).inc()
        return True

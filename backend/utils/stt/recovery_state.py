"""Session-scoped live recovery episode state; exactly one per ListenReceiver.

The controller is the single authority on recovery lifecycle and dial
accounting. It owns one wall-clock episode per provider death: every real
dial, the paced prefix replay, and the first nonempty successor transcript
must complete inside it. Socket acceptance alone never clears the deadline.
Target identities are kept in memory only — never endpoint or user labels.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from enum import Enum
from typing import Any, Callable

from starlette.websockets import WebSocketState

from utils.stt.live_metrics import RECOVERY_ATTEMPTS, provider_family

# One recovery episode per provider death.
RECOVERY_EPISODE_SECONDS = 60.0
# Each actual dial gets at most this much of the remaining episode.
RECOVERY_DIAL_SECONDS = 5.0
# max 16 registry targets plus the possible four legacy protocol identities.
MAX_RECOVERY_TARGETS = 20
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
        # The dial that killed the leg, normalized for bounded metric labels.
        self.source_family: str | None = None
        # Proof binding: text and adoption count only for the current
        # candidate; a retired candidate's late callbacks never release.
        self._candidate: Any = None
        self._candidate_text = False

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
        # A successor that dies while its predecessor's text is still unproven
        # shares the same deadline; only adopted + nonempty text clears it.
        if self._deadline is None:
            self._deadline = self._clock() + RECOVERY_EPISODE_SECONDS
        if family is not None:
            self.source_family = family
        # A new death invalidates the previous candidate's adoption/text proof.
        self._candidate = None
        self._candidate_text = False
        self._adopted = False
        self.state = RecoveryState.provider_died

    def set_candidate(self, token: Any) -> None:
        """Bind proof to this candidate before its replay prefix starts."""
        if self.state in (RecoveryState.exhausted, RecoveryState.client_leaving):
            return
        self._candidate = token
        self._candidate_text = False
        self._adopted = False

    def replaying(self) -> None:
        if self.state not in (RecoveryState.exhausted, RecoveryState.client_leaving):
            self.state = RecoveryState.replaying

    def _release(self) -> None:
        if self._adopted and self._candidate_text:
            self._deadline = None
            self.state = RecoveryState.recovered

    def adopted(self, token: Any = None) -> None:
        """Frozen prefix written and leg adopted; the deadline still waits on
        this candidate's text. Adoption without text never clears it."""
        if self.state in (RecoveryState.exhausted, RecoveryState.client_leaving):
            return
        if self._candidate is not None and token is not None and token is not self._candidate:
            return
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

    def exhaust(self) -> None:
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

    def grant_reentry(self, identity: str) -> None:
        """Permit one extra dial of a previously attempted identity (Soniox
        rescue). Tagged separately; it never resets the episode deadline."""
        self._reentry_grants.add(identity)

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
        return bool(self._reentry_grants - self._reentry_used)

    def can_attempt(self, identity: str) -> bool:
        if self._blocked():
            return False
        if identity in self.attempted_targets:
            return identity in self._reentry_grants and identity not in self._reentry_used
        return len(self.attempted_targets) < MAX_RECOVERY_TARGETS

    def reserve(self, identity: str, successor: str | None = None) -> bool:
        """Count a real connection once, just before it is dialed. A target's
        second dial is refused except one granted transient re-entry, shared
        by every transient reconnect/rescue scope."""
        if self._blocked():
            return False
        if identity in self.attempted_targets:
            if not (identity in self._reentry_grants and identity not in self._reentry_used):
                return False
            self._reentry_used.add(identity)
        else:
            if len(self.attempted_targets) >= MAX_RECOVERY_TARGETS:
                return False
            self.attempted_targets.add(identity)
        self.dial_attempts += 1
        # Metric only for actual recovery dials — the initial connect runs
        # before any episode exists; selector probes/capacity skips never
        # reach this seam.
        if self._deadline is not None:
            RECOVERY_ATTEMPTS.labels(
                source=provider_family(self.source_family), successor=provider_family(successor or identity)
            ).inc()
        return True

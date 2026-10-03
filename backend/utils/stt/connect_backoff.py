"""Short per-target connect-refusal backoff for the configured live chain.

A burst of provider refusals at the connect seam (post-upgrade 429s, refused
sockets) is transient-capacity evidence local to this process: it is neither
account nor selection-health evidence, so it never feeds those benches. When
the threshold lands inside a sliding window the target is held out for a short
cooldown, then exactly one exclusive probe re-tests it. Refused probes double
the cooldown up to a cap; a real serving proof resets the gate for that target
only. Outstanding pre-open admissions may still reset the gate, while a
successful reset (or a new probe claim) invalidates their late results, so a
stale callback — or one surviving an eviction — can never re-open or corrupt
a recovering target.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import Callable

REFUSAL_THRESHOLD = 3
REFUSAL_WINDOW_SECONDS = 10.0
INITIAL_COOLDOWN_SECONDS = 2.0
MAX_COOLDOWN_SECONDS = 10.0
MAX_IDENTITIES = 64

PROVIDER_FAMILIES = frozenset({'parakeet', 'modulate', 'soniox', 'deepgram'})


def _bounded_provider(provider: str) -> str:
    return provider if provider in PROVIDER_FAMILIES else 'unknown'


class _TargetState:
    __slots__ = ('provider', 'refusals', 'open', 'cooldown_until', 'cooldown_seconds', 'probe_in_flight', 'epoch')

    def __init__(self, provider: str, cooldown_seconds: float, threshold: int) -> None:
        self.provider = provider
        self.refusals: deque[float] = deque(maxlen=threshold)
        self.open = False
        self.cooldown_until = 0.0
        self.cooldown_seconds = cooldown_seconds
        self.probe_in_flight = False
        self.epoch = 0


class ConnectLease:
    """One admission to dial; finish() is idempotent and stale-safe."""

    def __init__(self, backoff: 'ConnectRefusalBackoff', state: _TargetState, epoch: int, probe: bool) -> None:
        self._backoff = backoff
        self.state = state
        self.epoch = epoch
        self.probe = probe
        self.finished = False

    def finish(self, *, success: bool = False, refused: bool = False) -> None:
        self._backoff.finish_lease(self, success=success, refused=refused)


class ConnectRefusalBackoff:
    """Process-local thresholded per-target refusal gate with one probe slot."""

    def __init__(
        self,
        *,
        threshold: int = REFUSAL_THRESHOLD,
        window_seconds: float = REFUSAL_WINDOW_SECONDS,
        initial_cooldown_seconds: float = INITIAL_COOLDOWN_SECONDS,
        max_cooldown_seconds: float = MAX_COOLDOWN_SECONDS,
        max_identities: int = MAX_IDENTITIES,
        clock: Callable[[], float] = time.monotonic,
        on_event: Callable[[str, str], None] | None = None,
    ) -> None:
        self._threshold = threshold
        self._window_seconds = window_seconds
        self._initial_cooldown_seconds = initial_cooldown_seconds
        self._max_cooldown_seconds = max_cooldown_seconds
        self._max_identities = max_identities
        self._clock = clock
        self.on_event = on_event
        self._states: OrderedDict[str, _TargetState] = OrderedDict()
        self._lock = threading.Lock()

    def _event(self, provider: str, event: str) -> None:
        if self.on_event is not None:
            try:
                self.on_event(provider, event)
            except Exception:
                pass

    def _state(self, identity: str, provider: str) -> _TargetState:
        state = self._states.get(identity)
        if state is None:
            state = _TargetState(_bounded_provider(provider), self._initial_cooldown_seconds, self._threshold)
            self._states[identity] = state
            while len(self._states) > self._max_identities:
                self._states.popitem(last=False)
        else:
            self._states.move_to_end(identity)
        return state

    def reset(self) -> None:
        with self._lock:
            self._states.clear()

    def acquire(self, identity: str, *, provider: str = 'unknown', force: bool = False) -> ConnectLease | None:
        with self._lock:
            state = self._state(identity, provider)
            now = self._clock()
            if not state.open:
                return ConnectLease(self, state, state.epoch, probe=False)
            if state.probe_in_flight or now < state.cooldown_until:
                if force:
                    self._event(state.provider, 'escape')
                    return ConnectLease(self, state, state.epoch, probe=False)
                self._event(state.provider, 'skipped')
                return None
            state.probe_in_flight = True
            state.epoch += 1
            self._event(state.provider, 'probe')
            return ConnectLease(self, state, state.epoch, probe=True)

    def cooldown_until(self, identity: str) -> float:
        with self._lock:
            state = self._states.get(identity)
            return state.cooldown_until if state is not None else 0.0

    def _reset(self, state: _TargetState) -> None:
        announce = state.open or bool(state.refusals)
        state.refusals.clear()
        state.open = False
        state.probe_in_flight = False
        state.cooldown_until = 0.0
        state.cooldown_seconds = self._initial_cooldown_seconds
        state.epoch += 1
        if announce:
            self._event(state.provider, 'reset')

    def finish_lease(self, lease: ConnectLease, *, success: bool, refused: bool) -> None:
        with self._lock:
            if lease.finished:
                return
            lease.finished = True
            state = lease.state
            if lease.epoch != state.epoch:
                return
            now = self._clock()
            if lease.probe:
                state.probe_in_flight = False
                if success:
                    self._reset(state)
                elif refused:
                    state.cooldown_seconds = min(state.cooldown_seconds * 2, self._max_cooldown_seconds)
                    state.cooldown_until = now + state.cooldown_seconds
                else:
                    state.cooldown_until = now + state.cooldown_seconds
                return
            if success:
                self._reset(state)
                return
            if not refused or state.open:
                return
            cutoff = now - self._window_seconds
            while state.refusals and state.refusals[0] <= cutoff:
                state.refusals.popleft()
            state.refusals.append(now)
            if len(state.refusals) >= self._threshold:
                state.open = True
                state.cooldown_until = now + state.cooldown_seconds
                self._event(state.provider, 'opened')


_shared = ConnectRefusalBackoff()


def connect_backoff() -> ConnectRefusalBackoff:
    return _shared

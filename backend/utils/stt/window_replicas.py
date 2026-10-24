"""Process-local live-window GPU quarantine, never a family/fleet bench.

Only ready IPs supplied by the pressure poller may be selected. One failed pod
cannot exclude its siblings; every POST has a distinct bounded admission token
so an old completion cannot heal a newer failure. Discovery owns background work;
the HTTP seam below posts only the admitted audio and shares its queue budget.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import math
import logging
import os
import random
import time
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx

from utils.observability.fallback import record_fallback
from utils.stt.live_metrics import WINDOW_REPLICA_ATTEMPTS
from utils.stt.window_anchor import RawSegment, parse_tdt_segments

logger = logging.getLogger(__name__)


def parse_window_response(
    response: httpx.Response, duration: float, normalize: Callable[[RawSegment], RawSegment]
) -> list[RawSegment]:
    data = response.json()
    if not isinstance(data, dict) or ('text' not in data and 'segments' not in data):
        raise ValueError('Invalid TDT response')
    return [normalize(segment) for segment in parse_tdt_segments(data, duration)]


def service_snapshot_allows(pressure: Any, circuit_state: str, replicas: WindowReplicas) -> bool:
    """Use the admission owner's own fresh/grace math; never invent headroom."""
    if circuit_state != 'closed' or not replicas.service_available():
        return False
    if pressure.ready_replicas():
        return False  # never use the VIP to bypass quarantined known pods
    try:
        minimum = int(os.getenv('PARAKEET_BATCH_PRESSURE_MIN_REPLICAS', '2'))
    except ValueError:
        return False
    return pressure.allows(os.getenv('PARAKEET_BATCH_PRESSURE_POOL_HOST', ''), minimum)


async def post_service_window(
    post: Callable[[bytes], Awaitable[httpx.Response]],
    fail: Callable[..., None],
    normalize: Callable[[RawSegment], RawSegment],
    pcm: bytes,
    duration: float,
) -> list[RawSegment]:
    """One VIP POST during admitted pressure grace; no unknown-pod quarantine."""
    outcome = 'service_error'
    try:
        response = await post(pcm)
        if response.status_code == 503 and response.headers.get('X-Omi-STT-Error') == 'queue_timeout':
            outcome = 'service_queue_timeout'
            fail('capacity_full', capacity_subtype='queue_timeout')
        elif response.status_code in (401, 403, 402, 429):
            fail(
                {
                    401: 'provider_auth_rejected',
                    403: 'provider_auth_rejected',
                    402: 'provider_budget_exhausted',
                    429: 'provider_rate_limited',
                }[response.status_code]
            )
        response.raise_for_status()
        segments = parse_window_response(response, duration, normalize)
        outcome = 'service_text' if segments else 'service_empty'
        record_fallback(
            component='stt_selection',
            from_mode='parakeet',
            to_mode='parakeet',
            reason='timeout',
            outcome='degraded',
        )
        return segments
    except asyncio.CancelledError:
        outcome = 'service_cancelled'
        raise
    finally:
        WINDOW_REPLICA_ATTEMPTS.labels(outcome=outcome).inc()


def can_route_replicas(api_url: str, family_url: str | None, ready: tuple[str, ...]) -> bool:
    """Only the default, internal HTTP family endpoint may use its pod pool."""
    parsed = urlsplit(api_url)
    return api_url == family_url and parsed.scheme == 'http' and parsed.username is None and bool(ready)


class QueueTimeout(TimeoutError):
    """Deadline expired while waiting for the listener's STT semaphore."""


async def post_window(
    wav: bytes, *, url: str, budget: float, get_client: Callable[[], Any], get_semaphore: Callable[[], Any]
) -> httpx.Response:
    """One HTTP attempt; semaphore time consumes the same advertised budget."""
    acquired = False
    try:
        async with asyncio.timeout(budget) as deadline:
            async with get_semaphore():
                acquired = True
                remaining = max(0.0, (deadline.when() or 0) - asyncio.get_running_loop().time())
                remaining = math.floor(remaining * 1000) / 1000
                if remaining <= 0:
                    raise TimeoutError('post budget exhausted at semaphore admission')
                return await get_client().post(
                    url,
                    files={'file': ('audio.wav', wav, 'audio/wav')},
                    headers={
                        'X-Omi-STT-Surface': 'live-window',
                        'X-Omi-STT-Timeout-Seconds': f'{remaining:.3f}',
                    },
                )
    except (TimeoutError, httpx.TimeoutException):
        if not acquired:
            raise QueueTimeout() from None
        raise


@dataclass
class _State:
    generation: int = 0
    failures: int = 0
    until: float = 0.0
    probing: bool = False


@dataclass(frozen=True)
class ReplicaAdmission:
    ip: str
    state: _State
    generation: int

    def url(self, original: str) -> str:
        parsed = urlsplit(original)
        host = f'[{self.ip}]' if ':' in self.ip else self.ip
        return urlunsplit((parsed.scheme, f'{host}:8080', parsed.path, parsed.query, ''))


class WindowReplicas:
    MAX_REPLICAS = 64
    BASE_COOLDOWN_SECONDS = 120.0
    MAX_COOLDOWN_SECONDS = 300.0

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._states: dict[str, _State] = {}
        # Different listener processes must not all start on the first DNS IP.
        self._cursor = random.randrange(self.MAX_REPLICAS)

    def claim(self, ready: tuple[str, ...], *, exclude: frozenset[str] = frozenset()) -> ReplicaAdmission | None:
        candidates = sorted(set(ready))[: self.MAX_REPLICAS]
        if not candidates:
            return None  # missing discovery cannot erase known quarantines
        live = set(candidates)
        # Removed/recreated pods cannot leave permanent state or grow the map.
        self._states = {ip: state for ip, state in self._states.items() if ip in live}
        for ip in candidates:
            self._states.setdefault(ip, _State())
        start = self._cursor % len(candidates)
        self._cursor += 1
        now = self._clock()
        for ip in candidates[start:] + candidates[:start]:
            if ip in exclude:
                continue
            state = self._states.setdefault(ip, _State())
            if state.probing or state.until > now:
                continue
            # Exactly one half-open POST per listener/replica pair. Closed
            # replicas still permit concurrent ordinary traffic.
            if state.failures:
                state.probing = True
            return ReplicaAdmission(ip, state, state.generation)
        return None

    def service_available(self) -> bool:
        """Missing discovery may use the VIP only with some known closed pod.

        No history is not an outage. Open/half-open pods keep their original
        deadlines and probe ownership until fresh identities can name a probe.
        """
        return not self._states or any(state.failures == 0 for state in self._states.values())

    def settle(self, admission: ReplicaAdmission, *, failed: bool | None) -> None:
        state = admission.state
        if state.generation != admission.generation:
            return
        state.probing = False
        if failed is None:
            return  # cancellation is not provider evidence; release the probe
        # A closed-pod success must not invalidate a concurrent failure. A
        # failure or completed half-open probe *does* supersede old results.
        if failed or state.failures:
            state.generation += 1
        if failed:
            state.failures = min(3, state.failures + 1)
            cooldown = min(self.MAX_COOLDOWN_SECONDS, self.BASE_COOLDOWN_SECONDS * 2 ** (state.failures - 1))
            state.until = self._clock() + cooldown
            logger.warning('Parakeet window replica quarantined replica=%s cooldown_seconds=%s', admission.ip, cooldown)
        else:
            state.failures = 0
            state.until = 0.0


window_replicas = WindowReplicas()

import os
import random
import asyncio
import time
import websockets
import logging
from enum import Enum

from utils.metrics import PUSHER_CIRCUIT_BREAKER_STATE

logger = logging.getLogger(__name__)

_CIRCUIT_STATE_MAP = {'closed': 0, 'open': 1, 'half_open': 2}

PusherAPI = os.getenv('HOSTED_PUSHER_API_URL')


# ---------------------------------------------------------------------------
# Circuit Breaker (pod-level singleton)
# ---------------------------------------------------------------------------


class CircuitState(str, Enum):
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'


class PusherCircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open and rejecting connections."""

    pass


class PusherCircuitBreaker:
    """Pod-level circuit breaker for pusher connections.

    Tracks failures across all sessions on this process. When failure rate
    exceeds the threshold, the breaker trips OPEN and all connect attempts
    fail-fast until a cooldown period passes. A single probe is allowed in
    HALF_OPEN state; if it succeeds the breaker closes, if it fails the
    breaker reopens.

    Thread-safety: asyncio is single-threaded per event loop, so no locks
    are needed for state reads/writes. The probe lock ensures only one
    coroutine attempts the HALF_OPEN probe at a time.
    """

    def __init__(
        self,
        failure_threshold: int = 20,
        failure_window: float = 30.0,
        cooldown: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.failure_window = failure_window
        self.cooldown = cooldown

        self._state = CircuitState.CLOSED
        self._failures: list = []  # timestamps of recent failures
        self._opened_at: float = 0.0
        self._probe_lock = asyncio.Lock()
        self._probe_in_progress = False

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self.cooldown:
                self._state = CircuitState.HALF_OPEN
                self._update_metric()
                logger.info("Pusher circuit breaker -> HALF_OPEN (cooldown elapsed)")
        return self._state

    def _update_metric(self):
        PUSHER_CIRCUIT_BREAKER_STATE.set(_CIRCUIT_STATE_MAP.get(self._state.value, 0))

    def record_failure(self):
        now = time.monotonic()
        self._failures.append(now)
        # Evict old failures outside the window
        cutoff = now - self.failure_window
        self._failures = [t for t in self._failures if t > cutoff]
        if self._state == CircuitState.CLOSED and len(self._failures) >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = now
            self._update_metric()
            logger.warning(
                f"Pusher circuit breaker -> OPEN ({len(self._failures)} failures in {self.failure_window}s window)"
            )
        elif self._state == CircuitState.HALF_OPEN:
            # Probe failed — reopen
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            self._probe_in_progress = False
            self._update_metric()
            logger.warning("Pusher circuit breaker -> OPEN (half-open probe failed)")

    def record_success(self):
        if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            logger.info(f"Pusher circuit breaker -> CLOSED (success from {self._state.value})")
        self._state = CircuitState.CLOSED
        self._failures.clear()
        self._probe_in_progress = False
        self._update_metric()

    def can_attempt(self) -> bool:
        """Check if a connection attempt is allowed."""
        state = self.state  # triggers OPEN→HALF_OPEN transition if cooldown elapsed
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN and not self._probe_in_progress:
            return True
        return False

    def acquire_probe(self) -> bool:
        """Try to become the single HALF_OPEN probe. Returns True if acquired."""
        if self.state == CircuitState.HALF_OPEN and not self._probe_in_progress:
            self._probe_in_progress = True
            return True
        return False


# Module-level singleton — shared across all sessions on this process
_circuit_breaker = PusherCircuitBreaker()


def get_circuit_breaker() -> PusherCircuitBreaker:
    return _circuit_breaker


async def connect_to_trigger_pusher(uid: str, sample_rate: int = 8000, retries: int = 3, is_active: callable = None):
    breaker = get_circuit_breaker()
    logger.info(f"connect_to_trigger_pusher {uid} (breaker={breaker.state.value})")

    for attempt in range(retries):
        if is_active is not None and not is_active():
            logger.warning(f"Session ended, aborting Pusher retry {uid}")
            return None

        # Circuit breaker check
        if not breaker.can_attempt():
            logger.warning(f"Pusher circuit breaker OPEN, failing fast {uid}")
            raise PusherCircuitBreakerOpen(f"Circuit breaker open, pusher unavailable {uid}")

        # If HALF_OPEN, only one probe allowed
        is_probe = breaker.state == CircuitState.HALF_OPEN
        if is_probe and not breaker.acquire_probe():
            logger.warning(f"Pusher circuit breaker HALF_OPEN, another probe in progress {uid}")
            raise PusherCircuitBreakerOpen(f"Circuit breaker half-open, probe in progress {uid}")

        try:
            result = await _connect_to_trigger_pusher(uid, sample_rate)
            breaker.record_success()
            return result
        except Exception as error:
            breaker.record_failure()
            logger.error(f'An error occurred: {error} {uid}')
            if attempt == retries - 1:
                raise
            # After breaker trips, don't waste time retrying
            if not breaker.can_attempt():
                logger.warning(f"Pusher circuit breaker tripped during retries, failing fast {uid}")
                raise PusherCircuitBreakerOpen(f"Circuit breaker open during retries {uid}")

        backoff_delay = calculate_backoff_with_jitter(attempt)
        logger.warning(f"Waiting {backoff_delay:.0f}ms before next retry... {uid}")
        await asyncio.sleep(backoff_delay / 1000)

    raise Exception(f'Could not open socket: All retry attempts failed.', uid)


async def _connect_to_trigger_pusher(uid: str, sample_rate: int = 8000):
    try:
        logger.info(f"Connecting to Pusher transcripts trigger WebSocket... {uid}")
        ws_host = PusherAPI.replace("http", "ws")
        socket = await websockets.connect(
            f"{ws_host}/v1/trigger/listen?uid={uid}&sample_rate={sample_rate}",
            ping_interval=30,
            ping_timeout=60,
            close_timeout=3,
        )
        logger.info(f"Connected to Pusher transcripts trigger WebSocket. {uid}")
        return socket
    except Exception as e:
        logger.error(f"Exception in connect_to_transcript_pusher: {e} {uid}")
        raise


# Calculate backoff with jitter
def calculate_backoff_with_jitter(attempt, base_delay=1000, max_delay=15000):
    jitter = random.random() * base_delay
    backoff = min(((2**attempt) * base_delay) + jitter, max_delay)
    return backoff

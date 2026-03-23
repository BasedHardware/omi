"""SafeDeepgramSocket — connection wrapper with auto-keepalive and dead detection (#5870).

This module is intentionally lightweight (no heavy imports) so that unit tests
can import SafeDeepgramSocket without pulling in GCP/Soniox/storage dependencies.

Architecture: SafeDeepgramSocket is the SOLE keepalive owner for a DG connection.
No other layer (GatedDeepgramSocket, transcribe.py) should call keep_alive() directly.
A background daemon thread sends keepalive when idle > keepalive_interval_sec.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KeepaliveConfig:
    """Configuration for auto-keepalive behavior.

    keepalive_interval_sec: send keepalive after this much idle time (must be > 0).
    check_period_sec: how often the background thread checks for idle (must be > 0).

    DG idle timeout is 10s. Default 5s interval with 1s check gives ample margin.
    """

    keepalive_interval_sec: float = 5.0
    check_period_sec: float = 1.0

    def __post_init__(self):
        if self.keepalive_interval_sec <= 0:
            raise ValueError(f'keepalive_interval_sec must be > 0, got {self.keepalive_interval_sec}')
        if self.check_period_sec <= 0:
            raise ValueError(f'check_period_sec must be > 0, got {self.check_period_sec}')


class SafeDeepgramSocket:
    """Wraps a raw Deepgram LiveConnection with auto-keepalive and dead-connection detection.

    Auto-keepalive: A background daemon thread sends keepalive when the connection
    has been idle (no send/finalize) for longer than keepalive_interval_sec.
    Thread starts eagerly in constructor — the main DG socket can be idle from
    creation (e.g. during speech profile phase) and needs protection immediately.

    Dead detection: Monitors send() and keep_alive() return values. When either
    returns False or raises, marks connection as permanently dead (one-way latch).

    This is the SOLE keepalive owner — GatedDeepgramSocket and orchestrator code
    must NOT call keep_alive() directly.
    """

    _is_safe_dg_socket = True  # Marker for duck-type checks (avoids circular import)

    def __init__(
        self,
        dg_connection,
        cfg: Optional[KeepaliveConfig] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._conn = dg_connection
        self._cfg = cfg or KeepaliveConfig()
        self._clock = clock
        self._dg_dead = False
        self._closed = False
        self._lock = threading.Lock()
        self._last_activity: float = self._clock()
        self._keepalive_count = 0
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._keepalive_loop, daemon=True, name='dg-keepalive')
        self._thread.start()

    def _keepalive_loop(self):
        """Background loop: send keepalive when idle > interval."""
        while not self._stop_event.wait(self._cfg.check_period_sec):
            with self._lock:
                if self._dg_dead or self._closed:
                    return
                elapsed = self._clock() - self._last_activity
                if elapsed >= self._cfg.keepalive_interval_sec:
                    self._send_keepalive_locked()

    def _send_keepalive_locked(self):
        """Send keepalive to DG. Caller MUST hold self._lock."""
        try:
            ret = self._conn.keep_alive()
            if ret is False:
                logger.warning('DG keep_alive returned False, connection dead')
                self._dg_dead = True
            else:
                self._keepalive_count += 1
                self._last_activity = self._clock()
        except Exception:
            logger.warning('DG keep_alive exception, connection dead')
            self._dg_dead = True

    @property
    def is_connection_dead(self) -> bool:
        """True if DG connection has been detected as dead."""
        return self._dg_dead

    @property
    def keepalive_count(self) -> int:
        """Number of keepalives successfully sent by the background thread."""
        return self._keepalive_count

    def send(self, data: bytes) -> None:
        """Send audio to DG, marking connection dead if send fails."""
        with self._lock:
            if self._dg_dead or self._closed:
                return
            try:
                ret = self._conn.send(data)
                if ret is False:
                    logger.warning('DG send returned False, connection dead')
                    self._dg_dead = True
                else:
                    self._last_activity = self._clock()
            except Exception:
                logger.warning('DG send exception, connection dead')
                self._dg_dead = True

    def finalize(self) -> None:
        """Flush pending transcript."""
        with self._lock:
            if self._closed:
                return
            self._conn.finalize()
            self._last_activity = self._clock()

    def finish(self) -> None:
        """Stop keepalive thread and close DG connection. Idempotent."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._stop_event.set()
        self._thread.join(timeout=2.0)
        self._conn.finish()

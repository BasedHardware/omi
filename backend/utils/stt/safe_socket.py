"""SafeDeepgramSocket — thin wrapper with dead-connection detection (#5870).

This module is intentionally lightweight (no heavy imports) so that unit tests
can import SafeDeepgramSocket without pulling in GCP/Soniox/storage dependencies.
"""

import logging

logger = logging.getLogger(__name__)


class SafeDeepgramSocket:
    """Wraps a raw Deepgram LiveConnection with dead-connection detection.

    Monitors send() and keep_alive() return values. When either returns False
    or raises, marks connection as permanently dead (one-way latch).

    This ensures dead-detection works regardless of whether a VAD gate is used.
    """

    _is_safe_dg_socket = True  # Marker for duck-type checks (avoids circular import)

    def __init__(self, dg_connection):
        self._conn = dg_connection
        self._dg_dead = False

    @property
    def is_connection_dead(self) -> bool:
        """True if DG connection has been detected as dead."""
        return self._dg_dead

    def send(self, data: bytes) -> None:
        """Send audio to DG, marking connection dead if send fails."""
        if self._dg_dead:
            return
        ret = self._conn.send(data)
        if ret is False:
            logger.warning('DG send returned False, connection dead')
            self._dg_dead = True

    def keep_alive(self):
        """Send keepalive to DG, marking connection dead on failure."""
        if self._dg_dead:
            return False
        try:
            ret = self._conn.keep_alive()
            if ret is False:
                logger.warning('DG keep_alive returned False, connection dead')
                self._dg_dead = True
            return ret
        except Exception:
            logger.warning('DG keep_alive exception, connection dead')
            self._dg_dead = True
            return False

    def finalize(self) -> None:
        """Flush pending transcript."""
        self._conn.finalize()

    def finish(self) -> None:
        """Close DG connection."""
        self._conn.finish()

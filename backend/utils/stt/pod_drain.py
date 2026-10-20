"""Process-wide marker: this listen pod has begun draining (SIGTERM or shutdown).

Once set, uvicorn closes every client websocket with 1012 and tears down
live sessions; any provider leg that dies from then on died because of our
restart, not because the provider failed. ``LiveLegOutcome`` censors those
deaths so a rolling restart cannot feed the cost-gate burst detector.
The marker is one-way for the life of the process.
"""

from __future__ import annotations

import signal
import threading
from typing import Any

_draining = False
_installed = False


def mark_draining() -> None:
    global _draining
    _draining = True


def is_draining() -> bool:
    return _draining


def install_drain_signal_marker() -> None:
    """Chain the server's SIGTERM handler; set the marker first, change nothing else."""
    global _installed
    if _installed or threading.current_thread() is not threading.main_thread():
        return
    previous = signal.getsignal(signal.SIGTERM)

    def handle(signum: int, frame: Any) -> None:
        mark_draining()
        if callable(previous):
            previous(signum, frame)
        elif previous == signal.SIG_DFL:
            signal.signal(signum, signal.SIG_DFL)
            signal.raise_signal(signum)

    signal.signal(signal.SIGTERM, handle)
    _installed = True

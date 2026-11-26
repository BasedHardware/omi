"""Opt-in wall-clock prefix on harness service logs.

The backend's text log format has no time (Cloud Logging stamps records in
production), so a local run cannot say how long a step took. With
``OMI_HARNESS_LOG_TIMESTAMPS=1`` every backend log record and every harness
line starts with the UTC time, to the millisecond:

    02:10:22.899Z INFO utils.conversations.v3...: ...

Off (the default) nothing changes.
"""

from __future__ import annotations

import logging
import os
import time

ENV = "OMI_HARNESS_LOG_TIMESTAMPS"


def enabled() -> bool:
    return os.environ.get(ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def now() -> str:
    wall = time.time()
    return time.strftime("%H:%M:%S", time.gmtime(wall)) + f".{int(wall * 1000) % 1000:03d}Z"


def line(text: str) -> str:
    """A harness-printed line, stamped when the switch is on."""
    return f"{now()} {text}" if enabled() else text


class _Stamped(logging.Formatter):
    def __init__(self, inner: logging.Formatter | None) -> None:
        super().__init__()
        self._inner = inner or logging.Formatter(logging.BASIC_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        wall = record.created
        stamp = time.strftime("%H:%M:%S", time.gmtime(wall)) + f".{int(wall * 1000) % 1000:03d}Z"
        return f"{stamp} {self._inner.format(record)}"


def install() -> bool:
    """Stamp the records of the handlers the backend already configured. Call after importing the app."""
    if not enabled():
        return False
    for handler in logging.getLogger().handlers:
        if not isinstance(handler.formatter, _Stamped):
            handler.setFormatter(_Stamped(handler.formatter))
    return True

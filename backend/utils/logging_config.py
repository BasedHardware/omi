"""Severity-aware logging config for services running on GKE / Cloud Logging.

On GKE the Cloud Logging agent classifies anything a container writes to
**stderr** as ERROR severity, and stdout as INFO/DEFAULT. Python's default
``logging.StreamHandler`` (and ``logging.basicConfig``) targets stderr, so
routine INFO request logs were being ingested as ERROR — drowning out real
failures and producing false-positive alert noise (issues #9136, #9138, #9135).

``configure_split_stream_logging`` routes records below WARNING to stdout and
WARNING/ERROR/CRITICAL to stderr so Cloud Logging severities map correctly,
while preserving the default ``levelname:name:message`` format.
"""

import logging
import sys
from typing import Optional, TextIO


class _MaxLevelFilter(logging.Filter):
    """Only allow records strictly below ``level`` (keeps errors off stdout)."""

    def __init__(self, level: int) -> None:
        super().__init__()
        self._level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self._level


def configure_split_stream_logging(
    level: int = logging.INFO,
    *,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> None:
    """Configure the root logger to split records across stdout/stderr by severity.

    INFO/DEBUG go to stdout (Cloud Logging severity INFO); WARNING and above go
    to stderr (severity ERROR). Replaces any existing root handlers so it is safe
    to call in place of ``logging.basicConfig``.
    """
    out_stream = stdout if stdout is not None else sys.stdout
    err_stream = stderr if stderr is not None else sys.stderr

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(logging.BASIC_FORMAT)

    stdout_handler = logging.StreamHandler(out_stream)
    stdout_handler.setLevel(level)
    stdout_handler.addFilter(_MaxLevelFilter(logging.WARNING))
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(err_stream)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    root.addHandler(stdout_handler)
    root.addHandler(stderr_handler)

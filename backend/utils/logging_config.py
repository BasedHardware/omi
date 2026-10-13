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


class SuccessfulHealthAccessFilter(logging.Filter):
    """Suppress only Uvicorn's routine successful probe access records.

    Platform request logs and failed probes remain available. Unknown record
    shapes pass through so a Uvicorn format change cannot hide failures.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != 'uvicorn.access' or record.levelno != logging.INFO:
            return True
        args = record.args
        if not isinstance(args, tuple) or len(args) != 5:
            return True
        _, method, path, _, status = args
        return not (method in ('GET', 'HEAD') and path in ('/v1/health', '/health', '/ready') and status == 200)


def configure_health_access_logging() -> None:
    """Install once on the emitting logger, independent of its handlers."""
    logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(item, SuccessfulHealthAccessFilter) for item in logger.filters):
        logger.addFilter(SuccessfulHealthAccessFilter())


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

    configure_health_access_logging()

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

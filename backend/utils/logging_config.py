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
import os
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


class CloudRunAccessFilter(logging.Filter):
    """Drop every Uvicorn access record on Cloud Run.

    Cloud Run already writes one ``run.googleapis.com/requests`` entry per
    request, with status, latency and URL, so the stdout access line is a
    duplicate. GKE services (listen, pusher) have no such platform log and keep
    their access lines.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name != 'uvicorn.access'


def running_on_cloud_run() -> bool:
    return bool(os.environ.get('K_SERVICE', '').strip())


def configure_health_access_logging() -> None:
    """Install once on the emitting logger, independent of its handlers."""
    logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(item, SuccessfulHealthAccessFilter) for item in logger.filters):
        logger.addFilter(SuccessfulHealthAccessFilter())
    if running_on_cloud_run() and not any(isinstance(item, CloudRunAccessFilter) for item in logger.filters):
        logger.addFilter(CloudRunAccessFilter())


# Outbound HTTP client libraries log one INFO line per request. The lines are
# the bulk of listen stderr (the batch-metrics poll) and backfill stderr, and
# httpx prints the full URL, including signed GCS query strings. Warnings and
# errors from these loggers still pass.
NOISY_HTTP_CLIENT_LOGGERS = ('httpx', 'httpcore', 'google.resumable_media')


def quiet_http_client_loggers() -> None:
    for name in NOISY_HTTP_CLIENT_LOGGERS:
        logger = logging.getLogger(name)
        if logger.level == logging.NOTSET or logger.level < logging.WARNING:
            logger.setLevel(logging.WARNING)


# NeMo routes every message through this one logger and sets propagate=False,
# so a root-level change never reaches it. The three markers are emitted once
# per GPU batch (timestamps INFO, two Lhotse dataloader warnings). Other
# nemo_logger warnings and errors still pass.
NEMO_LOGGER_NAME = 'nemo_logger'
REPETITIVE_NEMO_MESSAGE_MARKERS = (
    'Timestamps requested, setting decoding timestamps to True',
    'are ignored by Lhotse dataloader',
    'You are using a non-tarred dataset and requested tokenization during data sampling',
)


class RepetitiveNeMoMessageFilter(logging.Filter):
    """Drop NeMo's per-batch timestamps and Lhotse dataloader chatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        return not any(marker in message for marker in REPETITIVE_NEMO_MESSAGE_MARKERS)


def quiet_repetitive_nemo_logs() -> None:
    logger = logging.getLogger(NEMO_LOGGER_NAME)
    if not any(isinstance(item, RepetitiveNeMoMessageFilter) for item in logger.filters):
        logger.addFilter(RepetitiveNeMoMessageFilter())


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
    quiet_http_client_loggers()

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

"""Severity-aware logging setup for the pusher service.

GKE/Cloud Run's logging agent infers Cloud Logging severity from the stream a
line is written to: stdout -> INFO, stderr -> ERROR. Python's
``logging.basicConfig()`` sends every record to stderr, so normal INFO request
logs surface as ERROR severity and bury real errors in the noise (issue #9138).

Split the streams by level so severity is reported correctly: INFO/WARNING go to
stdout, ERROR/CRITICAL go to stderr.
"""

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging to route records to stdout/stderr by level.

    Records below ERROR go to stdout; ERROR and above go to stderr, so the
    Cloud Logging agent tags each line with the correct severity.
    """
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    logging.basicConfig(level=level, handlers=[stdout_handler, stderr_handler])

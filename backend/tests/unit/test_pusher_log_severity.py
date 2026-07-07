"""Regression test for issue #9138: pusher INFO logs surfaced as ERROR severity.

``logging.basicConfig()`` sends every record to stderr, which the GKE/Cloud Run
logging agent tags as ERROR. ``configure_logging`` must split records by level so
INFO/WARNING go to stdout and ERROR/CRITICAL go to stderr.
"""

import logging
import sys

from pusher.logging_config import configure_logging


def _reset_root_logging():
    root = logging.getLogger()
    saved = root.handlers[:]
    saved_level = root.level
    for handler in saved:
        root.removeHandler(handler)
    return saved, saved_level


def _restore_root_logging(saved, saved_level):
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    for handler in saved:
        root.addHandler(handler)
    root.setLevel(saved_level)


def test_configure_logging_routes_by_severity():
    saved, saved_level = _reset_root_logging()
    try:
        configure_logging(logging.INFO)
        handlers = logging.getLogger().handlers
        streams = {h.stream for h in handlers if isinstance(h, logging.StreamHandler)}
        assert sys.stdout in streams
        assert sys.stderr in streams

        stdout_handler = next(h for h in handlers if getattr(h, "stream", None) is sys.stdout)
        stderr_handler = next(h for h in handlers if getattr(h, "stream", None) is sys.stderr)

        info = logging.LogRecord("t", logging.INFO, __file__, 1, "hi", None, None)
        warning = logging.LogRecord("t", logging.WARNING, __file__, 1, "hi", None, None)
        error = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", None, None)

        # INFO/WARNING belong on stdout, never stderr.
        assert stdout_handler.filter(info)
        assert stdout_handler.filter(warning)
        assert not stdout_handler.filter(error)

        # ERROR belongs on stderr only.
        assert error.levelno >= stderr_handler.level
        assert info.levelno < stderr_handler.level
    finally:
        _restore_root_logging(saved, saved_level)

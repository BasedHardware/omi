import io
import logging

import pytest

from utils.logging_config import configure_split_stream_logging


@pytest.fixture
def restore_root_logging():
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        yield
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)


def test_info_goes_to_stdout_and_errors_to_stderr(restore_root_logging):
    out, err = io.StringIO(), io.StringIO()
    configure_split_stream_logging(stdout=out, stderr=err)

    logger = logging.getLogger("pusher.test")
    logger.info("routine request line")
    logger.warning("something suspicious")
    logger.error("real failure")

    stdout_text = out.getvalue()
    stderr_text = err.getvalue()

    # INFO must NOT land on stderr (which GKE would tag as ERROR severity).
    assert "routine request line" in stdout_text
    assert "routine request line" not in stderr_text

    # WARNING and ERROR must land on stderr and stay off stdout.
    assert "something suspicious" in stderr_text
    assert "real failure" in stderr_text
    assert "something suspicious" not in stdout_text
    assert "real failure" not in stdout_text


def test_replaces_existing_root_handlers(restore_root_logging):
    root = logging.getLogger()
    sentinel = logging.NullHandler()
    root.addHandler(sentinel)

    configure_split_stream_logging(stdout=io.StringIO(), stderr=io.StringIO())

    assert sentinel not in root.handlers
    assert len(root.handlers) == 2

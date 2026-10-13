import io
import logging

import pytest

from utils.logging_config import (
    SuccessfulHealthAccessFilter,
    configure_health_access_logging,
    configure_split_stream_logging,
)


@pytest.fixture
def restore_root_logging():
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    access = logging.getLogger('uvicorn.access')
    saved_access_filters = list(access.filters)
    try:
        yield
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)
        access.filters[:] = saved_access_filters


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


@pytest.mark.parametrize('method,path', [('GET', '/health'), ('HEAD', '/v1/health'), ('GET', '/ready')])
def test_successful_health_access_is_filtered(method, path):
    record = logging.LogRecord(
        'uvicorn.access', logging.INFO, '', 0, '%s - "%s %s HTTP/%s" %d', ('127.0.0.1', method, path, '1.1', 200), None
    )
    assert not SuccessfulHealthAccessFilter().filter(record)


@pytest.mark.parametrize(
    'name,level,args',
    [
        ('uvicorn.access', logging.INFO, ('127.0.0.1', 'GET', '/health', '1.1', 503)),
        ('uvicorn.access', logging.INFO, ('127.0.0.1', 'GET', '/v1/conversations', '1.1', 200)),
        ('uvicorn.access', logging.INFO, ('127.0.0.1', 'POST', '/health', '1.1', 200)),
        ('uvicorn.access', logging.INFO, ('127.0.0.1', 'GET', '/health?detail=true', '1.1', 200)),
        ('uvicorn.access', logging.WARNING, ('127.0.0.1', 'GET', '/health', '1.1', 200)),
        ('application', logging.INFO, ('127.0.0.1', 'GET', '/health', '1.1', 200)),
        ('uvicorn.access', logging.INFO, ('unknown record',)),
        ('uvicorn.access', logging.INFO, ()),
    ],
)
def test_probe_filter_preserves_errors_traffic_and_unknown_shapes(name, level, args):
    record = logging.LogRecord(name, level, '', 0, 'message', args, None)
    assert SuccessfulHealthAccessFilter().filter(record)


def test_health_filter_installs_once_and_operates_on_emitting_logger():
    logger = logging.getLogger('uvicorn.access')
    saved_filters = list(logger.filters)
    try:
        logger.filters.clear()
        configure_health_access_logging()
        configure_health_access_logging()
        assert sum(isinstance(item, SuccessfulHealthAccessFilter) for item in logger.filters) == 1
        healthy = logging.LogRecord(
            logger.name, logging.INFO, '', 0, 'probe', ('127.0.0.1', 'GET', '/health', '1.1', 200), None
        )
        failed = logging.LogRecord(
            logger.name, logging.INFO, '', 0, 'probe', ('127.0.0.1', 'GET', '/health', '1.1', 503), None
        )
        assert not logger.filter(healthy)
        assert logger.filter(failed)
    finally:
        logger.filters[:] = saved_filters

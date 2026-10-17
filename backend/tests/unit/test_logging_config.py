import io
import logging

import pytest

from utils.logging_config import (
    CloudRunAccessFilter,
    NEMO_LOGGER_NAME,
    RepetitiveNeMoMessageFilter,
    SuccessfulHealthAccessFilter,
    configure_health_access_logging,
    configure_split_stream_logging,
    NOISY_HTTP_CLIENT_LOGGERS,
    quiet_http_client_loggers,
    quiet_repetitive_nemo_logs,
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


def _access_record(status: int = 200, name: str = 'uvicorn.access') -> logging.LogRecord:
    return logging.LogRecord(
        name, logging.INFO, '', 0, 'access', ('127.0.0.1', 'GET', '/v2/sync-local-files/x', '1.1', status), None
    )


def test_cloud_run_drops_every_access_record(monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'backend')
    logger = logging.getLogger('uvicorn.access')
    saved_filters = list(logger.filters)
    try:
        logger.filters.clear()
        configure_health_access_logging()
        configure_health_access_logging()
        assert sum(isinstance(item, CloudRunAccessFilter) for item in logger.filters) == 1
        assert not logger.filter(_access_record(200))
        assert not logger.filter(_access_record(429))
        assert not logger.filter(_access_record(500))
        assert CloudRunAccessFilter().filter(_access_record(200, name='application'))
    finally:
        logger.filters[:] = saved_filters


@pytest.mark.parametrize('value', [None, '', '  '])
def test_outside_cloud_run_access_records_are_kept(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('K_SERVICE', raising=False)
    else:
        monkeypatch.setenv('K_SERVICE', value)
    logger = logging.getLogger('uvicorn.access')
    saved_filters = list(logger.filters)
    try:
        logger.filters.clear()
        configure_health_access_logging()
        assert not any(isinstance(item, CloudRunAccessFilter) for item in logger.filters)
        assert logger.filter(_access_record(200))
    finally:
        logger.filters[:] = saved_filters


def _nemo_record(message: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(NEMO_LOGGER_NAME, level, 'nemo.py', 1, message, (), None)


def test_repetitive_nemo_messages_are_dropped_and_other_records_pass():
    message_filter = RepetitiveNeMoMessageFilter()
    dropped = (
        'Timestamps requested, setting decoding timestamps to True. Capture them in Hypothesis object',
        'The following configuration keys are ignored by Lhotse dataloader: use_start_end_token',
        'You are using a non-tarred dataset and requested tokenization during data sampling (pretokenize=True).',
    )
    for message in dropped:
        assert not message_filter.filter(_nemo_record(message, logging.WARNING))
    assert message_filter.filter(_nemo_record('CUDA out of memory', logging.ERROR))
    assert message_filter.filter(
        _nemo_record("Option 'tarred_random_access' is deprecated and replaced.", logging.WARNING)
    )
    broken = logging.LogRecord(NEMO_LOGGER_NAME, logging.ERROR, 'nemo.py', 1, 'bad %s %s', ('only',), None)
    assert message_filter.filter(broken)


def test_quiet_repetitive_nemo_logs_installs_once_on_nemo_logger():
    logger = logging.getLogger(NEMO_LOGGER_NAME)
    saved_filters = list(logger.filters)
    try:
        logger.filters.clear()
        quiet_repetitive_nemo_logs()
        quiet_repetitive_nemo_logs()
        assert sum(isinstance(item, RepetitiveNeMoMessageFilter) for item in logger.filters) == 1
        assert not logger.filter(_nemo_record('Timestamps requested, setting decoding timestamps to True'))
        assert logger.filter(_nemo_record('decoder failed to initialize', logging.ERROR))
    finally:
        logger.filters[:] = saved_filters


def test_http_client_loggers_drop_info_but_keep_warnings():
    saved = {name: logging.getLogger(name).level for name in NOISY_HTTP_CLIENT_LOGGERS}
    try:
        for name in NOISY_HTTP_CLIENT_LOGGERS:
            logging.getLogger(name).setLevel(logging.NOTSET)
        logging.getLogger('httpx').setLevel(logging.ERROR)
        quiet_http_client_loggers()
        assert logging.getLogger('httpx').level == logging.ERROR
        for name in ('httpcore', 'google.resumable_media'):
            logger = logging.getLogger(name)
            assert not logger.isEnabledFor(logging.INFO)
            assert logger.isEnabledFor(logging.WARNING)
        assert not logging.getLogger('google.resumable_media._helpers').isEnabledFor(logging.INFO)
    finally:
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)

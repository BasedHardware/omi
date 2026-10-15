"""Process-level logging contract, without application or vendor imports."""

import asyncio
import io
import json
import logging
import pathlib
import shutil
import subprocess
import sys

import pytest

import omi_logging as logs


@pytest.fixture(autouse=True)
def isolated_logging(monkeypatch):
    names = ['', *logs.LOGGER_LEVELS]
    saved = [
        (
            logging.getLogger(n),
            list(logging.getLogger(n).handlers),
            list(logging.getLogger(n).filters),
            logging.getLogger(n).level,
            logging.getLogger(n).propagate,
            logging.getLogger(n).disabled,
        )
        for n in names
    ]
    for key in ('K_SERVICE', 'CLOUD_RUN_JOB', 'KUBERNETES_SERVICE_HOST', 'GOOGLE_CLOUD_PROJECT', 'OMI_LOG_FORMAT'):
        monkeypatch.delenv(key, raising=False)
    yield
    for logger, handlers, filters, level, propagate, disabled in saved:
        logger.handlers[:], logger.filters[:] = handlers, filters
        logger.setLevel(level)
        logger.propagate, logger.disabled = propagate, disabled


def test_one_line_severity_exception_and_idempotence(monkeypatch):
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    output = io.StringIO()
    for _ in range(2):
        logs.configure_logging('diarizer', environment='prod', stdout=output)
    logger = logging.getLogger('uvicorn.error')
    logger.info('normal')
    logger.warning('warning')
    try:
        raise ValueError('controlled failure')
    except ValueError:
        logger.exception('failed')
    entries = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [e['severity'] for e in entries] == ['INFO', 'WARNING', 'ERROR']
    assert entries[-1]['message'].startswith('failed\nTraceback')
    assert 'ValueError: controlled failure' in entries[-1]['message']
    assert entries[-1]['@type'].endswith('ReportedErrorEvent')
    assert entries[-1]['logging.googleapis.com/labels'] == {'service': 'diarizer', 'environment': 'prod'}
    assert len(logging.getLogger().handlers) == 1


@pytest.mark.parametrize('marker', ['K_SERVICE', 'CLOUD_RUN_JOB', 'KUBERNETES_SERVICE_HOST', 'GOOGLE_CLOUD_PROJECT'])
def test_runtime_detection(monkeypatch, marker):
    monkeypatch.setenv(marker, 'present')
    output = io.StringIO()
    logs.configure_logging('test', stdout=output)
    logging.warning('hello')
    assert json.loads(output.getvalue())['severity'] == 'WARNING'


def test_local_text_and_override(monkeypatch):
    output = io.StringIO()
    logs.configure_logging('test', stdout=output)
    logging.info('local')
    assert output.getvalue() == 'INFO root: local\n'
    monkeypatch.setenv('K_SERVICE', 'backend')
    monkeypatch.setenv('OMI_LOG_FORMAT', 'text')
    logs.configure_logging('test', stdout=output)
    logging.info('override')
    assert output.getvalue().endswith('INFO root: override\n')


def test_concurrent_trace_context_and_exception_reset(monkeypatch):
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    output = io.StringIO()
    logs.configure_logging('test', project='test-project', stdout=output)

    async def app(scope, receive, send):
        await asyncio.sleep(0)
        logging.info(scope['label'])
        if scope.get('fail'):
            raise ValueError('test')

    middleware = logs.TraceContextMiddleware(app)

    async def run():
        await asyncio.gather(
            middleware(
                {'type': 'http', 'label': 'cloud', 'headers': [(b'x-cloud-trace-context', b'a' * 32 + b'/42;o=1')]},
                None,
                None,
            ),
            middleware(
                {
                    'type': 'websocket',
                    'label': 'w3c',
                    'headers': [(b'traceparent', b'00-' + b'b' * 32 + b'-0000000000000001-00')],
                },
                None,
                None,
            ),
        )
        with pytest.raises(ValueError):
            await middleware(
                {
                    'type': 'http',
                    'label': 'failing',
                    'fail': True,
                    'headers': [(b'x-cloud-trace-context', b'a' * 32 + b'/42')],
                },
                None,
                None,
            )
        logging.info('outside')

    asyncio.run(run())
    entries = {e['message']: e for e in map(json.loads, output.getvalue().splitlines())}
    assert entries['cloud']['logging.googleapis.com/trace'].endswith('/' + 'a' * 32)
    assert entries['cloud']['logging.googleapis.com/spanId'] == '000000000000002a'
    assert entries['cloud']['logging.googleapis.com/trace_sampled'] is True
    assert entries['w3c']['logging.googleapis.com/trace'].endswith('/' + 'b' * 32)
    assert 'logging.googleapis.com/trace' not in entries['outside']


@pytest.mark.parametrize('header', [b'bad', b'0' * 32 + b'/1', b'a' * 32 + b'/18446744073709551616'])
def test_invalid_trace_is_ignored(header):
    assert logs.trace_context({b'x-cloud-trace-context': header}) is None


@pytest.mark.parametrize(
    'service,kept',
    [
        ('diarizer', False),
        ('nllb', False),
        ('parakeet', False),
        ('pusher', False),
        ('vad', False),
        ('backend-listen', True),
        ('llm-gateway', True),
        ('diarizer-batch', True),
    ],
)
def test_access_policy(monkeypatch, service, kept):
    monkeypatch.setenv('KUBERNETES_SERVICE_HOST', 'cluster')
    output = io.StringIO()
    logs.configure_logging(service, stdout=output)
    logger = logging.getLogger('uvicorn.access')
    logger.info('%s %s %s %s %s', 'client', 'GET', '/metrics', '1.1', 200)
    assert not output.getvalue()
    logger.info('%s %s %s %s %s', 'client', 'POST', '/request', '1.1', 200)
    assert bool(output.getvalue()) == kept
    logger.error('real failure')
    assert 'real failure' in output.getvalue()


def test_nemo_errors_never_suppressed(monkeypatch):
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    output = io.StringIO()
    logs.configure_logging('parakeet', stdout=output)
    logger = logging.getLogger('nemo_logger')
    logger.warning(logs.NEMO_REPEATS[0])
    assert not output.getvalue()
    logger.error(logs.NEMO_REPEATS[0])
    assert json.loads(output.getvalue())['severity'] == 'ERROR'


def test_module_import_does_not_depend_on_vendor_utils(tmp_path):
    # Reproduce NeMo's top-level utils collision in an isolated interpreter.
    shutil.copyfile(pathlib.Path(logs.__file__), tmp_path / 'omi_logging.py')
    vendor = tmp_path / 'utils'
    vendor.mkdir()
    (vendor / '__init__.py').write_text('raise RuntimeError("vendor utils imported")\n')
    result = subprocess.run(
        [sys.executable, '-c', 'from omi_logging import configure_logging; configure_logging("parakeet")'],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

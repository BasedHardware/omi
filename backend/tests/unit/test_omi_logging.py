"""Process-level logging contract, without application or vendor imports."""

import asyncio
import contextvars
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


@pytest.mark.parametrize(
    'header', [b'bad', b'0' * 32 + b'/1', b'a' * 32 + b'/18446744073709551616', b'\xff' + b'a' * 32 + b'/42']
)
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


def test_cloud_text_rollback_preserves_error_stream(monkeypatch):
    monkeypatch.setenv('KUBERNETES_SERVICE_HOST', 'cluster')
    monkeypatch.setenv('OMI_LOG_FORMAT', 'text')
    out, err = io.StringIO(), io.StringIO()
    logs.configure_logging('diarizer', stdout=out, stderr=err)
    logging.info('normal')
    logging.error('failure')
    assert 'normal' in out.getvalue() and 'failure' not in out.getvalue()
    assert 'failure' in err.getvalue() and 'normal' not in err.getvalue()


def test_text_default_keeps_cloud_split_until_json_opt_in(monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'backend')
    out, err = io.StringIO(), io.StringIO()
    logs.configure_logging('backend', default_format='text', stdout=out, stderr=err)
    logging.info('normal')
    logging.error('failure')
    assert out.getvalue() == 'INFO root: normal\n'
    assert err.getvalue() == 'ERROR root: failure\n'
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    out = io.StringIO()
    logs.configure_logging('backend', default_format='text', stdout=out)
    logging.info('opted in')
    assert json.loads(out.getvalue())['message'] == 'opted in'


def test_invalid_default_format_is_rejected():
    with pytest.raises(ValueError):
        logs.configure_logging('backend', default_format='JSON')


def test_requested_level_constrains_named_loggers():
    output = io.StringIO()
    logs.configure_logging('test', level=logging.ERROR, stdout=output)
    logging.getLogger('uvicorn.error').info('info')
    logging.getLogger('nemo_logger').info('info')
    logging.getLogger('httpx').warning('warning')
    assert not output.getvalue()
    logging.getLogger('uvicorn.error').error('failure')
    assert 'failure' in output.getvalue()


def test_project_id_alone_does_not_disable_access(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'local-project')
    output = io.StringIO()
    logs.configure_logging('diarizer', stdout=output)
    logging.getLogger('uvicorn.access').info('%s %s %s %s %s', 'client', 'POST', '/request', '1.1', 200)
    assert json.loads(output.getvalue())['logger'] == 'uvicorn.access'


def test_outer_server_exception_log_retains_trace_without_leaking(monkeypatch):
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    output = io.StringIO()
    logs.configure_logging('test', project='test-project', stdout=output)
    failure = ValueError('controlled')

    async def app(scope, receive, send):
        raise failure

    async def run():
        middleware = logs.TraceContextMiddleware(app)
        for headers in [[(b'x-cloud-trace-context', b'a' * 32 + b'/42;o=1')], []]:
            try:
                await middleware({'type': 'http', 'headers': headers}, None, None)
            except ValueError:
                logging.getLogger('uvicorn.error').exception('Exception in ASGI application')
        logging.info('outside')

    asyncio.run(run())
    entries = list(map(json.loads, output.getvalue().splitlines()))
    assert entries[0]['logging.googleapis.com/trace'].endswith('/' + 'a' * 32)
    assert entries[0]['logging.googleapis.com/spanId'] == '000000000000002a'
    assert all('logging.googleapis.com/trace' not in entry for entry in entries[1:])


@pytest.mark.parametrize('rejection', [AttributeError, asyncio.CancelledError, KeyboardInterrupt])
def test_exception_metadata_failure_does_not_replace_original(rejection):
    class ImmutableError(Exception):
        def __setattr__(self, name, value):
            raise rejection('immutable')

    failure = ImmutableError('original')

    async def app(scope, receive, send):
        raise failure

    with pytest.raises(ImmutableError) as caught:
        asyncio.run(logs.TraceContextMiddleware(app)({'type': 'http'}, None, None))
    assert caught.value is failure
    assert logs._TRACE.get() is None


@pytest.mark.parametrize(
    'metadata', [None, 'bad', ('bad', 'bad', True), ('a' * 32, 'b' * 16, object()), KeyboardInterrupt()]
)
def test_bad_exception_metadata_cannot_discard_error(monkeypatch, metadata):
    class CustomError(Exception):
        def __getattribute__(self, name):
            if name == '_omi_logging_trace':
                if isinstance(metadata, BaseException):
                    raise metadata
                return metadata
            return super().__getattribute__(name)

    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    output = io.StringIO()
    logs.configure_logging('test', project='project', stdout=output)
    failure = CustomError('original')
    logging.error('outer failure', exc_info=(type(failure), failure, None))
    entry = json.loads(output.getvalue())
    assert 'original' in entry['message']
    assert 'logging.googleapis.com/trace' not in entry


def test_malformed_nemo_diagnostic_does_not_escape_filter():
    record = logging.LogRecord('nemo_logger', logging.WARNING, '', 0, '%s %s', ('one',), None)
    assert logs.NeMoFilter().filter(record)


def test_surrogate_message_is_valid_utf8_json(monkeypatch):
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    output = io.BytesIO()
    stream = io.TextIOWrapper(output, encoding='utf-8', errors='strict', write_through=True)
    logs.configure_logging('test', stdout=stream)
    message = 'filename ' + chr(0xDCFF) + ' café'
    logging.warning(message)
    encoded = output.getvalue()
    assert encoded.isascii()
    entry = json.loads(encoded.decode('utf-8'))
    assert entry['message'] == message
    assert entry['severity'] == 'WARNING'


@pytest.mark.parametrize('policy,kept', [(None, False), ('platform', False), ('keep', True)])
def test_cloud_run_access_override(monkeypatch, policy, kept):
    monkeypatch.setenv('K_SERVICE', 'backend')
    output = io.StringIO()
    logs.configure_logging('backend', access_policy=policy, stdout=output)
    logging.getLogger('uvicorn.access').info('%s %s %s %s %s', 'client', 'GET', '/request', '1.1', 200)
    assert bool(output.getvalue()) is kept


@pytest.mark.parametrize(
    'parent',
    [b'00-' + b'b' * 32 + b'-0000000000000001-00', b'invalid', b'', b'\xff00-' + b'b' * 32 + b'-0000000000000001-00'],
)
def test_w3c_trace_takes_precedence_with_legacy_fallback(parent):
    result = logs.trace_context({b'traceparent': parent, b'x-cloud-trace-context': b'a' * 32 + b'/42;o=1'})
    expected = (
        ('b' * 32, '0000000000000001', False) if parent.startswith(b'00-') else ('a' * 32, '000000000000002a', True)
    )
    assert result == expected


@pytest.mark.parametrize('level', [logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL])
def test_only_errors_force_error_reporting(monkeypatch, level):
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    output = io.StringIO()
    logs.configure_logging('test', stdout=output)
    try:
        raise ValueError('controlled')
    except ValueError:
        logging.log(level, 'diagnostic', exc_info=True)
    entry = json.loads(output.getvalue())
    assert 'Traceback' in entry['message']
    assert ('@type' in entry) is (level >= logging.ERROR)
    assert ('serviceContext' in entry) is (level >= logging.ERROR)
    assert entry['severity'] == logging.getLevelName(level)


def test_executor_adoption_copies_context_without_leaking(monkeypatch):
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    output = io.StringIO()
    logs.configure_logging('parakeet', project='test-project', stdout=output)

    async def app(scope, receive, send):
        await asyncio.get_running_loop().run_in_executor(
            None, contextvars.copy_context().run, logging.warning, 'worker'
        )

    async def run():
        await logs.TraceContextMiddleware(app)(
            {'type': 'http', 'headers': [(b'x-cloud-trace-context', b'a' * 32 + b'/42;o=1')]}, None, None
        )
        await asyncio.get_running_loop().run_in_executor(None, logging.warning, 'outside')

    asyncio.run(run())
    worker, outside = map(json.loads, output.getvalue().splitlines())
    assert worker['logging.googleapis.com/trace'].endswith('/' + 'a' * 32)
    assert 'logging.googleapis.com/trace' not in outside


def test_successful_liveness_is_filtered_but_failure_is_kept(monkeypatch):
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    output = io.StringIO()
    logs.configure_logging('nllb', access_policy='keep', stdout=output)
    logger = logging.getLogger('uvicorn.access')
    logger.info('%s %s %s %s %s', 'client', 'GET', '/live', '1.1', 200)
    assert not output.getvalue()
    logger.info('%s %s %s %s %s', 'client', 'GET', '/live', '1.1', 503)
    assert json.loads(output.getvalue())['logger'] == 'uvicorn.access'

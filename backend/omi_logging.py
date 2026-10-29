"""Dependency-free process logging, safe even when a vendor owns ``utils``.

Images must copy this module to their application import root. Call configure_logging
before importing application dependencies, then install TraceContextMiddleware.
"""

import contextvars
import datetime
import json
import logging
import os
import re
import sys
from typing import Any, Awaitable, Callable, Mapping, TextIO, cast

_TRACE: contextvars.ContextVar[tuple[str, str, bool] | None] = contextvars.ContextVar('omi_log_trace', default=None)
LOGGER_LEVELS = {
    'httpx': logging.WARNING,
    'httpcore': logging.WARNING,
    'urllib3': logging.WARNING,
    'google.resumable_media': logging.WARNING,
    'uvicorn': logging.INFO,
    'uvicorn.error': logging.INFO,
    'uvicorn.access': logging.INFO,
    'nemo_logger': logging.INFO,
}
LB_LOGGED_SERVICES = frozenset({'diarizer', 'nllb', 'parakeet', 'pusher', 'vad'})
PROBE_PATHS = frozenset({'/health', '/v1/health', '/live', '/ready', '/metrics', '/batch/metrics'})
NEMO_REPEATS = (
    'Timestamps requested, setting decoding timestamps to True',
    'are ignored by Lhotse dataloader',
    'You are using a non-tarred dataset and requested tokenization during data sampling',
)


def trace_context(headers: Mapping[bytes, bytes]) -> tuple[str, str, bool] | None:
    """Parse validated IDs only; never retain request URLs or other headers."""
    parent = headers.get(b'traceparent', b'').decode('ascii', errors='replace')
    match = re.fullmatch(r'00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})', parent)
    if match and int(match[1], 16) and int(match[2], 16):
        return match[1], match[2], bool(int(match[3], 16) & 1)
    cloud = headers.get(b'x-cloud-trace-context', b'').decode('ascii', errors='replace')
    match = re.fullmatch(r'([0-9a-fA-F]{32})/(\d{1,20})(?:;o=([01]))?', cloud)
    if match and int(match[1], 16) and 0 < int(match[2]) < 2**64:
        return match[1].lower(), f'{int(match[2]):016x}', match[3] == '1'
    return None


class TraceContextMiddleware:
    """Keep trace context scoped to one HTTP/WebSocket ASGI invocation."""

    def __init__(self, app: Callable[..., Awaitable[Any]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        token = _TRACE.set(trace_context(dict(scope.get('headers', ()))))
        try:
            return await self.app(scope, receive, send)
        except BaseException as error:
            # Uvicorn logs after this middleware unwinds. Carry only validated IDs
            # on the exception so its outer log keeps the originating trace.
            try:
                setattr(error, '_omi_logging_trace', _TRACE.get())
            except BaseException:
                pass  # Never replace the original failure if a custom exception rejects attributes.
            raise
        finally:
            _TRACE.reset(token)


def _exception_trace(error: BaseException | None) -> tuple[str, str, bool] | None:
    """Optional metadata must never prevent delivery of the original error log."""
    try:
        value = getattr(error, '_omi_logging_trace', None)
        if type(value) is not tuple:
            return None
        value = cast(tuple[Any, ...], value)
        if (
            len(value) == 3
            and type(value[0]) is str
            and type(value[1]) is str
            and type(value[2]) is bool
            and re.fullmatch(r'[0-9a-f]{32}', value[0])
            and re.fullmatch(r'[0-9a-f]{16}', value[1])
            and int(value[0], 16)
            and int(value[1], 16)
        ):
            return cast(tuple[str, str, bool], value)
    except BaseException:
        pass  # A custom exception attribute accessor cannot break logging.
    return None


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, environment: str, project: str | None) -> None:
        super().__init__()
        self.service, self.environment, self.project = service, environment, project

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message += '\n' + self.formatException(record.exc_info)
        if record.stack_info:
            message += '\n' + self.formatStack(record.stack_info)
        payload: dict[str, Any] = {
            'severity': {logging.WARNING: 'WARNING', logging.CRITICAL: 'CRITICAL'}.get(
                record.levelno, record.levelname
            ),
            'message': message,
            'logger': record.name,
            'timestamp': datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat(),
            'logging.googleapis.com/labels': {'service': self.service, 'environment': self.environment},
        }
        if record.exc_info and record.levelno >= logging.ERROR:
            payload['@type'] = 'type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent'
            payload['serviceContext'] = {'service': self.service}
        trace = _TRACE.get()
        if trace is None and record.exc_info:
            trace = _exception_trace(record.exc_info[1])
        if trace and self.project:
            payload['logging.googleapis.com/trace'] = f'projects/{self.project}/traces/{trace[0]}'
            payload['logging.googleapis.com/spanId'] = trace[1]
            payload['logging.googleapis.com/trace_sampled'] = trace[2]
        return json.dumps(payload, ensure_ascii=True, separators=(',', ':'))


class BelowWarningFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.WARNING


class AccessFilter(logging.Filter):
    def __init__(self, off: bool) -> None:
        super().__init__()
        self.off = off

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != 'uvicorn.access' or record.exc_info or record.levelno >= logging.ERROR:
            return True
        if self.off:
            return False
        args = record.args
        if record.levelno != logging.INFO or not isinstance(args, tuple) or len(args) != 5:
            return True
        _, method, path, _, status = args
        return not (method in ('GET', 'HEAD') and path in PROBE_PATHS and status == 200)


class NeMoFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR or record.exc_info:
            return True
        try:
            message = record.getMessage()
        except Exception:
            return True  # Let the handler contain malformed vendor diagnostics.
        return not any(marker in message for marker in NEMO_REPEATS)


def configure_logging(
    service: str,
    *,
    environment: str | None = None,
    project: str | None = None,
    level: int = logging.INFO,
    access_policy: str | None = None,
    default_format: str | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """Own stdout JSON logging; cloud text rollback uses legacy split streams.

    access_policy is ``keep`` or ``platform``; omitted selects known LB coverage.
    Configure again after vendor imports if they replace their own handlers.
    OMI_LOG_FORMAT=text is an explicit rollback/debug override, including on GCP.
    default_format (``json`` or ``text``) applies only when OMI_LOG_FORMAT is unset:
    a service whose log consumers are not yet admitted passes ``text`` so adopting
    the shared setup keeps its textPayload filters, and OMI_LOG_FORMAT=json opts in.
    """
    if not service or access_policy not in (None, 'keep', 'platform'):
        raise ValueError('service and a valid access policy are required')
    if default_format not in (None, 'json', 'text'):
        raise ValueError('default_format must be json or text')
    mode = os.getenv('OMI_LOG_FORMAT', '').strip().lower()
    if mode not in ('', 'json', 'text'):
        raise ValueError('OMI_LOG_FORMAT must be json or text')
    mode = mode or default_format or ''
    cloud_run = bool(os.getenv('K_SERVICE') or os.getenv('CLOUD_RUN_JOB'))
    on_kubernetes = bool(os.getenv('KUBERNETES_SERVICE_HOST'))
    on_gcp = cloud_run or on_kubernetes or bool(os.getenv('GOOGLE_CLOUD_PROJECT'))
    structured = mode == 'json' or (not mode and on_gcp)
    environment = environment or os.getenv('OMI_ENV_STAGE') or os.getenv('ENVIRONMENT') or 'unknown'
    project = project or os.getenv('GOOGLE_CLOUD_PROJECT') or os.getenv('GCP_PROJECT') or os.getenv('GCLOUD_PROJECT')
    handler = logging.StreamHandler(stdout if stdout is not None else sys.stdout)
    handler.setFormatter(
        JsonFormatter(service, environment, project)
        if structured
        else logging.Formatter('%(levelname)s %(name)s: %(message)s')
    )
    handler.setLevel(level)
    handlers = [handler]
    if on_gcp and not structured:
        handler.addFilter(BelowWarningFilter())
        errors = logging.StreamHandler(stderr if stderr is not None else sys.stderr)
        errors.setLevel(max(level, logging.WARNING))
        errors.setFormatter(handler.formatter)
        handlers.append(errors)
    root = logging.getLogger()
    root.handlers[:] = handlers
    root.setLevel(level)
    for name, threshold in LOGGER_LEVELS.items():
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.disabled = False
        logger.setLevel(threshold)
    access = logging.getLogger('uvicorn.access')
    access.filters.clear()
    off = access_policy == 'platform' or (
        access_policy is None and (cloud_run or (on_kubernetes and service in LB_LOGGED_SERVICES))
    )
    access.addFilter(AccessFilter(off))
    nemo = logging.getLogger('nemo_logger')
    nemo.filters[:] = [NeMoFilter()]

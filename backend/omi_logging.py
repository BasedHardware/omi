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

_TRACE = contextvars.ContextVar('omi_log_trace', default=None)
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
PROBE_PATHS = frozenset({'/health', '/v1/health', '/ready', '/metrics', '/batch/metrics'})
NEMO_REPEATS = (
    'Timestamps requested, setting decoding timestamps to True',
    'are ignored by Lhotse dataloader',
    'You are using a non-tarred dataset and requested tokenization during data sampling',
)


def trace_context(headers):
    """Parse validated IDs only; never retain request URLs or other headers."""
    cloud = headers.get(b'x-cloud-trace-context', b'').decode('ascii', errors='ignore')
    match = re.fullmatch(r'([0-9a-fA-F]{32})/(\d{1,20})(?:;o=([01]))?', cloud)
    if match and int(match[1], 16) and 0 < int(match[2]) < 2**64:
        return match[1].lower(), f'{int(match[2]):016x}', match[3] == '1'
    parent = headers.get(b'traceparent', b'').decode('ascii', errors='ignore')
    match = re.fullmatch(r'00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})', parent)
    if match and int(match[1], 16) and int(match[2], 16):
        return match[1], match[2], bool(int(match[3], 16) & 1)
    return None


class TraceContextMiddleware:
    """Keep trace context scoped to one HTTP/WebSocket ASGI invocation."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        token = _TRACE.set(trace_context(dict(scope.get('headers', ()))))
        try:
            return await self.app(scope, receive, send)
        finally:
            _TRACE.reset(token)


class JsonFormatter(logging.Formatter):
    def __init__(self, service, environment, project):
        super().__init__()
        self.service, self.environment, self.project = service, environment, project

    def format(self, record):
        message = record.getMessage()
        if record.exc_info:
            message += '\n' + self.formatException(record.exc_info)
        if record.stack_info:
            message += '\n' + self.formatStack(record.stack_info)
        payload = {
            'severity': {logging.WARNING: 'WARNING', logging.CRITICAL: 'CRITICAL'}.get(
                record.levelno, record.levelname
            ),
            'message': message,
            'logger': record.name,
            'timestamp': datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat(),
            'logging.googleapis.com/labels': {'service': self.service, 'environment': self.environment},
        }
        if record.exc_info:
            payload['@type'] = 'type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent'
            payload['serviceContext'] = {'service': self.service}
        trace = _TRACE.get()
        if trace and self.project:
            payload['logging.googleapis.com/trace'] = f'projects/{self.project}/traces/{trace[0]}'
            payload['logging.googleapis.com/spanId'] = trace[1]
            payload['logging.googleapis.com/trace_sampled'] = trace[2]
        return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


class AccessFilter(logging.Filter):
    def __init__(self, off):
        super().__init__()
        self.off = off

    def filter(self, record):
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
    def filter(self, record):
        if record.levelno >= logging.ERROR or record.exc_info:
            return True
        return not any(marker in record.getMessage() for marker in NEMO_REPEATS)


def configure_logging(service, *, environment=None, project=None, level=logging.INFO, access_policy=None, stdout=None):
    """Own one stdout handler. Repeated setup replaces policy without duplication.

    access_policy is ``keep`` or ``platform``; omitted selects known LB coverage.
    Configure again after vendor imports if they replace their own handlers.
    OMI_LOG_FORMAT=text is an explicit rollback/debug override, including on GCP.
    """
    if not service or access_policy not in (None, 'keep', 'platform'):
        raise ValueError('service and a valid access policy are required')
    mode = os.getenv('OMI_LOG_FORMAT', '').strip().lower()
    if mode not in ('', 'json', 'text'):
        raise ValueError('OMI_LOG_FORMAT must be json or text')
    cloud_run = bool(os.getenv('K_SERVICE') or os.getenv('CLOUD_RUN_JOB'))
    on_gcp = cloud_run or bool(os.getenv('KUBERNETES_SERVICE_HOST') or os.getenv('GOOGLE_CLOUD_PROJECT'))
    structured = mode == 'json' or (not mode and on_gcp)
    environment = environment or os.getenv('OMI_ENV_STAGE') or os.getenv('ENVIRONMENT') or 'unknown'
    project = project or os.getenv('GOOGLE_CLOUD_PROJECT') or os.getenv('GCP_PROJECT') or os.getenv('GCLOUD_PROJECT')
    handler = logging.StreamHandler(stdout if stdout is not None else sys.stdout)
    handler.setFormatter(
        JsonFormatter(service, environment, project)
        if structured
        else logging.Formatter('%(levelname)s %(name)s: %(message)s')
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name, threshold in LOGGER_LEVELS.items():
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.disabled = False
        logger.setLevel(threshold)
    access = logging.getLogger('uvicorn.access')
    access.filters.clear()
    off = (
        cloud_run or access_policy == 'platform' or (access_policy is None and on_gcp and service in LB_LOGGED_SERVICES)
    )
    access.addFilter(AccessFilter(off))
    nemo = logging.getLogger('nemo_logger')
    nemo.filters[:] = [NeMoFilter()]

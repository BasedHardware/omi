"""Measure server-observed upload admission without reading bodies or changing sync."""

from prometheus_client import Histogram
from starlette.datastructures import Headers

from config.request_clock import bounded_hold_state, recovered_label
from utils.observability.fleet import record_upload

UPLOAD_PATHS = frozenset({'/v1/sync-local-files', '/v2/sync-local-files'})
HOLD_AGE = Histogram(
    'omi_batch_pipeline_upload_hold_age_seconds',
    'Client-reported age of the oldest sealed file when a held upload is sent',
    ['hold_state', 'recovered'],
    buckets=(1, 5, 15, 30, 60, 120, 300, 360, 600, 900, 1200, 1800, 3600, 7200, 14400, 86400),
)


def observe_hold_age(age_ms, hold_state, recovered=False):
    # Limit parsing before int() and accept only the client's decimal format.
    if not isinstance(age_ms, str) or not 1 <= len(age_ms) <= 8 or not age_ms.isascii() or not age_ms.isdecimal():
        return
    milliseconds = int(age_ms)
    if milliseconds <= 86_400_000:
        HOLD_AGE.labels(bounded_hold_state(hold_state), recovered_label(recovered)).observe(milliseconds / 1000)


class SyncUploadMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or scope['path'].rstrip('/') not in UPLOAD_PATHS:
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        platform, channel = headers.get('x-app-platform'), headers.get('x-build-channel')
        record_upload('started', platform, channel)
        outcome = 'failed'

        async def measured_send(message):
            nonlocal outcome
            if message['type'] == 'http.response.start':
                status = message['status']
                outcome = (
                    'accepted'
                    if status == 202
                    else ('completed' if 200 <= status < 300 and status != 207 else 'failed')
                )
            await send(message)

        try:
            await self.app(scope, receive, measured_send)
        finally:
            record_upload(outcome, platform, channel)

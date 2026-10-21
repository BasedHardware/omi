"""Measure server-observed upload admission without reading bodies or changing sync."""

from starlette.datastructures import Headers

from utils.observability.fleet import record_upload

UPLOAD_PATHS = frozenset({'/v1/sync-local-files', '/v2/sync-local-files'})


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

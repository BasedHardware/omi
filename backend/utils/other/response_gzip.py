"""Response gzip compression with streaming-endpoint exemptions.

The API serves JSON responses to browsers, the web admin and OkHttp-based
clients uncompressed today; those clients send ``Accept-Encoding: gzip`` and
pay the transfer on the Cloud Run / GCE egress lines. This middleware applies
Starlette's ``GZipMiddleware`` for ordinary buffered responses only.

Starlette's GZipMiddleware compresses any matching response, including
``StreamingResponse``. Token/SSE/audio streams must keep their chunk
boundaries and first-byte latency, so the routes that stream are exempted by
path before the request reaches the compressor:

- routes declared ``response_class=StreamingResponse`` (voice-messages SSE,
  both ``/v1/tts/synthesize`` routes, the ``/v1/sync/audio/`` download) are
  pinned by ``tests/unit/test_response_gzip.py``, which fails when a new
  streaming route appears without an exemption;
- routes that return ``StreamingResponse`` conditionally (``/v2/chat/completions``
  with ``stream: true``, the desktop gemini proxy, the chunked
  ``/v1/users/export`` document) are exempted here and listed manually.

New streaming routes must be added to the exemption set in the same change.
"""

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

_EXEMPT_PATHS = frozenset(
    {
        '/v2/voice-messages',
        '/v1/tts/synthesize',
        '/v2/tts/synthesize',
        '/v2/chat/completions',
    }
)
_EXEMPT_PREFIXES = (
    '/v1/sync/audio/',  # audio file download stream
    '/v1/proxy/gemini',  # desktop gemini proxy and its -stream sibling
    '/v1/users/export',  # chunked JSON export document
)


def _is_exempt(path: str) -> bool:
    return path in _EXEMPT_PATHS or path.startswith(_EXEMPT_PREFIXES)


class GatedGZipMiddleware:
    """GZipMiddleware, except for the streaming endpoints named above."""

    def __init__(self, app: ASGIApp, minimum_size: int = 1024, compresslevel: int = 6) -> None:
        self.app = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] == 'http' and _is_exempt(scope.get('path', '')):
            await self.app(scope, receive, send)
            return
        await self._gzip(scope, receive, send)

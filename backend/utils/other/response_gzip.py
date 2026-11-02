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

Starlette's compressor matches a bare substring ``"gzip" in accept-encoding``
and ignores quality values, so a client sending ``gzip;q=0`` would still be
compressed. ``_gzip_acceptable`` parses the quality values first (RFC 9110
§12.5.3) and routes such requests to the plain app.
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


def _header(scope: Scope, name: str) -> str:
    raw = name.encode('latin-1')
    for key, value in scope.get('headers') or []:
        if key == raw:
            return value.decode('latin-1')
    return ''


def _gzip_acceptable(accept_encoding: str) -> bool:
    """True when gzip is named with a non-zero quality value (RFC 9110 §12.5.3).

    A wildcard-only header (``*``) passes this check but stays identity in
    practice: the underlying Starlette compressor requires the literal
    ``gzip`` token. Serving identity is always RFC-acceptable.
    """
    codings: dict[str, float] = {}
    for part in accept_encoding.split(','):
        piece = part.split(';')
        token = piece[0].strip().lower()
        if not token:
            continue
        q = 1.0
        for param in piece[1:]:
            param = param.strip()
            if param[:2].lower() == 'q=':
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
        codings[token] = q
    if 'gzip' in codings:
        return codings['gzip'] > 0
    return codings.get('*', 0.0) > 0


class GatedGZipMiddleware:
    """GZipMiddleware, except for the streaming endpoints named above and for
    clients whose Accept-Encoding rules gzip out with a zero quality value."""

    def __init__(self, app: ASGIApp, minimum_size: int = 1024, compresslevel: int = 6) -> None:
        self.app = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] == 'http':
            if _is_exempt(scope.get('path', '')):
                await self.app(scope, receive, send)
                return
            accept_encoding = _header(scope, 'accept-encoding')
            if accept_encoding and not _gzip_acceptable(accept_encoding):
                await self.app(scope, receive, send)
                return
        await self._gzip(scope, receive, send)

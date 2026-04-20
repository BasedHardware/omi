"""Reject HTTP requests whose Content-Length exceeds a global cap.

Installed as a Starlette middleware in main.py. Without this every
UploadFile endpoint (app logo, persona avatar, audio sample, limitless
zip, sync batches) lives at the mercy of whatever body size the client
decides to send. An attacker who uploads a multi-GB file causes the
worker to buffer it in memory and OOM long before the endpoint's
per-request logic runs.

The cap is large enough for legitimate traffic (500 MiB by default —
covers the biggest Limitless export we have data on) but will stop
a trivially constructed DoS payload. Individual endpoints should still
add tighter per-endpoint caps (see _MAX_PCM_BODY_BYTES in chat.py and
the Limitless zip-bomb guard).

Streaming clients that omit Content-Length (HTTP/1.1 chunked) bypass
this header check; the per-endpoint logic still applies.
"""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_DEFAULT_MAX_BYTES = 500 * 1024 * 1024  # 500 MiB

_MAX_REQUEST_BYTES = int(os.getenv('MAX_REQUEST_BYTES') or _DEFAULT_MAX_BYTES)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Return 413 Payload Too Large if Content-Length exceeds the cap."""

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get('content-length')
        if cl:
            try:
                n = int(cl)
            except ValueError:
                return JSONResponse({'detail': 'Invalid Content-Length'}, status_code=400)
            if n < 0 or n > _MAX_REQUEST_BYTES:
                return JSONResponse(
                    {'detail': f'Request body exceeds {_MAX_REQUEST_BYTES} bytes'},
                    status_code=413,
                )
        return await call_next(request)

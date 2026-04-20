"""Per-request BYOK (Bring Your Own Keys) key plumbing.

The desktop client sends user-provided API keys as headers on every request
(`X-BYOK-OpenAI`, `X-BYOK-Anthropic`, `X-BYOK-Gemini`, `X-BYOK-Deepgram`).
A FastAPI middleware stashes them in a per-request contextvar; the LLM/STT
clients can then read them without re-reading the request object.

Keys are NEVER persisted — only fingerprints (see `database.users.set_byok_active`).
"""

from contextvars import ContextVar
from typing import Dict, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.websockets import WebSocket

BYOK_HEADERS = {
    'openai': 'x-byok-openai',
    'anthropic': 'x-byok-anthropic',
    'gemini': 'x-byok-gemini',
    'deepgram': 'x-byok-deepgram',
}

# Keys for the current request, if the client supplied them.
# Default is None (not {}) to avoid sharing a mutable object across contexts.
_byok_ctx: ContextVar[Optional[Dict[str, str]]] = ContextVar('byok_keys', default=None)


def get_byok_keys() -> Dict[str, str]:
    """The keys attached to the current request (may be empty)."""
    return _byok_ctx.get() or {}


def get_byok_key(provider: str) -> Optional[str]:
    keys = _byok_ctx.get()
    if keys is None:
        return None
    return keys.get(provider)


def has_byok_keys() -> bool:
    """True if the current request carries at least one BYOK header."""
    keys = _byok_ctx.get()
    return bool(keys)


def set_byok_keys(keys: Dict[str, str]):
    """Used by the middleware; also useful from WS handlers that read headers manually."""
    _byok_ctx.set({k: v for k, v in keys.items() if v})


def extract_byok_from_websocket(websocket: WebSocket) -> Dict[str, str]:
    """Read BYOK headers from a WebSocket's initial upgrade request.

    BaseHTTPMiddleware only fires for HTTP scope, so WebSocket handlers must
    call this manually and then pass the result to ``set_byok_keys``.
    """
    keys: Dict[str, str] = {}
    for provider, header in BYOK_HEADERS.items():
        value = websocket.headers.get(header)
        if value:
            keys[provider] = value
    return keys


class BYOKMiddleware(BaseHTTPMiddleware):
    """Extract BYOK headers from each HTTP request into the contextvar.

    NOTE: BaseHTTPMiddleware does NOT fire for WebSocket connections
    (scope["type"] == "websocket"). WebSocket handlers must call
    ``extract_byok_from_websocket`` + ``set_byok_keys`` manually.
    """

    async def dispatch(self, request: Request, call_next):
        keys: Dict[str, str] = {}
        for provider, header in BYOK_HEADERS.items():
            value = request.headers.get(header)
            if value:
                keys[provider] = value
        token = _byok_ctx.set(keys)
        try:
            return await call_next(request)
        finally:
            _byok_ctx.reset(token)

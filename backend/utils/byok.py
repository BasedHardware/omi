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

_BYOK_HEADERS = {
    'openai': 'x-byok-openai',
    'anthropic': 'x-byok-anthropic',
    'gemini': 'x-byok-gemini',
    'deepgram': 'x-byok-deepgram',
}

# Keys for the current request, if the client supplied them. Empty dict otherwise.
_byok_ctx: ContextVar[Dict[str, str]] = ContextVar('byok_keys', default={})


def get_byok_keys() -> Dict[str, str]:
    """The keys attached to the current request (may be empty)."""
    return _byok_ctx.get()


def get_byok_key(provider: str) -> Optional[str]:
    return _byok_ctx.get().get(provider)


def set_byok_keys(keys: Dict[str, str]):
    """Used by the middleware; also useful from WS handlers that read headers manually."""
    _byok_ctx.set({k: v for k, v in keys.items() if v})


class BYOKMiddleware(BaseHTTPMiddleware):
    """Extract BYOK headers from each request into the contextvar."""

    async def dispatch(self, request: Request, call_next):
        keys: Dict[str, str] = {}
        for provider, header in _BYOK_HEADERS.items():
            value = request.headers.get(header)
            if value:
                keys[provider] = value
        token = _byok_ctx.set(keys)
        try:
            return await call_next(request)
        finally:
            _byok_ctx.reset(token)

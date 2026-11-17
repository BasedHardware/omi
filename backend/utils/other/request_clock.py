"""Server request arrival before multipart parsing; no client-supplied clock."""

from contextvars import ContextVar

started_at: ContextVar[float | None] = ContextVar('omi_request_started_at', default=None)

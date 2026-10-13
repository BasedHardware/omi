"""Per-sink delivery context, propagated through retries without adapter-global state."""

from contextvars import ContextVar
from typing import Any

send_sequence: ContextVar[int] = ContextVar('messaging_send_sequence', default=0)
send_markup: ContextVar[dict | None] = ContextVar('messaging_send_markup', default=None)
send_guard: ContextVar[Any] = ContextVar('messaging_send_guard', default=None)

# Resolve just before provider IO, after pacing, against durable webhook admission.
send_reply_target: ContextVar[Any] = ContextVar('messaging_send_reply_target', default=None)
send_first_chunk: ContextVar[bool] = ContextVar('messaging_send_first_chunk', default=True)

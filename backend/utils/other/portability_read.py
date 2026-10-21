"""Read context for user-data portability exports.

An export stream runs owner reads inside a ``PortabilityReadContext`` scope. In
that scope, encrypted-field reads fail closed: ``encryption.decrypt`` returns its
input unchanged on failure (a display-oriented fallback), which is acceptable for
UI but must never let a truncated or foreign-key blob sail through a portability
export as if it were plaintext.
"""

import contextvars
import threading
from typing import Any, Optional


class PortabilityReadCancelled(Exception):
    """The export's owning request disconnected; stop reading user data."""


class PortabilityReadVerificationError(RuntimeError):
    """An encrypted field could not be verified as successfully decrypted."""


class PortabilityReadContext:
    def __init__(self, cancelled: Optional[threading.Event] = None) -> None:
        self.cancelled = cancelled if cancelled is not None else threading.Event()

    def cancel(self) -> None:
        self.cancelled.set()

    def check(self) -> None:
        if self.cancelled.is_set():
            raise PortabilityReadCancelled()


_current: contextvars.ContextVar[Optional[PortabilityReadContext]] = contextvars.ContextVar(
    'omi_portability_read_context', default=None
)


def current_portability_read() -> Optional[PortabilityReadContext]:
    return _current.get()


def check_portability_read() -> None:
    """Cooperative cancellation point; a no-op outside an export scope."""

    context = current_portability_read()
    if context is not None:
        context.check()


def verified_encrypted_read(raw: Any, decoded: Any) -> Any:
    """Reject an encrypted field whose decrypt returned its input unchanged.

    ``encryption.decrypt`` falls back to returning the ciphertext on error.
    Under a portability scope that fallback means the payload never decrypted —
    exporting it would either corrupt the archive or leak ciphertext — so it is
    a hard failure. Outside a scope this is a pass-through.
    """

    if current_portability_read() is not None and isinstance(raw, str) and raw != '' and decoded == raw:
        raise PortabilityReadVerificationError('encrypted field failed to decrypt for portability export')
    return decoded


def iter_portability_guarded(iterable):
    """Yield from a query stream with a cancellation check around each read.

    The underlying iterator is closed when this wrapper exits for any reason —
    normal exhaustion, an exception, or generator ``close()`` — so a cancelled
    export does not leave a live Firestore stream behind.
    """

    iterator = iter(iterable)
    try:
        while True:
            check_portability_read()
            try:
                item = next(iterator)
            except StopIteration:
                return
            check_portability_read()
            yield item
    finally:
        close = getattr(iterator, 'close', None)
        if callable(close):
            close()


class portability_read_scope:
    """Context manager scoping a PortabilityReadContext for the current context."""

    def __init__(self, context: Optional[PortabilityReadContext] = None) -> None:
        self.context = context if context is not None else PortabilityReadContext()
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> PortabilityReadContext:
        self._token = _current.set(self.context)
        return self.context

    def __exit__(self, *exc_info: object) -> None:
        if self._token is not None:
            _current.reset(self._token)
            self._token = None

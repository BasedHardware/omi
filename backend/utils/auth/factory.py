"""Auth backend selection (ADR-0034). ``AUTH_BACKEND`` picks the adapter; default ``firebase``
(first-class cloud). Adapters are imported lazily and initialized on first use — no ``initialize_app``
at import (which today runs as an import-time side effect in four processes)."""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from utils.auth.ports import AuthProvider

logger = logging.getLogger(__name__)

DEFAULT_AUTH_BACKEND = "firebase"
VALID_AUTH_BACKENDS = frozenset({"firebase", "oidc"})

_lock = threading.Lock()
_instance: Optional[AuthProvider] = None


def auth_backend_name() -> str:
    """The selected auth backend, normalized (``firebase`` default | ``oidc``).

    Read this to gate Firebase-proprietary surfaces (e.g. the FirebaseUI external-app OAuth page)
    without instantiating a provider — it mirrors the exact normalization ``get_auth_provider`` uses.
    An unset/blank value defaults to ``firebase``; an unrecognized value is logged and coerced to the
    default so the gate and the provider agree (a typo never silently mis-gates OAuth surfaces).
    """
    value = (os.getenv("AUTH_BACKEND") or "").strip().lower() or DEFAULT_AUTH_BACKEND
    if value not in VALID_AUTH_BACKENDS:
        logger.error("Invalid AUTH_BACKEND=%r; falling back to %r", value, DEFAULT_AUTH_BACKEND)
        return DEFAULT_AUTH_BACKEND
    return value


def get_auth_provider() -> AuthProvider:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                backend = auth_backend_name()
                if backend == "firebase":
                    from utils.auth.adapters.firebase import FirebaseAuthProvider

                    _instance = FirebaseAuthProvider()
                elif backend == "oidc":
                    from utils.auth.adapters.oidc import OIDCAuthProvider

                    _instance = OIDCAuthProvider()
                else:
                    raise ValueError(f"unknown AUTH_BACKEND: {backend!r} (expected 'firebase' or 'oidc')")
    return _instance


def reset_auth_provider_for_tests() -> None:
    """Drop the cached singleton so a test can re-select the backend from the environment.

    Also clears the OIDC adapter's JWKS cache so an AUTH_BACKEND/OIDC env change between tests takes
    effect (the provider singleton alone would leave stale JWKS state behind)."""
    global _instance
    with _lock:
        _instance = None
    try:
        from utils.auth.adapters.oidc import reset_jwks_cache_for_tests

        reset_jwks_cache_for_tests()
    except Exception:
        # The OIDC adapter may be unimportable in a firebase-only test env; nothing to reset then.
        pass


__all__ = ["auth_backend_name", "get_auth_provider", "reset_auth_provider_for_tests"]

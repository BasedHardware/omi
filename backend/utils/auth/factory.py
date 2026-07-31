"""Auth backend selection (ADR-0034). ``AUTH_BACKEND`` picks the adapter; default ``firebase``
(first-class cloud). Adapters are imported lazily and initialized on first use — no ``initialize_app``
at import (which today runs as an import-time side effect in four processes)."""

from __future__ import annotations

import os
import threading
from typing import Optional

from utils.auth.ports import AuthProvider

_lock = threading.Lock()
_instance: Optional[AuthProvider] = None


def get_auth_provider() -> AuthProvider:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                backend = (os.getenv("AUTH_BACKEND") or "firebase").strip().lower()
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
    """Drop the cached singleton so a test can re-select the backend from the environment."""
    global _instance
    with _lock:
        _instance = None


__all__ = ["get_auth_provider", "reset_auth_provider_for_tests"]

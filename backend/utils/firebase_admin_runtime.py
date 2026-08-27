"""Runtime fences for Firebase Admin in isolated local QA stacks.

This module is the one place allowed to name ``firebase_admin.auth`` outside the auth adapter
(``.github/scripts/auth_boundary_baseline.json``), and the exception is not a concession: everything
here FENCES that SDK rather than calling it for authentication. It replaces twenty named
``firebase_admin.auth`` mutators with a raiser and denies ADC discovery, so a local dogfood stack
cannot write to the real Firebase project. There is no OIDC equivalent of "disable Firebase's
create_user" to port it to; the neutral form of this fence is not running Firebase at all.

It stays neutral by staying inert. Every entry point returns before importing anything Google unless
BOTH ``OMI_JIT_QA_LOCAL_STACK=1`` and the auth port is on its Firebase adapter — the second condition
is ours (upstream has one provider, so it gates on the QA flag alone, and on ``AUTH_BACKEND=oidc``
that would import and monkeypatch an SDK the process never uses).
"""

from __future__ import annotations

import os
from typing import Any, Mapping

_AUTH_MUTATORS = frozenset(
    {
        "create_custom_token",
        "create_oidc_provider_config",
        "create_saml_provider_config",
        "create_session_cookie",
        "create_user",
        "delete_oidc_provider_config",
        "delete_saml_provider_config",
        "delete_user",
        "delete_users",
        "generate_email_verification_link",
        "generate_password_reset_link",
        "generate_sign_in_with_email_link",
        "import_users",
        "revoke_refresh_tokens",
        "set_custom_user_claims",
        "update_oidc_provider_config",
        "update_saml_provider_config",
        "update_user",
    }
)


def _auth_backend_is_firebase(environ: Mapping[str, str] | None = None) -> bool:
    """Whether the configured auth provider is the Firebase adapter (ADR-0034).

    Everything in this module fences the *Firebase Admin SDK*: it replaces named
    ``firebase_admin.auth`` mutators and denies ADC discovery. On a deployment whose auth port is
    the OIDC adapter there is no Firebase to fence, and arming the guard would import and monkeypatch
    an SDK the process never uses. Upstream has one provider so it gates on the QA flag alone; here
    the flag says "local QA stack", which is not the same question as "is this Firebase".

    Read through the same env the rest of the module reads, and via the factory's own name/default so
    the two cannot drift.
    """

    from utils.auth.factory import DEFAULT_AUTH_BACKEND

    source = os.environ if environ is None else environ
    return (source.get("AUTH_BACKEND") or "").strip().lower() in {"", DEFAULT_AUTH_BACKEND}


def firebase_verify_only_enabled(environ: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    if source.get("OMI_JIT_QA_LOCAL_STACK", "").strip() != "1":
        return False
    return _auth_backend_is_firebase(environ)


def firebase_verify_only_credential(environ: Mapping[str, str] | None = None) -> Any | None:
    """Return an anonymous Admin credential for ID-token verification only.

    Firebase ID-token verification downloads public certificates and uses the
    explicit project ID; it does not need an OAuth access token. Returning
    AnonymousCredentials prevents the Admin client from borrowing development
    ADC for an Auth mutation.
    """

    if not firebase_verify_only_enabled(environ):
        return None
    from firebase_admin import credentials
    from google.auth.credentials import AnonymousCredentials

    class VerifyOnlyCredential(credentials.Base):
        def get_credential(self) -> AnonymousCredentials:
            return AnonymousCredentials()

    return VerifyOnlyCredential()


def install_firebase_auth_mutation_guard(
    environ: Mapping[str, str] | None = None, *, auth_module: Any | None = None
) -> bool:
    """Mechanically deny every Firebase Auth mutation in local JIT QA."""

    if not firebase_verify_only_enabled(environ):
        return False
    if auth_module is None:
        from firebase_admin import auth as auth_module

    def blocked(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Firebase Auth mutations are disabled in local JIT QA")

    missing = [name for name in _AUTH_MUTATORS if not hasattr(auth_module, name)]
    if missing:
        raise RuntimeError("Firebase Auth mutation guard is incomplete: " + ", ".join(sorted(missing)))
    for name in _AUTH_MUTATORS:
        setattr(auth_module, name, blocked)
    return True


def install_google_adc_guard(
    environ: Mapping[str, str] | None = None, *, google_auth_module: Any | None = None
) -> bool:
    """Deny ADC discovery in general local-JIT backend processes.

    The separate loopback Vertex broker deliberately does not set
    ``OMI_JIT_QA_LOCAL_STACK`` and is therefore the only child that can use the
    host's development ADC.
    """

    if not firebase_verify_only_enabled(environ):
        return False
    if google_auth_module is None:
        import google.auth as google_auth_module

    def blocked(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Google ADC is disabled in local JIT QA; use the loopback Vertex gateway")

    google_auth_module.default = blocked
    return True


__all__ = [
    "firebase_verify_only_credential",
    "firebase_verify_only_enabled",
    "install_firebase_auth_mutation_guard",
    "install_google_adc_guard",
]

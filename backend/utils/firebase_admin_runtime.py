"""Runtime fences for Firebase Admin in isolated local QA stacks."""

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


def firebase_verify_only_enabled(environ: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    return source.get("OMI_JIT_QA_LOCAL_STACK", "").strip() == "1" or (
        source.get("OMI_JIT_QA_AUTH_ONLY", "").strip().casefold() in {"1", "true", "yes", "on"}
        and (source.get("OMI_ENV_STAGE") or "").strip().casefold() == "dev"
        and (source.get("GOOGLE_CLOUD_PROJECT") or "").strip() == "based-hardware-dev"
    )


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

    source = os.environ if environ is None else environ
    # The local hermetic stack must deny all ADC discovery because it uses the
    # loopback Vertex broker. Cloud QA still needs Firestore ADC for its
    # isolated data plane, so its auth-only fence is intentionally narrower.
    if source.get("OMI_JIT_QA_LOCAL_STACK", "").strip() != "1":
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

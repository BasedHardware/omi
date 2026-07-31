"""Neutral auth port (ADR-0034/0004).

The domain speaks a neutral ``Principal`` (who is making this request) and ``UserProfile`` (a user's
profile fields) — never a Firebase ``UserRecord`` or a raw decoded-JWT dict. Adapters map the contract
onto Firebase Auth (reference) or any OIDC provider (self-hostable; Keycloak is the example). Selected
by ``AUTH_BACKEND`` via ``factory.get_auth_provider()``.

Two verbs are Firebase-proprietary and the OIDC adapter raises ``errors.Unsupported`` for them
(ADR-0034 §3): ``mint_custom_token`` and ``exchange_idp_credential`` (the ``signInWithIdp`` REST dance).
On-prem uses standard OIDC (Authorization Code + PKCE) directly against the provider, which needs
neither. Anonymous auth is likewise Firebase-only: ``Principal.is_anonymous`` is always False on OIDC.

The ADMIN_KEY impersonation and the LOCAL_DEVELOPMENT dev-bypass are NOT adapter concerns — they wrap
``verify_token`` in the shared seam (``authenticate``), so both dependency stacks share one behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class Principal:
    """Who is making a request — the neutral result of verifying a bearer token."""

    uid: str
    email: Optional[str] = None
    email_verified: bool = False
    is_anonymous: bool = False
    provider: Optional[str] = None  # e.g. 'google.com' / 'password' / 'anonymous' / an OIDC issuer
    claims: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UserProfile:
    """A user's profile fields — the backend-neutral shape of a Firebase UserRecord / OIDC user."""

    uid: str
    email: Optional[str] = None
    email_verified: bool = False
    phone_number: Optional[str] = None
    display_name: Optional[str] = None
    photo_url: Optional[str] = None
    disabled: bool = False
    providers: List[str] = field(default_factory=list)


@runtime_checkable
class AuthProvider(Protocol):
    """The neutral auth contract. ``verify_token`` is the hot path (HTTP + WS); the rest are user ops."""

    def verify_token(self, bearer: str, *, check_revoked: bool = False) -> Principal:
        """Validate a bearer token and return its Principal. ``check_revoked=True`` also rejects tokens
        revoked server-side (used by the anonymous migrate-owner proof). Raises errors.InvalidToken/
        ExpiredToken/RevokedToken/JWKSUnavailable — never a backend SDK exception."""
        ...

    def get_user_profile(self, uid: str) -> UserProfile:
        """Look up a user's profile by uid (Firebase get_user / Keycloak Admin API)."""
        ...

    def update_user_profile(self, uid: str, *, display_name: Optional[str] = None) -> None: ...

    def delete_user(self, uid: str) -> None: ...

    # --- Firebase-only (OIDC raises errors.Unsupported) ---
    def mint_custom_token(self, uid: str) -> str: ...

    def exchange_idp_credential(self, provider: str, id_token: str, access_token: Optional[str] = None) -> str:
        """Exchange a provider (google/apple) credential for the canonical uid (Firebase signInWithIdp)."""
        ...


__all__ = ["Principal", "UserProfile", "AuthProvider"]

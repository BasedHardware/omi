"""In-memory ``AuthProvider`` fake for hermetic unit tests of migrated callers (WP3, ADR-0034).

Register bearer→Principal and uid→UserProfile up front; the adapters have their own live dual-backend
contract test (Firebase emulator ↔ Keycloak). This fake lets callers migrated to ``utils.auth`` be
unit-tested without any auth backend and without ad-hoc ``firebase_admin.auth`` stubbing.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

from utils.auth.errors import AuthError, ExpiredToken, InvalidToken, JWKSUnavailable, RevokedToken, Unsupported
from utils.auth.ports import Principal, UserProfile


class FakeAuthProvider:
    """In-memory AuthProvider. ``supports_firebase_only`` toggles whether the Firebase-only verbs work
    (set False to emulate the OIDC adapter, which raises Unsupported for custom_token/idp-exchange)."""

    def __init__(self, *, supports_firebase_only: bool = True):
        self._principals: Dict[str, Principal] = {}
        self._profiles: Dict[str, UserProfile] = {}
        self._supports_firebase_only = supports_firebase_only
        self._revoked: set[str] = set()
        self._errors: Dict[str, AuthError] = {}
        self.deleted: List[str] = []
        self.minted: List[str] = []

    # --- test setup ---
    def register(self, bearer: str, principal: Principal) -> "FakeAuthProvider":
        self._principals[bearer] = principal
        return self

    def register_profile(self, profile: UserProfile) -> "FakeAuthProvider":
        self._profiles[profile.uid] = profile
        return self

    def register_revoked(self, bearer: str) -> "FakeAuthProvider":
        """Mark a token revoked server-side. It STILL verifies until a caller passes ``check_revoked``.

        That asymmetry is the semantic, not a shortcut: a signed JWT stays signature-valid after a
        logout, which is exactly why ``check_revoked`` exists and why the OIDC adapter pays for a
        separate introspection call. A fake that raised regardless would let a caller pass a test it
        would fail in production.
        """
        self._revoked.add(bearer)
        return self

    def register_expired(self, bearer: str) -> "FakeAuthProvider":
        return self.register_error(bearer, ExpiredToken(f"expired: {bearer!r}"))

    def register_jwks_unavailable(self, bearer: str) -> "FakeAuthProvider":
        return self.register_error(bearer, JWKSUnavailable(f"keys unavailable for: {bearer!r}"))

    def register_error(self, bearer: str, error: AuthError) -> "FakeAuthProvider":
        """Any neutral error, including a bare ``AuthError`` — the class ADR-0074 maps an unexpected
        adapter failure to, whose handling callers also need to be able to test."""
        self._errors[bearer] = error
        return self

    # --- port ---
    def verify_token(self, bearer: str, *, check_revoked: bool = False) -> Principal:
        """The whole neutral taxonomy is reachable from here (BACKLOG L15).

        It used to ignore ``check_revoked`` and raise only ``InvalidToken``, which made two real
        behaviours inexpressible through this fake: the migrate-owner revocation proof
        (``routers/apps.py``, the one caller that asks for it) and the WebSocket close-code contract,
        which routes each error CLASS to a different client recovery. So every migrated caller was
        tested by stubbing ``firebase_admin.auth`` instead — 54 files — and the port stayed crossed
        almost only by the Firebase adapter.
        """
        registered_error = self._errors.get(bearer)
        if registered_error is not None:
            raise registered_error
        try:
            principal = self._principals[bearer]
        except KeyError:
            raise InvalidToken(f"unknown token: {bearer!r}")
        if check_revoked and bearer in self._revoked:
            raise RevokedToken(f"revoked: {bearer!r}")
        return principal

    def get_user_profile(self, uid: str) -> UserProfile:
        return self._profiles.get(uid) or UserProfile(uid=uid)

    def update_user_profile(self, uid: str, *, display_name: Optional[str] = None) -> None:
        if display_name is not None:
            base = self._profiles.get(uid) or UserProfile(uid=uid)
            self._profiles[uid] = replace(base, display_name=display_name)

    def delete_user(self, uid: str) -> None:
        self.deleted.append(uid)
        self._profiles.pop(uid, None)

    def mint_custom_token(self, uid: str) -> str:
        if not self._supports_firebase_only:
            raise Unsupported("mint_custom_token is Firebase-only")
        self.minted.append(uid)
        return f"custom-token:{uid}"

    def exchange_idp_credential(self, provider: str, id_token: str, access_token: Optional[str] = None) -> str:
        if not self._supports_firebase_only:
            raise Unsupported("exchange_idp_credential is Firebase-only")
        return f"uid-for:{provider}:{id_token}"


__all__ = ["FakeAuthProvider"]

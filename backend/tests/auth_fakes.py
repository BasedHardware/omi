"""In-memory ``AuthProvider`` fake for hermetic unit tests of migrated callers (WP3, ADR-0034).

Register bearer→Principal and uid→UserProfile up front; the adapters have their own live dual-backend
contract test (Firebase emulator ↔ Keycloak). This fake lets callers migrated to ``utils.auth`` be
unit-tested without any auth backend and without ad-hoc ``firebase_admin.auth`` stubbing.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

from utils.auth.errors import InvalidToken, Unsupported
from utils.auth.ports import Principal, UserProfile


class FakeAuthProvider:
    """In-memory AuthProvider. ``supports_firebase_only`` toggles whether the Firebase-only verbs work
    (set False to emulate the OIDC adapter, which raises Unsupported for custom_token/idp-exchange)."""

    def __init__(self, *, supports_firebase_only: bool = True):
        self._principals: Dict[str, Principal] = {}
        self._profiles: Dict[str, UserProfile] = {}
        self._supports_firebase_only = supports_firebase_only
        self.deleted: List[str] = []
        self.minted: List[str] = []

    # --- test setup ---
    def register(self, bearer: str, principal: Principal) -> "FakeAuthProvider":
        self._principals[bearer] = principal
        return self

    def register_profile(self, profile: UserProfile) -> "FakeAuthProvider":
        self._profiles[profile.uid] = profile
        return self

    # --- port ---
    def verify_token(self, bearer: str, *, check_revoked: bool = False) -> Principal:
        try:
            return self._principals[bearer]
        except KeyError:
            raise InvalidToken(f"unknown token: {bearer!r}")

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

"""Generic OIDC auth adapter for the auth port (ADR-0034) — the self-hostable reference.

One adapter for any standard OIDC provider (Keycloak is the example; Authentik/Auth0/etc. work the
same by changing the issuer). Token verification is JWKS-based JWT validation with PyJWT +
cryptography (both already pinned — no new dependency). User-profile reads/writes use the provider's
Admin API (Keycloak's ``/admin/realms/{realm}/users``). The two Firebase-proprietary verbs
(``mint_custom_token`` / ``exchange_idp_credential``) raise ``Unsupported`` — on-prem uses standard
OIDC Authorization-Code+PKCE directly, which needs neither (ADR-0034 §3). Anonymous is Firebase-only,
so ``Principal.is_anonymous`` is always False here.

Env — verification: ``OIDC_ISSUER`` (e.g. http://keycloak:8080/realms/omi), ``OIDC_JWKS_URL``
(default ``{issuer}/protocol/openid-connect/certs``), ``OIDC_AUDIENCE`` (optional; aud is verified
only when set). Admin API: ``OIDC_ADMIN_API_URL`` (e.g. .../admin/realms/omi), ``OIDC_ADMIN_TOKEN_URL``,
``OIDC_ADMIN_CLIENT_ID``, ``OIDC_ADMIN_CLIENT_SECRET``.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional

from utils.auth import errors
from utils.auth.ports import Principal, UserProfile

# Outbound admin-API calls pin an explicit timeout so a hung IdP never blocks a worker thread
# indefinitely (the utils outbound-timeout guard enforces this).
_HTTP_TIMEOUT_SECONDS = 10.0

_jwks_lock = threading.Lock()
_jwks_client: Any = None


def _issuer() -> str:
    iss = (os.getenv("OIDC_ISSUER") or "").strip()
    if not iss:
        raise errors.AuthError("OIDC_ISSUER is not configured")
    return iss.rstrip("/")


def _jwks_url() -> str:
    return (os.getenv("OIDC_JWKS_URL") or "").strip() or f"{_issuer()}/protocol/openid-connect/certs"


def _get_jwks_client() -> Any:
    global _jwks_client
    if _jwks_client is None:
        with _jwks_lock:
            if _jwks_client is None:
                from jwt import PyJWKClient  # lazy: only the oidc backend needs PyJWT

                _jwks_client = PyJWKClient(_jwks_url())
    return _jwks_client


def reset_jwks_cache_for_tests() -> None:
    global _jwks_client
    _jwks_client = None


class OIDCAuthProvider:
    """AuthProvider over any OIDC provider (Keycloak reference). uid == the token's ``sub`` claim."""

    def verify_token(self, bearer: str, *, check_revoked: bool = False) -> Principal:
        import jwt

        audience = (os.getenv("OIDC_AUDIENCE") or "").strip() or None
        try:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(bearer)
            decoded: Dict[str, Any] = jwt.decode(
                bearer,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=_issuer(),
                options={"verify_aud": audience is not None},
            )
        except jwt.ExpiredSignatureError as exc:
            raise errors.ExpiredToken(str(exc))
        except jwt.PyJWKClientError as exc:
            raise errors.JWKSUnavailable(str(exc))
        except jwt.InvalidTokenError as exc:
            raise errors.InvalidToken(str(exc))
        except Exception as exc:  # JWKS fetch/transport failures
            raise errors.JWKSUnavailable(str(exc))

        return Principal(
            uid=decoded["sub"],
            email=decoded.get("email"),
            email_verified=bool(decoded.get("email_verified", False)),
            is_anonymous=False,  # OIDC has no anonymous principal (ADR-0034 §3)
            provider=decoded.get("iss"),
            claims=decoded,
        )

    # --- Admin API (Keycloak) ---
    def _admin_token(self) -> str:
        import httpx

        token_url = (os.getenv("OIDC_ADMIN_TOKEN_URL") or "").strip()
        client_id = (os.getenv("OIDC_ADMIN_CLIENT_ID") or "").strip()
        client_secret = (os.getenv("OIDC_ADMIN_CLIENT_SECRET") or "").strip()
        if not (token_url and client_id and client_secret):
            raise errors.AuthError("OIDC admin API is not configured (OIDC_ADMIN_TOKEN_URL/CLIENT_ID/CLIENT_SECRET)")
        resp = httpx.post(
            token_url,
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            raise errors.AuthError(f"OIDC admin token request failed: status={resp.status_code}")
        return resp.json()["access_token"]

    def _admin_api(self) -> str:
        url = (os.getenv("OIDC_ADMIN_API_URL") or "").strip()
        if not url:
            raise errors.AuthError("OIDC_ADMIN_API_URL is not configured")
        return url.rstrip("/")

    def get_user_profile(self, uid: str) -> UserProfile:
        import httpx

        resp = httpx.get(
            f"{self._admin_api()}/users/{uid}",
            headers={"Authorization": f"Bearer {self._admin_token()}"},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            raise errors.AuthError(f"OIDC get_user failed: status={resp.status_code}")
        rep: Dict[str, Any] = resp.json()
        name = " ".join(p for p in [rep.get("firstName"), rep.get("lastName")] if p) or None
        return UserProfile(
            uid=rep.get("id", uid),
            email=rep.get("email"),
            email_verified=bool(rep.get("emailVerified", False)),
            phone_number=(rep.get("attributes", {}) or {}).get("phone_number", [None])[0],
            display_name=name,
            photo_url=None,
            disabled=not bool(rep.get("enabled", True)),
            providers=[fi.get("identityProvider") for fi in (rep.get("federatedIdentities") or []) if fi.get("identityProvider")],
        )

    def update_user_profile(self, uid: str, *, display_name: Optional[str] = None) -> None:
        import httpx

        if display_name is None:
            return
        first, _, last = display_name.partition(" ")
        resp = httpx.put(
            f"{self._admin_api()}/users/{uid}",
            headers={"Authorization": f"Bearer {self._admin_token()}"},
            json={"firstName": first, "lastName": last},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code not in (200, 204):
            raise errors.AuthError(f"OIDC update_user failed: status={resp.status_code}")

    def delete_user(self, uid: str) -> None:
        import httpx

        resp = httpx.delete(
            f"{self._admin_api()}/users/{uid}",
            headers={"Authorization": f"Bearer {self._admin_token()}"},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        # Deletion is idempotent: a 404 means the identity is already gone (a prior attempt succeeded
        # before the wipe marker committed, or the user was removed out-of-band). The account-deletion
        # worker treats an already-absent auth user as success — mirror that here so retries complete
        # instead of looping on a fatal "wipe failed". Matches Firebase, whose UserNotFoundError the
        # worker already swallows, and the object-store adapters' no-raise-on-missing delete.
        if resp.status_code == 404:
            return
        if resp.status_code not in (200, 204):
            raise errors.AuthError(f"OIDC delete_user failed: status={resp.status_code}")

    # --- Firebase-only verbs (ADR-0034 §3) ---
    def mint_custom_token(self, uid: str) -> str:
        raise errors.Unsupported("mint_custom_token is Firebase-only; OIDC uses standard Auth-Code+PKCE")

    def exchange_idp_credential(self, provider: str, id_token: str, access_token: Optional[str] = None) -> str:
        raise errors.Unsupported("exchange_idp_credential is Firebase-only; OIDC brokers IdPs at the provider")


__all__ = ["OIDCAuthProvider"]

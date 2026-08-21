"""Generic OIDC auth adapter for the auth port (ADR-0034) — the self-hostable reference.

One adapter for any standard OIDC provider (Keycloak is the example; Authentik/Auth0/etc. work the
same by changing the issuer). Token verification is JWKS-based JWT validation with PyJWT +
cryptography (both already pinned — no new dependency). User-profile reads/writes use the provider's
Admin API (Keycloak's ``/admin/realms/{realm}/users``). The two Firebase-proprietary verbs
(``mint_custom_token`` / ``exchange_idp_credential``) raise ``Unsupported`` — on-prem uses standard
OIDC Authorization-Code+PKCE directly, which needs neither (ADR-0034 §3). Anonymous is Firebase-only,
so ``Principal.is_anonymous`` is always False here.

Env — verification: ``OIDC_ISSUER`` (e.g. http://keycloak:8080/realms/omi), ``OIDC_JWKS_URL``
(default ``{issuer}/protocol/openid-connect/certs``), ``OIDC_AUDIENCE`` (**required** — verify_token
fail-closes without it, to prevent cross-client token confusion), ``OIDC_SIGNING_ALGS`` (optional,
comma-separated; default ``RS256`` — set for a provider that signs with ES256/PS256/EdDSA). Admin API:
``OIDC_ADMIN_API_URL`` (e.g. .../admin/realms/omi), ``OIDC_ADMIN_TOKEN_URL``, ``OIDC_ADMIN_CLIENT_ID``,
``OIDC_ADMIN_CLIENT_SECRET``.

Profile operations target the provider's Admin API and its representation (Keycloak's user JSON:
firstName/lastName, attributes, federatedIdentities). Token *verification* is provider-agnostic, but
profile reads/writes are Keycloak-shaped — a different provider needs its own admin mapping (ADR-0034 §3).
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional
from urllib.parse import quote

from utils.auth import errors
from utils.auth.ports import Principal, UserProfile

# Outbound admin-API calls pin an explicit timeout so a hung IdP never blocks a worker thread
# indefinitely (the utils outbound-timeout guard enforces this).
_HTTP_TIMEOUT_SECONDS = 10.0


def _admin_path_segment(uid: str) -> str:
    """Encode a uid so it can only ever be ONE path segment of an Admin API URL.

    The uid reaches these methods from callers, and one of them is a request parameter:
    ``POST /v1/apps/migrate-owner`` passes ``old_id`` to ``get_user`` *before* its
    ``source_uid != old_id`` eligibility check. Interpolated raw, a value containing ``/`` or ``..``
    reshapes the request — httpx normalises dot segments (RFC 3986), so ``../groups`` turns a user
    lookup into ``GET /admin/realms/{realm}/groups`` carried by the admin client's bearer token. The
    response is never returned to the caller, so this was a blind request-forgery primitive rather
    than a data leak, but it is one that does not exist under Firebase (its SDK takes a uid, not a
    URL). Encoding belongs here, at the boundary that owns the URL: a check bolted onto one router
    would leave the other two verbs exposed. A Keycloak uid is a UUID, so the normal case is
    unchanged — ``safe=''`` also escapes any reserved character rather than trusting the provider's
    id format.
    """
    return quote(uid, safe='')

_jwks_lock = threading.Lock()
_jwks_client: Any = None


def _issuer() -> str:
    iss = (os.getenv("OIDC_ISSUER") or "").strip()
    if not iss:
        raise errors.AuthError("OIDC_ISSUER is not configured")
    return iss.rstrip("/")


def _jwks_url() -> str:
    return (os.getenv("OIDC_JWKS_URL") or "").strip() or f"{_issuer()}/protocol/openid-connect/certs"


def _oidc_http(call: Any) -> Any:
    """Run an httpx call, translating a transport failure (connect/timeout/DNS) into the neutral
    ``JWKSUnavailable`` (transient/retryable) so no raw httpx exception escapes the auth port — the
    introspection and admin-API calls sit outside verify_token's translation block (cubic PR 10887
    oidc.py:150/186)."""
    import httpx

    try:
        return call()
    except httpx.HTTPError as exc:
        raise errors.JWKSUnavailable(f"OIDC endpoint unreachable: {exc}")


def _oidc_json(resp: Any) -> dict:
    """Parse a response body into a JSON object, mapping a non-JSON payload OR a valid-but-not-object
    payload (list/string/number) to a neutral ``AuthError`` — otherwise the raw ValueError/JSONDecodeError
    or a later ``.get`` ``AttributeError`` leaks through the port (cubic PR 10887 oidc.py:68)."""
    try:
        parsed = resp.json()
    except ValueError as exc:
        raise errors.AuthError(f"OIDC returned a non-JSON response: {exc}")
    if not isinstance(parsed, dict):
        raise errors.AuthError(f"OIDC returned a non-object JSON payload: {type(parsed).__name__}")
    return parsed


def _signing_algs() -> list[str]:
    """Permitted JWT signing algorithms. Default RS256 (Keycloak/Auth0's default); override via
    ``OIDC_SIGNING_ALGS`` (comma-separated) for a provider that signs with ES256/PS256/EdDSA — otherwise
    valid tokens on those algorithms are silently rejected (cubic PR 10887 oidc.py:82)."""
    raw = (os.getenv("OIDC_SIGNING_ALGS") or "RS256").strip()
    return [a.strip() for a in raw.split(",") if a.strip()] or ["RS256"]


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

        audience = (os.getenv("OIDC_AUDIENCE") or "").strip()
        if not audience:
            # Fail-closed: without an expected audience the API would accept ANY token the
            # issuer signed, including one minted for a different client in the same realm
            # (cross-client token confusion). Require it explicitly (cubic review PR 10887).
            # NOTE: Keycloak's default aud is "account" for every client — set OIDC_AUDIENCE to a
            # dedicated audience added via a client Audience mapper for real cross-client isolation.
            raise errors.AuthError(
                "OIDC_AUDIENCE must be set: audience validation is required (fail-closed) to prevent cross-client token confusion"
            )
        try:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(bearer)
            decoded: Dict[str, Any] = jwt.decode(
                bearer,
                signing_key.key,
                algorithms=_signing_algs(),
                audience=audience,
                issuer=_issuer(),
                # require exp + sub explicitly: PyJWT verifies exp only when PRESENT, so a token minted
                # WITHOUT exp would otherwise be accepted (never-expiring identity); and sub is the uid
                # (read below), so a token without it must fail closed as InvalidToken here, not KeyError
                # 500 downstream (cubic review PR 10887).
                options={"verify_aud": True, "require": ["exp", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise errors.ExpiredToken(str(exc))
        except jwt.PyJWKClientError as exc:
            raise errors.JWKSUnavailable(str(exc))
        except jwt.InvalidTokenError as exc:
            raise errors.InvalidToken(str(exc))
        except errors.AuthError:
            # A configuration error surfaced inside the try (e.g. _issuer()/_jwks_url() with OIDC_ISSUER
            # unset) is permanent — let it propagate as-is instead of the broad handler below reclassifying
            # it as JWKSUnavailable (a transient/retryable class) (cubic PR 10887 oidc.py:84).
            raise
        except OSError as exc:
            # JWKS fetch/transport failure — URLError, timeouts, DNS, connection refused are all OSError
            # subclasses. This is the transient class the WS mapper turns into 4001 "refresh your token",
            # and it is the only thing that should be.
            raise errors.JWKSUnavailable(str(exc))
        except Exception as exc:
            # Anything else here is OURS, not the client's: a TypeError, a wrong admin config, an
            # unexpected library shape. Mapping it to JWKSUnavailable told the client to refresh a token
            # that was fine — forever, since a deterministic bug never stops happening — and HTTP hid it
            # behind the same 401 (BACKLOG L13). A plain AuthError maps to close code 1008 instead.
            #
            # This mirrors the Firebase adapter, which already made this exact distinction: its
            # ``_translate`` maps an unknown failure to ``AuthError`` and says why. The two adapters now
            # agree, which is the point of having a neutral taxonomy at all.
            raise errors.AuthError(str(exc))

        if check_revoked and not self._introspect_active(bearer):
            # A JWT stays signature/exp-valid after a server-side logout/revocation; only introspection
            # (RFC 7662) reflects the live session state. ``active: false`` => revoked/invalidated.
            raise errors.RevokedToken("token is not active (revoked or invalidated server-side)")

        return Principal(
            uid=decoded["sub"],
            email=decoded.get("email"),
            email_verified=bool(decoded.get("email_verified", False)),
            is_anonymous=False,  # OIDC has no anonymous principal (ADR-0034 §3)
            provider=decoded.get("iss"),
            claims=decoded,
        )

    def _introspect_active(self, token: str) -> bool:
        """RFC 7662 token introspection — the revocation check for stateless OIDC (``check_revoked``).

        Reuses the confidential admin client to authenticate the introspection POST; the endpoint
        defaults to ``{issuer}/protocol/openid-connect/token/introspect`` (override OIDC_INTROSPECTION_URL).
        Returns the ``active`` flag; a caller that asked for revocation checking without the client
        credentials configured gets a loud AuthError rather than a silent pass (fail-closed).
        """
        import httpx

        url = (os.getenv("OIDC_INTROSPECTION_URL") or "").strip() or f"{_issuer()}/protocol/openid-connect/token/introspect"
        client_id = (os.getenv("OIDC_ADMIN_CLIENT_ID") or "").strip()
        client_secret = (os.getenv("OIDC_ADMIN_CLIENT_SECRET") or "").strip()
        if not (client_id and client_secret):
            raise errors.AuthError(
                "check_revoked requires OIDC introspection credentials (OIDC_ADMIN_CLIENT_ID/OIDC_ADMIN_CLIENT_SECRET)"
            )
        resp = _oidc_http(
            lambda: httpx.post(
                url,
                data={"token": token, "client_id": client_id, "client_secret": client_secret},
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
        )
        if resp.status_code != 200:
            raise errors.JWKSUnavailable(f"OIDC introspection failed: status={resp.status_code}")
        # RFC 7662: `active` is a JSON boolean. Require the literal ``True`` — ``bool(...)`` would treat a
        # non-compliant string like ``"false"`` (truthy) as an active token, failing OPEN on revocation
        # (cubic PR 10887 oidc.py:181). Anything that is not literally True keeps revocation fail-closed.
        return _oidc_json(resp).get("active") is True

    # --- Admin API (Keycloak) ---
    def _admin_token(self) -> str:
        import httpx

        token_url = (os.getenv("OIDC_ADMIN_TOKEN_URL") or "").strip()
        client_id = (os.getenv("OIDC_ADMIN_CLIENT_ID") or "").strip()
        client_secret = (os.getenv("OIDC_ADMIN_CLIENT_SECRET") or "").strip()
        if not (token_url and client_id and client_secret):
            raise errors.AuthError("OIDC admin API is not configured (OIDC_ADMIN_TOKEN_URL/CLIENT_ID/CLIENT_SECRET)")
        resp = _oidc_http(
            lambda: httpx.post(
                token_url,
                data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
        )
        if resp.status_code != 200:
            raise errors.AuthError(f"OIDC admin token request failed: status={resp.status_code}")
        token = _oidc_json(resp).get("access_token")
        if not token:
            raise errors.AuthError("OIDC admin token response missing access_token")
        return token

    def _admin_api(self) -> str:
        url = (os.getenv("OIDC_ADMIN_API_URL") or "").strip()
        if not url:
            raise errors.AuthError("OIDC_ADMIN_API_URL is not configured")
        return url.rstrip("/")

    def get_user_profile(self, uid: str) -> UserProfile:
        import httpx

        resp = _oidc_http(
            lambda: httpx.get(
                f"{self._admin_api()}/users/{_admin_path_segment(uid)}",
                headers={"Authorization": f"Bearer {self._admin_token()}"},
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
        )
        if resp.status_code != 200:
            raise errors.AuthError(f"OIDC get_user failed: status={resp.status_code}")
        rep: Dict[str, Any] = _oidc_json(resp)
        name = " ".join(p for p in [rep.get("firstName"), rep.get("lastName")] if p) or None
        return UserProfile(
            uid=rep.get("id", uid),
            email=rep.get("email"),
            email_verified=bool(rep.get("emailVerified", False)),
            # ``or [None]`` (not a ``[None]`` default): Keycloak can return an attribute present but
            # EMPTY (``{"phone_number": []}``), where a plain default would not fire and ``[][0]`` raises.
            phone_number=((rep.get("attributes", {}) or {}).get("phone_number") or [None])[0],
            display_name=name,
            photo_url=None,
            disabled=not bool(rep.get("enabled", True)),
            providers=[fi.get("identityProvider") for fi in (rep.get("federatedIdentities") or []) if fi.get("identityProvider")],
            created_at=rep.get("createdTimestamp"),  # Keycloak exposes account creation as epoch ms
        )

    def update_user_profile(self, uid: str, *, display_name: Optional[str] = None) -> None:
        import httpx

        if display_name is None:
            return
        first, _, last = display_name.partition(" ")
        resp = _oidc_http(
            lambda: httpx.put(
                f"{self._admin_api()}/users/{_admin_path_segment(uid)}",
                headers={"Authorization": f"Bearer {self._admin_token()}"},
                json={"firstName": first, "lastName": last},
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
        )
        if resp.status_code not in (200, 204):
            raise errors.AuthError(f"OIDC update_user failed: status={resp.status_code}")

    def delete_user(self, uid: str) -> None:
        import httpx

        resp = _oidc_http(
            lambda: httpx.delete(
                f"{self._admin_api()}/users/{_admin_path_segment(uid)}",
                headers={"Authorization": f"Bearer {self._admin_token()}"},
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
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

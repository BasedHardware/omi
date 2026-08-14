"""Firebase Auth adapter — the reference implementation of the auth port (ADR-0034).

Encapsulates exactly the ``firebase_admin.auth`` logic that was scattered across the backend
(verify_id_token, get_user, update_user, delete_user, create_custom_token, the signInWithIdp REST
exchange), translating Firebase SDK exceptions into the neutral ``errors`` taxonomy. Admin init stays
lazy (firebase_admin is imported/initialized on first use, not at module import).
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from utils.auth import errors
from utils.auth.ports import Principal, UserProfile

# Pin an explicit timeout on the Identity Toolkit call so a hung provider never blocks indefinitely
# (the utils outbound-timeout guard enforces this).
_HTTP_TIMEOUT_SECONDS = 10.0


def _auth():
    from firebase_admin import auth  # lazy: only the firebase backend needs the SDK

    return auth


def _translate(exc: Exception) -> errors.AuthError:
    import firebase_admin.auth as fa

    # getattr with an empty-tuple fallback: a firebase version (or an incomplete test stub) that lacks
    # one of these classes just makes that isinstance branch never match — never an ImportError.
    revoked = getattr(fa, 'RevokedIdTokenError', ())
    expired = getattr(fa, 'ExpiredIdTokenError', ())
    cert = getattr(fa, 'CertificateFetchError', ())
    invalid = getattr(fa, 'InvalidIdTokenError', ())

    if isinstance(exc, revoked):
        return errors.RevokedToken(str(exc))
    if isinstance(exc, expired):
        return errors.ExpiredToken(str(exc))
    if isinstance(exc, cert):
        return errors.JWKSUnavailable(str(exc))
    if isinstance(exc, invalid):
        return errors.InvalidToken(str(exc))
    return errors.InvalidToken(str(exc))


class FirebaseAuthProvider:
    """AuthProvider over Firebase Auth. ``uid`` is the Firebase uid."""

    def verify_token(self, bearer: str, *, check_revoked: bool = False) -> Principal:
        try:
            decoded: Any = _auth().verify_id_token(bearer, check_revoked=check_revoked)
        except Exception as exc:  # firebase SDK exceptions -> neutral taxonomy
            raise _translate(exc)
        firebase_claims = decoded.get('firebase') or {}
        sign_in_provider = firebase_claims.get('sign_in_provider')
        return Principal(
            uid=decoded['uid'],
            email=decoded.get('email'),
            email_verified=bool(decoded.get('email_verified', False)),
            is_anonymous=sign_in_provider == 'anonymous',
            provider=sign_in_provider,
            claims=dict(decoded),
        )

    def get_user_profile(self, uid: str) -> UserProfile:
        rec = _auth().get_user(uid)
        providers: List[str] = [getattr(p, 'provider_id', '') for p in (getattr(rec, 'provider_data', None) or [])]
        return UserProfile(
            uid=rec.uid,
            email=getattr(rec, 'email', None),
            email_verified=bool(getattr(rec, 'email_verified', False)),
            phone_number=getattr(rec, 'phone_number', None),
            display_name=getattr(rec, 'display_name', None),
            photo_url=getattr(rec, 'photo_url', None),
            disabled=bool(getattr(rec, 'disabled', False)),
            providers=[p for p in providers if p],
            created_at=getattr(getattr(rec, 'user_metadata', None), 'creation_timestamp', None),
        )

    def update_user_profile(self, uid: str, *, display_name: Optional[str] = None) -> None:
        if display_name is not None:
            _auth().update_user(uid, display_name=display_name)

    def delete_user(self, uid: str) -> None:
        _auth().delete_user(uid)

    def mint_custom_token(self, uid: str) -> str:
        token = _auth().create_custom_token(uid)
        return token.decode('utf-8') if isinstance(token, bytes) else str(token)

    def exchange_idp_credential(self, provider: str, id_token: str, access_token: Optional[str] = None) -> str:
        """Firebase signInWithIdp REST exchange → the canonical Firebase uid (needs FIREBASE_API_KEY)."""
        import httpx

        api_key = (os.getenv('FIREBASE_API_KEY') or '').strip()
        if not api_key:
            raise errors.AuthError('FIREBASE_API_KEY not configured')
        provider_id = {'google': 'google.com', 'apple': 'apple.com'}.get(provider)
        if not provider_id:
            raise errors.AuthError(f'unsupported provider: {provider}')
        # URL-encode every field: opaque provider tokens can contain form-reserved
        # characters (& = +), which would otherwise corrupt the signInWithIdp postBody
        # and fail the exchange for some Google/Apple sign-ins.
        from urllib.parse import urlencode

        params = {'id_token': id_token, 'providerId': provider_id}
        if access_token:
            params['access_token'] = access_token
        post_body = urlencode(params)
        url = f'https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={api_key}'
        resp = httpx.post(
            url,
            json={'postBody': post_body, 'requestUri': 'http://localhost', 'returnIdpCredential': True, 'returnSecureToken': True},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            raise errors.AuthError(f'signInWithIdp failed: status={resp.status_code}')
        uid = resp.json().get('localId')
        if not uid:
            raise errors.AuthError('no uid returned from signInWithIdp')
        return uid


__all__ = ["FirebaseAuthProvider"]

import hmac
import os

from fastapi import HTTPException, Request

_TWITTER_TOOLS_SECRET_ENV = 'TWITTER_TOOLS_SECRET'
_QUERY_TOKEN_PARAM = 'twitter_tools_token'


def _configured_secret() -> str | None:
    secret = os.getenv(_TWITTER_TOOLS_SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def _presented_token(request: Request) -> str | None:
    auth = request.headers.get('Authorization')
    if auth:
        scheme, _, credentials = auth.partition(' ')
        if scheme.lower() == 'bearer' and credentials.strip():
            return credentials.strip()
    query_token = request.query_params.get(_QUERY_TOKEN_PARAM)
    if query_token and query_token.strip():
        return query_token.strip()
    return None


def require_twitter_tools_auth(request: Request) -> None:
    """Authenticate backend-invoked tool routes by shared secret.

    These routes carry uid inside the JSON body, so the guard only
    authenticates the caller; the body's uid stays the data-plane key.
    """
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail='twitter tools auth is not configured')

    token = _presented_token(request)
    if not token or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail='unauthorized')


def disconnect_sig(uid: str) -> str:
    """HMAC signature binding a /disconnect link to a uid.

    The settings page renders a browser GET link, so the Bearer/secret
    guard cannot apply; the server signs the uid and the endpoint
    verifies it instead.
    """
    secret = _configured_secret() or ''
    return hmac.new(secret.encode(), uid.encode(), 'sha256').hexdigest()[:32]


def verify_disconnect_sig(uid: str, sig: str) -> None:
    if _configured_secret() is None:
        raise HTTPException(status_code=503, detail='twitter tools auth is not configured')
    if not sig or not hmac.compare_digest(sig, disconnect_sig(uid)):
        raise HTTPException(status_code=401, detail='unauthorized')

"""Small auth primitives shared by Omi plugin apps."""

import secrets


def generate_oauth_state(token_bytes: int = 32) -> str:
    """Return a URL-safe random OAuth state value."""
    return secrets.token_urlsafe(token_bytes)


def require_bearer_token(authorization: str | None) -> str | None:
    """Extract a bearer token without logging or validating provider secrets."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token

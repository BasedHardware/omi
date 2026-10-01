"""Constant-time, fail-closed ADMIN_KEY verification for the `secret-key` routes."""

import hmac
import os


def admin_key_matches(secret_key: str | None) -> bool:
    """Return True only for a non-empty ``secret_key`` equal to a non-empty configured ADMIN_KEY.

    The ad-hoc ``secret_key != os.getenv('ADMIN_KEY')`` checks on the admin routes are False when
    both sides are empty, so a deployment where ADMIN_KEY resolves to ``""`` (an operator error the
    repo's own workflows treat as real) authenticates an empty ``secret-key`` as admin. They also
    compare with ``!=``, which is not constant-time. This fails closed on an unset/empty configured
    key and an empty candidate, and compares in constant time.
    """
    expected = os.getenv('ADMIN_KEY')
    if not expected or not secret_key:
        return False
    # Compare as bytes: `compare_digest` raises TypeError for str arguments containing non-ASCII
    # characters (Starlette decodes header values as latin-1, so an unauthenticated client can
    # send `secret-key: é`), which would turn a bad key into a 500. Bytes also keep it constant-time.
    return hmac.compare_digest(secret_key.encode('utf-8'), expected.encode('utf-8'))

"""firebase `_translate` must map UNKNOWN failures (SDK not initialized, transport/cert glitch) to
AuthError, not InvalidToken (cubic review PR 10887, review 4939247683).

The LOCAL_DEVELOPMENT uid-123 fallback (utils/other/endpoints.py) catches only InvalidToken; if a
setup/transport failure were labeled InvalidToken it would slip through and grant every request the
same identity. Genuine invalid/malformed tokens still surface via InvalidIdTokenError -> InvalidToken.
"""

from __future__ import annotations

import firebase_admin.auth as fa

from utils.auth import errors
from utils.auth.adapters.firebase import _translate


def test_unknown_exception_maps_to_autherror_not_invalidtoken():
    result = _translate(ValueError("The default Firebase app does not exist"))
    assert isinstance(result, errors.AuthError)
    assert not isinstance(result, errors.InvalidToken)


def test_genuine_invalid_token_still_maps_to_invalidtoken():
    # InvalidIdTokenError is one of the four token classes -> the dev fallback still works for real
    # invalid tokens.
    exc = fa.InvalidIdTokenError("bad token")
    assert isinstance(_translate(exc), errors.InvalidToken)


def test_expired_and_revoked_keep_their_neutral_types():
    assert isinstance(_translate(fa.ExpiredIdTokenError("expired", cause=None)), errors.ExpiredToken)
    assert isinstance(_translate(fa.RevokedIdTokenError("revoked")), errors.RevokedToken)

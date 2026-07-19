"""Regression: Apple Sign-In name capture (desktop web-OAuth flow).

Apple sends the user's name ONLY on the first authorization, in the ``user``
form field of the form_post callback — never in the id_token. Before the fix the
callback ignored that field, so the name was lost and desktop onboarding showed
the "there" placeholder. ``_parse_apple_user_name`` is the parser the fix added
and calls from ``auth_callback_apple_post`` before threading the name through the
auth code into the Firebase ``display_name``.

Note: the callback/token wiring is exercised by review + the desktop path rather
than a unit test here, because ``test_auth_redirect_uri.py`` stubs ``firebase_admin``
in ``sys.modules`` and executing the real callback in the same session collides
with that stub. This file stays pure so it is co-run safe.
"""

import json

import pytest

from routers.auth import _parse_apple_user_name


def test_parse_apple_user_name_full():
    user = json.dumps({"name": {"firstName": "Skander", "lastName": "Karoui"}, "email": "x@y.com"})
    assert _parse_apple_user_name(user) == "Skander Karoui"


def test_parse_apple_user_name_first_only():
    assert _parse_apple_user_name(json.dumps({"name": {"firstName": "Skander", "lastName": ""}})) == "Skander"


def test_parse_apple_user_name_last_only():
    assert _parse_apple_user_name(json.dumps({"name": {"firstName": "", "lastName": "Karoui"}})) == "Karoui"


def test_parse_apple_user_name_strips_whitespace():
    assert (
        _parse_apple_user_name(json.dumps({"name": {"firstName": " Skander ", "lastName": " Karoui "}}))
        == "Skander Karoui"
    )


@pytest.mark.parametrize(
    "bad",
    [None, "", "not-json", json.dumps({"email": "x@y.com"}), json.dumps({"name": {}}), json.dumps({"name": None})],
)
def test_parse_apple_user_name_absent_or_garbage(bad):
    assert _parse_apple_user_name(bad) is None

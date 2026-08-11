"""X OAuth callback: redirect allowlist + callback-page escaping.

The callback page interpolates a client-supplied value (`success_redirect_url`
kept in the OAuth state, and the `error` query parameter) into an HTML
attribute and an inline <script>. Both the allowlist and the escaping are
covered here, against the real router module -- routers.x_connector imports
under tests/conftest.py's environment, so no sys.modules stubbing is needed
(backend/AGENTS.md: never mutate sys.modules at module scope).
"""

from __future__ import annotations

import pytest

from routers.x_connector import (
    DEFAULT_DEEP_LINK,
    _redirect_html,
    _validated_success_redirect,
    is_allowed_success_redirect_url,
)


@pytest.mark.parametrize(
    "uri",
    [
        "omi://x/callback",
        "omi-computer-dev://x/callback",
        "omi-computer://x/callback",
        "http://127.0.0.1:8765/callback",
        "http://localhost:3000/cb",
    ],
)
def test_allowed_success_redirect_urls(uri):
    assert is_allowed_success_redirect_url(uri) is True


@pytest.mark.parametrize(
    "uri",
    [
        "https://evil.example",
        "https://evil.example/steal",
        "http://attacker.example.com/cb",
        "javascript:alert(1)",
        "data:text/html,hi",
        "",
        "://missing-scheme",
        # Markup delimiters: the callback page is the sink.
        "omi://x/</script><script>alert(1)</script>",
        'omi://x/"onload="alert(1)',
        "omi://x/callback\n<script>alert(1)</script>",
    ],
)
def test_rejected_success_redirect_urls(uri):
    assert is_allowed_success_redirect_url(uri) is False


def test_callback_falls_back_to_default_for_https_evil():
    assert _validated_success_redirect("https://evil.example") == DEFAULT_DEEP_LINK


def test_callback_keeps_omi_deep_link():
    assert _validated_success_redirect("omi://x/callback") == "omi://x/callback"


def test_callback_keeps_dev_scheme():
    uri = "omi-computer-dev://auth/x"
    assert _validated_success_redirect(uri) == uri


def test_empty_falls_back_to_default():
    assert _validated_success_redirect(None) == DEFAULT_DEEP_LINK
    assert _validated_success_redirect("") == DEFAULT_DEEP_LINK


def test_callback_page_never_lets_a_link_close_the_script_element():
    """Second line of defence: even a link that reached the sink must not be
    able to terminate <script> or open a tag."""
    body = _redirect_html('omi://x/</script><script>alert(1)</script>', True, 'X connected').body.decode()
    assert '<script>alert(1)</script>' not in body
    # Exactly one script element -- the page's own.
    assert body.count('<script>') == 1
    assert body.count('</script>') == 1


def test_callback_page_escapes_the_error_query_value():
    """`error` is an unauthenticated query parameter on the callback route."""
    body = _redirect_html(f'{DEFAULT_DEEP_LINK}?error=" onload="alert(1)', False, 'Connection cancelled').body.decode()
    meta = body.split('<style>')[0]
    # The injected quote must not close the content attribute.
    assert '" onload=' not in meta
    assert '&quot; onload=' in meta


def test_callback_page_escapes_the_message():
    body = _redirect_html(DEFAULT_DEEP_LINK, False, '<img src=x onerror=alert(1)>').body.decode()
    assert '<img' not in body

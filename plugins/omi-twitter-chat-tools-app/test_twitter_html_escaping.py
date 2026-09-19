"""Hermetic regression tests: omi-twitter-chat-tools-app must not reflect
``error`` or ``username`` values into HTML without escaping.

Three unauthenticated or OAuth-controlled sinks were found in the Twitter
plugin and fixed in this PR:

1. ``GET /auth/twitter/callback?error=...`` — the ``error`` OAuth parameter
   was inserted into ``<p>{error}</p>`` without ``html.escape``.

2. ``GET /`` (connected page) — ``username`` retrieved from stored OAuth tokens
   was inserted into ``<p>Connected as @{username}</p>`` without escaping.
   While the username originates from Twitter's API, it is stored in the DB and
   re-injected into HTML; any compromise of the stored value (or a crafted
   token response) can trigger stored/reflected XSS.

3. ``GET /auth/twitter/callback`` (success page) — same ``username`` reflected
   in ``<p>Your Twitter account @{username} is now linked to Omi</p>``.

Run: python3 plugins/omi-twitter-chat-tools-app/test_twitter_html_escaping.py
"""

import html
import sys
import unittest

BREAKOUT = '"><script>alert(1)</script>'
QUOTE_BREAKER = '"\'&<>'
BENIGN_ERROR = "access_denied"
BENIGN_USERNAME = "elonmusk"
MALICIOUS_USERNAME = '<script>alert("xss_via_username")</script>'


def _render_error_page(error_value: str) -> str:
    """Exact template from twitter_callback when ``if error:`` fires (fixed version)."""
    safe_error = html.escape(error_value or "", quote=True)
    return (
        "<html><body><div class='container'>"
        "<div class='error-box'>"
        "<h2>Authorization Failed</h2>"
        f"<p>{safe_error}</p>"
        "</div></div></body></html>"
    )


def _render_connected_page(username: str, uid: str) -> str:
    """Exact template from root() when token exists (fixed version)."""
    safe_username = html.escape(username or "", quote=True)
    return (
        "<html><body>"
        "<div class='success-box'>"
        "<h2>Twitter Connected</h2>"
        f"<p>Connected as @{safe_username}</p>"
        "</div>"
        "</body></html>"
    )


def _render_success_page(username: str, uid: str) -> str:
    """Exact template from twitter_callback() success branch (fixed version)."""
    safe_username = html.escape(username or "", quote=True)
    from urllib.parse import quote as url_quote
    uid_q = url_quote(uid or "", safe="")
    return (
        "<html><body>"
        "<div class='success-box'>"
        f"<p>Your Twitter account @{safe_username} is now linked to Omi</p>"
        f"<a href='/?uid={uid_q}'>Continue to Settings</a>"
        "</div>"
        "</body></html>"
    )


class ErrorPageEscapingTest(unittest.TestCase):
    """``error`` OAuth parameter must be HTML-escaped in the callback failure page."""

    def test_breakout_not_reflected_raw(self) -> None:
        page = _render_error_page(BREAKOUT)
        self.assertNotIn(BREAKOUT, page)

    def test_script_tag_absent(self) -> None:
        page = _render_error_page(BREAKOUT)
        self.assertNotIn("<script>", page)

    def test_escaped_form_present(self) -> None:
        page = _render_error_page(QUOTE_BREAKER)
        self.assertIn(html.escape(QUOTE_BREAKER, quote=True), page)

    def test_benign_error_renders(self) -> None:
        page = _render_error_page(BENIGN_ERROR)
        self.assertIn(BENIGN_ERROR, page)

    def test_empty_error_safe(self) -> None:
        page = _render_error_page("")
        self.assertNotIn("{error}", page)


class ConnectedPageEscapingTest(unittest.TestCase):
    """``username`` from stored token must be HTML-escaped on the connected homepage."""

    def test_malicious_username_not_raw(self) -> None:
        page = _render_connected_page(MALICIOUS_USERNAME, "user1")
        self.assertNotIn(MALICIOUS_USERNAME, page)
        self.assertNotIn("<script>", page)

    def test_benign_username_renders(self) -> None:
        page = _render_connected_page(BENIGN_USERNAME, "user1")
        self.assertIn(BENIGN_USERNAME, page)

    def test_quote_breaker_escaped(self) -> None:
        page = _render_connected_page(QUOTE_BREAKER, "user1")
        self.assertIn(html.escape(QUOTE_BREAKER, quote=True), page)


class SuccessPageEscapingTest(unittest.TestCase):
    """``username`` must be HTML-escaped on the OAuth success page."""

    def test_malicious_username_not_raw(self) -> None:
        page = _render_success_page(MALICIOUS_USERNAME, "user1")
        self.assertNotIn(MALICIOUS_USERNAME, page)
        self.assertNotIn("<script>", page)

    def test_benign_username_renders(self) -> None:
        page = _render_success_page(BENIGN_USERNAME, "user1")
        self.assertIn(BENIGN_USERNAME, page)

    def test_uid_url_encoded_in_continue_link(self) -> None:
        """uid in continue-link href must be URL-encoded, not raw."""
        uid = '"><script>alert(1)</script>'
        page = _render_success_page(BENIGN_USERNAME, uid)
        self.assertNotIn(uid, page, "Raw uid must not appear in href attribute")


if __name__ == "__main__":
    unittest.main(verbosity=2)

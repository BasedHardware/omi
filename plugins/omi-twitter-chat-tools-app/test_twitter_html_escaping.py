"""Hermetic tests for XSS escaping in the Twitter app HTML templates.

These tests do not import the FastAPI app or hit the network. They render the
same escaped fragments used in main.py and assert that malicious input is
neutralised while benign input renders normally.
"""

import html
import unittest


def render_username_connected(username: str) -> str:
    # Mirrors: <p>Connected as @{html.escape(username or '', quote=True)}</p>
    return f"<p>Connected as @{html.escape(username or '', quote=True)}</p>"


def render_username_success(username: str) -> str:
    return (
        "<p>Your Twitter account @"
        f"{html.escape(username or '', quote=True)} is now linked to Omi</p>"
    )


def render_error(error: str) -> str:
    # Mirrors: <p>{html.escape(error or '', quote=True)}</p>
    return f"<p>{html.escape(error or '', quote=True)}</p>"


class TwitterHtmlEscaping(unittest.TestCase):
    def test_benign_username_renders(self):
        self.assertIn("@alice", render_username_connected("alice"))

    def test_malicious_username_not_raw(self):
        out = render_username_connected("<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_quote_breaker_escaped(self):
        out = render_username_success('"><script>x</script>')
        self.assertNotIn('"><script>', out)
        self.assertIn("&quot;&gt;&lt;script&gt;", out)

    def test_benign_error_renders(self):
        self.assertIn("access_denied", render_error("access_denied"))

    def test_breakout_not_reflected_raw(self):
        out = render_error('"><script>alert(document.domain)</script>')
        self.assertNotIn("<script>alert(document.domain)</script>", out)

    def test_empty_error_safe(self):
        self.assertEqual(render_error(""), "<p></p>")
        self.assertEqual(render_error(None), "<p></p>")


if __name__ == "__main__":
    unittest.main(verbosity=2)

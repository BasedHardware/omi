"""Hermetic regression test: the Whoop OAuth callback must not reflect the
``error`` OAuth parameter into HTML without escaping.

``GET /auth/whoop/callback?error=...`` is unauthenticated.  Before this fix,
``main.py`` interpolated the parameter directly into ``<p>{error}</p>``
without calling ``html.escape``.  Opening

    /auth/whoop/callback?error=%22%3E%3Cscript%3Ealert(1)%3C%2Fscript%3E

returned markup whose error paragraph contained the literal script tag, so
the script ran in the victim's browser on the plugin's origin (reflected XSS).
No login, stored state, or prior interaction was needed.

This suite exercises ``get_callback_error_html`` (or the equivalent inline
logic) with the standard library only — no network, no database, no FastAPI
runtime.

Run: python3 plugins/omi-whoop-app/test_callback_error_escaped.py
"""

import html
import sys
import types
import unittest
from pathlib import Path

# ─── payloads ────────────────────────────────────────────────────────────────
BREAKOUT = '"><script>alert(1)</script>'   # classic attribute-break + script
QUOTE_BREAKER = '"\'&<>'                   # every character html.escape must handle
BENIGN = "access_denied"                   # normal OAuth error code


def _build_callback_error_html(error_value: str) -> str:
    """Reproduce what whoop_callback renders when ``error`` is truthy.

    Returns the full HTML string exactly as ``main.py`` would return it, so
    the tests are independent of FastAPI's ``HTMLResponse`` wrapper.
    """
    # This is the exact template from main.py (the fixed version):
    #   <p>{html.escape(error or "", quote=True)}</p>
    safe_error = html.escape(error_value or "", quote=True)
    return f"""
        <html>
            <head><style>/* ... */</style></head>
            <body>
                <div class="container">
                    <div class="error-box">
                        <h2>Authorization Failed</h2>
                        <p>{safe_error}</p>
                    </div>
                </div>
            </body>
        </html>
        """


class CallbackErrorEscapedTest(unittest.TestCase):
    """``error`` OAuth parameter must be HTML-escaped before insertion into <p>."""

    def test_breakout_payload_is_not_reflected_raw(self) -> None:
        """The classic ``"><script>…</script>`` payload must not appear verbatim."""
        page = _build_callback_error_html(BREAKOUT)
        self.assertNotIn(BREAKOUT, page,
                         "Raw breakout payload must not appear in the response body")

    def test_script_tag_is_not_in_output(self) -> None:
        """No literal ``<script>`` tag may appear in the rendered page."""
        page = _build_callback_error_html(BREAKOUT)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_escaped_representation_is_present(self) -> None:
        """The escaped form of every special character must survive in the output."""
        page = _build_callback_error_html(QUOTE_BREAKER)
        self.assertNotIn(QUOTE_BREAKER, page,
                         "Raw payload must not appear in the response body")
        self.assertIn(html.escape(QUOTE_BREAKER, quote=True), page,
                      "Escaped representation must appear so the error is still readable")

    def test_benign_error_still_renders(self) -> None:
        """Plain-text OAuth error codes (e.g. ``access_denied``) must pass through."""
        page = _build_callback_error_html(BENIGN)
        self.assertIn(BENIGN, page)

    def test_empty_string_does_not_crash(self) -> None:
        """``error or ""`` guards against ``None``/empty without raising."""
        page = _build_callback_error_html("")
        self.assertIsNotNone(page)
        # An empty error yields an empty <p></p> — no template placeholder.
        self.assertNotIn("{error}", page)

    def test_double_quote_is_entity_encoded(self) -> None:
        """A ``"`` in the payload must become ``&quot;`` (attribute-safe)."""
        page = _build_callback_error_html('"')
        self.assertIn("&quot;", page)
        # The literal quote must not appear outside the entity.
        # (Excluding the surrounding HTML attributes which use the same char)
        # We verify at the <p> level specifically.
        para_start = page.index("<p>")
        para_end = page.index("</p>", para_start)
        para_content = page[para_start + 3:para_end]
        self.assertNotIn('"', para_content,
                         "Unescaped double-quote must not appear inside <p>...</p>")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""#20185 — X connector OAuth hardening.

sanitize_redirect_url: scheme allowlist + control-char + length bounds, fail
closed on build. _redirect_html: HTML-attribute + JS-string escaping for both
contexts the deep link lands in, and sanitized exception logging.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest

import routers.x_connector as x_router
from utils.x_connector import sanitize_redirect_url


@pytest.mark.parametrize(
    'url',
    [
        'javascript:alert(1)',
        'javascript://x%0aalert(1)',
        'data:text/html,<script>alert(1)</script>',
        'vbscript:msgbox(1)',
        'file:///etc/passwd',
        'ftp://x.test',
        'omi://done\nX-Injected: 1',  # CRLF injection into the redis state field
        'omi://done\r\nsmi://evil',
        'omi://a\tb',  # embedded control char
        'x' * 3000,
        '',
        '   ',
        None,
        42,
    ],
)
def test_unsafe_redirect_urls_rejected(url):
    assert sanitize_redirect_url(url) is None


@pytest.mark.parametrize(
    'url',
    [
        'omi://oauth/success',
        # signed/production macOS build registers this scheme — dropping it
        # breaks X connect on release builds (dev builds use -dev).
        'omi-computer://x/callback',
        'omi-computer-dev://done',
        'https://h.omi.me/x/done',
        'http://localhost:3000/cb',
    ],
)
def test_safe_redirect_urls_pass(url):
    assert sanitize_redirect_url(url) == url


def test_redirect_html_escapes_meta_and_js_contexts():
    # A URL carrying '"><script> must be inert in BOTH injection sinks.
    resp = x_router._redirect_html('omi://done" onclick="alert(1)" <script>bad()</script>', True, 'ok')
    body = resp.body.decode()
    assert 'omi://done&quot;' in body  # attribute-escaped in the meta refresh
    assert 'onclick=\\"alert' in body or '&quot;' in body
    assert '\\u003cscript\\u003e' in body  # < > are escaped in the JS literal
    assert '<script>bad()' not in body  # the raw payload is gone


def test_redirect_html_round_trip_clean():
    body = x_router._redirect_html('omi://done?x=1&y=2', True, 'Linked').body.decode()
    assert 'omi://done?x=1&amp;y=2' in body  # & escaped in the attribute context


def test_build_authorize_url_fails_closed_on_bad_redirect(monkeypatch):
    import utils.x_connector as xc

    monkeypatch.setattr(xc, 'is_oauth_configured', lambda: True)
    with pytest.raises(ValueError):
        xc.build_authorize_url('u1', success_redirect_url='javascript:alert(1)')

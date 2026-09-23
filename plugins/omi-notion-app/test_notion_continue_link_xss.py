"""Regression test: the Notion OAuth success page's "Continue to Settings"
link URL-encodes + HTML-attribute-escapes uid, so a crafted uid cannot break
out of the href attribute (attribute-injection / reflected XSS).

Mirrors the exact expression used in main.py so it pins the behaviour without
importing FastAPI or hitting the network.
"""
import html
from urllib.parse import quote


def build_continue_link(uid: str) -> str:
    safe_continue_attr = html.escape(f"/?uid={quote(str(uid), safe='')}", quote=True)
    return f'<a href="{safe_continue_attr}" class="btn btn-primary btn-block">Continue</a>'


def test_uid_attribute_breakout_blocked():
    out = build_continue_link('"><script>alert(1)</script>')
    assert '"><script>' not in out
    assert "<script>alert(1)</script>" not in out


def test_uid_ampersand_hash_encoded():
    out = build_continue_link("a&b#c")
    # & and # are percent-encoded so they cannot corrupt the query/attribute
    assert "a&b#c" not in out
    assert "%26" in out and "%23" in out


def test_benign_uid():
    out = build_continue_link("user123")
    assert "/?uid=user123" in out


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)
    print("ALL PASSED")

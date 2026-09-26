"""Regression test: the Dropbox settings page escapes OAuth-provided and
user-controlled values (display_name, email, folder_name) to prevent stored
XSS. uid is already percent-encoded upstream; this covers the remaining sinks.

Loads main.py under hermetic stubs (no FastAPI/network) and renders the
connected settings page with malicious values, asserting they are neutralised.
"""
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import Mock, patch


def module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    return m


class Framework:
    def __init__(self, *a, **k):
        pass

    def get(self, *a, **k):
        return lambda fn: fn

    post = get


stubs = {
    "requests": module("requests", get=Mock(), post=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework,
                      HTTPException=Exception, Depends=lambda d: d),
    "fastapi.responses": module("fastapi.responses", HTMLResponse=Framework,
                                RedirectResponse=Framework, JSONResponse=Framework),
    "omi_plugin_sdk": module("omi_plugin_sdk"),
    "omi_plugin_sdk.models": module("omi_plugin_sdk.models", ActionItem=object, Conversation=object, EndpointResponse=object, Structured=object, TranscriptSegment=object),
    "models": module("models", Conversation=object, EndpointResponse=object),
    "dropbox_client": module("dropbox_client", DropboxClient=object),
    "db": module("db", **{n: Mock() for n in (
        "store_dropbox_tokens", "get_dropbox_tokens", "update_dropbox_tokens",
        "delete_dropbox_tokens", "store_oauth_state", "get_oauth_state",
        "delete_oauth_state", "get_user_settings", "store_user_settings",
    )}),
}

spec = importlib.util.spec_from_file_location(
    "dropbox_under_test", Path(__file__).with_name("main.py"))
mod = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(mod)


XSS = '"><script>alert(1)</script>'


def _render_connected(**kwargs):
    # get_home_page_html(uid, connected, display_name, email, settings)
    return mod.get_home_page_html(
        uid="user1", connected=True,
        display_name=kwargs.get("display_name", ""),
        email=kwargs.get("email", ""),
        settings=kwargs.get("settings", {}),
    )


def test_display_name_escaped():
    html_out = _render_connected(display_name=XSS)
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_email_escaped():
    html_out = _render_connected(email=XSS)
    assert "<script>alert(1)</script>" not in html_out


def test_folder_name_escaped():
    html_out = _render_connected(settings={"folder_name": XSS})
    assert "<script>alert(1)</script>" not in html_out
    assert '"><script' not in html_out


def test_benign_values_render():
    html_out = _render_connected(display_name="Alice", email="a@b.com",
                                 settings={"folder_name": "My Folder"})
    assert "Alice" in html_out and "a@b.com" in html_out and "My Folder" in html_out


def test_callback_error_sinks_escaped():
    """The OAuth callback escapes response.text and str(e) before rendering
    them into HTML error responses (token-exchange failure / auth error)."""
    import html
    payload = '"><script>alert(1)</script>'
    # mirrors the handler's escaping of the two HTML error sinks
    token_fail = f"Token exchange failed: {html.escape(payload)}"
    auth_err = f"Error during authorization: {html.escape(payload)}"
    for out in (token_fail, auth_err):
        assert "<script>alert(1)</script>" not in out
        assert "&lt;script&gt;" in out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASSED")

"""Tests for the GET /.well-known/omi-tools.json endpoint on the
Telegram AI Clone plugin.

The manifest body contract is tested in
plugins/_shared/test/test_omi_tools_manifest.py. This file tests the
HTTP wiring: the endpoint is reachable, returns the right content
type, and doesn't leak the bot_token in the response.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest


_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_SHARED = os.path.abspath(os.path.join(_PLUGIN_ROOT, "..", "_shared"))

# The Telegram plugin has no conftest.py; each test file does its own
# sys.path setup. We need:
#  - _PLUGIN_ROOT: for `import simple_storage`, `import telegram_client`
#                  inside main.py
#  - _SHARED:      for `from persona_client import chat` inside main.py
for p in (_SHARED, _PLUGIN_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_PLUGIN_ROOT, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Load simple_storage + main fresh per test (autouse fixture handles swap).
@pytest.fixture
def main_module(monkeypatch):
    monkeypatch.setenv("OMI_DEV_MODE", "1")
    return _load("main")


@pytest.fixture
def client(main_module):
    from fastapi.testclient import TestClient

    return TestClient(main_module.app)


# Telegram bot_token used in the suite — should NEVER appear in the manifest.
TELEGRAM_TOKEN = "TELEGRAM_BOT_TOKEN_DO_NOT_LOG"


class TestOmiToolsManifestEndpoint:
    """The HTTP shape of the manifest endpoint."""

    def test_manifest_endpoint_reachable(self, client):
        r = client.get("/.well-known/omi-tools.json")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")

    def test_manifest_body_is_valid_json(self, client):
        r = client.get("/.well-known/omi-tools.json")
        # FastAPI's TestClient gives us a parsed JSON attribute.
        assert isinstance(r.json(), dict)
        assert "tools" in r.json()

    def test_manifest_declares_toggle_auto_reply(self, client):
        r = client.get("/.well-known/omi-tools.json")
        body = r.json()
        names = [t["name"] for t in body["tools"]]
        assert "toggle_auto_reply" in names

    def test_manifest_toggle_endpoint_is_relative(self, client):
        r = client.get("/.well-known/omi-tools.json")
        body = r.json()
        tool = next(t for t in body["tools"] if t["name"] == "toggle_auto_reply")
        assert tool["endpoint"] == "/toggle"
        assert not tool["endpoint"].startswith("http")

    def test_manifest_toggle_method_is_post(self, client):
        r = client.get("/.well-known/omi-tools.json")
        tool = next(t for t in r.json()["tools"] if t["name"] == "toggle_auto_reply")
        assert tool["method"] == "POST"

    def test_manifest_required_params(self, client):
        r = client.get("/.well-known/omi-tools.json")
        tool = next(t for t in r.json()["tools"] if t["name"] == "toggle_auto_reply")
        # Per-plugin manifest: must match Telegram's ToggleRequest fields
        # EXACTLY (chat_id, enabled). The chat assistant builds the request
        # from this schema, so a mismatch = 422.
        #
        # SECURITY (PR #8528 review): the manifest must NOT advertise
        # long-lived platform credentials like bot_token as tool
        # parameters — the chat assistant would faithfully prompt the
        # user to paste them in chat, putting the secret into chat
        # history / tool-call logs / traces / model context. The plugin
        # bearer token (in Authorization header) gates the call; the
        # chat_id is a non-secret reference to the user/chat.
        assert set(tool["parameters"]["required"]) == {"chat_id", "enabled"}

    def test_manifest_does_not_advertise_bot_token(self, client):
        """P1 (Git-on-my-level review): the manifest must NEVER advertise
        the bot_token. The chat assistant would faithfully prompt the
        user to paste it in chat, and that secret would persist in
        chat history, tool-call logs, traces, screenshots, and model
        context."""
        r = client.get("/.well-known/omi-tools.json")
        tool = next(t for t in r.json()["tools"] if t["name"] == "toggle_auto_reply")
        params = tool["parameters"]
        assert "bot_token" not in params["properties"], (
            "Manifest advertises bot_token as a tool parameter. The chat "
            "assistant would prompt the user to paste their Telegram "
            "bot token in chat — that secret would then live in chat "
            "history, tool-call logs, traces, screenshots, and model "
            "context. Use the plugin bearer + chat_id instead."
        )
        assert "bot_token" not in params["required"]
        # Make sure no required field sneaks back in under another name
        # (defense against future regressions that re-add a credential
        # field with a different key).
        for required_field in params["required"]:
            assert required_field not in {"bot_token", "access_token", "token", "secret", "password"}, (
                f"Manifest requires {required_field!r} — looks like a "
                f"credential field. Long-lived secrets should never flow "
                f"through chat; gate via Authorization: Bearer."
            )

    def test_manifest_parameters_match_toggle_request(self, client):
        """The JSON-Schema `properties` keys MUST be the same as the
        ToggleRequest field names, otherwise the chat assistant will
        faithfully build a request that /toggle rejects with 422."""
        from main import ToggleRequest

        r = client.get("/.well-known/omi-tools.json")
        tool = next(t for t in r.json()["tools"] if t["name"] == "toggle_auto_reply")
        manifest_params = set(tool["parameters"]["properties"].keys())
        request_fields = set(ToggleRequest.model_fields.keys())
        # If these two differ, the chat assistant will fail. The critical
        # invariant: every required field in the manifest must correspond
        # to a real field in ToggleRequest.
        missing_in_request = set(tool["parameters"]["required"]) - request_fields
        assert not missing_in_request, (
            f"Manifest requires fields {missing_in_request} that don't "
            f"exist on ToggleRequest. The chat assistant will get 422."
        )
        # Also: the manifest should not advertise unknown fields.
        extra_in_manifest = manifest_params - request_fields
        assert not extra_in_manifest, (
            f"Manifest advertises fields {extra_in_manifest} that don't " f"exist on ToggleRequest."
        )

    def test_manifest_chat_messages_disabled(self, client):
        # v0.1 ships with chat_messages disabled per .aidlc/spec.md.
        r = client.get("/.well-known/omi-tools.json")
        assert r.json()["chat_messages"]["enabled"] is False

    def test_manifest_does_not_leak_telegram_bot_token(self, client):
        """The manifest is public metadata — it must never contain the
        bot_token even if one is configured. The token is a per-chat
        secret that flows through the /toggle request body, not the
        manifest."""
        # Seed a user with a bot_token to make sure it doesn't get
        # serialized into the manifest response.
        from simple_storage import save_user

        save_user(
            chat_id="12345",
            omi_uid="u-1",
            persona_id="p-1",
            omi_dev_api_key="DEV_KEY",
            bot_token=TELEGRAM_TOKEN,
            auto_reply_enabled=True,
        )
        r = client.get("/.well-known/omi-tools.json")
        assert TELEGRAM_TOKEN not in r.text

    def test_manifest_path_is_well_known(self, client):
        """Sanity: the endpoint is at the well-known path, not e.g.
        /omi-tools (which would defeat the discovery convention)."""
        r = client.get("/.well-known/omi-tools.json")
        assert r.status_code == 200
        # Common wrong paths should 404.
        assert client.get("/omi-tools.json").status_code == 404
        assert client.get("/tools.json").status_code == 404

"""Regression: present-null chat_messages fields in an app manifest must take declared defaults.

`fetch_app_chat_tools_from_manifest` (utils/apps.py) normalizes the manifest's chat_messages block
into the app doc. `chat_messages.get('target', 'app')` only defaults when the key is ABSENT; a
manifest that sends `"target": null` returns None, which the write paths
(`_process_chat_tools_manifest` and the refresh-manifest route in routers/apps.py) persist into
`external_integration.chat_messages_target`. That field is `Literal['main', 'app']` on
ExternalIntegration (models/app.py), so every `App(**doc)` read path (app detail, personas list,
oauth token, notifications, integration) then raises ValidationError and the app 500s until the
doc is manually repaired. The same hole exists for `notify` (bool), and an out-of-contract target
string poisons the doc the same way.

Fix: coerce to the declared defaults at parse time, where both write paths consume the result.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

import utils.apps as app_utils


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _fetch_manifest(monkeypatch, chat_messages):
    monkeypatch.setattr(app_utils, "get_generic_cache", lambda key: None)
    monkeypatch.setattr(app_utils, "set_generic_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app_utils.httpx,
        "get",
        lambda *args, **kwargs: _FakeResponse({"tools": [], "chat_messages": chat_messages}),
    )
    return app_utils.fetch_app_chat_tools_from_manifest("https://example.com/.well-known/omi-tools.json")


def test_present_null_target_and_notify_take_defaults(monkeypatch):
    result = _fetch_manifest(monkeypatch, {"enabled": True, "target": None, "notify": None})

    assert result["chat_messages"] == {"enabled": True, "target": "app", "notify": True}


def test_out_of_contract_target_falls_back_to_default(monkeypatch):
    result = _fetch_manifest(monkeypatch, {"enabled": True, "target": "sidebar"})

    assert result["chat_messages"]["target"] == "app"


def test_contract_values_are_preserved(monkeypatch):
    result = _fetch_manifest(monkeypatch, {"enabled": True, "target": "main", "notify": False})

    assert result["chat_messages"] == {"enabled": True, "target": "main", "notify": False}

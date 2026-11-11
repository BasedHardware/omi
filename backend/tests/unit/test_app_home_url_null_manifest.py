"""Regression: chat-tools manifest resolution must not 500 on a present-null app_home_url.

routers.apps._process_chat_tools_manifest resolves relative tool endpoints against
external_integration['app_home_url']. app_home_url is Optional[str] = None (models/app.py), so a
create/update request can send it explicitly as null. The code used
`external_integration.get('app_home_url', '').rstrip('/')`, whose '' default only applies when the
key is ABSENT; a present null slips the default and `None.rstrip('/')` raises AttributeError, an
unhandled 500 on POST/PATCH /v1/apps and POST /v1/apps/{app_id}/refresh-manifest. The `if base_url:`
guard on the next line shows an empty home URL is a valid state (endpoints stay relative), so a null
must behave like absent, not crash. Fix: `(get('app_home_url') or '')` at both call sites.

Seam: _process_chat_tools_manifest is pure except the manifest fetch, which is a module-level
function reference monkeypatched here (no sys.modules mutation, no import-time IO).
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

import routers.apps as apps


def _fake_manifest(url, **kwargs):
    # kwargs so both call sites work: fetch_app_chat_tools_from_manifest(url) and (url, force_refresh=True).
    return {'tools': [{'name': 'do_thing', 'endpoint': '/api/action'}]}


def test_null_app_home_url_skips_resolution_without_crash(monkeypatch):
    monkeypatch.setattr(apps, 'fetch_app_chat_tools_from_manifest', _fake_manifest)
    ext = {'chat_tools_manifest_url': 'https://valid.example', 'app_home_url': None}

    result = apps._process_chat_tools_manifest(ext, {})  # must not raise

    # A null home URL yields an empty base, so the relative endpoint is left as-is (resolution skipped).
    assert result['chat_tools'][0]['endpoint'] == '/api/action'


def test_absent_app_home_url_still_skips_resolution(monkeypatch):
    monkeypatch.setattr(apps, 'fetch_app_chat_tools_from_manifest', _fake_manifest)
    ext = {'chat_tools_manifest_url': 'https://valid.example'}  # key absent

    result = apps._process_chat_tools_manifest(ext, {})

    assert result['chat_tools'][0]['endpoint'] == '/api/action'


def test_present_app_home_url_resolves_relative_endpoint(monkeypatch):
    monkeypatch.setattr(apps, 'fetch_app_chat_tools_from_manifest', _fake_manifest)
    ext = {'chat_tools_manifest_url': 'https://valid.example', 'app_home_url': 'https://example.com/'}

    result = apps._process_chat_tools_manifest(ext, {})

    # A real home URL still resolves relative endpoints to absolute (trailing slash stripped).
    assert result['chat_tools'][0]['endpoint'] == 'https://example.com/api/action'

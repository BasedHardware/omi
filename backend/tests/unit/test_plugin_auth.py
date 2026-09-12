"""Tests for backend.utils.plugin_auth (mirrors omi_plugin_sdk.auth)."""

import hmac
import time
from hashlib import sha256

from utils.plugin_auth import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    UID_HEADER,
    build_plugin_auth_headers,
    get_plugin_webhook_secret,
    maybe_plugin_auth_headers,
    sign_plugin_payload,
)


def test_sign_matches_sdk_algorithm():
    secret = 's'
    uid = 'u1'
    ts = '1700000000'
    body = b'{"a":1}'
    expected = hmac.new(secret.encode(), f'{uid}.{ts}.'.encode() + body, sha256).hexdigest()
    assert sign_plugin_payload(secret=secret, uid=uid, timestamp=ts, body=body) == expected


def test_build_headers_roundtrip_shape(monkeypatch):
    monkeypatch.setenv('OMI_PLUGIN_WEBHOOK_SECRET', 'sekrit')
    body = b'x'
    headers = build_plugin_auth_headers(secret='sekrit', uid='uid-1', body=body)
    assert headers[UID_HEADER] == 'uid-1'
    assert headers[TIMESTAMP_HEADER].isdigit()
    assert len(headers[SIGNATURE_HEADER]) == 64


def test_maybe_headers_empty_without_secret(monkeypatch):
    monkeypatch.delenv('OMI_PLUGIN_WEBHOOK_SECRET', raising=False)
    assert maybe_plugin_auth_headers(uid='u', body=b'') == {}


def test_maybe_headers_when_secret_set(monkeypatch):
    monkeypatch.setenv('OMI_PLUGIN_WEBHOOK_SECRET', 'sekrit')
    headers = maybe_plugin_auth_headers(uid='u', body=b'abc')
    assert headers[UID_HEADER] == 'u'
    assert SIGNATURE_HEADER in headers


def test_get_secret_strips(monkeypatch):
    monkeypatch.setenv('OMI_PLUGIN_WEBHOOK_SECRET', '  abc  ')
    assert get_plugin_webhook_secret() == 'abc'
    monkeypatch.setenv('OMI_PLUGIN_WEBHOOK_SECRET', '   ')
    assert get_plugin_webhook_secret() is None

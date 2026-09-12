"""Unit tests for omi_plugin_sdk.auth."""

import time

import pytest

from omi_plugin_sdk.auth import (
    PluginAuthError,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    UID_HEADER,
    build_auth_headers,
    resolve_authenticated_uid,
    sign_payload,
    verify_headers,
    verify_payload,
)


SECRET = "test-plugin-webhook-secret"
UID = "user-abc"


def test_sign_verify_roundtrip():
    body = b'{"hello":"world"}'
    ts = str(int(time.time()))
    sig = sign_payload(secret=SECRET, uid=UID, timestamp=ts, body=body)
    assert verify_payload(secret=SECRET, uid=UID, timestamp=ts, body=body, signature=sig)


def test_tampered_body_rejected():
    ts = str(int(time.time()))
    sig = sign_payload(secret=SECRET, uid=UID, timestamp=ts, body=b"a")
    assert not verify_payload(secret=SECRET, uid=UID, timestamp=ts, body=b"b", signature=sig)


def test_skew_rejected():
    body = b""
    old_ts = str(int(time.time()) - 10_000)
    sig = sign_payload(secret=SECRET, uid=UID, timestamp=old_ts, body=body)
    assert not verify_payload(secret=SECRET, uid=UID, timestamp=old_ts, body=body, signature=sig)


def test_build_and_verify_headers():
    body = b'{"x":1}'
    headers = build_auth_headers(secret=SECRET, uid=UID, body=body)
    assert headers[UID_HEADER] == UID
    assert TIMESTAMP_HEADER in headers and SIGNATURE_HEADER in headers
    assert verify_headers(secret=SECRET, headers=headers, body=body) == UID


def test_resolve_rejects_bare_uid_without_secret():
    with pytest.raises(PluginAuthError):
        resolve_authenticated_uid(
            secret=None,
            header_map={},
            query_uid=UID,
            body_uid=None,
            body=b"",
        )


def test_resolve_accepts_signed_headers():
    body = b'{"uid":"user-abc"}'
    headers = build_auth_headers(secret=SECRET, uid=UID, body=body)
    got = resolve_authenticated_uid(
        secret=SECRET,
        header_map=headers,
        query_uid=UID,
        body_uid=None,
        body=body,
    )
    assert got == UID


def test_resolve_uid_mismatch_rejected():
    headers = build_auth_headers(secret=SECRET, uid=UID, body=b"")
    with pytest.raises(PluginAuthError):
        resolve_authenticated_uid(
            secret=SECRET,
            header_map=headers,
            query_uid="other-uid",
            body_uid=None,
            body=b"",
        )


def test_allow_uid_only_escape_hatch():
    assert (
        resolve_authenticated_uid(
            secret=None,
            header_map={},
            query_uid=UID,
            body_uid=None,
            allow_uid_only=True,
        )
        == UID
    )

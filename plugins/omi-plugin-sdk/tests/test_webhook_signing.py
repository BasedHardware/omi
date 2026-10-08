import hashlib
import hmac

import pytest

from omi_plugin_sdk import verify_signature
from omi_plugin_sdk.webhook_signing import (
    DEFAULT_TOLERANCE_SECONDS,
    SIGNATURE_HEADER,
    compute_signature,
    parse_signature_header,
)

SECRET = "whsec_test-secret-one"
OTHER_SECRET = "whsec_test-secret-two"
BODY = b'{"id":"conversation-1","structured":{"title":"Plan"}}'
UID = "user-abc123"
NOW = 1_760_000_000


def _sign(secret, body=BODY, uid=UID, timestamp=NOW):
    # Built by hand so the test pins the wire format rather than trusting the module under test.
    return hmac.new(secret.encode(), f"{timestamp}.{uid}.".encode() + body, hashlib.sha256).hexdigest()


def _headers(body=BODY, secrets=(SECRET,), uid=UID, timestamp=NOW):
    return {SIGNATURE_HEADER: ",".join([f"t={timestamp}", *(f"v1={_sign(s, body, uid, timestamp)}" for s in secrets)])}


def test_canonical_string_is_timestamp_dot_uid_dot_body():
    assert compute_signature(SECRET, NOW, UID, BODY) == _sign(SECRET)
    # A delivery with no uid signs an empty segment, not a missing one.
    assert compute_signature(SECRET, NOW, "", BODY) == _sign(SECRET, uid="")


def test_verify_round_trip():
    assert verify_signature(_headers(), BODY, SECRET, uid=UID, now=NOW) is True


def test_verify_rejects_wrong_secret_and_tampered_body():
    assert verify_signature(_headers(), BODY, OTHER_SECRET, uid=UID, now=NOW) is False
    assert verify_signature(_headers(), BODY.replace(b"conversation-1", b"conversation-2"), SECRET, uid=UID, now=NOW) is False


def test_verify_rejects_a_replay_aimed_at_another_uid():
    headers = _headers(uid=UID)
    assert verify_signature(headers, BODY, SECRET, uid=UID, now=NOW) is True
    assert verify_signature(headers, BODY, SECRET, uid="victim-uid", now=NOW) is False
    assert verify_signature(headers, BODY, SECRET, uid="", now=NOW) is False


def test_verify_rejects_stale_and_future_timestamps():
    headers = _headers()
    assert verify_signature(headers, BODY, SECRET, uid=UID, now=NOW + DEFAULT_TOLERANCE_SECONDS) is True
    assert verify_signature(headers, BODY, SECRET, uid=UID, now=NOW + DEFAULT_TOLERANCE_SECONDS + 1) is False
    assert verify_signature(headers, BODY, SECRET, uid=UID, now=NOW - DEFAULT_TOLERANCE_SECONDS - 1) is False
    assert verify_signature(headers, BODY, SECRET, uid=UID, now=NOW + 1000, tolerance_seconds=2000) is True


@pytest.mark.parametrize(
    "value",
    ["", "t=abc,v1=00", "t=1760000000", "v1=00", "garbage", "t=1760000000,v1=", "t=1760000000,v1=ÿÿ-not-hex"],
)
def test_verify_rejects_missing_or_malformed_headers(value):
    headers = {SIGNATURE_HEADER: value} if value else {}
    assert verify_signature(headers, BODY, SECRET, uid=UID, now=NOW) is False


def test_verify_refuses_a_str_body_and_accepts_bytes_like_bodies():
    assert verify_signature(_headers(), BODY.decode(), SECRET, uid=UID, now=NOW) is False
    assert verify_signature(_headers(), bytearray(BODY), SECRET, uid=UID, now=NOW) is True
    assert verify_signature(_headers(), memoryview(BODY), SECRET, uid=UID, now=NOW) is True


def test_verify_finds_the_header_case_insensitively():
    headers = {key.lower(): value for key, value in _headers().items()}
    assert verify_signature(headers, BODY, SECRET, uid=UID, now=NOW) is True


def test_rotation_header_verifies_against_either_secret():
    headers = _headers(secrets=(SECRET, OTHER_SECRET))
    timestamp, signatures = parse_signature_header(headers[SIGNATURE_HEADER])
    assert timestamp == NOW
    assert signatures == [_sign(SECRET), _sign(OTHER_SECRET)]
    assert verify_signature(headers, BODY, SECRET, uid=UID, now=NOW) is True
    assert verify_signature(headers, BODY, OTHER_SECRET, uid=UID, now=NOW) is True
    assert verify_signature(headers, BODY, "whsec_never-issued", uid=UID, now=NOW) is False


def test_parse_signature_header_ignores_unknown_schemes():
    assert parse_signature_header(f"t={NOW}, v1=aa, v2=future, v1=bb, novalue") == (NOW, ["aa", "bb"])


def test_verify_uses_the_wall_clock_when_now_is_omitted(monkeypatch):
    import omi_plugin_sdk.webhook_signing as module

    monkeypatch.setattr(module.time, "time", lambda: NOW + 10)
    assert verify_signature(_headers(), BODY, SECRET, uid=UID) is True

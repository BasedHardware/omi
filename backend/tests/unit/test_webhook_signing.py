"""Receiver-side contract for signed webhooks (#20939): sign, verify, reject, rotate."""

import httpx
import pytest

from utils import webhook_signing as signing

SECRET = 'whsec_test-secret-one'
OTHER_SECRET = 'whsec_test-secret-two'
BODY = b'{"id":"conversation-1","structured":{"title":"Plan"}}'
UID = 'user-abc123'
NOW = 1_760_000_000


def _headers(body=BODY, secrets=(SECRET,), timestamp=NOW, uid=UID):
    return signing.signature_headers(
        body, list(secrets), uid=uid, event='memory_created', delivery_id='d-1', timestamp=timestamp
    )


def test_generate_secret_is_prefixed_url_safe_and_unique():
    first, second = signing.generate_secret(), signing.generate_secret()
    assert first.startswith(signing.SECRET_PREFIX) and second.startswith(signing.SECRET_PREFIX)
    # token_urlsafe(32) is 43 characters: 32 random bytes, no padding.
    assert len(first) == len(signing.SECRET_PREFIX) + 43
    assert first != second
    assert set(first[len(signing.SECRET_PREFIX) :]) <= set(
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    )


def test_canonical_string_is_timestamp_dot_uid_dot_body():
    import hashlib
    import hmac

    expected = hmac.new(SECRET.encode(), f'{NOW}.{UID}.'.encode() + BODY, hashlib.sha256).hexdigest()
    assert signing.compute_signature(SECRET, NOW, UID, BODY) == expected
    assert _headers()[signing.SIGNATURE_HEADER] == f't={NOW},v1={expected}'
    # A delivery with no uid signs an empty segment, not a missing one.
    no_uid = hmac.new(SECRET.encode(), f'{NOW}..'.encode() + BODY, hashlib.sha256).hexdigest()
    assert signing.compute_signature(SECRET, NOW, '', BODY) == no_uid


def test_sign_and_verify_round_trip():
    headers = _headers()
    assert headers[signing.EVENT_HEADER] == 'memory_created'
    assert headers[signing.DELIVERY_HEADER] == 'd-1'
    assert signing.verify(headers, BODY, SECRET, uid=UID, now=NOW) is True


def test_verify_rejects_wrong_secret():
    assert signing.verify(_headers(), BODY, OTHER_SECRET, uid=UID, now=NOW) is False


def test_verify_rejects_tampered_body():
    tampered = BODY.replace(b'conversation-1', b'conversation-2')
    assert signing.verify(_headers(), tampered, SECRET, uid=UID, now=NOW) is False


def test_verify_rejects_a_replay_aimed_at_another_uid():
    # Most bodies do not carry uid; it travels in the query string. A captured delivery replayed
    # with ?uid=<victim> inside the tolerance window must still fail.
    headers = _headers(uid=UID)
    assert signing.verify(headers, BODY, SECRET, uid=UID, now=NOW) is True
    assert signing.verify(headers, BODY, SECRET, uid='victim-uid', now=NOW) is False
    assert signing.verify(headers, BODY, SECRET, uid='', now=NOW) is False
    assert signing.verify(_headers(uid=''), BODY, SECRET, uid=UID, now=NOW) is False


def test_verify_rejects_a_replayed_delivery_outside_the_tolerance_window():
    headers = _headers()
    assert signing.verify(headers, BODY, SECRET, uid=UID, now=NOW + signing.DEFAULT_TOLERANCE_SECONDS) is True
    assert signing.verify(headers, BODY, SECRET, uid=UID, now=NOW + signing.DEFAULT_TOLERANCE_SECONDS + 1) is False
    # A timestamp from the future is just as suspicious as a stale one.
    assert signing.verify(headers, BODY, SECRET, uid=UID, now=NOW - signing.DEFAULT_TOLERANCE_SECONDS - 1) is False
    assert signing.verify(headers, BODY, SECRET, uid=UID, now=NOW + 1000, tolerance_seconds=2000) is True


@pytest.mark.parametrize(
    'value',
    ['', 't=abc,v1=00', 't=1760000000', 'v1=00', 'garbage', 't=1760000000,v1=', 't=1760000000,v1=ÿÿ-not-hex'],
)
def test_verify_rejects_missing_or_malformed_signature_headers(value):
    headers = {signing.SIGNATURE_HEADER: value} if value else {}
    assert signing.verify(headers, BODY, SECRET, uid=UID, now=NOW) is False


def test_verify_refuses_a_str_body():
    # Re-encoding parsed JSON does not reproduce the wire bytes; refusing str makes that loud.
    assert signing.verify(_headers(), BODY.decode(), SECRET, uid=UID, now=NOW) is False
    assert signing.verify(_headers(), bytearray(BODY), SECRET, uid=UID, now=NOW) is True
    assert signing.verify(_headers(), memoryview(BODY), SECRET, uid=UID, now=NOW) is True


def test_verify_finds_the_header_case_insensitively():
    headers = {key.lower(): value for key, value in _headers().items()}
    assert signing.verify(headers, BODY, SECRET, uid=UID, now=NOW) is True


def test_rotation_header_carries_one_signature_per_secret_and_either_verifies():
    headers = _headers(secrets=(SECRET, OTHER_SECRET))
    timestamp, signatures = signing.parse_signature_header(headers[signing.SIGNATURE_HEADER])
    assert timestamp == NOW
    assert signatures == [
        signing.compute_signature(SECRET, NOW, UID, BODY),
        signing.compute_signature(OTHER_SECRET, NOW, UID, BODY),
    ]
    assert signing.verify(headers, BODY, SECRET, uid=UID, now=NOW) is True
    assert signing.verify(headers, BODY, OTHER_SECRET, uid=UID, now=NOW) is True
    assert signing.verify(headers, BODY, 'whsec_never-issued', uid=UID, now=NOW) is False


def test_parse_signature_header_ignores_unknown_schemes():
    timestamp, signatures = signing.parse_signature_header(f't={NOW}, v1=aa, v2=future, v1=bb, novalue')
    assert timestamp == NOW
    assert signatures == ['aa', 'bb']


def test_sign_requires_a_secret():
    with pytest.raises(ValueError):
        signing.sign(BODY, [], uid=UID)


@pytest.mark.parametrize(
    'payload',
    [
        {'segments': [{'text': 'héllo — ünïcode 🎉', 'speaker': 'SPEAKER_00'}], 'session_id': 'uid-1'},
        {'summary': None, 'nested': {'list': [1, 2.5, True, 'x']}, 'empty': {}},
        [],
    ],
)
def test_encode_json_body_matches_what_httpx_sends_for_json(payload):
    # The signed bytes have to be the bytes a receiver gets; pin our encoder to httpx's own.
    assert signing.encode_json_body(payload) == httpx.Request('POST', 'https://receiver.example/', json=payload).content


def test_signed_body_kwargs_without_a_secret_leaves_the_request_untouched():
    headers = {'Content-Type': 'application/json', 'Idempotency-Key': 'k'}
    payload = {'a': 1}
    assert signing.signed_body_kwargs(None, headers, uid=UID, event='x', delivery_id='k', json_payload=payload) == {
        'json': payload
    }
    assert signing.signed_body_kwargs([], headers, uid=UID, event='x', delivery_id='k', content=b'\x00') == {
        'content': b'\x00'
    }
    assert headers == {'Content-Type': 'application/json', 'Idempotency-Key': 'k'}


def test_signed_body_kwargs_serializes_json_once_and_adds_the_headers():
    headers = {'Idempotency-Key': 'k'}
    payload = {'a': 1, 'b': 'ü'}
    kwargs = signing.signed_body_kwargs(
        [SECRET], headers, uid=UID, event='day_summary', delivery_id='k', json_payload=payload, timestamp=NOW
    )
    assert kwargs == {'content': signing.encode_json_body(payload)}
    assert headers['Content-Type'] == 'application/json'
    assert headers[signing.EVENT_HEADER] == 'day_summary'
    assert headers[signing.DELIVERY_HEADER] == 'k'
    assert signing.verify(headers, kwargs['content'], SECRET, uid=UID, now=NOW) is True
    assert signing.verify(headers, kwargs['content'], SECRET, uid='other', now=NOW) is False


def test_signed_body_kwargs_keeps_a_caller_content_type_and_binary_body():
    headers = {'content-type': 'application/octet-stream'}
    kwargs = signing.signed_body_kwargs(
        [SECRET], headers, uid=UID, event='audio_bytes', delivery_id='k', content=b'\x01\x02'
    )
    assert kwargs == {'content': b'\x01\x02'}
    assert headers['content-type'] == 'application/octet-stream'
    assert 'Content-Type' not in headers
    assert signing.verify(headers, b'\x01\x02', SECRET, uid=UID) is True

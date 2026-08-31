"""A notification the transport cannot carry must not vanish quietly (BACKLOG L17).

Hex-armor is not free. `_encode_for` encrypts per RFC 8291 and then hex-encodes the ciphertext, because
ntfy is a text-only transport — which **doubles** the body. Measured with the real crypto:

  action-item bulk delete, 100 ids (the chunk size `notifications.py` uses, sized for FCM's 4 KB):
      plaintext 3850 B  ->  on the wire 7906 B
  and against a live ntfy v2.11.0 with its default `message-size-limit` of 4096:
      3466 B -> 200 · 4206 B -> 400 · 7906 B -> 400  ("invalid request: attachments not allowed",
      because ntfy treats an over-limit body as an attachment, and attachments are off by default)

So every bulk delete to an encrypted endpoint was rejected — and `_classify` files any non-2xx that is not
404/410 as transient, log-only. The notification was simply gone, with no counter and no cleanup.

Two halves, and only one of them is ours to fix in code:

  * the deployment must be able to carry what the code sends: `NTFY_MESSAGE_SIZE_LIMIT` is now declared
    on both targets (see the compose/Helm contract test at the bottom);
  * a size rejection must be RECORDED, because the other payload — the Apple Reminders sync — is not
    chunked at all and no server limit can bound it. Measured (55-char descriptions): it exceeds ntfy's
    default at 15 items, 16 KiB at ~100, and **FCM's own 4 KB at 30** — so the unbounded payload is
    upstream's limit on both transports, not our divergence. What we owe is the signal.
"""

from __future__ import annotations

from typing import List

import pytest

from utils.push import unifiedpush


@pytest.fixture
def events(monkeypatch):
    recorded: list[dict] = []
    monkeypatch.setattr(unifiedpush, 'record_fallback', lambda **kw: recorded.append(kw))
    return recorded


# --- the classification -------------------------------------------------------------------------


def test_a_size_rejection_is_recorded_not_just_logged(events):
    dead: List[str] = []

    assert unifiedpush._classify('https://ntfy/u1', 400, dead) is False

    assert dead == [], 'the endpoint is fine — it is the payload that does not fit'
    assert len(events) == 1
    assert events[0]['component'] == 'push'
    assert events[0]['to_mode'] == 'dropped'
    assert events[0]['reason'] == 'capability_mismatch'
    assert events[0]['outcome'] == 'exhausted', 'no retry can make an over-limit body fit'


def test_a_413_is_the_same_class(events):
    """ntfy answers 400 for an over-limit body; a plain WebPush server answers 413. Same outcome."""
    assert unifiedpush._classify('https://ntfy/u1', 413, dead=[]) is False
    assert events[0]['reason'] == 'capability_mismatch'


def test_a_dead_endpoint_is_still_cleanup_not_a_size_problem(events):
    dead: List[str] = []

    for status in (404, 410):
        assert unifiedpush._classify('https://ntfy/gone', status, dead) is False

    assert dead == ['https://ntfy/gone', 'https://ntfy/gone']
    assert events == [], 'a gone endpoint is cleanup, not a payload that does not fit'


def test_a_transport_error_stays_transient(events):
    """`status is None` is a network error: the same message may well arrive next time, so it must NOT be
    labelled as a payload the transport cannot carry."""
    assert unifiedpush._classify('https://ntfy/u1', None, dead=[]) is False
    assert events == []


def test_a_server_error_stays_transient(events):
    """5xx is the server having a bad moment, not a body that is too big."""
    for status in (500, 502, 503):
        assert unifiedpush._classify('https://ntfy/u1', status, dead=[]) is False
    assert events == []


def test_success_records_nothing(events):
    assert unifiedpush._classify('https://ntfy/u1', 200, dead=[]) is True
    assert events == []


# --- the measured cost of hex-armor -------------------------------------------------------------


def test_hex_armor_doubles_the_body_and_the_test_says_by_how_much():
    """Pins the property the chunk sizes have to respect. If a future encoding stops doubling (base64
    would be 1.33x), this test is where the number is stated, not a comment."""
    import base64
    import json
    import os

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from models.other import UnifiedPushEndpoint

    private_key = ec.generate_private_key(ec.SECP256R1())
    raw_public = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    encode = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b'=').decode()  # noqa: E731
    endpoint = UnifiedPushEndpoint(url='https://ntfy/u1', p256dh=encode(raw_public), auth=encode(os.urandom(16)))

    plaintext = json.dumps({'data': {'ids': ','.join('x' * 36 for _ in range(100))}}).encode()
    body, headers = unifiedpush._encode_for(endpoint, plaintext)

    assert headers['Content-Type'] == 'text/plain'
    assert len(body) > 2 * len(plaintext), 'hex-armor at least doubles it (plus the RFC 8291 overhead)'


def test_an_endpoint_without_keys_pays_nothing():
    """The plaintext fallback (pre-encryption client) is the payload itself — the doubling is the price of
    encryption, not of the transport."""
    from models.other import UnifiedPushEndpoint

    endpoint = UnifiedPushEndpoint(url='https://ntfy/u1', p256dh=None, auth=None)
    plaintext = b'{"data": {"ids": "abc"}}'

    body, headers = unifiedpush._encode_for(endpoint, plaintext)

    assert body == plaintext
    assert headers['Content-Type'] == 'application/json'


# --- the deployment side ------------------------------------------------------------------------


def test_both_targets_declare_a_size_limit_that_fits_the_biggest_bounded_payload():
    """STATIC TRIPWIRE over the committed deployment files.

    ntfy's default is 4096 and the biggest BOUNDED payload the backend sends is 7906 B on the wire (the
    100-id bulk delete), so an undeclared limit rejects it. Both targets must declare one, and it must
    actually be large enough — a declaration that is still too small would read as fixed.
    """
    import re
    from pathlib import Path

    repository = Path(__file__).resolve().parents[3]
    sources = {
        'compose': repository / 'deploy/onprem/compose.selfhost.yaml',
        'helm': repository / 'deploy/onprem/helm/omi-oss/templates/ntfy-statefulset.yaml',
    }
    for name, path in sources.items():
        assert path.exists(), f'{name}: {path} moved — point this test at the new one'
        text = path.read_text(encoding='utf-8')
        match = re.search(r'NTFY_MESSAGE_SIZE_LIMIT[^0-9]{0,40}(\d+)', text)
        assert match, f'{name} does not declare NTFY_MESSAGE_SIZE_LIMIT (ntfy defaults to 4096)'
        assert int(match.group(1)) >= 7906, f'{name} declares {match.group(1)}, too small for a 100-id chunk'

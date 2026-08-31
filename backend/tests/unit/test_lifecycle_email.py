"""Unit tests for utils.email.lifecycle: unsubscribe tokens, opt-out
fail-closed behavior, and the send-claim ledger.

``send_lifecycle_email`` itself (the httpx.post call) is exercised indirectly
through ``run_day3_reengagement`` in test_day3_reengagement.py, where the
opted-out-between-selection-and-send scenario needs the full orchestration
context. This file covers the pieces that stand on their own.
"""

from __future__ import annotations

import pytest

from tests.unit.fixtures.generic_firestore_fake import FakeFirestore
from utils.email.lifecycle import (
    LifecycleEmailNotConfigured,
    claim_lifecycle_send,
    is_lifecycle_opted_out,
    mint_unsubscribe_token,
    release_lifecycle_send,
    set_lifecycle_opted_out,
    unsubscribe_url,
    verify_unsubscribe_token,
)

SIGNING_SECRET = 'test-lifecycle-signing-secret-do-not-use-in-prod'


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch):
    monkeypatch.setenv('LIFECYCLE_EMAIL_SIGNING_SECRET', SIGNING_SECRET)


# --- unsubscribe token -------------------------------------------------


def test_unsubscribe_token_round_trips():
    token = mint_unsubscribe_token('uid-round-trip')
    assert verify_unsubscribe_token(token) == 'uid-round-trip'


def test_unsubscribe_token_tampered_signature_returns_none():
    token = mint_unsubscribe_token('uid-tamper')
    uid_part, sig_part = token.split('.', 1)
    # Flip the last character of the signature; base64url alphabet keeps this
    # a syntactically valid token, just cryptographically wrong.
    flipped = ('a' if sig_part[-1] != 'a' else 'b') + sig_part[1:]
    tampered = f'{uid_part}.{flipped}'
    assert verify_unsubscribe_token(tampered) is None


def test_unsubscribe_token_for_another_purpose_is_rejected():
    token = mint_unsubscribe_token('uid-cross-purpose', purpose='some-other-feature')
    assert verify_unsubscribe_token(token) is None  # default purpose is 'lifecycle'
    assert verify_unsubscribe_token(token, purpose='some-other-feature') == 'uid-cross-purpose'


@pytest.mark.parametrize(
    'garbage',
    ['', 'not-a-token', 'missing-dot-separator', '...', 'a.b.c', '!!!.!!!'],
)
def test_garbage_tokens_return_none(garbage):
    assert verify_unsubscribe_token(garbage) is None


def test_unsubscribe_url_points_at_the_api_that_serves_the_route(monkeypatch):
    """The link has to reach the service that actually has the endpoint.

    `/email/unsubscribe` is a FastAPI route on the backend, so the link must be
    built from `BASE_API_URL`. Building it from `share_base_url()` -- the
    conversation-share web origin -- produces a link that 404s, and takes the
    `List-Unsubscribe` header down with it, since that carries the same URL.
    An asserted `startswith('http')` would pass for either, which is why this
    pins the host.
    """
    monkeypatch.setenv('BASE_API_URL', 'https://api.example.test/')

    url = unsubscribe_url('uid-link')

    assert url.startswith('https://api.example.test/email/unsubscribe?token=')


def test_unsubscribe_url_refuses_to_guess_a_host(monkeypatch):
    """No `BASE_API_URL` means no working opt-out, so no send may proceed."""
    monkeypatch.delenv('BASE_API_URL', raising=False)

    with pytest.raises(LifecycleEmailNotConfigured):
        unsubscribe_url('uid-link')


# --- opt-out ------------------------------------------------------------


def test_is_lifecycle_opted_out_fails_closed_on_read_error():
    class _RaisingFirestore(FakeFirestore):
        def collection(self, path):
            raise RuntimeError('firestore unavailable')

    assert is_lifecycle_opted_out('uid-error', firestore_client=_RaisingFirestore()) is True


def test_is_lifecycle_opted_out_fails_closed_when_user_doc_missing():
    db = FakeFirestore()
    assert is_lifecycle_opted_out('uid-nonexistent', firestore_client=db) is True


def test_set_and_read_opt_out_round_trip():
    db = FakeFirestore(docs={'users/uid-optout': {}})
    assert is_lifecycle_opted_out('uid-optout', firestore_client=db) is False

    set_lifecycle_opted_out('uid-optout', True, firestore_client=db)
    assert is_lifecycle_opted_out('uid-optout', firestore_client=db) is True

    set_lifecycle_opted_out('uid-optout', False, firestore_client=db)
    assert is_lifecycle_opted_out('uid-optout', firestore_client=db) is False


def test_opting_out_twice_is_idempotent():
    db = FakeFirestore(docs={'users/uid-double': {}})
    set_lifecycle_opted_out('uid-double', True, firestore_client=db)
    set_lifecycle_opted_out('uid-double', True, firestore_client=db)
    assert is_lifecycle_opted_out('uid-double', firestore_client=db) is True


# --- send claim ledger ---------------------------------------------------


def test_claim_lifecycle_send_prevents_a_second_claim():
    db = FakeFirestore()
    assert claim_lifecycle_send('uid-claim', 'campaign-x', firestore_client=db) is True
    assert claim_lifecycle_send('uid-claim', 'campaign-x', firestore_client=db) is False


def test_claim_is_scoped_per_campaign():
    db = FakeFirestore()
    assert claim_lifecycle_send('uid-claim', 'campaign-a', firestore_client=db) is True
    assert claim_lifecycle_send('uid-claim', 'campaign-b', firestore_client=db) is True


def test_release_allows_a_later_retry_to_reclaim():
    db = FakeFirestore()
    assert claim_lifecycle_send('uid-retry', 'campaign-x', firestore_client=db) is True
    release_lifecycle_send('uid-retry', 'campaign-x', firestore_client=db)
    assert claim_lifecycle_send('uid-retry', 'campaign-x', firestore_client=db) is True

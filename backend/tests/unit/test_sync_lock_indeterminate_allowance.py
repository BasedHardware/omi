"""A synced conversation may only be locked when the allowance was actually decided.

`resolve_transcription_allowance` fails closed, so an entitlement it could not resolve
comes back as no managed minutes. That is right for the listen WebSocket, where the
alternative is opening a billed STT socket on an unknown entitlement. The sync path reused
the same boolean to stamp `is_locked` onto the stored conversation, and `is_locked` is only
ever cleared by a subscription transition (`unlock_all_conversations` is called from the
three payment handlers and nowhere else).

So one Firestore timeout while an Unlimited subscriber synced a recording paywalled that
conversation behind a 402 for good. `resolve_conversation_processing_allowance` already
treats the same two reasons as allowed (#12663); this brings the durable lock in line.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

import pytest

from utils import subscription as sub


@pytest.fixture
def allowance(monkeypatch):
    def _install(mode, reason):
        resolved = sub.TranscriptionAllowance(mode, 0, reason)
        monkeypatch.setattr(sub, 'resolve_transcription_allowance', lambda uid, source=None: resolved)

    return _install


def test_an_unresolvable_allowance_does_not_paywall_the_conversation(allowance):
    allowance(sub.TRANSCRIPTION_MODE_ON_DEVICE, 'allowance_unavailable')

    assert sub.should_paywall_synced_conversation('uid_1') is False


def test_an_untrusted_usage_record_does_not_paywall_the_conversation(allowance):
    allowance(sub.TRANSCRIPTION_MODE_ON_DEVICE, 'usage_invalid')

    assert sub.should_paywall_synced_conversation('uid_1') is False


def test_an_exhausted_allowance_still_paywalls_the_conversation(allowance):
    allowance(sub.TRANSCRIPTION_MODE_ON_DEVICE, 'plan_allowance_exhausted')

    assert sub.should_paywall_synced_conversation('uid_1') is True


def test_no_subscription_still_paywalls_the_conversation(allowance):
    allowance(sub.TRANSCRIPTION_MODE_ON_DEVICE, 'subscription_inactive')

    assert sub.should_paywall_synced_conversation('uid_1') is True


def test_a_paywalled_trial_still_paywalls_the_conversation(allowance):
    allowance(sub.TRANSCRIPTION_MODE_BLOCKED, 'trial_paywalled')

    assert sub.should_paywall_synced_conversation('uid_1') is True


@pytest.mark.parametrize('reason', ['plan_within_allowance', 'plan_unlimited', 'byok', 'marketplace_reviewer'])
def test_a_user_with_managed_minutes_is_never_paywalled(allowance, reason):
    allowance(sub.TRANSCRIPTION_MODE_MANAGED, reason)

    assert sub.should_paywall_synced_conversation('uid_1') is False


def test_the_listen_gate_keeps_failing_closed_on_an_unresolvable_allowance(allowance):
    allowance(sub.TRANSCRIPTION_MODE_ON_DEVICE, 'allowance_unavailable')

    assert sub.has_transcription_credits('uid_1') is False

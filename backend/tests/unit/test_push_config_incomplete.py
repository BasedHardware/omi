"""Selecting `unifiedpush` without its base URL must not look like working push (BACKLOG L18).

Measured on the running on-prem backend before the fix:

  PUSH_NOTIFICATION_BACKEND=unifiedpush, UNIFIEDPUSH_INTERNAL_BASE_URL unset
    -> resolve_push_backend() == 'unifiedpush'          (selected, nothing validates it)
    -> _send_one_sync(...) == None                      (every send fails, no exception)
    -> omi_fallback_total: NO push series at all        (the loss is not even counted)

So the operator gets a backend that answers "unifiedpush", a readiness probe that passes, and one ERROR
log per endpoint per notification — 100% of push lost, and invisible to the counter that exists to make
exactly this visible.

The refusal inside `_target_url` is correct and stays: the stored endpoint is user-registered, so POSTing
to it verbatim would be an SSRF primitive. The defect is that the deployment presents itself as delivering.

Two things change. The selector resolves an unusable `unifiedpush` to **`disabled`** — first-class in
ADR-0011 — and records it; and a startup check says so at boot, in the house style of
`validate_stripe_price_ids` (log loudly, name the consequence, do not refuse to boot: push is the one
cloud exception, not the critical path).

`disabled` and NOT `fcm`, deliberately: the existing typo path falls back to FCM because that is upstream's
default, but here the operator has *declared* an on-prem transport. Sending their users' notifications to
Google because their base URL is missing is the vendor-fallback class this project keeps closing (L40).
"""

from __future__ import annotations

import pytest

from utils.push import selector
from utils.push.base import DISABLED, FCM, UNIFIEDPUSH


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv('PUSH_NOTIFICATION_BACKEND', raising=False)
    monkeypatch.delenv('UNIFIEDPUSH_INTERNAL_BASE_URL', raising=False)


@pytest.fixture
def events(monkeypatch):
    recorded: list[dict] = []
    monkeypatch.setattr(selector, 'record_fallback', lambda **kw: recorded.append(kw))
    return recorded


# --- the selector ---------------------------------------------------------------------------------


def test_unifiedpush_without_a_base_url_resolves_to_disabled(monkeypatch, events):
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')

    assert selector.resolve_push_backend() == DISABLED
    assert len(events) == 1
    assert events[0]['component'] == 'push'
    assert events[0]['from_mode'] == UNIFIEDPUSH
    assert events[0]['to_mode'] == DISABLED
    assert events[0]['reason'] == 'config_incomplete'


def test_it_does_not_fall_back_to_fcm(monkeypatch, events):
    """The operator declared an on-prem transport. Answering with Google's would be the vendor fallback
    this project keeps closing (L40) — and on an air-gapped-ish stack it would fail anyway, later and
    less clearly."""
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')

    assert selector.resolve_push_backend() != FCM


def test_a_blank_base_url_counts_as_missing(monkeypatch, events):
    """`export UNIFIEDPUSH_INTERNAL_BASE_URL=` in a shell, or an empty value in an env-file, is the most
    likely way to get here — and `_target_url` treats it as unset too, so the selector must agree."""
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')
    monkeypatch.setenv('UNIFIEDPUSH_INTERNAL_BASE_URL', '   ')

    assert selector.resolve_push_backend() == DISABLED


def test_unifiedpush_with_a_base_url_is_untouched(monkeypatch, events):
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')
    monkeypatch.setenv('UNIFIEDPUSH_INTERNAL_BASE_URL', 'http://ntfy:80')

    assert selector.resolve_push_backend() == UNIFIEDPUSH
    assert events == []


def test_the_other_backends_do_not_care_about_the_base_url(monkeypatch, events):
    """The legacy principal: an FCM deployment (upstream's default, and every existing install) must be
    completely unaffected by a variable it has never heard of."""
    assert selector.resolve_push_backend() == FCM

    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'fcm')
    assert selector.resolve_push_backend() == FCM

    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'disabled')
    assert selector.resolve_push_backend() == DISABLED
    assert events == []


def test_a_typo_still_degrades_to_fcm(monkeypatch, events):
    """Unchanged, and different on purpose: a value nobody recognises is a typo, and upstream's default
    is the right answer for it. A RECOGNISED transport that cannot work is a different situation."""
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpsuh')

    assert selector.resolve_push_backend() == FCM
    assert events[0]['reason'] == 'config_invalid'
    assert events[0]['to_mode'] == FCM


# --- the startup check ----------------------------------------------------------------------------


def test_the_startup_check_names_the_consequence(monkeypatch, caplog):
    """House style of `validate_stripe_price_ids`: say what breaks, at boot, without refusing to boot.
    Before this, the first sign was an ERROR log per endpoint on the first notification — hours later,
    in a different log line, on a different day."""
    import logging

    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')

    with caplog.at_level(logging.ERROR, logger='utils.push.selector'):
        selector.validate_push_configuration()

    assert 'STARTUP' in caplog.text
    assert 'UNIFIEDPUSH_INTERNAL_BASE_URL' in caplog.text
    assert 'no push notification will be delivered' in caplog.text


def test_the_startup_check_is_quiet_when_the_configuration_is_usable(monkeypatch, caplog):
    import logging

    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')
    monkeypatch.setenv('UNIFIEDPUSH_INTERNAL_BASE_URL', 'http://ntfy:80')

    with caplog.at_level(logging.ERROR, logger='utils.push.selector'):
        selector.validate_push_configuration()

    assert caplog.text == ''


def test_the_startup_check_is_quiet_for_fcm_and_disabled(monkeypatch, caplog):
    """It must not nag a deployment that never chose UnifiedPush."""
    import logging

    for backend in ('fcm', 'disabled', ''):
        monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', backend)
        caplog.clear()
        with caplog.at_level(logging.ERROR, logger='utils.push.selector'):
            selector.validate_push_configuration()
        assert caplog.text == '', backend


def test_the_startup_check_never_raises(monkeypatch):
    """A notification transport must not take the API down: push is the one admitted cloud exception
    (ADR-0011), not the critical path. Same call, twice, with the worst input."""
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')
    selector.validate_push_configuration()
    selector.validate_push_configuration()

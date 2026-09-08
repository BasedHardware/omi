from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Iterator

import pytest
from fastapi import HTTPException

from routers import auth
from testing.import_isolation import load_module_fresh, stub_modules
from utils.referrals import (
    REFERRAL_COOKIE_NAME,
    ReferralCodeError,
    create_referral_code,
    is_new_referral_account,
    referral_claim_patch,
    referrer_uid_from_code,
)

TEST_SECRET = b'referral-test-secret-that-is-at-least-32-bytes'
REFERRALS_ROUTER_PATH = Path(__file__).resolve().parents[2] / 'routers' / 'referrals.py'


@contextmanager
def _loaded_referrals_router() -> Iterator[ModuleType]:
    endpoints = ModuleType('utils.other.endpoints')
    endpoints.get_current_user_uid = lambda: 'test-user'
    with stub_modules({'utils.other.endpoints': endpoints}):
        yield load_module_fresh('routers.referrals', str(REFERRALS_ROUTER_PATH))


def test_referral_code_round_trips_and_rejects_tampering():
    code = create_referral_code('referrer-123', secret=TEST_SECRET)

    assert referrer_uid_from_code(code, secret=TEST_SECRET) == 'referrer-123'

    with pytest.raises(ReferralCodeError, match='invalid_referral_signature'):
        referrer_uid_from_code(f'{code[:-1]}x', secret=TEST_SECRET)


def test_referral_claim_grants_exactly_30_days_of_operator():
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    patch, reason = referral_claim_patch(
        referred_uid='new-user',
        referrer_uid='referrer',
        is_new_user=True,
        user_data={'subscription': {'plan': 'basic', 'status': 'active'}},
        now=now,
    )

    assert patch is not None
    assert reason == 'granted'
    assert patch['subscription']['plan'] == 'operator'
    assert patch['subscription']['status'] == 'active'
    assert patch['subscription']['cancel_at_period_end'] is True
    assert patch['subscription']['current_period_end'] - patch['subscription']['current_period_start'] == 30 * 86400
    assert patch['referral']['program'] == 'desktop_operator_month_v1'
    assert patch['referral']['referrer_uid'] == 'referrer'


@pytest.mark.parametrize(
    ('referred_uid', 'referrer_uid', 'is_new_user', 'user_data', 'expected_reason'),
    [
        ('same-user', 'same-user', True, {}, 'self_refer'),
        ('existing-user', 'referrer', False, {}, 'existing_account'),
        ('paid-user', 'referrer', True, {'subscription': {'plan': 'operator'}}, 'paid'),
        ('claimed-user', 'referrer', True, {'referral': {'program': 'desktop_operator_month_v1'}}, 'already_claimed'),
    ],
)
def test_referral_claim_never_self_refers_rewards_existing_users_or_overwrites_paid_accounts(
    referred_uid, referrer_uid, is_new_user, user_data, expected_reason
):
    patch, reason = referral_claim_patch(
        referred_uid=referred_uid,
        referrer_uid=referrer_uid,
        is_new_user=is_new_user,
        user_data=user_data,
    )
    assert patch is None
    assert reason == expected_reason


def test_referral_link_captures_secure_cookie_and_opens_signup_before_download(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    monkeypatch.setenv('REFERRAL_PUBLIC_BASE_URL', 'https://omi.me')
    code = create_referral_code('referrer-123')

    with _loaded_referrals_router() as referrals:
        events = []
        monkeypatch.setattr(referrals, 'emit_posthog_event', lambda *event: events.append(event))
        response = referrals.capture_referral(code)

    assert response.status_code == 302
    assert response.headers['location'] == f'https://app.omi.me/login?referral={code}&environment=prod'
    cookie = response.headers['set-cookie']
    assert f'{REFERRAL_COOKIE_NAME}={code}' in cookie
    assert 'HttpOnly' in cookie
    assert 'Secure' in cookie
    assert 'SameSite=lax' in cookie
    assert events == [('referrer-123', 'Referral Link Captured', {'program': 'desktop_operator_month_v1'})]


def test_unknown_referral_link_does_not_emit_capture(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())

    with _loaded_referrals_router() as referrals:
        events = []
        monkeypatch.setattr(referrals, 'emit_posthog_event', lambda *event: events.append(event))

        with pytest.raises(HTTPException) as error:
            referrals.capture_referral('invalid')

    assert error.value.status_code == 404
    assert events == []


def test_dev_referral_opens_signup_against_the_dev_backend(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    monkeypatch.setenv('REFERRAL_PUBLIC_BASE_URL', 'https://api.omiapi.com')
    code = create_referral_code('referrer-123')

    with _loaded_referrals_router() as referrals:
        response = referrals.capture_referral(code)

    assert response.headers['location'] == f'https://app.omi.me/login?referral={code}&environment=dev'


def test_referral_claim_grants_trial_only_to_a_fresh_authenticated_account(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    code = create_referral_code('referrer-123')
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    claims = []
    events = []

    with _loaded_referrals_router() as referrals:
        monkeypatch.setattr(
            referrals.firebase_admin.auth,
            'get_user',
            lambda _uid: SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=now_ms)),
        )
        monkeypatch.setattr(
            referrals,
            'claim_referral_trial',
            lambda referred_uid, referrer_uid, *, is_new_user: claims.append((referred_uid, referrer_uid, is_new_user))
            or (True, 'granted'),
        )
        monkeypatch.setattr(referrals, 'emit_posthog_event', lambda *event: events.append(event))
        response = referrals.claim_referral(referrals.ReferralClaimRequest(code=code), 'new-user')

    assert response.claimed is True
    assert response.trial_days == 30
    assert claims == [('new-user', 'referrer-123', True)]
    assert events == [
        ('new-user', 'Referral Claimed', {'program': 'desktop_operator_month_v1', 'claimed': True, 'reason': 'granted'})
    ]


def test_referral_claim_marks_an_existing_authenticated_account_ineligible(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    code = create_referral_code('referrer-123')
    old_ms = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    claims = []
    events = []

    with _loaded_referrals_router() as referrals:
        monkeypatch.setattr(
            referrals.firebase_admin.auth,
            'get_user',
            lambda _uid: SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=old_ms)),
        )
        monkeypatch.setattr(
            referrals,
            'claim_referral_trial',
            lambda referred_uid, referrer_uid, *, is_new_user: claims.append((referred_uid, referrer_uid, is_new_user))
            or (False, 'existing_account'),
        )
        monkeypatch.setattr(referrals, 'emit_posthog_event', lambda *event: events.append(event))
        response = referrals.claim_referral(referrals.ReferralClaimRequest(code=code), 'existing-user')

    assert response.claimed is False
    assert claims == [('existing-user', 'referrer-123', False)]
    assert events == [
        (
            'existing-user',
            'Referral Claimed',
            {'program': 'desktop_operator_month_v1', 'claimed': False, 'reason': 'existing_account'},
        )
    ]


@pytest.mark.parametrize(
    ('uid', 'referrer_uid', 'reason'),
    [
        ('same-user', 'same-user', 'self_refer'),
        ('paid-user', 'referrer-123', 'paid'),
        ('claimed-user', 'referrer-123', 'already_claimed'),
    ],
)
def test_referral_claim_emits_ineligible_reason(monkeypatch, uid, referrer_uid, reason):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    code = create_referral_code(referrer_uid)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    with _loaded_referrals_router() as referrals:
        events = []
        monkeypatch.setattr(
            referrals.firebase_admin.auth,
            'get_user',
            lambda _uid: SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=now_ms)),
        )
        monkeypatch.setattr(referrals, 'claim_referral_trial', lambda *_args, **_kwargs: (False, reason))
        monkeypatch.setattr(referrals, 'emit_posthog_event', lambda *event: events.append(event))
        response = referrals.claim_referral(referrals.ReferralClaimRequest(code=code), uid)

    assert response.claimed is False
    assert events == [
        (
            uid,
            'Referral Claimed',
            {'program': 'desktop_operator_month_v1', 'claimed': False, 'reason': reason},
        )
    ]


def test_referral_claim_rejects_an_invalid_code_before_loading_the_user(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())

    with _loaded_referrals_router() as referrals:
        get_user = lambda _uid: pytest.fail('invalid referral must not load the user')
        monkeypatch.setattr(referrals.firebase_admin.auth, 'get_user', get_user)

        with pytest.raises(HTTPException) as error:
            referrals.claim_referral(referrals.ReferralClaimRequest(code='invalid'), 'new-user')

    assert error.value.status_code == 404
    assert error.value.detail == 'Referral link not found'


def test_referral_new_user_window_rejects_missing_future_and_old_timestamps():
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)

    assert is_new_referral_account(int(now.timestamp() * 1000), now=now) is True
    assert is_new_referral_account(None, now=now) is False
    assert is_new_referral_account(int((now.timestamp() + 1) * 1000), now=now) is False
    assert is_new_referral_account(int((now.timestamp() - 901) * 1000), now=now) is False


def test_authenticated_referrer_receives_a_stable_unique_https_link(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    monkeypatch.delenv('REFERRAL_PUBLIC_BASE_URL', raising=False)

    with _loaded_referrals_router() as referrals:
        events = []
        monkeypatch.setattr(referrals, 'emit_posthog_event', lambda *event: events.append(event))
        first = referrals.get_referral_link('referrer-123').referral_url
        second = referrals.get_referral_link('referrer-123').referral_url
        other = referrals.get_referral_link('another-user').referral_url

    assert first == second
    assert first != other
    assert first.startswith('https://omi.me/r/ref1.')
    assert events == [
        ('referrer-123', 'Referral Link Issued', {'program': 'desktop_operator_month_v1'}),
        ('referrer-123', 'Referral Link Issued', {'program': 'desktop_operator_month_v1'}),
        ('another-user', 'Referral Link Issued', {'program': 'desktop_operator_month_v1'}),
    ]


def test_authenticated_referrer_uses_configured_dev_public_origin(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    monkeypatch.setenv('REFERRAL_PUBLIC_BASE_URL', 'https://api.omiapi.com/')

    with _loaded_referrals_router() as referrals:
        referral_url = referrals.get_referral_link('referrer-123').referral_url

    assert referral_url.startswith('https://api.omiapi.com/r/ref1.')
    assert referrer_uid_from_code(referral_url.rsplit('/', 1)[-1]) == 'referrer-123'


def test_referral_link_returns_sanitized_unavailable_response_when_signing_fails(monkeypatch):
    with _loaded_referrals_router() as referrals:

        def signing_failure(_uid):
            raise ReferralCodeError('missing_referral_signing_secret')

        monkeypatch.setattr(referrals, 'referral_link', signing_failure)

        with pytest.raises(HTTPException) as error:
            referrals.get_referral_link('referrer-123')

    assert error.value.status_code == 503
    assert error.value.detail == 'Referral links are temporarily unavailable'
    assert 'signing' not in error.value.detail


@pytest.mark.asyncio
async def test_new_user_auth_redeems_captured_referral(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    monkeypatch.setenv('FIREBASE_API_KEY', 'test-key')
    referral_code = create_referral_code('referrer-123')
    claims = []
    events = []

    class Response:
        status_code = 200
        text = ''

        @staticmethod
        def json():
            return {'localId': 'new-user', 'isNewUser': True}

    class Client:
        @staticmethod
        async def post(*_args, **_kwargs):
            return Response()

    def claim(referred_uid, referrer_uid, *, is_new_user):
        claims.append((referred_uid, referrer_uid, is_new_user))
        return True, 'granted'

    async def run_inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(auth, 'get_auth_client', lambda: Client())
    monkeypatch.setattr(auth, 'claim_referral_trial', claim)
    monkeypatch.setattr(auth, 'emit_posthog_event', lambda *event: events.append(event))
    monkeypatch.setattr(auth, 'run_blocking', run_inline)
    monkeypatch.setattr(auth.firebase_admin.auth, 'create_custom_token', lambda _uid: b'custom-token', raising=False)

    token = await auth._generate_custom_token('google', 'provider-token', referral_code=referral_code)

    assert token == 'custom-token'
    assert claims == [('new-user', 'referrer-123', True)]
    assert events == [
        ('new-user', 'Referral Claimed', {'program': 'desktop_operator_month_v1', 'claimed': True, 'reason': 'granted'})
    ]


@pytest.mark.asyncio
async def test_existing_user_auth_does_not_redeem_referral(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    monkeypatch.setenv('FIREBASE_API_KEY', 'test-key')
    referral_code = create_referral_code('referrer-123')
    claims = []

    class Response:
        status_code = 200
        text = ''

        @staticmethod
        def json():
            return {'localId': 'existing-user', 'isNewUser': False}

    class Client:
        @staticmethod
        async def post(*_args, **_kwargs):
            return Response()

    async def run_inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(auth, 'get_auth_client', lambda: Client())
    monkeypatch.setattr(auth, 'claim_referral_trial', lambda *args, **kwargs: claims.append((args, kwargs)))
    monkeypatch.setattr(auth, 'run_blocking', run_inline)
    monkeypatch.setattr(auth.firebase_admin.auth, 'create_custom_token', lambda _uid: b'custom-token', raising=False)

    await auth._generate_custom_token('google', 'provider-token', referral_code=referral_code)

    assert claims == []

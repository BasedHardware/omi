from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Iterator

import pytest

from routers import auth
from testing.import_isolation import load_module_fresh, stub_modules
from utils.referrals import (
    REFERRAL_COOKIE_NAME,
    ReferralCodeError,
    create_referral_code,
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


def test_referral_claim_grants_exactly_30_days_of_desktop_pro():
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    patch = referral_claim_patch(
        referred_uid='new-user',
        referrer_uid='referrer',
        is_new_user=True,
        user_data={'subscription': {'plan': 'basic', 'status': 'active'}},
        now=now,
    )

    assert patch is not None
    assert patch['subscription']['plan'] == 'architect'
    assert patch['subscription']['status'] == 'active'
    assert patch['subscription']['cancel_at_period_end'] is True
    assert patch['subscription']['current_period_end'] - patch['subscription']['current_period_start'] == 30 * 86400
    assert patch['referral']['referrer_uid'] == 'referrer'


@pytest.mark.parametrize(
    ('referred_uid', 'referrer_uid', 'is_new_user', 'user_data'),
    [
        ('same-user', 'same-user', True, {}),
        ('existing-user', 'referrer', False, {}),
        ('paid-user', 'referrer', True, {'subscription': {'plan': 'operator'}}),
        ('claimed-user', 'referrer', True, {'referral': {'program': 'desktop_pro_month_v1'}}),
    ],
)
def test_referral_claim_never_self_refers_rewards_existing_users_or_overwrites_paid_accounts(
    referred_uid, referrer_uid, is_new_user, user_data
):
    assert (
        referral_claim_patch(
            referred_uid=referred_uid,
            referrer_uid=referrer_uid,
            is_new_user=is_new_user,
            user_data=user_data,
        )
        is None
    )


def test_referral_link_captures_secure_cookie_and_opens_existing_desktop_download(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    code = create_referral_code('referrer-123')

    with _loaded_referrals_router() as referrals:
        response = referrals.capture_referral(code)

    assert response.status_code == 302
    assert response.headers['location'] == 'https://macos.omi.me'
    cookie = response.headers['set-cookie']
    assert f'{REFERRAL_COOKIE_NAME}={code}' in cookie
    assert 'HttpOnly' in cookie
    assert 'Secure' in cookie
    assert 'SameSite=lax' in cookie


def test_authenticated_referrer_receives_a_stable_unique_https_link(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())

    with _loaded_referrals_router() as referrals:
        first = referrals.get_referral_link('referrer-123').referral_url
        second = referrals.get_referral_link('referrer-123').referral_url
        other = referrals.get_referral_link('another-user').referral_url

    assert first == second
    assert first != other
    assert first.startswith('https://api.omi.me/r/ref1.')


@pytest.mark.asyncio
async def test_new_user_auth_redeems_captured_referral(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_SECRET', TEST_SECRET.decode())
    monkeypatch.setenv('FIREBASE_API_KEY', 'test-key')
    referral_code = create_referral_code('referrer-123')
    claims = []

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
        return True

    async def run_inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(auth, 'get_auth_client', lambda: Client())
    monkeypatch.setattr(auth, 'claim_referral_trial', claim)
    monkeypatch.setattr(auth, 'run_blocking', run_inline)
    monkeypatch.setattr(auth.firebase_admin.auth, 'create_custom_token', lambda _uid: b'custom-token', raising=False)

    token = await auth._generate_custom_token('google', 'provider-token', referral_code=referral_code)

    assert token == 'custom-token'
    assert claims == [('new-user', 'referrer-123', True)]


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

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database import referral_campaign as ledger
from tests.unit.fixtures.referral_campaign import LocalCheckoutAdapter, POLICY, prepare, seed_user, settle
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_referrals import _loaded_referrals_router
from utils import referral_campaign as policy_module
from utils.referral_campaign import campaign_code


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'true')
    client = StrictFirestore()
    seed_user(client, 'owner')
    monkeypatch.setattr(ledger, '_client', lambda injected=None: injected or client)
    monkeypatch.setattr(ledger, 'current_policy', lambda: POLICY)
    monkeypatch.setattr(policy_module, 'current_policy', lambda: POLICY)
    with _loaded_referrals_router() as router:
        monkeypatch.setattr(router, 'TrustedCheckoutAdapter', LocalCheckoutAdapter)
        monkeypatch.setattr(router, 'current_policy', lambda: POLICY)
        app = FastAPI()
        app.include_router(router.router)
        app.dependency_overrides[router.auth.get_current_user_uid_readonly] = lambda: 'owner'
        yield TestClient(app), client, router


def test_real_routes_three_claim_retries_reentry_and_authenticated_uid(runtime):
    http, client, _ = runtime
    base = '/v2/users/me/referral/campaign'
    assert http.get(base).json()['qualified_purchases'] == 0
    for i in range(2):
        prepare(client, f'buyer-{i}')
        settle(client, f'buyer-{i}', f'order-{i}')
    assert http.get(base).json()['claimable_months'] == 2
    for _ in range(3):
        result = http.post(base + '/claim', json={'uid': 'attacker'}).json()
        assert result['qualified_purchases'] == 2 and result['claimed_months'] == 2
        assert result['claimable_months'] == 0
    assert http.get(base).json()['claimed_months'] == 2
    assert ('users', 'attacker') not in client.rows
    assert len([p for p in client.rows if p[0] == 'referral_awards']) == 1


def test_disabled_routes_cannot_issue_link_checkout_or_grant(runtime, monkeypatch):
    http, client, _ = runtime
    monkeypatch.setenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'false')
    before = dict(client.rows)
    base = '/v2/users/me/referral/campaign'
    assert http.get(base).json()['enabled'] is False
    assert http.post(base + '/claim').json()['referral_url'] is None
    assert http.post(base + '/attribution', json={'code': 'ref2.invalid.signature'}).status_code == 503
    assert client.rows == before


def test_new_link_goes_only_to_hardware_landing_and_self_attribution_rejected(runtime):
    http, _, _ = runtime
    code = campaign_code('owner', policy=POLICY)
    response = http.get('/r/' + code, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['location'].startswith('https://app.omi.me/referral/hardware?code=ref2.')
    assert 'login' not in response.headers['location']
    response = http.post('/v2/users/me/referral/campaign/attribution', json={'code': code})
    assert response.status_code == 409 and response.json()['detail'] == 'self_referral'


def test_missing_checkout_bridge_blocks_requests_even_if_flag_enabled(runtime, monkeypatch):
    http, client, router = runtime

    class MissingAdapter:
        ready = False

    monkeypatch.setattr(router, 'TrustedCheckoutAdapter', MissingAdapter)
    before = dict(client.rows)
    result = http.get('/v2/users/me/referral/campaign').json()
    assert result['enabled'] is False and result['reason'] == 'checkout_activation_required'
    assert http.post('/v2/users/me/referral/campaign/claim').json() == result
    assert client.rows == before

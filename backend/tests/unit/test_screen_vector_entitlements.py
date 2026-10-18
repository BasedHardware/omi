"""The three screen-vector consumers share billed identity, never a stored-price guess."""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from config.plan_catalog import LADDER_V1_PRICE_BINDINGS, RECOGNIZED_STRIPE_PRICE_PLAN_TYPES
from routers import desktop_proxy
from utils import screen_vector_entitlements as authority, subscription

LEGACY = next(price for price, plan in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if plan.value == 'plus')
PERIOD_END = int(datetime.now(timezone.utc).timestamp()) + 3600


def billed(price, subscription_id='sub_fixture', uid='synthetic'):
    return {'id': subscription_id, 'metadata': {'uid': uid}, 'items': {'data': [{'price': {'id': price}}]}}


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(authority, '_identity_cache', OrderedDict())
    for index, binding in enumerate(LADDER_V1_PRICE_BINDINGS.values()):
        monkeypatch.setenv(binding['env_var'], f'price_ladder_{index}')
    state = SimpleNamespace(
        stored={
            'plan': 'plus',
            'stripe_subscription_id': 'sub_fixture',
            'current_price_id': None,
            'current_period_end': PERIOD_END,
        },
        billed=billed('price_ladder_0'),
        clock=100.0,
        executors=[],
    )
    monkeypatch.setattr(authority, 'time', SimpleNamespace(monotonic=lambda: state.clock))
    state.db = Mock(side_effect=lambda *a, **k: state.stored)
    state.sdk_read = authority.read_stripe_subscription
    state.provider = Mock(side_effect=lambda *a: state.billed)
    monkeypatch.setattr(authority.users_db, 'get_user_valid_subscription', state.db)
    monkeypatch.setattr(authority, 'get_customer_firestore_client', lambda: 'customer-plane')
    monkeypatch.setattr(authority, 'read_stripe_subscription', state.provider)

    async def inline(executor, fn, *args, **kwargs):
        state.executors.append(executor)
        return fn(*args, **kwargs)

    monkeypatch.setattr(authority, 'run_blocking', inline)
    monkeypatch.setattr(desktop_proxy, 'get_byok_key', lambda _: None)
    monkeypatch.delenv('CLOUD_SCREEN_VECTORS_EMBED_REFUSAL_ENABLED', raising=False)
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize('stored_price', [None, LEGACY, 'price_stale_unknown', 'price_ladder_0'])
@pytest.mark.parametrize('billed_price,allowed', [('price_ladder_0', False), (LEGACY, True)])
async def test_real_proxy_and_vector_paths_use_billed_identity(state, stored_price, billed_price, allowed):
    state.stored['current_price_id'] = stored_price
    state.billed = billed(billed_price)
    path = 'models/gemini-embedding-001:embedContent'
    if allowed:
        await desktop_proxy._enforce_managed_plan_gate('synthetic', path, '1')
    else:
        with pytest.raises(HTTPException) as error:
            await desktop_proxy._enforce_managed_plan_gate('synthetic', path, '1')
        assert error.value.status_code == 402
        assert error.value.detail['reason'] == 'ladder_pro_required'
    assert await subscription.grants_cloud_screen_vectors('synthetic') is allowed
    assert state.stored['current_price_id'] == stored_price, 'read-only authority must not repair account rows'
    state.provider.assert_called_once_with('sub_fixture')
    assert state.executors == [authority.db_executor, authority.stripe_executor] * 2
    assert all(
        call.kwargs == {'provision': False, 'firestore_client': 'customer-plane'} for call in state.db.call_args_list
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('price,plan', sorted(RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items()))
@pytest.mark.parametrize('stripe_backed', [False, True])
async def test_each_legacy_paid_price_and_non_stripe_grandfather_remains_entitled(state, price, plan, stripe_backed):
    state.stored.update(
        plan=plan.value, current_price_id=price, stripe_subscription_id='sub_fixture' if stripe_backed else None
    )
    state.billed = billed(price)
    await desktop_proxy._enforce_managed_plan_gate('synthetic', 'models/gemini-embedding-001:embedContent', '1')
    assert await subscription.grants_cloud_screen_vectors('synthetic') is True
    assert state.provider.call_count == int(stripe_backed)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure',
    ['db', 'provider', 'unknown_price', 'wrong_subscription', 'wrong_owner', 'missing_item', 'multiple_items'],
)
async def test_unknown_authority_is_neither_upsell_nor_vector_grant(state, failure):
    if failure == 'db':
        state.db.side_effect = RuntimeError('unavailable')
    elif failure == 'provider':
        state.provider.side_effect = RuntimeError('unavailable')
    elif failure == 'unknown_price':
        state.billed = billed('price_unknown_billed')
    elif failure == 'wrong_subscription':
        state.billed = billed(LEGACY, subscription_id='sub_other')
    elif failure == 'wrong_owner':
        state.billed = billed(LEGACY, uid='other-owner')
    elif failure == 'missing_item':
        state.billed['items']['data'] = []
    else:
        state.billed['items']['data'] *= 2
    with pytest.raises(HTTPException) as error:
        await desktop_proxy._enforce_managed_plan_gate('synthetic', 'models/gemini-embedding-001:embedContent', '1')
    assert error.value.status_code == 503
    with pytest.raises(authority.ScreenVectorAuthorityUnavailable):
        await subscription.grants_cloud_screen_vectors('synthetic')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'header,byok_owner,kill',
    [(None, None, None), ('unknown', None, None), ('1', 'synthetic', None), ('1', None, 'false')],
)
async def test_early_exits_do_not_read_any_authority(state, monkeypatch, header, byok_owner, kill):
    monkeypatch.setattr(desktop_proxy, 'get_byok_key', lambda _: 'key' if byok_owner else None)
    monkeypatch.setattr(desktop_proxy, 'get_byok_uid', lambda: byok_owner)
    monkeypatch.setattr(desktop_proxy, 'has_validated_byok_keys', lambda: bool(byok_owner))
    if kill:
        monkeypatch.setenv('CLOUD_SCREEN_VECTORS_EMBED_REFUSAL_ENABLED', kill)
    await desktop_proxy._enforce_managed_plan_gate('synthetic', 'models/gemini-embedding-001:embedContent', header)
    state.db.assert_not_called()
    state.provider.assert_not_called()


def test_cache_freshness_scope_invalidation_and_force_refresh(state):
    resolve = lambda uid='synthetic': authority.resolve_subscription(uid, state.stored)['capabilities'][
        'cloud_screen_vectors'
    ]
    assert resolve() is False
    state.billed = billed(LEGACY)
    assert resolve() is False
    state.clock += 61
    assert resolve() is True
    state.stored['current_price_id'] = LEGACY
    assert resolve() is True
    assert state.provider.call_count == 3
    state.billed = billed('price_ladder_0')
    fresh = authority.refresh_subscription('synthetic', state.stored, force_refresh=True)
    assert (
        authority.resolve_subscription('synthetic', fresh, already_fresh=True)['capabilities']['cloud_screen_vectors']
        is False
    )
    assert state.provider.call_count == 4, 'GET reuses its already-fresh identity without a duplicate call'
    authority.clear('synthetic')
    assert resolve() is False
    state.billed = billed(LEGACY, uid='other')
    assert resolve('other') is True
    assert state.provider.call_count == 6


def test_negative_cache_retries_after_recovery_without_using_stale_positive(state):
    authority.resolve_subscription('synthetic', state.stored)
    state.clock += 61
    state.provider.side_effect = RuntimeError('unavailable')
    with pytest.raises(authority.ScreenVectorAuthorityUnavailable):
        authority.resolve_subscription('synthetic', state.stored)
    state.provider.side_effect = lambda *a: billed(LEGACY)
    with pytest.raises(authority.ScreenVectorAuthorityUnavailable):
        authority.resolve_subscription('synthetic', state.stored)
    assert state.provider.call_count == 2
    state.clock += 6
    assert authority.resolve_subscription('synthetic', state.stored)['capabilities']['cloud_screen_vectors'] is True


def test_cache_is_bounded_and_same_identity_refresh_is_single_flight(state):
    for index in range(authority.MAX_CACHE_ENTRIES + 1):
        authority._store_price((str(index),), LEGACY)
    assert len(authority._identity_cache) == authority.MAX_CACHE_ENTRIES
    assert ('0',) not in authority._identity_cache
    start, entered, release = Barrier(4), Event(), Event()

    def read(_id):
        entered.set()
        assert release.wait(2)
        return billed(LEGACY)

    state.provider.side_effect = read

    def resolve():
        start.wait(timeout=2)
        return authority.resolve_subscription('synthetic', state.stored)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(resolve) for _ in range(4)]
        assert entered.wait(2)
        release.set()
        assert all(f.result(timeout=2)['capabilities']['cloud_screen_vectors'] for f in futures)
    state.provider.assert_called_once()


def test_lazy_sdk_uses_bounded_timeout_without_retries(monkeypatch):
    from unittest.mock import MagicMock

    authority._stripe_client.cache_clear()
    monkeypatch.delenv('SCREEN_VECTOR_STRIPE_API_KEY', raising=False)
    client = MagicMock()
    client.subscriptions.retrieve.return_value.to_dict.return_value = billed(LEGACY)
    constructor = Mock(return_value=client)
    http = Mock(return_value='bounded-http-client')
    monkeypatch.setattr(authority.stripe, 'api_key', 'test-not-real')
    monkeypatch.setattr(authority.stripe, 'StripeClient', constructor)
    monkeypatch.setattr(authority.stripe, 'RequestsClient', http)
    assert authority.read_stripe_subscription('sub_fixture') == billed(LEGACY)
    assert authority.read_stripe_subscription('sub_fixture') == billed(LEGACY)
    constructor.assert_called_once_with('test-not-real', max_network_retries=0, http_client='bounded-http-client')
    http.assert_called_once_with(timeout=5)
    assert client.subscriptions.retrieve.call_count == 2
    authority._stripe_client.cache_clear()


def test_changed_subscription_identity_misses_cache_and_policy_is_never_cached(state, monkeypatch):
    assert authority.resolve_subscription('synthetic', state.stored)['capabilities']['cloud_screen_vectors'] is False
    # The same billed ID now maps to Pro through the configured catalog binding;
    # policy is recomputed without another provider read.
    monkeypatch.delenv('LADDER_V1_PLUS_MONTH_PRICE_ID')
    monkeypatch.setenv('LADDER_V1_PRO_MONTH_PRICE_ID', 'price_ladder_0')
    assert authority.resolve_subscription('synthetic', state.stored)['capabilities']['cloud_screen_vectors'] is True
    state.provider.assert_called_once()
    state.stored['stripe_subscription_id'] = 'sub_changed'
    state.billed = billed(LEGACY, subscription_id='sub_changed')
    assert authority.resolve_subscription('synthetic', state.stored)['capabilities']['cloud_screen_vectors'] is True
    assert state.provider.call_args.args == ('sub_changed',)
    assert state.provider.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('stored_price', [None, LEGACY, 'price_stale_unknown'])
async def test_no_ladder_configuration_preserves_legacy_without_any_stripe_credential(state, monkeypatch, stored_price):
    for binding in LADDER_V1_PRICE_BINDINGS.values():
        monkeypatch.delenv(binding['env_var'], raising=False)
    monkeypatch.delenv('SCREEN_VECTOR_STRIPE_API_KEY', raising=False)
    monkeypatch.delenv('STRIPE_API_KEY', raising=False)
    monkeypatch.setattr(authority.stripe, 'api_key', None)
    state.stored['current_price_id'] = stored_price
    state.provider.side_effect = AssertionError('legacy-only configuration called Stripe')
    await desktop_proxy._enforce_managed_plan_gate('synthetic', 'models/gemini-embedding-001:embedContent', '1')
    assert await subscription.grants_cloud_screen_vectors('synthetic') is True
    refreshed = authority.refresh_subscription('synthetic', state.stored)
    assert refreshed == state.stored
    state.provider.assert_not_called()


def test_restricted_key_preferred_and_identity_cache_is_credential_scoped(state, monkeypatch):
    from unittest.mock import MagicMock

    assert authority.resolve_subscription('synthetic', state.stored)['capabilities']['cloud_screen_vectors'] is False
    monkeypatch.setenv('SCREEN_VECTOR_STRIPE_API_KEY', 'restricted-fixture-key')
    state.billed = billed(LEGACY)
    assert authority.resolve_subscription('synthetic', state.stored)['capabilities']['cloud_screen_vectors'] is True
    assert state.provider.call_count == 2, 'credential switch cannot reuse an older provider namespace'
    monkeypatch.setattr(authority.stripe, 'api_key', 'main-billing-fixture-key')
    authority._stripe_client.cache_clear()
    client = MagicMock()
    client.subscriptions.retrieve.return_value.to_dict.return_value = billed(LEGACY)
    constructor = Mock(return_value=client)
    monkeypatch.setattr(authority.stripe, 'StripeClient', constructor)
    monkeypatch.setattr(authority.stripe, 'RequestsClient', Mock(return_value='http'))
    assert state.sdk_read('sub_fixture') == billed(LEGACY)
    constructor.assert_called_once_with('restricted-fixture-key', max_network_retries=0, http_client='http')
    authority._stripe_client.cache_clear()


@pytest.mark.parametrize('price', [LEGACY, 'price_unmapped_legacy'])
def test_explicit_legacy_subscription_refresh_keeps_current_price_fresh(state, monkeypatch, price):
    for binding in LADDER_V1_PRICE_BINDINGS.values():
        monkeypatch.delenv(binding['env_var'], raising=False)
    state.billed = billed(price)
    refreshed = authority.refresh_subscription('synthetic', state.stored, force_refresh=True)
    assert refreshed['current_price_id'] == price
    assert state.stored['current_price_id'] is None
    assert (
        authority.resolve_subscription('synthetic', refreshed, already_fresh=True)['capabilities'][
            'cloud_screen_vectors'
        ]
        is True
    )
    state.provider.assert_called_once_with('sub_fixture')


def test_fresh_but_unmapped_mixed_price_is_not_a_legacy_grant(state):
    state.billed = billed('price_unmapped_billed')
    refreshed = authority.refresh_subscription('synthetic', state.stored, force_refresh=True)
    assert refreshed['current_price_id'] == 'price_unmapped_billed'
    with pytest.raises(authority.ScreenVectorAuthorityUnavailable):
        authority.resolve_subscription('synthetic', refreshed, already_fresh=True)
    with pytest.raises(authority.ScreenVectorAuthorityUnavailable):
        authority.resolve_subscription('synthetic', state.stored)
    state.provider.assert_called_once_with('sub_fixture')

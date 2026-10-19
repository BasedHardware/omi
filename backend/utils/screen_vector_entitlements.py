"""Read-only screen-vector authority shared by API signal, proxy and persistence.

With mixed ladder configuration, Stripe-backed records require billed identity
even when their stored price is a known legacy price. Legacy-only configuration
hot paths and non-Stripe records retain catalog grandfathering without a provider read. Async
callers sequence DB and Stripe executors; synchronous HTTP handlers may call
refresh_subscription directly. No executor waits or account writes occur here.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from functools import lru_cache
import os
from threading import Lock
import time
from typing import Any, cast

import stripe

from config.plan_catalog import (
    configured_ladder_prices,
    LADDER_V1_STRIPE_PRICES,
    resolve_price_entitlements,
    resolve_subscription_entitlements,
)
from database import users as users_db
from database._client import get_customer_firestore_client
from utils.executors import db_executor, stripe_executor, run_blocking

SUCCESS_TTL_SECONDS = 60
FAILURE_TTL_SECONDS = 5
MAX_CACHE_ENTRIES = 2048
CacheKey = tuple[Any, ...]
_identity_cache: OrderedDict[CacheKey, tuple[str | None, float]] = OrderedDict()
_cache_lock = Lock()
# Fixed-size single-flight locks bound both memory and concurrent refreshes.
_refresh_locks = tuple(Lock() for _ in range(32))


class ScreenVectorAuthorityUnavailable(RuntimeError):
    """The billed identity is unknown; neither a grant nor an upsell is justified."""


@lru_cache(maxsize=2)
def _stripe_client(api_key: str) -> stripe.StripeClient:
    return stripe.StripeClient(api_key, max_network_retries=0, http_client=stripe.RequestsClient(timeout=5))


def _stripe_api_key() -> str | None:
    return os.getenv('SCREEN_VECTOR_STRIPE_API_KEY') or stripe.api_key or os.getenv('STRIPE_API_KEY')


def read_stripe_subscription(subscription_id: str) -> dict[str, Any]:
    key = _stripe_api_key()
    if not key:
        raise ScreenVectorAuthorityUnavailable('Stripe credentials unavailable')
    return _stripe_client(key).subscriptions.retrieve(subscription_id).to_dict()


def _field(subscription: Any, name: str, default: Any = None) -> Any:
    return (
        cast(Mapping[str, Any], subscription).get(name, default)
        if isinstance(subscription, Mapping)
        else getattr(subscription, name, default)
    )


def read_subscription(uid: str) -> Any:
    return users_db.get_user_valid_subscription(uid, provision=False, firestore_client=get_customer_firestore_client())


def clear(uid: str) -> None:
    with _cache_lock:
        for key in list(_identity_cache):
            if key[0] == uid:
                del _identity_cache[key]


def _cached_price(key: CacheKey) -> tuple[bool, str | None]:
    with _cache_lock:
        cached = _identity_cache.get(key)
        if cached is None:
            return False, None
        price, expires = cached
        if time.monotonic() >= expires:
            del _identity_cache[key]
            return False, None
        _identity_cache.move_to_end(key)
        return True, price


def _store_price(key: CacheKey, price: str | None) -> None:
    with _cache_lock:
        _identity_cache[key] = (price, time.monotonic() + (SUCCESS_TTL_SECONDS if price else FAILURE_TTL_SECONDS))
        _identity_cache.move_to_end(key)
        while len(_identity_cache) > MAX_CACHE_ENTRIES:
            _identity_cache.popitem(last=False)


def _billed_price(uid: str, subscription: Any, *, force_refresh: bool) -> str:
    subscription_id = _field(subscription, 'stripe_subscription_id')
    key = (
        uid,
        subscription_id,
        _stripe_api_key(),
        *(_field(subscription, name) for name in ('plan', 'current_price_id', 'current_period_end', 'status')),
    )
    with _refresh_locks[hash(key) % len(_refresh_locks)]:
        hit, price = _cached_price(key) if not force_refresh else (False, None)
        if not hit:
            try:
                billed = read_stripe_subscription(subscription_id)
                if billed.get('id') != subscription_id:
                    raise ScreenVectorAuthorityUnavailable('Subscription identity mismatch')
                if billed.get('metadata', {}).get('uid', uid) != uid:
                    raise ScreenVectorAuthorityUnavailable('Subscription owner mismatch')
                items = billed.get('items', {}).get('data', [])
                if len(items) != 1:
                    raise ScreenVectorAuthorityUnavailable('Ambiguous subscription price')
                price = items[0]['price']['id']
                if not isinstance(price, str) or not price:
                    raise ScreenVectorAuthorityUnavailable('Missing subscription price')
            except Exception as error:
                _store_price(key, None)
                raise ScreenVectorAuthorityUnavailable('Billed identity unavailable') from error
            _store_price(key, price)
        if price is None:
            raise ScreenVectorAuthorityUnavailable('Billed identity unavailable')
        return price


def refresh_subscription(uid: str, subscription: Any, *, force_refresh: bool = False) -> Any:
    """Copy only billed price identity, preserving real plan/period and input ownership."""
    if not _field(subscription, 'stripe_subscription_id'):
        return subscription
    # With no ladder identity in service, every paid price retains legacy policy.
    # Hot paths must not require a new desktop credential. Explicit GET refresh
    # retains its existing provider read so current-price UI/allowance stay fresh.
    if not force_refresh and not configured_ladder_prices() and not LADDER_V1_STRIPE_PRICES:
        return subscription
    price = _billed_price(uid, subscription, force_refresh=force_refresh)
    if isinstance(subscription, Mapping):
        return dict(cast(Mapping[str, Any], subscription), current_price_id=price)
    return subscription.model_copy(update={'current_price_id': price})


def resolve_subscription(uid: str, subscription: Any, *, already_fresh: bool = False) -> dict[str, Any]:
    snapshot = subscription if already_fresh else refresh_subscription(uid, subscription)
    if _field(snapshot, 'stripe_subscription_id') and (configured_ladder_prices() or LADDER_V1_STRIPE_PRICES):
        # Identity is cached, policy is not. Mixed-mode unknown prices cannot
        # inherit a stored legacy grant, even for an already-fresh GET snapshot.
        try:
            resolve_price_entitlements(_field(snapshot, 'current_price_id'))
        except Exception as error:
            raise ScreenVectorAuthorityUnavailable('Billed price policy unavailable') from error
    return resolve_subscription_entitlements(snapshot or {'plan': 'basic'})


async def resolve_for_uid(uid: str) -> dict[str, Any]:
    subscription = await run_blocking(db_executor, read_subscription, uid)
    return await run_blocking(stripe_executor, resolve_subscription, uid, subscription)

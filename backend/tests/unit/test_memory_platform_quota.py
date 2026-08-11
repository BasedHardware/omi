"""Plan entitlement + metering contract for the Memory Platform API."""

import pytest
from fastapi import HTTPException

import database.memory_platform_usage as platform_usage_db
import utils.memory.platform_quota as platform_quota
from models.users import PlanType, Subscription
from utils.subscription import FREE_PLATFORM_API_REQUESTS_PER_MONTH, get_plan_limits


class _FakeRedis:
    def __init__(self, start=0, fail=False):
        self.values = {}
        self.fail = fail
        self.start = start

    def get(self, key):
        if self.fail:
            raise RuntimeError('redis down')
        return self.values.get(key, self.start)

    def incr(self, key, amount=1):
        if self.fail:
            raise RuntimeError('redis down')
        self.values[key] = self.values.get(key, self.start) + amount
        return self.values[key]

    def decr(self, key, amount=1):
        self.values[key] = self.values.get(key, self.start) - amount
        return self.values[key]

    def expire(self, key, ttl):
        return True


def _use_plan(monkeypatch, plan):
    monkeypatch.setattr(
        platform_quota,
        'users_db',
        type('_Users', (), {'get_user_valid_subscription': staticmethod(lambda _uid: Subscription(plan=plan))}),
    )


def test_basic_plan_has_a_usable_non_zero_platform_allowance():
    limit = get_plan_limits(PlanType.basic).platform_api_requests_per_month

    assert limit == FREE_PLATFORM_API_REQUESTS_PER_MONTH
    assert limit > 0


def test_existing_basic_subscriber_is_still_served(monkeypatch):
    """Legacy principal: a user already on `basic` keeps being served."""
    _use_plan(monkeypatch, PlanType.basic)
    monkeypatch.setattr(platform_usage_db, 'r', _FakeRedis())

    platform_quota.enforce_platform_quota('user-1')

    snapshot = platform_quota.get_platform_quota_snapshot('user-1')
    assert snapshot['plan_type'] == 'basic'
    assert snapshot['allowed'] is True
    assert snapshot['used'] == 1
    assert snapshot['remaining'] == FREE_PLATFORM_API_REQUESTS_PER_MONTH - 1


def test_over_quota_raises_429_naming_the_plan_and_limit(monkeypatch):
    _use_plan(monkeypatch, PlanType.basic)
    monkeypatch.setattr(platform_usage_db, 'r', _FakeRedis(start=FREE_PLATFORM_API_REQUESTS_PER_MONTH))

    with pytest.raises(HTTPException) as excinfo:
        platform_quota.enforce_platform_quota('user-1')

    assert excinfo.value.status_code == 429
    detail = excinfo.value.detail
    assert detail['error'] == 'platform_quota_exceeded'
    assert detail['plan_type'] == 'basic'
    assert detail['limit'] == FREE_PLATFORM_API_REQUESTS_PER_MONTH
    assert detail['reset_at'] > 0


def test_paid_plan_is_uncapped_and_never_metered(monkeypatch):
    _use_plan(monkeypatch, PlanType.operator)
    redis = _FakeRedis()
    monkeypatch.setattr(platform_usage_db, 'r', redis)

    platform_quota.enforce_platform_quota('user-1')

    assert redis.values == {}
    snapshot = platform_quota.get_platform_quota_snapshot('user-1')
    assert snapshot['limit'] is None
    assert snapshot['remaining'] is None
    assert snapshot['allowed'] is True


def test_counter_outage_fails_open_and_records_a_fallback(monkeypatch):
    _use_plan(monkeypatch, PlanType.basic)
    monkeypatch.setattr(platform_usage_db, 'r', _FakeRedis(fail=True))
    recorded = []
    monkeypatch.setattr(platform_usage_db, 'record_fallback', lambda **kwargs: recorded.append(kwargs))

    platform_quota.enforce_platform_quota('user-1')

    assert len(recorded) == 1
    assert recorded[0]['component'] == 'memory_platform'
    assert recorded[0]['outcome'] == 'degraded'


def test_web_quota_client_type_matches_the_response_model():
    """The web billing client must name the fields this route actually returns.

    STATIC CHECKER: this reads the TypeScript source rather than executing it.
    It exists because the web surface shipped a `PlatformApiQuota` interface with
    invented `included_requests`/`used_requests`/`remaining_requests` fields while
    the route was still pending, which renders an empty quota bar against the
    real response. The model side is real introspection, so adding or renaming a
    field on `MemoryPlatformQuota` fails here until the client is updated.
    """
    import re
    from pathlib import Path

    from models.memory_platform import MemoryPlatformQuota

    root = Path(__file__).resolve().parents[3]
    client = (root / 'web' / 'frontend' / 'src' / 'lib' / 'api' / 'billing.ts').read_text(encoding='utf-8')

    body = re.search(r'export interface PlatformApiQuota \{(.*?)\n\}', client, re.S)
    assert body, 'PlatformApiQuota interface not found in web/frontend/src/lib/api/billing.ts'
    declared = set(re.findall(r'^\s*(\w+)\??:', body.group(1), re.M))

    assert declared == set(MemoryPlatformQuota.model_fields), (
        f'client fields {sorted(declared)} != MemoryPlatformQuota fields ' f'{sorted(MemoryPlatformQuota.model_fields)}'
    )


def test_web_billing_client_calls_the_route_that_exists():
    """STATIC CHECKER: the quota seam must point at the real path.

    The web client originally called `/v1/payments/platform-api-quota`, a route
    that was never implemented on any surface.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    client = (root / 'web' / 'frontend' / 'src' / 'lib' / 'api' / 'billing.ts').read_text(encoding='utf-8')

    assert '/v1/memory/platform/quota' in client
    assert 'platform-api-quota' not in client


def test_web_search_client_type_matches_the_response_model():
    """The web search client must name the field the search route actually returns.

    STATIC CHECKER: this reads the TypeScript source rather than executing it.
    It exists because the client declared `memories` while
    `ProductMemorySearchResponse` returns `items`, so every successful search
    decoded to nothing and the widget rendered an empty result list. The model
    side is real introspection, so renaming the results field on the response
    model fails here until the client follows.
    """
    import re
    from pathlib import Path

    from models.memory_product import ProductMemorySearchResponse

    root = Path(__file__).resolve().parents[3]
    client = (root / 'web' / 'frontend' / 'src' / 'lib' / 'api' / 'memory-platform.ts').read_text(encoding='utf-8')

    body = re.search(r'export interface PlatformSearchResponse \{(.*?)\n\}', client, re.S)
    assert body, 'PlatformSearchResponse interface not found in web/frontend/src/lib/api/memory-platform.ts'
    declared = set(re.findall(r'^\s*(\w+)\??:', body.group(1), re.M))

    model_fields = set(ProductMemorySearchResponse.model_fields)
    unknown = declared - model_fields
    assert not unknown, f'client declares fields the response model does not return: {sorted(unknown)}'
    assert 'items' in declared, 'the client must decode the results page from `items`'

    # The consumer has to read the same field the interface declares.
    widget = (
        root / 'web' / 'frontend' / 'src' / 'app' / 'memory-platform' / 'components' / 'memory-widget.tsx'
    ).read_text(encoding='utf-8')
    assert 'response?.items' in widget
    assert 'response?.memories' not in widget


def test_web_browser_clients_do_not_read_the_server_only_api_url():
    """STATIC CHECKER: browser API modules must use the public backend origin.

    `API_URL` is not a `NEXT_PUBLIC_*` variable, so Next.js does not inline it
    into the client bundle. A browser module reading it resolves every request to
    a relative path against the web origin instead of the backend.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    api_dir = root / 'web' / 'frontend' / 'src' / 'lib' / 'api'
    browser_clients = ['billing.ts', 'mcp-keys.ts', 'memory-platform.ts']

    for name in browser_clients:
        source = (api_dir / name).read_text(encoding='utf-8')
        assert 'envConfig.API_URL' not in source, f'{name} reads the server-only API_URL in a browser module'
        assert 'browserApiBase' in source, f'{name} must resolve its base through browserApiBase'

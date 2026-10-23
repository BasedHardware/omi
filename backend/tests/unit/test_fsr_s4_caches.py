"""Serving-path read counts and cache correctness; Redis Lua runs in fakeredis."""

import asyncio
import copy
import json
import time
from datetime import datetime, timezone
from contextvars import Context
from types import SimpleNamespace

import fakeredis
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from google.cloud.firestore_v1.transforms import Increment

from database import account_deletion_marker as deletion
from database import desktop_update_policy, serving_query_reads, user_usage, users
from models.users import PlanType, Subscription
from routers import users as router, payment, desktop_prompts, updates
from utils.other import endpoints as auth
from database import fsr_read_cache as cache
from utils import subscription
from tests.unit.fixtures.shadow_usage_firestore import Transaction


class Snapshot:
    def __init__(self, path, data):
        self.id = path.split('/')[-1]
        self.exists = data is not None
        self.data = copy.deepcopy(data)

    def to_dict(self):
        return copy.deepcopy(self.data)


class Store:
    project = 'test-project'
    _database = '(default)'

    def __init__(self):
        self.docs = {'users/u': {'subscription': {'plan': 'basic', 'status': 'active'}, 'byok': {}}}
        self.reads = []
        self.writes = []

    def collection(self, name):
        return Ref(self, name)

    def transaction(self):
        return Transaction()

    def batch(self):
        class Batch:
            def __init__(self):
                self.pending = []

            def set(self, ref, data, merge=False):
                self.pending.append((ref, data, merge))

            def commit(self):
                for ref, data, merge in self.pending:
                    ref.set(data, merge=merge)

        return Batch()


class Ref:
    def __init__(self, store, path, filters=(), count=None):
        self.store, self.path, self.filters, self.count = store, path, filters, count

    @property
    def id(self):
        return self.path.split('/')[-1]

    def document(self, name):
        return Ref(self.store, self.path + '/' + name)

    def collection(self, name):
        return Ref(self.store, self.path + '/' + name)

    def get(self, fields=None, transaction=None):
        if transaction is not None and transaction.pending:
            raise RuntimeError('Firestore transactions must read before writing')
        self.store.reads.append(self.path)
        data = self.store.docs.get(self.path)
        if fields is not None and data is not None:
            data = {key: value for key, value in data.items() if key in fields}
        return Snapshot(self.path, data)

    def where(self, *args, filter=None):
        condition = (filter.field_path, filter.op_string, filter.value) if filter else args
        return Ref(self.store, self.path, (*self.filters, condition), self.count)

    def limit(self, count):
        return Ref(self.store, self.path, self.filters, count)

    def stream(self):
        rows = []
        for path, data in sorted(self.store.docs.items()):
            if path.rsplit('/', 1)[0] != self.path:
                continue
            if not all(
                data.get(field) == value if op == '==' else data.get(field) >= value
                for field, op, value in self.filters
            ):
                continue
            rows.append((path, data))
        for path, data in rows[: self.count]:
            self.store.reads.append(path)
            yield Snapshot(path, data)

    def set(self, data, merge=False):
        target = self.store.docs.setdefault(self.path, {}) if merge else {}

        def apply(dest, source):
            for key, value in source.items():
                if isinstance(value, Increment):
                    dest[key] = dest.get(key, 0) + value._value
                elif isinstance(value, dict):
                    apply(dest.setdefault(key, {}), value)
                else:
                    dest[key] = copy.deepcopy(value)

        apply(target, data)
        self.store.docs[self.path] = target
        self.store.writes.append(self.path)

    def update(self, data):
        self.set(data, merge=True)


@pytest.fixture
def env(monkeypatch):
    store = Store()
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(cache, '_redis', lambda: redis)
    monkeypatch.setattr(users, 'db', store)
    monkeypatch.setattr(users, 'get_data_plane_firestore_client', lambda: store)
    monkeypatch.setattr(deletion, 'get_data_plane_firestore_client', lambda: store)
    monkeypatch.setattr(user_usage, 'db', store)
    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *args, **kwargs: 'basic')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    cache._configs.clear()
    return store, redis


def enable(monkeypatch, *names):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(dict.fromkeys(names, 100)))


@pytest.mark.parametrize('enabled,expected', [(False, 6), (True, 1)])
def test_deletion_negative_cache_read_count(env, monkeypatch, enabled, expected):
    if enabled:
        enable(monkeypatch, 'deletion_marker_cache')
    for _ in range(6):
        assert deletion.get_user_deletion_wipe_status('u') is None
    assert len(env[0].reads) == expected


def test_deletion_next_request_fenced_after_real_intent_writer(env, monkeypatch):
    enable(monkeypatch, 'deletion_marker_cache')
    assert deletion.get_user_deletion_wipe_status('u') is None

    def commit(transaction, ref, job_id):
        ref.set({'wipe_status': 'pending', 'wipe_job_id': job_id}, merge=True)
        # The warm absent entry cannot be used even before writer completion.
        assert deletion.get_user_deletion_wipe_status('u') == 'pending'
        return {'wipe_job_id': job_id, 'dispatch_claimed': True}

    monkeypatch.setattr(users, '_mark_user_deletion_wipe_intent_txn', commit)
    users.mark_user_deletion_wipe_intent('u')
    assert deletion.get_user_deletion_wipe_status('u') == 'pending'
    assert deletion.get_user_deletion_wipe_status('u') == 'pending'  # Positive state stays durable.
    users.cancel_user_deletion_wipe('u')
    assert deletion.get_user_deletion_wipe_status('u') == 'cancelled'


def test_lever_off_writer_still_fences_enabled_readers(env, monkeypatch):
    # Mixed rollout: an enabled revision warms the cache, then an old/off-cohort revision writes.
    enable(monkeypatch, 'deletion_marker_cache', 'subscription_cache')
    assert deletion.get_user_deletion_wipe_status('u') is None
    assert users.get_user_valid_subscription('u').plan == PlanType.basic

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    monkeypatch.setattr(
        users,
        '_mark_user_deletion_wipe_intent_txn',
        lambda transaction, ref, job_id: ref.set({'wipe_status': 'pending', 'wipe_job_id': job_id}, merge=True)
        or {'wipe_job_id': job_id, 'dispatch_claimed': True},
    )
    users.mark_user_deletion_wipe_intent('u')
    users.update_user_subscription(
        'u', {'plan': 'operator', 'status': 'active', 'current_period_end': int(time.time()) + 3600}
    )

    enable(monkeypatch, 'deletion_marker_cache', 'subscription_cache')
    assert deletion.get_user_deletion_wipe_status('u') == 'pending'
    assert users.get_user_valid_subscription('u').plan == PlanType.operator


@pytest.mark.parametrize('enabled,expected', [(False, 4), (True, 1)])
def test_subscription_read_count_and_deep_copies(env, monkeypatch, enabled, expected):
    if enabled:
        enable(monkeypatch, 'subscription_cache')
    first = users.get_user_subscription('u')
    first.limits.transcription_seconds = 987654
    first.plan = PlanType.operator
    for _ in range(3):
        result = users.get_user_valid_subscription('u')
        assert result.plan == PlanType.basic
        assert result.limits.transcription_seconds != 987654
    assert len(env[0].reads) == expected


def test_subscription_webhook_write_visible_immediately(env, monkeypatch):
    enable(monkeypatch, 'subscription_cache')
    assert users.get_user_valid_subscription('u').plan == PlanType.basic
    # This is the shared writer called by every Stripe webhook update/grant.
    users.update_user_subscription(
        'u', {'plan': 'operator', 'status': 'active', 'current_period_end': int(time.time()) + 3600}
    )
    assert users.get_user_valid_subscription('u').plan == PlanType.operator


def test_byok_cache_invalidated_by_real_deactivation_writer(env, monkeypatch):
    enable(monkeypatch, 'subscription_cache')
    env[0].docs['users/u']['byok'] = {'active': True, 'last_seen_at': datetime.now(timezone.utc)}
    assert users.is_byok_active('u')
    assert users.is_byok_active('u')
    assert len(env[0].reads) == 1
    users.clear_byok_active('u')
    assert not users.is_byok_active('u')
    assert len(env[0].reads) == 2


@pytest.mark.parametrize('enabled,expected', [(False, 10), (True, 2)])
def test_usage_month_counts_and_writer_never_undercounts(env, monkeypatch, enabled, expected):
    store, _ = env
    date = datetime(2026, 10, 16, tzinfo=timezone.utc)
    for hour in range(2):
        store.docs[f'users/u/hourly_usage/2026-10-16-{hour:02}'] = {
            'id': f'2026-10-16-{hour:02}',
            'year': 2026,
            'month': 10,
            'transcription_seconds': 10,
        }
    if enabled:
        enable(monkeypatch, 'usage_month_cache')
    for _ in range(5):
        assert user_usage.get_monthly_usage_stats_since('u', date, date)['transcription_seconds'] == 20
    assert len(store.reads) == expected
    user_usage.update_hourly_usage('u', date, {'transcription_seconds': 100})
    assert user_usage.get_monthly_usage_stats_since('u', date, date)['transcription_seconds'] == 120


def test_usage_month_and_launch_boundary_separate(env, monkeypatch):
    enable(monkeypatch, 'usage_month_cache')
    store, _ = env
    for month in (9, 10):
        for day in (1, 16):
            key = f'2026-{month:02}-{day:02}-00'
            store.docs[f'users/u/hourly_usage/{key}'] = {
                'id': key,
                'year': 2026,
                'month': month,
                'transcription_seconds': day,
            }
    date = datetime(2026, 10, 16, tzinfo=timezone.utc)
    start = date.replace(day=1)
    assert user_usage.get_monthly_usage_stats_since('u', date, start)['transcription_seconds'] == 17
    assert user_usage.get_monthly_usage_stats_since('u', date, date)['transcription_seconds'] == 16
    assert user_usage.get_monthly_usage_stats_since('u', date.replace(month=9), start)['transcription_seconds'] == 0


@pytest.mark.parametrize('family', ['subscription_cache', 'deletion_marker_cache', 'usage_month_cache'])
def test_redis_down_falls_back_to_firestore(env, monkeypatch, family):
    enable(monkeypatch, family)

    class Down:
        def eval(self, *args):
            raise ConnectionError('unavailable')

    monkeypatch.setattr(cache, '_redis', Down)
    for _ in range(2):
        if family == 'subscription_cache':
            assert users.get_user_subscription('u').plan == PlanType.basic
        elif family == 'deletion_marker_cache':
            assert deletion.get_user_deletion_wipe_status('u') is None
        else:
            assert user_usage.get_monthly_usage_stats('u', datetime.now())['transcription_seconds'] == 0
    if family != 'usage_month_cache':
        assert len(env[0].reads) == 2
    # Durable writes also keep working during Redis failure.
    users.update_user_subscription('u', {'plan': 'basic', 'status': 'active'})
    assert env[0].writes == ['users/u']


def test_firestore_failure_is_not_retried_or_cached(env, monkeypatch):
    enable(monkeypatch, 'deletion_marker_cache')
    attempts = []

    def fail():
        attempts.append(1)
        raise RuntimeError('durable state unavailable')

    with cache.writing('deletion_marker_cache', 'u'):
        with pytest.raises(RuntimeError):
            cache.cached_read('deletion_marker_cache', 'u', 'test', fail)
    assert len(attempts) == 1


def test_inflight_old_read_cannot_repopulate_after_write(env, monkeypatch):
    enable(monkeypatch, 'subscription_cache')

    def fetch_before_write():
        users.update_user_subscription('u', {'plan': 'operator', 'status': 'active'})
        return {'plan': 'basic'}

    assert cache.cached_read('subscription_cache', 'u', 'race', fetch_before_write) == {'plan': 'basic'}
    assert cache.cached_read('subscription_cache', 'u', 'race', lambda: {'plan': 'operator'}) == {'plan': 'operator'}


def test_overlapping_writers_and_failed_end_keep_reads_durable(env, monkeypatch):
    enable(monkeypatch, 'subscription_cache')
    calls = []

    def fetch():
        calls.append(1)
        return len(calls)

    with cache.writing('subscription_cache', 'u'):
        with cache.writing('subscription_cache', 'u'):
            cache.cached_read('subscription_cache', 'u', 'race', fetch)
        cache.cached_read('subscription_cache', 'u', 'race', fetch)
    cache.cached_read('subscription_cache', 'u', 'race', fetch)
    assert len(calls) == 3
    assert cache.cached_read('subscription_cache', 'u', 'race', fetch) == 3


def test_fresh_purchase_bypasses_warm_subscription_and_byok(env, monkeypatch):
    enable(monkeypatch, 'subscription_cache')
    users.get_user_subscription('u')
    users.get_byok_state('u')
    env[0].docs['users/u']['subscription']['plan'] = 'operator'
    with cache.fresh_reads():
        assert users.get_user_subscription('u').plan == PlanType.operator
        users.get_byok_state('u')
    assert len(env[0].reads) == 4


@pytest.mark.parametrize('enabled,expected', [(False, 6), (True, 2)])
def test_request_memo_crosses_fastapi_threadpool_and_resets(env, monkeypatch, enabled, expected):
    if enabled:
        enable(monkeypatch, 'request_read_dedupe')
    app = FastAPI()

    def dependency():
        users.get_byok_state('u')
        return users.get_user_subscription('u')

    @app.get('/request', dependencies=[Depends(cache.request_read_scope)])
    def endpoint(_sub=Depends(dependency)):
        return {'plan': users.get_user_valid_subscription('u').plan}

    with TestClient(app) as client:
        assert client.get('/request').json() == {'plan': 'basic'}
        assert client.get('/request').json() == {'plan': 'basic'}
    assert len(env[0].reads) == expected


def test_request_writer_invalidates_shared_snapshot_and_return_value(env, monkeypatch):
    enable(monkeypatch, 'request_read_dedupe')

    async def request():
        scope = cache.request_read_scope()
        await anext(scope)
        try:
            assert users.get_user_subscription('u').plan == PlanType.basic
            users.update_user_subscription('u', {'plan': 'operator', 'status': 'active'})
            assert users.get_user_subscription('u').plan == PlanType.operator
        finally:
            await scope.aclose()

    asyncio.run(request())
    assert len(env[0].reads) == 2


@pytest.mark.parametrize('enabled,expected', [(False, 12), (True, 3)])
def test_desktop_serving_config_read_counts_and_platform_isolation(env, monkeypatch, enabled, expected):
    if enabled:
        enable(monkeypatch, 'serving_config_cache')
    store, _ = env
    store.docs['desktop_prompts/a'] = {'active': True, 'question': 'A', 'type': 'banner'}
    store.docs['desktop_prompts/b'] = {'active': True, 'question': 'B', 'type': 'stars'}
    store.docs['desktop_update_policy/current'] = {
        'active': True,
        'maximum_build_number': 100,
        'severity': 'required',
        'platforms': ['macos'],
    }
    for _ in range(4):
        prompts = serving_query_reads.list_active_desktop_prompt_snapshots(firestore_client=store)
        assert len(prompts) == 2
        doc = prompts[0].to_dict()
        doc['question'] = 'mutated'
        policy = desktop_update_policy.get_desktop_update_policy(50, firestore_client=store)
        assert policy['active']
        policy['severity'] = 'none'
    assert len(store.reads) == expected
    assert not desktop_update_policy.get_desktop_update_policy(200, firestore_client=store)['active']
    assert not desktop_update_policy.get_desktop_update_policy(50, 'windows', firestore_client=store)['active']
    assert (
        serving_query_reads.list_active_desktop_prompt_snapshots(firestore_client=store)[0].to_dict()['question'] == 'A'
    )


def test_serving_config_expires_and_does_not_serve_stale_after_error(env, monkeypatch):
    enable(monkeypatch, 'serving_config_cache')
    clock = [0.0]
    monkeypatch.setattr(cache.time, 'monotonic', lambda: clock[0])
    assert cache.serving_config('expiry', lambda: 1) == 1
    clock[0] = 61

    def fail():
        raise RuntimeError('firestore unavailable')

    with pytest.raises(RuntimeError):
        cache.serving_config('expiry', fail)
    assert cache.serving_config('expiry', lambda: 2) == 2


@pytest.mark.parametrize(
    'route,enabled,expected',
    [
        ('trial', False, 6),
        ('trial', True, 2),
        # +1 per request (this case issues two) for the trial-eligibility read of
        # stripe_customer_id; it joins the entitlement projection when request_read_dedupe
        # is on, so the deduped budget below is unchanged.
        ('subscription', False, 14),
        ('subscription', True, 5),
    ],
)
def test_real_users_endpoints_read_count_with_auth(env, monkeypatch, route, enabled, expected):
    store, _ = env
    if enabled:
        enable(monkeypatch, 'request_read_dedupe', 'deletion_marker_cache', 'subscription_cache', 'usage_month_cache')
    monkeypatch.setenv('SUBSCRIPTION_LAUNCH_DATE', '2020-01-01')
    now = datetime.now(timezone.utc)
    for hour in range(2):
        key = f'{now.year}-{now.month:02}-01-{hour:02}'
        store.docs[f'users/u/hourly_usage/{key}'] = {
            'id': key,
            'year': now.year,
            'month': now.month,
            'transcription_seconds': 10,
        }
    monkeypatch.setattr(auth, 'verify_token', lambda token: 'u')
    monkeypatch.setattr(auth, 'record_user_platform', lambda *args: None)
    monkeypatch.setattr(auth, 'record_client_device', lambda *args, **kwargs: None)
    monkeypatch.setattr(auth, 'validate_byok_request', lambda uid: None)
    monkeypatch.setattr(auth, '_recover_locked_content_if_request', lambda *args: None)
    monkeypatch.setattr(auth, '_enforce_cutover_http_if_request', lambda *args: None)
    monkeypatch.setattr(subscription, 'TRIAL_PAYWALL_ENABLED', True)
    monkeypatch.setattr(
        subscription,
        '_get_user',
        lambda uid: SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=(time.time() - 3600) * 1000)),
    )
    monkeypatch.setattr(router, 'is_marketplace_reviewer', lambda uid: False)
    monkeypatch.setattr(router, 'reconcile_basic_plan_with_stripe', lambda uid, sub: sub)
    monkeypatch.setattr(router, 'get_paid_plan_definitions', lambda: [])
    monkeypatch.setattr(router, 'should_hide_subscription_ui', lambda *args: False)
    monkeypatch.setattr(
        router,
        'get_phone_call_quota_snapshot',
        lambda uid: SimpleNamespace(to_client_dict=lambda: {'has_access': True, 'is_paid': False}),
    )
    monkeypatch.setattr(
        router,
        'get_chat_quota_snapshot',
        lambda *args, **kwargs: {
            'limit': 100,
            'used': 0,
            'allowed': True,
            'unit': 'questions',
            'reset_at': None,
        },
    )
    app = FastAPI()
    app.add_api_route('/v1/users/me/trial', router.get_user_trial_status)
    app.add_api_route('/v1/users/me/subscription', router.get_user_subscription_endpoint)
    with TestClient(app) as client:
        for _ in range(2):
            response = client.get(
                f'/v1/users/me/{route}', headers={'Authorization': 'Bearer token', 'X-App-Platform': 'ios'}
            )
            assert response.status_code == 200, response.text
    assert len(store.reads) == expected, store.reads

    if route == 'subscription' and enabled:
        # Simulate a completed payment whose begin AND end invalidations failed.
        assert users.get_user_subscription('u').plan == PlanType.basic  # warm Redis
        store.docs['users/u']['subscription'] = {
            'plan': 'operator',
            'status': 'active',
            'current_period_end': int(time.time()) + 3600,
        }
        # Cached generic reads remain Basic; the actual client unlock route must be fresh.
        assert users.get_user_subscription('u').plan == PlanType.basic
        with TestClient(app) as client:
            response = client.get('/v1/users/me/subscription', headers={'Authorization': 'Bearer token'})
        assert response.status_code == 200, response.text
        assert response.json()['subscription']['plan'] == 'unlimited'  # legacy client wire identity


def test_real_checkout_completion_invalidates_subscription(env, monkeypatch):
    enable(monkeypatch, 'subscription_cache')
    assert users.get_user_valid_subscription('u').plan == PlanType.basic
    updated = Subscription(plan=PlanType.operator, status='active', current_period_end=int(time.time()) + 3600)
    monkeypatch.setattr(payment.stripe.Subscription, 'retrieve', lambda sub_id: SimpleNamespace(to_dict=lambda: {}))
    monkeypatch.setattr(payment, '_build_subscription_from_stripe_object', lambda value: updated)

    class Session(dict):
        id = 'checkout-session'

    assert payment._update_subscription_from_session('u', Session(subscription='sub_1'))
    assert users.get_user_valid_subscription('u').plan == PlanType.operator


def test_failed_writer_end_leaves_persistent_fence(env, monkeypatch):
    enable(monkeypatch, 'subscription_cache')
    real = env[1]

    class EndUnavailable:
        def eval(self, script, *args):
            if script == cache._END:
                raise ConnectionError('end unavailable')
            return real.eval(script, *args)

    monkeypatch.setattr(cache, '_redis', EndUnavailable)
    users.get_user_subscription('u')
    users.update_user_subscription('u', {'plan': 'operator', 'status': 'active'})
    monkeypatch.setattr(cache, '_redis', lambda: real)
    assert users.get_user_subscription('u').plan == PlanType.operator
    assert users.get_user_subscription('u').plan == PlanType.operator
    assert len(env[0].reads) == 3


def test_usage_allowance_exhausts_immediately_after_write(env, monkeypatch):
    enable(monkeypatch, 'usage_month_cache', 'subscription_cache')
    monkeypatch.setenv('SUBSCRIPTION_LAUNCH_DATE', '2020-01-01')
    monkeypatch.setattr(subscription, 'transcription_allowance_seconds', lambda plan: 100)
    assert subscription.resolve_transcription_allowance('u', byok_active=False).remaining_seconds == 100
    user_usage.update_hourly_usage('u', datetime.now(timezone.utc), {'transcription_seconds': 100})
    allowance = subscription.resolve_transcription_allowance('u', byok_active=False)
    assert allowance.remaining_seconds == 0
    assert not allowance.managed


@pytest.mark.parametrize('family', ['subscription_cache', 'deletion_marker_cache', 'usage_month_cache'])
def test_corrupt_cache_falls_back_to_current_firestore(env, monkeypatch, family):
    enable(monkeypatch, family)
    store, redis = env
    now = datetime.now(timezone.utc)
    if family == 'subscription_cache':
        read = lambda: users.get_user_subscription('u').plan
        corrupt = {'plan': 'not-a-plan'}
        expected = PlanType.basic
    elif family == 'deletion_marker_cache':
        read = lambda: deletion.get_user_deletion_wipe_status('u')
        corrupt = 'cancelled'
        expected = None
    else:
        read = lambda: user_usage.get_monthly_usage_stats('u', now)['transcription_seconds']
        corrupt = {'transcription_seconds': 'not-a-number'}
        expected = 0
    assert read() == expected
    key = next(redis.scan_iter(match='*:data:*'))
    payload = json.loads(redis.get(key))
    payload['payload'] = corrupt
    redis.set(key, json.dumps(payload))
    assert read() == expected


@pytest.mark.parametrize('enabled,expected', [(False, 8), (True, 2)])
def test_desktop_prompts_endpoint_config_reads(env, monkeypatch, enabled, expected):
    store, _ = env
    if enabled:
        enable(monkeypatch, 'serving_config_cache')
    monkeypatch.setattr(serving_query_reads, 'get_firestore_client', lambda: store)
    store.docs['desktop_prompts/a'] = {'active': True, 'question': 'A', 'type': 'banner'}
    store.docs['desktop_prompts/b'] = {'active': True, 'question': 'B', 'type': 'stars'}
    for _ in range(4):
        response = desktop_prompts.get_desktop_prompts(uid='u')
        assert [prompt.id for prompt in response.prompts] == ['a', 'b']
    assert len(store.reads) == expected


@pytest.mark.parametrize('enabled,expected', [(False, 4), (True, 1)])
def test_desktop_update_policy_endpoint_config_reads(env, monkeypatch, enabled, expected):
    if enabled:
        enable(monkeypatch, 'serving_config_cache')
    store, _ = env
    monkeypatch.setattr(desktop_update_policy, 'get_firestore_client', lambda: store)
    store.docs['desktop_update_policy/current'] = {'active': True, 'maximum_build_number': 100, 'severity': 'required'}
    for _ in range(4):
        assert updates.get_desktop_update_policy_endpoint(platform='macos', current_build=50)['active']
    assert len(store.reads) == expected


def test_config_rollout_key_does_not_bucket_whole_revision_as_one_instance(monkeypatch):
    for name in ('HOSTNAME', 'K_REVISION', 'INSTANCE_ID', 'GAE_INSTANCE'):
        monkeypatch.delenv(name, raising=False)
    assert cache.serving_config_key() is None
    monkeypatch.setenv('K_REVISION', 'revision-a')
    assert cache.serving_config_key() is None
    monkeypatch.setenv('INSTANCE_ID', 'instance-a')
    assert cache.serving_config_key() == 'revision-a:instance-a'
    monkeypatch.setenv('HOSTNAME', 'pod-a')
    assert cache.serving_config_key() == 'pod-a'


@pytest.mark.parametrize(
    'family,env_name,maximum',
    [
        ('deletion_marker_cache', 'FSR_DELETION_NEGATIVE_TTL_SECONDS', 30),
        ('subscription_cache', 'FSR_SUBSCRIPTION_TTL_SECONDS', 60),
        ('usage_month_cache', 'FSR_USAGE_MONTH_TTL_SECONDS', 60),
    ],
)
@pytest.mark.parametrize('configured', [None, 'invalid', '0', '-50', '1', '999999'])
def test_cache_ttl_hard_bounds(env, monkeypatch, family, env_name, maximum, configured):
    enable(monkeypatch, family)
    monkeypatch.delenv(env_name, raising=False)
    if configured is not None:
        monkeypatch.setenv(env_name, configured)
    expected = 1 if configured in ('0', '-50', '1') else maximum
    assert cache.ttl(env_name, maximum) == expected
    assert cache._generation_ttl(family) == expected * 2
    assert cache.cached_read(family, 'u', 'cap', lambda: 123, seconds=999999) == 123
    remaining = env[1].pttl(cache._root(family, 'u') + ':data:cap')
    assert 0 < remaining <= expected * 1000


@pytest.mark.parametrize(
    'family,maximum',
    [
        ('deletion_marker_cache', 30),
        ('subscription_cache', 60),
        ('usage_month_cache', 60),
    ],
)
def test_both_invalidations_fail_staleness_expires_at_bound(env, monkeypatch, family, maximum):
    enable(monkeypatch, family)
    clock = [time.time()]
    monkeypatch.setattr(time, 'time', lambda: clock[0])
    real = env[1]
    durable = [0]

    def read():
        return cache.cached_read(family, 'u', 'outage', lambda: durable[0])

    assert read() == 0

    class InvalidationsUnavailable:
        def eval(self, script, *args):
            if script in (cache._BEGIN, cache._END):
                raise ConnectionError('invalidation unavailable')
            return real.eval(script, *args)

    monkeypatch.setattr(cache, '_redis', InvalidationsUnavailable)
    with cache.writing(family, 'u'):
        durable[0] = 1
    assert read() == 0  # The protocol is best effort; the TTL is the safety boundary.
    clock[0] += maximum + 0.01
    assert read() == 1


@pytest.mark.parametrize(
    'family,maximum',
    [
        ('deletion_marker_cache', 30),
        ('subscription_cache', 60),
        ('usage_month_cache', 60),
    ],
)
def test_slow_read_does_not_extend_ttl_bound(env, monkeypatch, family, maximum):
    enable(monkeypatch, family)
    clock = [0.0]
    monkeypatch.setattr(cache.time, 'monotonic', lambda: clock[0])

    def slow():
        clock[0] += maximum + 1
        return 123

    assert cache.cached_read(family, 'u', 'slow', slow) == 123
    assert not env[1].exists(cache._root(family, 'u') + ':data:slow')


@pytest.mark.parametrize('subscription_cache', [False, True])
def test_fresh_entitlement_refresh_discards_auth_memo_but_dedupes(env, monkeypatch, subscription_cache):
    enable(monkeypatch, 'request_read_dedupe', *(['subscription_cache'] if subscription_cache else []))

    async def request():
        scope = cache.request_read_scope()
        await anext(scope)
        try:
            assert users.get_user_subscription('u').plan == PlanType.basic
            # A webhook runs in another request and cannot clear this auth memo.
            Context().run(users.update_user_subscription, 'u', {'plan': 'operator', 'status': 'active'})
            assert users.get_user_subscription('u').plan == PlanType.basic
            with cache.fresh_cache_reads('u', 'subscription_cache'):
                assert users.get_user_subscription('u').plan == PlanType.operator
                assert users.get_user_subscription('u').plan == PlanType.operator
        finally:
            await scope.aclose()

    asyncio.run(request())
    assert len(env[0].reads) == 2


@pytest.mark.parametrize('delay', [5, 31])
def test_delayed_publication_cannot_extend_deletion_bound(env, monkeypatch, delay):
    enable(monkeypatch, 'deletion_marker_cache')
    clock = [time.time()]
    monkeypatch.setattr(time, 'time', lambda: clock[0])
    real = env[1]

    class DelayedPublish:
        def eval(self, script, *args):
            if script == cache._PUBLISH:
                clock[0] += delay
            return real.eval(script, *args)

    monkeypatch.setattr(cache, '_redis', DelayedPublish)
    assert deletion.get_user_deletion_wipe_status('u') is None
    key = cache._root('deletion_marker_cache', 'u') + ':data:absent:' + cache.plane_id(env[0])
    if delay > 30:
        assert not real.exists(key)
    else:
        assert 0 < real.pttl(key) <= (30 - delay) * 1000


def test_serving_config_ttl_is_capped(monkeypatch):
    from database import fsr_read_cache as s4_read_cache

    monkeypatch.setenv('FSR_SERVING_CONFIG_TTL_SECONDS', '999999')
    assert s4_read_cache.ttl('FSR_SERVING_CONFIG_TTL_SECONDS', 60) == 300


def test_request_read_scope_teardown_in_another_context():
    # Streaming responses finish yield dependencies in a different Context than the one that set the token.
    async def run():
        scope = cache.request_read_scope()
        await asyncio.create_task(scope.__anext__())
        holder = cache._request.get()
        with pytest.raises(StopAsyncIteration):
            await asyncio.create_task(scope.__anext__())
        return holder

    assert asyncio.run(run()) is None


def test_streaming_route_with_read_scope_returns_200(monkeypatch):
    from fastapi.responses import StreamingResponse

    app = FastAPI()

    @app.get('/stream')
    async def stream(_scope=Depends(cache.request_read_scope)):
        async def body():
            yield b'a'
            yield b'b'

        return StreamingResponse(body())

    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get('/stream')
    assert response.status_code == 200 and response.content == b'ab'

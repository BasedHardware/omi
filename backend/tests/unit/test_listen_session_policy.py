"""E2: preserve pre-snapshot routing and the recorded conversation arm."""

import ast
import asyncio
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.live_stt_registry import registry, routing_on, assigned, Target
from config.live_demand import resolve_live_demand
from config.policy import cohort_bucket
from config.policy.listen import (
    ListenSessionPolicy,
    resolve_listen_policy,
    current_listen_policy,
    window_allocation,
    window_percent,
    routing_mode,
    routing_timeout,
    disruption_gate,
    routing_enabled,
    hintable_allocation,
)
from config.policy.guard import violations, stage_policy_reads
from routers.listen import policy as store
from utils.stt import streaming
from utils.stt.live_rollout import window_selection_kwargs

UIDS = tuple(f'listen-policy-fixture-{index:04d}' for index in range(256)) + ('', 'a', 'uid:with:colon', '用户')
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def clear_pin():
    token = current_listen_policy.set(None)
    yield
    current_listen_policy.reset(token)


@pytest.mark.parametrize('share', [0, 0.1, 1, 5, 25, 50, 99.9, 100])
def test_exact_deployed_64_bit_membership(share):
    # Independent literal oracle from main 77d05f247590. Do not re-salt or
    # truncate to E1's original 32 bits. Fractional boundaries catch that drift.
    for uid in UIDS:
        bucket = int.from_bytes(hashlib.sha256(('parakeet-window:' + uid).encode()).digest()[:8], 'big') / 2**64 * 100
        assert cohort_bucket(uid, 'parakeet-window', bits=64) == bucket
        policy = resolve_listen_policy(uid, flags={'PARAKEET_WINDOW_ALLOCATION_PERCENT': str(share)})
        assert policy.window_allocated == (bool(uid) and bucket < share)
        assert assigned(uid, 'parakeet-window', share) == policy.window_allocated


@pytest.mark.parametrize('mode', ['off', 'shadow', 'on', 'ON', ' on ', 'invalid'])
@pytest.mark.parametrize('percent', ['0', '25', '100'])
def test_resolver_equals_unpinned_getters(monkeypatch, mode, percent):
    flags = {
        'STT_ROUTING_MODE': mode,
        'STT_ROUTING_ON_PERCENT': percent,
        'PARAKEET_WINDOW_ALLOCATION_PERCENT': percent,
        'STT_ROUTING_REDIS_TIMEOUT_SECONDS': '0.04',
        'STT_ROUTING_DISRUPTION_GATE': '0.09',
        'STT_FAILOVER_RECOVERY_ENABLED': 'true',
        'STT_SHED_CONNECT_FAILURES': '5',
        'STT_CIRCUIT_HALF_OPEN_PROBES': '2',
        'STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS': '70',
        'STT_NO_TEXT_SECONDS': '12',
        'STT_NO_TEXT_RESCUE_ENABLED': 'true',
        'STT_NO_TEXT_RESCUE_SECONDS': '100',
        'STT_SERVICE_MODELS': 'parakeet-window,modulate-velma-2,soniox',
        'STT_LEARNED_LANGUAGE_PROFILE': 'true',
        'STT_MULTI_LANGUAGE_HINTS': 'false',
        'STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT': percent,
        'STT_LIVE_DEMAND_ENABLED': 'true',
        'STT_LIVE_DEMAND_PERCENT': percent,
        'STT_LIVE_DEMAND_MIN_DWELL_SECONDS': '20',
    }
    for key, value in flags.items():
        monkeypatch.setenv(key, value)
    uid = UIDS[42]
    policy = resolve_listen_policy(uid, flags=flags)
    assert policy.routing_on == routing_on(uid)
    assert policy.window_allocated == window_allocation(uid)
    assert policy.window_allocation_percent == window_percent(strict=True)
    assert policy.routing_mode == routing_mode()
    assert policy.targets == registry()
    assert policy.routing_redis_timeout_seconds == routing_timeout()
    assert policy.routing_disruption_gate == disruption_gate()
    assert policy.demand_admitted == resolve_live_demand(flags=flags).admits(uid, explicit=True)
    assert policy.service_models == tuple(flags['STT_SERVICE_MODELS'].split(','))
    assert policy.failover_recovery_enabled and policy.no_text_rescue_enabled
    assert (policy.shed_connect_failures, policy.circuit_half_open_probes) == (5, 2)
    assert (policy.account_circuit_cooldown_seconds, policy.no_text_seconds, policy.no_text_rescue_seconds) == (
        70,
        12,
        100,
    )
    assert policy.learned_language_profile and not policy.multi_language_hints


@pytest.mark.parametrize('raw', ['-1', '101', 'nan', 'inf', 'bad'])
def test_invalid_window_keeps_legacy_clamp_and_strict_permission(monkeypatch, raw):
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', raw)
    if raw == 'bad':
        with pytest.raises(ValueError):
            window_allocation('owner')
    else:
        expected = window_allocation('owner')
    policy = resolve_listen_policy('owner', flags={'PARAKEET_WINDOW_ALLOCATION_PERCENT': raw})
    current_listen_policy.set(policy)
    with pytest.raises(ValueError):
        window_percent(strict=True)
    if raw == 'bad':
        with pytest.raises(ValueError):
            window_allocation('owner')
    else:
        assert window_allocation('owner') == expected


def test_roundtrip_immutability_hash_and_secret_exclusion():
    policy = resolve_listen_policy('owner', flags={'STT_ROUTING_MODE': 'on', 'STT_ROUTING_ON_PERCENT': '100'})
    raw = json.loads(json.dumps(policy.to_dict()))
    assert ListenSessionPolicy.from_dict(raw) == policy
    assert ListenSessionPolicy.from_dict({**raw, 'future_key': 'ignored'}) == policy
    with pytest.raises(FrozenInstanceError):
        policy.routing_on = False
    assert replace(policy, routing_on=False).policy_id != policy.policy_id
    with pytest.raises(ValueError, match='hash'):
        ListenSessionPolicy.from_dict({**raw, 'routing_on': False})
    assert resolve_listen_policy('owner', flags={'MODULATE_API_KEY': 'never-record-this'}) == resolve_listen_policy(
        'owner', flags={}
    )


def test_env_flip_retains_arm_static_targets_and_ramps(monkeypatch):
    initial = {'STT_ROUTING_MODE': 'on', 'STT_ROUTING_ON_PERCENT': '100', 'PARAKEET_WINDOW_ALLOCATION_PERCENT': '100'}
    policy = resolve_listen_policy('owner', flags=initial)
    current_listen_policy.set(policy)
    for key in initial:
        monkeypatch.setenv(key, 'off' if key.endswith('MODE') else '0')
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', '[]')
    assert routing_on('owner') and window_allocation('owner')
    assert Target('parakeet-window', 'parakeet', 0.02).ramp() == 100
    assert registry() is policy.targets  # no repeated parse
    assert policy.routing_arm == 'on'


@pytest.mark.parametrize('uid', [None, ''])
def test_missing_uid_rejected_before_pinned_cohort(uid):
    current_listen_policy.set(
        resolve_listen_policy(
            'owner',
            flags={
                'STT_ROUTING_MODE': 'on',
                'STT_ROUTING_ON_PERCENT': '100',
                'PARAKEET_WINDOW_ALLOCATION_PERCENT': '100',
                'STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT': '100',
            },
        )
    )
    assert not window_allocation(uid)
    assert not routing_enabled(uid)
    assert not hintable_allocation(uid)


@pytest.mark.parametrize('session_kind', ['multi-channel', 'byok'])
def test_pinned_window_arm_cannot_select_window_for_nonmanaged_session(monkeypatch, session_kind):
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.invalid')
    monkeypatch.setenv('MODULATE_API_KEY', 'test')
    monkeypatch.setattr('utils.byok.get_byok_keys', lambda: {'modulate': 'test'} if session_kind == 'byok' else {})
    policy = resolve_listen_policy(
        'owner', flags={'PARAKEET_WINDOW_ALLOCATION_PERCENT': '100'}, models=['parakeet-window', 'modulate-velma-2']
    )
    current_listen_policy.set(policy)
    assert policy.window_allocated
    host = SimpleNamespace(is_multi_channel=session_kind == 'multi-channel', use_custom_stt=False)
    selection = window_selection_kwargs(host, 'owner')
    assert selection == {}  # This surface deliberately omits window_uid.
    assert not window_allocation(None)
    assert streaming.get_stt_service_for_language('en', multi_lang_enabled=False, **selection) == (
        streaming.STTService.modulate,
        'en',
        'velma-2',
    )


class Redis:
    def __init__(self):
        self.data = {}
        self.ttls = {}
        self.calls = []

    async def get(self, key):
        self.calls.append('get')
        return self.data.get(key)

    async def expire(self, key, ttl):
        self.calls.append('expire')
        self.ttls[key] = ttl

    async def set(self, key, payload, *, nx, ex):
        self.calls.append('set')
        if nx and key in self.data:
            return False
        self.data[key] = payload
        self.ttls[key] = ex
        return True


@pytest.mark.asyncio
async def test_restart_reconnect_loads_without_resolving(monkeypatch):
    redis = Redis()
    original = resolve_listen_policy('owner', flags={'STT_ROUTING_MODE': 'on', 'STT_ROUTING_ON_PERCENT': '100'})
    resolver = Mock(return_value=original)
    first, source = await store.load_listen_policy('owner', 'conversation', resolver=resolver, redis_client=redis)
    assert source == 'resolved'
    resolver.assert_called_once()
    resolver.reset_mock(side_effect=True)
    resolver.side_effect = AssertionError('restart must load, never resolve')
    current_listen_policy.set(None)  # fresh pod / process
    monkeypatch.setenv('STT_ROUTING_MODE', 'off')
    second, source = await store.load_listen_policy('owner', 'conversation', resolver=resolver, redis_client=redis)
    assert source == 'redis' and second == first and second.routing_on
    resolver.assert_not_called()
    assert redis.ttls[store.policy_key('owner', 'conversation')] == store.POLICY_TTL_SECONDS >= 4 * 3600
    assert store.policy_key('another-owner', 'conversation') != store.policy_key('owner', 'conversation')


@pytest.mark.asyncio
async def test_healthy_first_write_is_not_fallback(monkeypatch, caplog):
    from utils.metrics import OMI_FALLBACK_TOTAL

    def fallback_count():
        return sum(
            sample.value
            for family in OMI_FALLBACK_TOTAL.collect()
            for sample in family.samples
            if sample.name == 'omi_fallback_total'
        )

    before = fallback_count()
    policy, source = await store.load_listen_policy(
        'owner', 'new-session', resolver=lambda: resolve_listen_policy('owner', flags={}), redis_client=Redis()
    )
    with caplog.at_level('INFO'):
        store.record_source(source, policy)
    assert source == 'resolved'
    assert fallback_count() == before
    assert not any('component=stt_live_session' in record.message for record in caplog.records)
    assert any('policy_source=resolved' in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_policy_storage_reuses_shared_async_client_without_closing_it(monkeypatch):
    from database import redis_db

    redis = Redis()
    redis.aclose = AsyncMock()
    shared = AsyncMock(return_value=redis)
    monkeypatch.setattr(redis_db, 'get_async_redis_client', shared)
    first, source = await store.load_listen_policy(
        'owner', 'session', resolver=lambda: resolve_listen_policy('owner', flags={})
    )
    assert source == 'resolved'
    second, source = await store.load_listen_policy('owner', 'session', resolver=Mock(side_effect=AssertionError))
    assert source == 'redis' and second == first
    assert shared.await_count == 2
    redis.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_first_writer_wins():
    redis = Redis()
    winner = resolve_listen_policy('owner', flags={'STT_ROUTING_MODE': 'on', 'STT_ROUTING_ON_PERCENT': '100'})
    loser = resolve_listen_policy('owner', flags={})

    async def raced_set(key, payload, *, nx, ex):
        redis.data[key] = json.dumps(winner.to_dict())
        return False

    redis.set = raced_set
    result, source = await store.load_listen_policy('owner', 'conversation', resolver=lambda: loser, redis_client=redis)
    assert source == 'redis' and result == winner


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['get', 'set', 'timeout', 'pool', 'invalid'])
async def test_redis_fail_open_is_bounded_and_records_fallback(monkeypatch, caplog, failure):
    redis = Redis()

    async def broken(*args, **kwargs):
        raise ConnectionError('do not expose Redis details')

    async def slow(*args, **kwargs):
        await asyncio.Event().wait()

    if failure in {'get', 'set'}:
        setattr(redis, failure, broken)
    elif failure in {'timeout', 'pool'}:
        if failure == 'pool':
            from database import redis_db

            monkeypatch.setattr(redis_db, 'get_async_redis_client', slow)
        else:
            redis.get = slow
        monkeypatch.setattr(store, 'REDIS_TIMEOUT_SECONDS', 0.01)
    else:
        redis.data[store.policy_key('owner', 'conversation')] = 'broken'
    policy = resolve_listen_policy('owner', flags={})
    resolver = Mock(return_value=policy)
    result, source = await asyncio.wait_for(
        store.load_listen_policy(
            'owner', 'conversation', resolver=resolver, redis_client=None if failure == 'pool' else redis
        ),
        timeout=0.2,
    )
    resolver.assert_called_once()
    before = store._source_counter().labels(policy_source='fallback')._value.get()
    with caplog.at_level('INFO'):
        store.record_source(source, result)
    assert source == 'fallback' and result == policy
    assert store._source_counter().labels(policy_source='fallback')._value.get() == before + 1
    lines = [r.message for r in caplog.records if 'event=listen_session_policy ' in r.message]
    assert len(lines) == 1 and 'policy_source=fallback' in lines[0] and policy.policy_id in lines[0]
    assert 'owner' not in lines[0] and 'conversation' not in lines[0] and 'Redis details' not in lines[0]


@pytest.mark.asyncio
async def test_rollback_preserves_legacy_keys():
    redis = Redis()
    old_key = 'users:owner:in_progress_memory_id'
    redis.data[old_key] = b'conversation'
    await store.load_listen_policy(
        'owner', 'conversation', resolver=lambda: resolve_listen_policy('owner', flags={}), redis_client=redis
    )
    # Exact old-reader expression from redis_db.get_in_progress_conversation_id.
    assert (await redis.get(old_key)).decode() == 'conversation'
    assert set(redis.data) == {old_key, store.policy_key('owner', 'conversation')}


def test_boundary_rejects_alias_reads_and_mid_session_resolution(tmp_path):
    backend = tmp_path / 'backend' / 'utils'
    backend.mkdir(parents=True)
    (backend / 'bad.py').write_text(
        "import os as o\ne = o.environ\nv = e.get('STT_ROUTING_NEW_KNOB')\nw = o.getenv('PARAKEET_WINDOW_ALLOCATION_PERCENT')\n"
    )
    errors = violations(tmp_path)
    assert any('STT_ROUTING_NEW_KNOB' in error for error in errors)
    assert any('PARAKEET_WINDOW_ALLOCATION_PERCENT' in error for error in errors)
    assert stage_policy_reads(
        'from config.policy import resolve_listen_policy\ndef frame():\n resolve_listen_policy("u")', 'utils/frame.py'
    )


def test_no_policy_io_or_resolver_added_to_frames():
    receiver = ast.parse((ROOT / 'backend/routers/listen/receiver.py').read_text())
    names = {
        node.func.id for node in ast.walk(receiver) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not names & {
        'resolve_listen_policy',
        'load_listen_policy',
        'initialize_session_policy',
        'persist_conversation_policy',
    }


def test_64_bit_bucket_boundary_cannot_be_truncated_to_32():
    uid = UIDS[42]
    digest = hashlib.sha256(('parakeet-window:' + uid).encode()).digest()
    short = int.from_bytes(digest[:4], 'big') / 2**32 * 100
    full = int.from_bytes(digest[:8], 'big') / 2**64 * 100
    boundary = (short + full) / 2
    assert short < boundary < full
    assert not resolve_listen_policy(uid, flags={'PARAKEET_WINDOW_ALLOCATION_PERCENT': str(boundary)}).window_allocated


@pytest.mark.asyncio
async def test_ttl_refresh_failure_does_not_discard_loaded_arm():
    redis = Redis()
    saved = resolve_listen_policy('owner', flags={'STT_ROUTING_MODE': 'on', 'STT_ROUTING_ON_PERCENT': '100'})
    redis.data[store.policy_key('owner', 'conversation')] = json.dumps(saved.to_dict())

    async def expire_failed(*args):
        raise ConnectionError('failed refresh')

    redis.expire = expire_failed
    resolve = Mock(side_effect=AssertionError('must retain usable saved policy'))
    result, source = await store.load_listen_policy('owner', 'conversation', resolver=resolve, redis_client=redis)
    assert source == 'redis' and result == saved
    resolve.assert_not_called()


@pytest.mark.parametrize(
    'key',
    [
        'STT_CIRCUIT_HALF_OPEN_PROBES',
        'STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS',
        'STT_NO_TEXT_SECONDS',
        'STT_ROUTING_DISRUPTION_GATE',
    ],
)
def test_unused_malformed_knobs_do_not_block_admission(key):
    policy = resolve_listen_policy('owner', flags={key: 'bad'})
    assert not policy.routing_on and policy.invalid_fields
    current_listen_policy.set(policy)
    if key == 'STT_ROUTING_DISRUPTION_GATE':
        with pytest.raises(ValueError):
            disruption_gate()


@pytest.mark.parametrize('flags', [{'STT_LIVE_DEMAND_PERCENT': 'invalid'}, {'STT_LIVE_DEMAND_MIN_DWELL_SECONDS': '-1'}])
def test_invalid_demand_defaults_keep_restart_content_hash(flags):
    policy = resolve_listen_policy('owner', flags=flags)
    assert ListenSessionPolicy.from_dict(json.loads(json.dumps(policy.to_dict()))) == policy


def test_default_policy_is_exactly_the_current_defaults():
    assert resolve_listen_policy('owner', flags={}) == ListenSessionPolicy()


@pytest.mark.parametrize('raw', ['bad', '-1', '0.02', '5', 'nan'])
def test_redis_timeout_getter_matrix(monkeypatch, raw):
    monkeypatch.setenv('STT_ROUTING_REDIS_TIMEOUT_SECONDS', raw)
    try:
        expected = min(0.1, max(0.01, float(raw)))
    except ValueError:
        expected = 0.075
    policy = resolve_listen_policy('owner', flags={'STT_ROUTING_REDIS_TIMEOUT_SECONDS': raw})
    assert policy.routing_redis_timeout_seconds == routing_timeout() == expected


@pytest.mark.parametrize('raw', ['bad', 'nan', '0', '1', '0.08'])
def test_disruption_gate_preserves_legacy_validation(monkeypatch, raw):
    monkeypatch.setenv('STT_ROUTING_DISRUPTION_GATE', raw)
    policy = resolve_listen_policy('owner', flags={'STT_ROUTING_DISRUPTION_GATE': raw})
    current_listen_policy.set(policy)
    if raw == '0.08':
        assert disruption_gate() == 0.08
    else:
        with pytest.raises(ValueError):
            disruption_gate()


@pytest.mark.parametrize(
    'raw,enabled', [('true', True), ('false', False), ('0', False), ('off', False), (' FALSE ', False), ('other', True)]
)
def test_new_main_ops_kill_remains_live_and_keeps_semantics(monkeypatch, raw, enabled):
    from config.policy import kill_switch

    policy = resolve_listen_policy('owner', flags={})
    current_listen_policy.set(policy)
    name = 'PARAKEET_WINDOW_STRANDED_DRIFT_SETTLE_ENABLED'
    monkeypatch.setenv(name, raw)
    assert kill_switch(name, policy_id=policy.policy_id) is enabled


def test_paid_spillover_settings_stay_recorded_after_flip(monkeypatch):
    from utils.stt import paid_admission

    flags = {'STT_PAID_SPILLOVER_BUDGET_ENABLED': 'true', 'STT_PAID_SPILLOVER_SONIOX_PER_MINUTE': '17'}
    policy = resolve_listen_policy('owner', flags=flags)
    current_listen_policy.set(policy)
    monkeypatch.setenv('STT_PAID_SPILLOVER_BUDGET_ENABLED', 'false')
    monkeypatch.setenv('STT_PAID_SPILLOVER_SONIOX_PER_MINUTE', '0')
    assert paid_admission.enabled() and paid_admission.limit('soniox') == 17


def test_invalid_spillover_cap_only_affects_its_provider():
    from utils.stt import paid_admission

    policy = resolve_listen_policy('owner', flags={'STT_PAID_SPILLOVER_SONIOX_PER_MINUTE': 'bad'})
    current_listen_policy.set(policy)
    assert paid_admission.limit('deepgram') == 30
    with pytest.raises(ValueError):
        paid_admission.limit('soniox')


def test_fallback_liveness_grace_is_pinned_but_nonlisten_getter_stays_process_owned():
    from config.policy.listen import fallback_liveness_grace

    assert fallback_liveness_grace(0.7) == 0.7
    policy = resolve_listen_policy('owner', flags={'STT_FALLBACK_LIVENESS_GRACE_SECONDS': '0.2'})
    current_listen_policy.set(policy)
    assert fallback_liveness_grace(0.7) == 0.2


@pytest.mark.asyncio
async def test_restart_does_not_reinterpret_registry_code_defaults(monkeypatch):
    import config.live_stt_registry as registry_module

    redis = Redis()
    original = resolve_listen_policy('owner', flags={})
    assert original.routing_targets_json
    first, _ = await store.load_listen_policy('owner', 'conversation', resolver=lambda: original, redis_client=redis)
    monkeypatch.setattr(registry_module, 'DEFAULT_TARGETS', (Target('soniox', 'soniox', 99.0, ramp_percent=0),))
    resolve = Mock(side_effect=AssertionError('saved resolved targets must survive code defaults changing'))
    loaded, source = await store.load_listen_policy('owner', 'conversation', resolver=resolve, redis_client=redis)
    assert source == 'redis'
    assert loaded.policy_id == first.policy_id
    assert loaded.targets == first.targets
    resolve.assert_not_called()

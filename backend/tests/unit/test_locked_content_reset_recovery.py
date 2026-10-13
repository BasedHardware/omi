"""Reset recovery orchestration against deterministic persistence/provider doubles."""

from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


class Redis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def release(self, *, keys, args):
        if self.values.get(keys[0]) == args[0]:
            self.values.pop(keys[0])

    def next_request(self):
        for key in list(self.values):
            if key.endswith(':retry'):
                self.values.pop(key)


@pytest.fixture
def env(monkeypatch):
    redis = Redis()
    state_data = {}
    state = MagicMock()
    state.get.side_effect = lambda: SimpleNamespace(to_dict=lambda: dict(state_data))
    state.set.side_effect = lambda value: state_data.update(value)
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value.document.return_value = state
    locks = {'memories': 0, 'actions': 0, 'conversations': 0}
    calls = []

    def unlock(kind):
        def run(uid, *, limit):
            assert uid == 'test-user'
            calls.append(kind)
            count = min(locks[kind], limit)
            locks[kind] -= count
            return count

        return run

    allowance = MagicMock(return_value=SimpleNamespace(managed=True, reason='plan_within_allowance'))
    signal = MagicMock()
    cache = MagicMock()
    fakes = {}
    for name in [
        'database.memories',
        'database.action_items',
        'database.conversations',
        'database.redis_db',
        'database._client',
        'utils.subscription',
        'utils.observability.fallback',
    ]:
        fakes[name] = ModuleType(name)
    fakes['database.memories'].unlock_all_memories = unlock('memories')
    fakes['database.action_items'].unlock_all_action_items = unlock('actions')
    fakes['database.conversations'].unlock_all_conversations = unlock('conversations')
    fakes['database.redis_db'].r = redis
    fakes['database.redis_db']._RELEASE_NOTIFICATIONS_JOB_RUN_LOCK_LUA = redis.release
    fakes['database.redis_db'].set_credits_invalidation_signal = signal
    fakes['database._client'].db = db
    fakes['utils.subscription'].resolve_transcription_allowance = allowance
    fakes['utils.subscription'].clear_trial_paywall_cache = cache
    fakes['utils.observability.fallback'].record_fallback = MagicMock()
    monkeypatch.setenv('LOCKED_CONTENT_RESET_RECOVERY_ENABLED', 'true')
    with stub_modules(fakes):
        module = load_module_fresh(
            'utils.locked_content_recovery', Path(__file__).resolve().parents[2] / 'utils/locked_content_recovery.py'
        )
        yield SimpleNamespace(
            module=module,
            redis=redis,
            state=state,
            state_data=state_data,
            locks=locks,
            calls=calls,
            allowance=allowance,
            signal=signal,
            cache=cache,
            fakes=fakes,
        )


def test_dark_default_does_no_persistence_work(env, monkeypatch):
    monkeypatch.delenv('LOCKED_CONTENT_RESET_RECOVERY_ENABLED')
    env.module.recover_locked_content('test-user', now=NOW)
    env.state.get.assert_not_called()
    assert env.redis.values == {} and env.calls == []


def test_idempotent_same_period_and_next_reset(env):
    env.locks.update(memories=2, actions=3, conversations=4)
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.locks == dict(memories=0, actions=0, conversations=0)
    assert env.state_data['completed_period'] == '2026-11'
    assert env.calls == ['memories', 'actions', 'conversations']
    env.signal.assert_called_once_with('test-user')
    env.cache.assert_called_once_with('test-user')
    # Content locked later in this period is held until its next reset.
    env.locks['conversations'] = 1
    env.redis.next_request()
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.locks['conversations'] == 1
    env.module.recover_locked_content('test-user', now=datetime(2026, 12, 1, tzinfo=timezone.utc))
    assert env.locks['conversations'] == 0


def test_redis_eviction_uses_durable_period_marker(env):
    env.state_data['completed_period'] = '2026-11'
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.calls == []
    env.allowance.assert_not_called()


def test_bounded_pass_resumes_until_empty_tail(env):
    env.locks.update(memories=201, actions=150, conversations=99)
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.locks == dict(memories=101, actions=50, conversations=0)
    assert not env.state_data
    for _ in range(2):
        env.redis.next_request()
        env.module.recover_locked_content('test-user', now=NOW)
    assert not any(env.locks.values())
    assert env.state_data['completed_period'] == '2026-11'


def test_partial_child_failure_resumes_without_repeating_committed_writes(env):
    env.locks.update(memories=5, actions=5, conversations=5)
    original = env.fakes['database.action_items'].unlock_all_action_items
    env.fakes['database.action_items'].unlock_all_action_items = MagicMock(side_effect=RuntimeError('simulated'))
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.locks == dict(memories=0, actions=5, conversations=5)
    assert not env.state_data
    assert not any(k.endswith(':lease') for k in env.redis.values)
    env.fakes['database.action_items'].unlock_all_action_items = original
    env.redis.next_request()
    env.module.recover_locked_content('test-user', now=NOW)
    assert not any(env.locks.values())
    assert env.state_data['completed_period'] == '2026-11'


def test_invalidation_failure_is_repaired_before_completion(env):
    env.locks['conversations'] = 3
    env.cache.side_effect = RuntimeError('simulated')
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.locks['conversations'] == 0 and not env.state_data
    env.cache.side_effect = None
    env.redis.next_request()
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.state_data['completed_period'] == '2026-11'
    assert env.cache.call_count == 2


@pytest.mark.parametrize(
    'reason',
    [
        'plan_allowance_exhausted',
        'usage_invalid',
        'allowance_unavailable',
        'subscription_inactive',
        'byok',
        'marketplace_reviewer',
    ],
)
def test_exhausted_or_untrusted_or_override_stays_locked(env, reason):
    env.locks.update(memories=3, actions=3, conversations=3)
    env.allowance.return_value = SimpleNamespace(managed=reason in {'byok', 'marketplace_reviewer'}, reason=reason)
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.calls == [] and not env.state_data
    assert all(value == 3 for value in env.locks.values())


def test_allowance_rechecked_between_collections(env):
    env.locks.update(memories=3, actions=3, conversations=3)
    env.allowance.side_effect = [
        SimpleNamespace(managed=True, reason='plan_within_allowance'),
        SimpleNamespace(managed=False, reason='plan_allowance_exhausted'),
    ]
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.locks == dict(memories=0, actions=3, conversations=3)
    assert not env.state_data


def test_lease_contention_does_not_run(env):
    env.redis.values['users:test-user:locked_content_reset:lease'] = 'other-owner'
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.calls == []
    assert env.redis.values['users:test-user:locked_content_reset:lease'] == 'other-owner'


def test_requests_throttled_before_usage_read(env):
    env.allowance.return_value = SimpleNamespace(managed=False, reason='plan_allowance_exhausted')
    env.module.recover_locked_content('test-user', now=NOW)
    env.module.recover_locked_content('test-user', now=NOW)
    assert env.allowance.call_count == 1

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

import desktop_backend
import main
from routers import jit_ledger_snapshot, jit_rollout
from utils.memory.jit_trigger_contract import TriggerAction
from utils.memory.jit_trigger_contract import DEFAULT_TRIGGER_RUNTIME_POLICY
from utils.memory.jit_trigger_snapshot import AuthoritativeTriggerRow, AuthoritativeTriggerSnapshot
from utils import jit_rollout as authority_module
from utils.jit_rollout import (
    JIT_LEDGER_MIGRATION_FLAG_KEY,
    JITDecisionReason,
    JITDecisionStage,
    JITErrorClass,
    JITFlagEvaluation,
    JITRolloutAuthority,
    PostHogJITFlagProvider,
    TriState,
    UNKNOWN_JIT_ROLLOUT_CACHE_SECONDS,
)
from utils.executors import run_blocking, sync_executor
from utils.other.endpoints import get_current_user_uid
from models.jit_trigger_feedback import JITTriggerFeedbackReceipt
from models.jit_proactivity import JITProactivityEventReceipt
from models.product_memory import MemoryItemStatus
from database.read_boundary import MalformedDocError


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('rollout', 'kill_switch', 'expected', 'reason'),
    [
        (TriState.ENABLED, TriState.DISABLED, TriState.ENABLED, JITDecisionReason.ROLLOUT_ENABLED),
        (TriState.DISABLED, TriState.DISABLED, TriState.DISABLED, JITDecisionReason.ROLLOUT_DISABLED),
        (TriState.ENABLED, TriState.ENABLED, TriState.DISABLED, JITDecisionReason.KILL_SWITCH_ENABLED),
        (TriState.UNKNOWN, TriState.DISABLED, TriState.UNKNOWN, JITDecisionReason.FLAG_ABSENT),
        (TriState.ENABLED, TriState.UNKNOWN, TriState.UNKNOWN, JITDecisionReason.FLAG_ABSENT),
    ],
)
async def test_authority_requires_known_rollout_true_and_known_kill_false(
    rollout,
    kill_switch,
    expected,
    reason,
):
    async def provider(uid: str) -> JITFlagEvaluation:
        assert uid == 'named-user'
        return JITFlagEvaluation(rollout, kill_switch, JITDecisionReason.FLAG_ABSENT)

    decision = await JITRolloutAuthority(provider).resolve(
        'named-user',
        stage=JITDecisionStage.INGRESS,
    )

    assert decision.effective == expected
    assert decision.reason == reason
    assert decision.permits_work is (expected == TriState.ENABLED)


@pytest.mark.asyncio
async def test_cache_expires_within_thirty_seconds_and_is_owner_isolated():
    clock = _Clock()
    calls: list[str] = []

    async def provider(uid: str) -> JITFlagEvaluation:
        calls.append(uid)
        enabled = uid == 'enabled-user'
        return JITFlagEvaluation(
            TriState.ENABLED if enabled else TriState.DISABLED,
            TriState.DISABLED,
            JITDecisionReason.EVALUATED,
        )

    authority = JITRolloutAuthority(provider, ttl_seconds=30, max_entries=2, monotonic=clock)
    first = await authority.resolve('enabled-user', stage=JITDecisionStage.READ_ONLY)
    cached = await authority.resolve('enabled-user', stage=JITDecisionStage.INGRESS)
    other = await authority.resolve('disabled-user', stage=JITDecisionStage.READ_ONLY)
    clock.now += 30.0
    expired = await authority.resolve('enabled-user', stage=JITDecisionStage.READ_ONLY)

    assert first.cache_hit is False
    assert cached.cache_hit is True
    assert other.effective == TriState.DISABLED
    assert expired.cache_hit is False
    assert calls == ['enabled-user', 'disabled-user', 'enabled-user']

    with pytest.raises(ValueError, match='ttl_seconds'):
        JITRolloutAuthority(provider, ttl_seconds=30.01)


@pytest.mark.asyncio
async def test_unknown_provider_results_use_short_negative_cache():
    """UNKNOWN caches briefly (fleet-scale cost bound) but never for the full TTL.

    A fleet whose flags are simply absent must not pay one uncached provider
    call per request, so unknown snapshots are held for a short negative TTL.
    They can never authorize work, and a provider recovery is observed as soon
    as the negative entry expires — well before the positive TTL.
    """

    calls = 0
    clock = {'now': 0.0}

    async def provider(_: str) -> JITFlagEvaluation:
        nonlocal calls
        calls += 1
        return JITFlagEvaluation(
            TriState.UNKNOWN,
            TriState.UNKNOWN,
            JITDecisionReason.PROVIDER_ERROR,
            JITErrorClass.PROVIDER,
        )

    authority = JITRolloutAuthority(provider, monotonic=lambda: clock['now'])
    first = await authority.resolve('user-1', stage=JITDecisionStage.INGRESS)
    second = await authority.resolve('user-1', stage=JITDecisionStage.INGRESS)
    assert calls == 1, 'a fresh unknown snapshot must be served from the negative cache'
    assert not first.permits_work and not second.permits_work

    clock['now'] = UNKNOWN_JIT_ROLLOUT_CACHE_SECONDS + 0.1
    await authority.resolve('user-1', stage=JITDecisionStage.INGRESS)
    assert calls == 2, 'the negative entry must expire long before the positive TTL'


@pytest.mark.asyncio
async def test_cache_has_a_hard_entry_cap():
    calls: list[str] = []

    async def provider(uid: str) -> JITFlagEvaluation:
        calls.append(uid)
        return JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)

    authority = JITRolloutAuthority(provider, max_entries=1)
    await authority.resolve('user-1', stage=JITDecisionStage.READ_ONLY)
    await authority.resolve('user-2', stage=JITDecisionStage.READ_ONLY)
    evicted = await authority.resolve('user-1', stage=JITDecisionStage.READ_ONLY)

    assert evicted.cache_hit is False
    assert calls == ['user-1', 'user-2', 'user-1']


class _FakePostHog:
    def __init__(self, flags):
        self.flags = flags
        self.uids: list[str] = []

    def get_feature_variants(self, uid: str):
        self.uids.append(uid)
        if isinstance(self.flags, BaseException):
            raise self.flags
        return self.flags


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('flags', 'rollout', 'kill_switch', 'reason', 'error_class'),
    [
        (
            {'jit-processing-v1': True, 'jit-processing-kill-switch-v1': False},
            TriState.ENABLED,
            TriState.DISABLED,
            JITDecisionReason.EVALUATED,
            JITErrorClass.NONE,
        ),
        (
            {'jit-processing-v1': False, 'jit-processing-kill-switch-v1': True},
            TriState.DISABLED,
            TriState.ENABLED,
            JITDecisionReason.EVALUATED,
            JITErrorClass.NONE,
        ),
        (
            {'jit-processing-v1': True},
            TriState.ENABLED,
            TriState.UNKNOWN,
            JITDecisionReason.FLAG_ABSENT,
            JITErrorClass.ABSENT,
        ),
        (
            {'jit-processing-v1': 'enabled', 'jit-processing-kill-switch-v1': False},
            TriState.UNKNOWN,
            TriState.DISABLED,
            JITDecisionReason.MALFORMED_RESPONSE,
            JITErrorClass.MALFORMED,
        ),
    ],
)
async def test_posthog_provider_parses_only_exact_boolean_flags(
    flags,
    rollout,
    kill_switch,
    reason,
    error_class,
):
    client = _FakePostHog(flags)
    provider = PostHogJITFlagProvider(client_factory=lambda: client)

    result = await provider('authenticated-user')

    assert client.uids == ['authenticated-user']
    assert result == JITFlagEvaluation(rollout, kill_switch, reason, error_class)


@pytest.mark.asyncio
async def test_general_jit_rollout_does_not_authorize_ledger_migration():
    client = _FakePostHog(
        {
            'jit-processing-v1': True,
            JIT_LEDGER_MIGRATION_FLAG_KEY: False,
            'jit-processing-kill-switch-v1': False,
        }
    )
    provider = PostHogJITFlagProvider(
        client_factory=lambda: client,
        rollout_flag_key=JIT_LEDGER_MIGRATION_FLAG_KEY,
    )

    result = await provider('qa-owner')

    assert result.rollout == TriState.DISABLED
    assert result.kill_switch == TriState.DISABLED
    assert result.reason == JITDecisionReason.EVALUATED


@pytest.mark.asyncio
async def test_absent_ledger_migration_flag_fails_off_even_when_general_rollout_is_enabled():
    provider = PostHogJITFlagProvider(
        client_factory=lambda: _FakePostHog(
            {
                'jit-processing-v1': True,
                'jit-processing-kill-switch-v1': False,
            }
        ),
        rollout_flag_key=JIT_LEDGER_MIGRATION_FLAG_KEY,
    )

    result = await provider('qa-owner')

    assert result.rollout == TriState.UNKNOWN
    assert result.kill_switch == TriState.DISABLED
    assert result.reason == JITDecisionReason.FLAG_ABSENT
    assert result.error_class == JITErrorClass.ABSENT


@pytest.mark.asyncio
async def test_posthog_provider_errors_and_timeouts_are_unknown(monkeypatch):
    error_provider = PostHogJITFlagProvider(client_factory=lambda: _FakePostHog(RuntimeError('secret detail')))
    errored = await error_provider('user-1')
    assert errored == JITFlagEvaluation(
        TriState.UNKNOWN,
        TriState.UNKNOWN,
        JITDecisionReason.PROVIDER_ERROR,
        JITErrorClass.PROVIDER,
    )

    unconfigured = await PostHogJITFlagProvider(client_factory=lambda: None)('user-1')
    assert unconfigured == JITFlagEvaluation(
        TriState.UNKNOWN,
        TriState.UNKNOWN,
        JITDecisionReason.CONFIGURATION_MISSING,
        JITErrorClass.CONFIGURATION,
    )

    async def timeout(*_args, **_kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(authority_module, 'run_blocking', timeout)
    timed_out = await PostHogJITFlagProvider(client_factory=lambda: _FakePostHog({}))('user-1')
    assert timed_out == JITFlagEvaluation(
        TriState.UNKNOWN,
        TriState.UNKNOWN,
        JITDecisionReason.PROVIDER_TIMEOUT,
        JITErrorClass.TIMEOUT,
    )


@pytest.mark.asyncio
async def test_posthog_decide_coalesces_same_uid_calls():
    started = threading.Event()
    release = threading.Event()

    class SlowPostHog:
        def __init__(self):
            self.calls = 0

        def get_feature_variants(self, _uid: str):
            self.calls += 1
            started.set()
            release.wait(1)
            return {'jit-processing-v1': True, 'jit-processing-kill-switch-v1': False}

    client = SlowPostHog()
    provider = PostHogJITFlagProvider(timeout_seconds=1, client_factory=lambda: client)
    tasks = [asyncio.create_task(provider('same-user')) for _ in range(32)]
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.001)
    assert started.is_set()
    release.set()

    results = await asyncio.gather(*tasks)
    assert client.calls == 1
    assert all(result.rollout == TriState.ENABLED for result in results)


@pytest.mark.asyncio
async def test_trigger_snapshot_final_refresh_bypasses_stale_posthog_call(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    class SequencedPostHog:
        def __init__(self):
            self.calls = 0

        def get_feature_variants(self, _uid: str):
            self.calls += 1
            if self.calls == 1:
                started.set()
                release.wait(1)
                return {'jit-processing-v1': True, 'jit-processing-kill-switch-v1': False}
            return {'jit-processing-v1': True, 'jit-processing-kill-switch-v1': True}

    client = SequencedPostHog()
    provider = PostHogJITFlagProvider(timeout_seconds=1, client_factory=lambda: client)
    authority = JITRolloutAuthority(provider)
    stale_call = asyncio.create_task(provider('owner'))
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.001)
    assert started.is_set()

    async def resolve(uid: str, *, stage: JITDecisionStage, force_refresh: bool = False):
        if not force_refresh:
            evaluation = JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)
            return authority_module._effective_decision(evaluation, cache_hit=False, cache_ttl_seconds=20)
        return await authority.resolve(uid, stage=stage, force_refresh=True)

    snapshot = AuthoritativeTriggerSnapshot(
        owner_id='owner',
        account_generation=7,
        head_commit_id='head',
        commit_sequence=11,
        snapshot_revision='secret-revision',
        complete=True,
        rows=(),
    )

    async def immediate(_executor, function, uid):
        assert function is jit_rollout.read_authoritative_trigger_snapshot
        assert uid == 'owner'
        return snapshot

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', resolve)
    monkeypatch.setattr(jit_rollout, 'run_blocking', immediate)

    try:
        response = await asyncio.wait_for(
            jit_rollout.get_jit_trigger_snapshot(Response(), uid='owner'),
            timeout=1,
        )
    finally:
        release.set()

    stale_result = await stale_call
    assert stale_result.rollout == TriState.ENABLED
    assert stale_result.kill_switch == TriState.DISABLED
    assert client.calls == 2
    assert response.complete is False
    assert response.rows == []
    assert response.snapshot_revision == ''
    assert response.failure_reason == 'rollout_not_enabled'


@pytest.mark.asyncio
async def test_posthog_coalescing_survives_caller_timeout_while_sdk_call_is_blocked():
    started = threading.Event()
    release = threading.Event()

    class BlockedPostHog:
        def __init__(self):
            self.calls = 0

        def get_feature_variants(self, _uid: str):
            self.calls += 1
            started.set()
            release.wait(1)
            return {'jit-processing-v1': True, 'jit-processing-kill-switch-v1': False}

    client = BlockedPostHog()
    provider = PostHogJITFlagProvider(timeout_seconds=0.02, client_factory=lambda: client)

    first = await provider('same-user')
    assert first.error_class == JITErrorClass.TIMEOUT
    assert started.is_set()

    second = await provider('same-user')
    assert second == first
    assert client.calls == 1

    release.set()
    for _ in range(100):
        if not provider._inflight:
            break
        await asyncio.sleep(0.01)
    assert not provider._inflight


@pytest.mark.asyncio
async def test_posthog_bulkhead_bounds_fanout_without_starving_sync_executor():
    started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()

    class SaturatedPostHog:
        def __init__(self):
            self.calls = 0

        def get_feature_variants(self, _uid: str):
            with lock:
                self.calls += 1
            started.set()
            release.wait(1)
            return {'jit-processing-v1': True, 'jit-processing-kill-switch-v1': False}

    client = SaturatedPostHog()
    provider = PostHogJITFlagProvider(timeout_seconds=0.05, client_factory=lambda: client)
    tasks = [asyncio.create_task(provider(f'user-{index}')) for index in range(24)]
    for _ in range(100):
        if client.calls >= 4:
            break
        await asyncio.sleep(0.001)
    assert started.is_set()

    # The PostHog control plane has its own four-worker bulkhead.  A saturated
    # decide fanout must leave the shared sync pipeline executor usable.
    assert await asyncio.wait_for(run_blocking(sync_executor, lambda: 'sync-ready'), timeout=0.5) == 'sync-ready'
    results = await asyncio.gather(*tasks)
    assert all(result.error_class == JITErrorClass.TIMEOUT for result in results)

    release.set()
    for _ in range(100):
        if client.calls >= 20:
            break
        await asyncio.sleep(0.01)
    assert client.calls == 20  # four workers plus sixteen queued submissions


def test_posthog_control_plane_shutdown_is_nonblocking(monkeypatch):
    calls = []

    class Executor:
        def shutdown(self, *, wait, cancel_futures):
            calls.append((wait, cancel_futures))

    monkeypatch.setattr(authority_module, '_posthog_control_executor', Executor())
    authority_module.close_posthog_control_plane()

    assert calls == [(False, True)]
    assert authority_module._posthog_control_executor is None


def test_read_only_route_uses_authenticated_uid_and_ignores_self_enrolment(monkeypatch):
    observed: list[tuple[str, JITDecisionStage, bool]] = []

    async def resolve(uid: str, *, stage: JITDecisionStage, force_refresh: bool = False):
        observed.append((uid, stage, force_refresh))
        evaluation = JITFlagEvaluation(TriState.DISABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)
        return authority_module._effective_decision(evaluation, cache_hit=False, cache_ttl_seconds=20)

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', resolve)
    app = FastAPI()
    app.include_router(jit_ledger_snapshot.router)
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'server-authenticated-user'
    jit_rollout.validate_jit_rollout_contract(app)

    response = TestClient(app).get(
        '/v1/jit/rollout-decision?uid=attacker&enabled=true&kill_switch=false',
    )

    assert response.status_code == 200
    assert response.json()['effective'] == 'disabled'
    assert observed == [('server-authenticated-user', JITDecisionStage.READ_ONLY, False)]


def test_main_and_desktop_apps_mount_one_read_only_decision_contract():
    for app in (main.app, desktop_backend._build_app()):
        jit_rollout.validate_jit_rollout_contract(app)
        route = next(route for route in app.routes if getattr(route, 'path', None) == '/v1/jit/rollout-decision')
        assert route.methods == {'GET'}


def test_trigger_snapshot_is_owner_authenticated_default_off_and_never_reads_memory(monkeypatch):
    async def resolve(uid: str, *, stage: JITDecisionStage, force_refresh: bool = False):
        assert uid == 'owner'
        evaluation = JITFlagEvaluation(TriState.DISABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)
        return authority_module._effective_decision(evaluation, cache_hit=False, cache_ttl_seconds=20)

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', resolve)
    monkeypatch.setattr(
        jit_rollout,
        'read_authoritative_trigger_snapshot',
        lambda *_args, **_kwargs: pytest.fail('flag-off request must not read the memory ledger'),
    )
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'

    response = TestClient(app).get('/v1/jit/trigger-snapshot?uid=attacker')

    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json() == {
        'owner_id': 'owner',
        'account_generation': 0,
        'head_commit_id': '',
        'commit_sequence': 0,
        'snapshot_revision': '',
        'complete': False,
        'rows': [],
        'policy': DEFAULT_TRIGGER_RUNTIME_POLICY.model_dump(mode='json'),
        'failure_reason': 'rollout_not_enabled',
    }


def test_trigger_snapshot_serializes_exhaustive_action_receipt(monkeypatch):
    observed: list[bool] = []

    async def resolve(uid: str, *, stage: JITDecisionStage, force_refresh: bool = False):
        observed.append(force_refresh)
        evaluation = JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)
        return authority_module._effective_decision(evaluation, cache_hit=False, cache_ttl_seconds=20)

    snapshot = AuthoritativeTriggerSnapshot(
        owner_id='owner',
        account_generation=7,
        head_commit_id='head',
        commit_sequence=11,
        snapshot_revision='revision',
        complete=True,
        rows=(
            AuthoritativeTriggerRow(
                memory_id='trigger-1',
                item_revision=3,
                updated_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
                trigger_condition={
                    'schema_version': 'jit_trigger.v1',
                    'match_mode': 'all',
                    'keywords': ['release'],
                    'action': {'type': 'agent_prompt', 'prompt': 'Give the next release step.'},
                },
                action=TriggerAction(type='agent_prompt', prompt='Give the next release step.'),
                wakeup_budget_per_day=1,
                snoozed_until=datetime(2026, 8, 25, tzinfo=timezone.utc),
            ),
        ),
    )

    async def immediate(_executor, function, uid):
        assert uid == 'owner'
        assert function is jit_rollout.read_authoritative_trigger_snapshot
        return snapshot

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', resolve)
    monkeypatch.setattr(jit_rollout, 'run_blocking', immediate)
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'

    payload = TestClient(app).get('/v1/jit/trigger-snapshot').json()

    assert payload['owner_id'] == 'owner'
    assert payload['snapshot_revision'] == 'revision'
    assert payload['rows'][0]['action'] == {
        'type': 'agent_prompt',
        'prompt': 'Give the next release step.',
    }
    assert payload['rows'][0]['snoozed_until'] == '2026-08-25T00:00:00Z'
    assert payload['policy'] == DEFAULT_TRIGGER_RUNTIME_POLICY.model_dump(mode='json')
    assert '"action"' in payload['rows'][0]['trigger_condition_json']
    assert observed == [False, True]


@pytest.mark.parametrize(
    ('rollout', 'kill_switch'),
    [
        (TriState.DISABLED, TriState.DISABLED),
        (TriState.ENABLED, TriState.ENABLED),
    ],
    ids=['rollout-disabled-during-scan', 'kill-switch-enabled-during-scan'],
)
def test_trigger_snapshot_final_authority_fence_discards_scan_after_disable_or_kill(monkeypatch, rollout, kill_switch):
    observed: list[bool] = []

    async def resolve(uid: str, *, stage: JITDecisionStage, force_refresh: bool = False):
        assert uid == 'owner'
        observed.append(force_refresh)
        evaluation = (
            JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)
            if not force_refresh
            else JITFlagEvaluation(rollout, kill_switch, JITDecisionReason.EVALUATED)
        )
        return authority_module._effective_decision(evaluation, cache_hit=False, cache_ttl_seconds=20)

    snapshot = AuthoritativeTriggerSnapshot(
        owner_id='owner',
        account_generation=7,
        head_commit_id='head',
        commit_sequence=11,
        snapshot_revision='secret-revision',
        complete=True,
        rows=(),
    )

    async def immediate(_executor, function, uid):
        assert function is jit_rollout.read_authoritative_trigger_snapshot
        assert uid == 'owner'
        return snapshot

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', resolve)
    monkeypatch.setattr(jit_rollout, 'run_blocking', immediate)
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'

    payload = TestClient(app).get('/v1/jit/trigger-snapshot').json()

    assert observed == [False, True]
    assert payload == {
        'owner_id': 'owner',
        'account_generation': 0,
        'head_commit_id': '',
        'commit_sequence': 0,
        'snapshot_revision': '',
        'complete': False,
        'rows': [],
        'policy': DEFAULT_TRIGGER_RUNTIME_POLICY.model_dump(mode='json'),
        'failure_reason': 'rollout_not_enabled',
    }


def test_trigger_snapshot_preserves_owner_generation_failure_as_non_actionable(monkeypatch):
    observed: list[bool] = []

    async def resolve(uid: str, *, stage: JITDecisionStage, force_refresh: bool = False):
        assert uid == 'owner'
        observed.append(force_refresh)
        evaluation = JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)
        return authority_module._effective_decision(evaluation, cache_hit=False, cache_ttl_seconds=20)

    stale_snapshot = AuthoritativeTriggerSnapshot(
        owner_id='owner',
        account_generation=7,
        head_commit_id='head-before-transition',
        commit_sequence=11,
        snapshot_revision='',
        complete=False,
        rows=(),
        failure_reason='authority_changed',
    )

    async def immediate(_executor, function, uid):
        assert function is jit_rollout.read_authoritative_trigger_snapshot
        assert uid == 'owner'
        return stale_snapshot

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', resolve)
    monkeypatch.setattr(jit_rollout, 'run_blocking', immediate)
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'

    payload = TestClient(app).get('/v1/jit/trigger-snapshot').json()

    assert observed == [False, True]
    assert payload['owner_id'] == 'owner'
    assert payload['account_generation'] == 7
    assert payload['head_commit_id'] == 'head-before-transition'
    assert payload['complete'] is False
    assert payload['rows'] == []
    assert payload['snapshot_revision'] == ''
    assert payload['failure_reason'] == 'authority_changed'


def test_trigger_feedback_is_owner_authenticated_and_remains_available_while_rollout_is_off(monkeypatch):
    observed = {}
    receipt = JITTriggerFeedbackReceipt(
        uid='owner',
        feedback_id='f' * 64,
        event_id='e' * 64,
        trigger_memory_id='trigger-1',
        account_generation=3,
        expected_trigger_revision=4,
        action='useful',
        recorded_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        request_hash='a' * 64,
        applied_trigger_revision=5,
    )

    async def immediate(_executor, function, uid, memory_id, **kwargs):
        observed.update(function=function, uid=uid, memory_id=memory_id, kwargs=kwargs)
        return SimpleNamespace(
            item=SimpleNamespace(memory_id=memory_id, item_revision=5, status=MemoryItemStatus.active),
            applied=True,
            receipt=receipt,
        )

    monkeypatch.setattr(jit_rollout, 'run_blocking', immediate)
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'

    response = TestClient(app).post(
        '/v1/jit/trigger-feedback?uid=attacker',
        json={
            'feedback_id': 'f' * 64,
            'event_id': 'e' * 64,
            'trigger_memory_id': 'trigger-1',
            'account_generation': 3,
            'trigger_revision': 4,
            'action': 'useful',
            'recorded_at': '2026-08-24T00:00:00Z',
        },
    )

    assert response.status_code == 200
    assert response.json()['applied'] is True
    assert response.json()['trigger_revision'] == 5
    assert observed['function'] is jit_rollout.apply_canonical_trigger_feedback
    assert observed['uid'] == 'owner'
    assert observed['kwargs']['event_id'] == 'e' * 64


def test_trigger_feedback_rejects_stale_authority_without_leaking_details(monkeypatch):
    async def conflict(*_args, **_kwargs):
        raise ValueError('secret stale target detail')

    monkeypatch.setattr(jit_rollout, 'run_blocking', conflict)
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'

    response = TestClient(app).post(
        '/v1/jit/trigger-feedback',
        json={
            'feedback_id': 'f' * 64,
            'event_id': 'e' * 64,
            'trigger_memory_id': 'trigger-1',
            'account_generation': 3,
            'trigger_revision': 4,
            'action': 'disable',
            'recorded_at': '2026-08-24T00:00:00Z',
        },
    )

    assert response.status_code == 409
    assert response.json()['detail'] == 'Trigger feedback authority changed or is unavailable'
    assert 'secret' not in response.text


def test_trigger_feedback_snooze_requires_a_later_expiry():
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'

    response = TestClient(app).post(
        '/v1/jit/trigger-feedback',
        json={
            'feedback_id': 'f' * 64,
            'event_id': 'e' * 64,
            'trigger_memory_id': 'trigger-1',
            'account_generation': 3,
            'trigger_revision': 4,
            'action': 'snooze',
            'recorded_at': '2026-08-24T00:00:00Z',
        },
    )

    assert response.status_code == 422


def test_proactivity_reservation_force_refreshes_paid_authority_and_uses_authenticated_owner(monkeypatch):
    observed = {}

    async def resolve(uid: str, *, stage: JITDecisionStage, force_refresh: bool = False):
        observed.update(resolve=(uid, stage, force_refresh))
        evaluation = JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)
        return authority_module._effective_decision(evaluation, cache_hit=False, cache_ttl_seconds=20)

    receipt = JITProactivityEventReceipt(
        uid='owner',
        event_id='e' * 64,
        candidate_id='c' * 64,
        operation='full_turn',
        account_generation=3,
        budget_day='2026-08-24',
        parent_event_id='a' * 64,
        device_id='d' * 64,
        created_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        request_hash='b' * 64,
    )

    async def immediate(_executor, function, uid, **kwargs):
        observed.update(function=function, uid=uid, kwargs=kwargs)
        return receipt, True

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', resolve)
    monkeypatch.setattr(jit_rollout, 'run_blocking', immediate)
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'

    response = TestClient(app).post(
        '/v1/jit/proactivity/reservations?uid=attacker',
        json={
            'event_id': 'e' * 64,
            'candidate_id': 'c' * 64,
            'operation': 'full_turn',
            'account_generation': 3,
            'device_id': 'd' * 64,
            'parent_event_id': 'a' * 64,
        },
    )

    assert response.status_code == 200
    assert response.json()['reserved'] is True
    assert observed['resolve'] == ('owner', JITDecisionStage.PAID_BOUNDARY, True)
    assert observed['function'] is jit_rollout.reserve_jit_proactivity_event
    assert observed['uid'] == 'owner'


def test_proactivity_reservation_does_no_mutation_when_killed(monkeypatch):
    async def resolve(*_args, **_kwargs):
        evaluation = JITFlagEvaluation(TriState.ENABLED, TriState.ENABLED, JITDecisionReason.EVALUATED)
        return authority_module._effective_decision(evaluation, cache_hit=False, cache_ttl_seconds=20)

    async def no_write(*_args, **_kwargs):
        pytest.fail('kill switch must block reservation writes')

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', resolve)
    monkeypatch.setattr(jit_rollout, 'run_blocking', no_write)
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'

    response = TestClient(app).post(
        '/v1/jit/proactivity/reservations',
        json={
            'event_id': 'e' * 64,
            'candidate_id': 'c' * 64,
            'operation': 'ambient_notification',
            'account_generation': 3,
            'device_id': 'd' * 64,
        },
    )

    assert response.status_code == 403


def test_proactivity_reservation_maps_malformed_authority_to_retryable_unavailable(monkeypatch):
    async def resolve(*_args, **_kwargs):
        evaluation = JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)
        return authority_module._effective_decision(evaluation, cache_hit=False, cache_ttl_seconds=20)

    async def malformed_authority(*_args, **_kwargs):
        raise MalformedDocError(
            document_path='users/owner/jit_proactivity/control',
            error_types=('missing',),
            error_fields=('account_generation',),
        )

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', resolve)
    monkeypatch.setattr(jit_rollout, 'run_blocking', malformed_authority)
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'

    response = TestClient(app).post(
        '/v1/jit/proactivity/reservations',
        json={
            'event_id': 'e' * 64,
            'candidate_id': 'c' * 64,
            'operation': 'ambient_notification',
            'account_generation': 3,
            'device_id': 'd' * 64,
        },
    )

    assert response.status_code == 503
    assert response.json() == {'detail': 'JIT proactive authority is temporarily unavailable'}
    assert 'users/owner' not in response.text
    assert 'account_generation' not in response.text

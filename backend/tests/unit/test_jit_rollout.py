from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import desktop_backend
from routers import jit_rollout
from utils import jit_rollout as authority_module
from utils.jit_rollout import (
    JITDecisionReason,
    JITDecisionStage,
    JITErrorClass,
    JITFlagEvaluation,
    JITRolloutAuthority,
    PostHogJITFlagProvider,
    TriState,
)
from utils.other.endpoints import get_current_user_uid


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
async def test_unknown_provider_results_are_not_cached():
    calls = 0

    async def provider(_: str) -> JITFlagEvaluation:
        nonlocal calls
        calls += 1
        return JITFlagEvaluation(
            TriState.UNKNOWN,
            TriState.UNKNOWN,
            JITDecisionReason.PROVIDER_ERROR,
            JITErrorClass.PROVIDER,
        )

    authority = JITRolloutAuthority(provider)
    await authority.resolve('user-1', stage=JITDecisionStage.INGRESS)
    await authority.resolve('user-1', stage=JITDecisionStage.INGRESS)

    assert calls == 2


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


def test_read_only_route_uses_authenticated_uid_and_ignores_self_enrolment(monkeypatch):
    observed: list[tuple[str, JITDecisionStage, bool]] = []

    async def resolve(uid: str, *, stage: JITDecisionStage, force_refresh: bool = False):
        observed.append((uid, stage, force_refresh))
        evaluation = JITFlagEvaluation(TriState.DISABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)
        return authority_module._effective_decision(evaluation, cache_hit=False, cache_ttl_seconds=20)

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', resolve)
    app = FastAPI()
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
    import main

    for app in (main.app, desktop_backend._build_app()):
        jit_rollout.validate_jit_rollout_contract(app)
        route = next(route for route in app.routes if getattr(route, 'path', None) == '/v1/jit/rollout-decision')
        assert route.methods == {'GET'}

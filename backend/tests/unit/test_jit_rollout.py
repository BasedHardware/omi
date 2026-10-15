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
from utils import jit_rollout as authority_module
from utils.jit_rollout import (
    DEFAULT_JIT_ROLLOUT_CACHE_SECONDS,
    JIT_ADMISSION_ALLOWLIST,
    JIT_KILL_SWITCH_FLAG_KEY,
    JIT_PROCESSING_FLAG_KEY,
    JITDecisionReason,
    JITDecisionStage,
    JITErrorClass,
    JITFlagEvaluation,
    JITRolloutAuthority,
    PostHogJITFlagProvider,
    TriState,
    UNKNOWN_JIT_ROLLOUT_CACHE_SECONDS,
    resolve_jit_rollout,
    resolve_jit_rollout_sync,
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


_ALLOWLIST_UID = next(iter(JIT_ADMISSION_ALLOWLIST))
_OTHER_ALLOWLIST_UID = next(uid for uid in JIT_ADMISSION_ALLOWLIST if uid != _ALLOWLIST_UID)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('rollout', 'provider_reason', 'expected', 'reason'),
    [
        (TriState.ENABLED, JITDecisionReason.EVALUATED, TriState.ENABLED, JITDecisionReason.ROLLOUT_ENABLED),
        (TriState.DISABLED, JITDecisionReason.EVALUATED, TriState.DISABLED, JITDecisionReason.ROLLOUT_DISABLED),
        (TriState.DISABLED, JITDecisionReason.FLAG_ABSENT, TriState.DISABLED, JITDecisionReason.FLAG_ABSENT),
        (TriState.UNKNOWN, JITDecisionReason.PROVIDER_TIMEOUT, TriState.UNKNOWN, JITDecisionReason.PROVIDER_TIMEOUT),
        (
            TriState.UNKNOWN,
            JITDecisionReason.MALFORMED_RESPONSE,
            TriState.UNKNOWN,
            JITDecisionReason.MALFORMED_RESPONSE,
        ),
    ],
)
async def test_authority_admits_only_known_true_exposure_flag(
    rollout,
    provider_reason,
    expected,
    reason,
):
    # Kill switch is held neutral (disabled) here: this test isolates the
    # rollout-flag-driven path. Kill-switch-as-authority is covered
    # separately below.
    async def provider(uid: str) -> JITFlagEvaluation:
        assert uid == 'named-user'
        return JITFlagEvaluation(rollout, TriState.DISABLED, provider_reason)

    decision = await JITRolloutAuthority(provider).resolve(
        'named-user',
        stage=JITDecisionStage.INGRESS,
    )

    assert decision.effective == expected
    assert decision.reason == reason
    assert decision.kill_switch == TriState.DISABLED
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
            {JIT_PROCESSING_FLAG_KEY: True, JIT_KILL_SWITCH_FLAG_KEY: True},
            TriState.ENABLED,
            TriState.ENABLED,
            JITDecisionReason.EVALUATED,
            JITErrorClass.NONE,
        ),
        (
            {JIT_PROCESSING_FLAG_KEY: False, JIT_KILL_SWITCH_FLAG_KEY: False},
            TriState.DISABLED,
            TriState.DISABLED,
            JITDecisionReason.EVALUATED,
            JITErrorClass.NONE,
        ),
        (
            {JIT_KILL_SWITCH_FLAG_KEY: False},
            TriState.DISABLED,
            TriState.DISABLED,
            JITDecisionReason.FLAG_ABSENT,
            JITErrorClass.ABSENT,
        ),
        (
            # Kill key absent from a well-formed response: PostHog omits a
            # boolean flag that evaluates false, so absence here means
            # disabled, not unknown -- even though the rollout value itself
            # is separately malformed.
            {JIT_PROCESSING_FLAG_KEY: 'enabled'},
            TriState.UNKNOWN,
            TriState.DISABLED,
            JITDecisionReason.MALFORMED_RESPONSE,
            JITErrorClass.MALFORMED,
        ),
    ],
)
async def test_posthog_provider_parses_the_exposure_and_kill_switch_flags(
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
async def test_kill_switch_flag_revokes_admission_even_when_rollout_is_enabled():
    """The kill switch is live authority again: it can only ever remove admission."""

    client = _FakePostHog(
        {
            JIT_PROCESSING_FLAG_KEY: True,
            JIT_KILL_SWITCH_FLAG_KEY: True,
        }
    )
    authority = JITRolloutAuthority(PostHogJITFlagProvider(client_factory=lambda: client))

    decision = await authority.resolve('named-user', stage=JITDecisionStage.READ_ONLY)

    assert decision.permits_work is False
    assert decision.effective == TriState.DISABLED
    assert decision.kill_switch == TriState.ENABLED
    assert decision.reason == JITDecisionReason.KILL_SWITCH_ENABLED


@pytest.mark.asyncio
async def test_kill_switch_absent_from_a_well_formed_response_means_disabled_and_full_cache_ttl():
    """PostHog omits a boolean flag entirely when it evaluates false for the distinct ID.

    A 0%-rollout kill switch -- its normal, healthy steady state -- is
    therefore ABSENT from a real decide response, not a present ``false``.
    Since the response itself is well-formed, that absence must read as
    DISABLED (the provider was reached and did not assert a kill), not
    UNKNOWN. Reading it as UNKNOWN would permanently downgrade every
    steady-state decision to the short negative-cache TTL and report a false
    "unknown" kill switch on the wire, for both allowlisted and regular UIDs.
    """

    client = _FakePostHog({JIT_PROCESSING_FLAG_KEY: True})

    regular_decision = await JITRolloutAuthority(PostHogJITFlagProvider(client_factory=lambda: client)).resolve(
        'named-user', stage=JITDecisionStage.READ_ONLY
    )
    assert regular_decision.kill_switch == TriState.DISABLED
    assert regular_decision.permits_work is True
    assert regular_decision.cache_ttl_seconds == int(DEFAULT_JIT_ROLLOUT_CACHE_SECONDS)

    allowlisted_decision = await JITRolloutAuthority(PostHogJITFlagProvider(client_factory=lambda: client)).resolve(
        _ALLOWLIST_UID, stage=JITDecisionStage.READ_ONLY
    )
    assert allowlisted_decision.kill_switch == TriState.DISABLED
    assert allowlisted_decision.permits_work is True
    assert allowlisted_decision.cache_ttl_seconds == int(DEFAULT_JIT_ROLLOUT_CACHE_SECONDS)


@pytest.mark.asyncio
async def test_kill_switch_present_but_malformed_stays_unknown_with_short_cache_ttl_and_never_blocks():
    client = _FakePostHog({JIT_PROCESSING_FLAG_KEY: True, JIT_KILL_SWITCH_FLAG_KEY: 'enabled'})

    regular_decision = await JITRolloutAuthority(PostHogJITFlagProvider(client_factory=lambda: client)).resolve(
        'named-user', stage=JITDecisionStage.READ_ONLY
    )
    assert regular_decision.kill_switch == TriState.UNKNOWN
    assert regular_decision.permits_work is True
    assert regular_decision.cache_ttl_seconds == int(UNKNOWN_JIT_ROLLOUT_CACHE_SECONDS)

    allowlisted_decision = await JITRolloutAuthority(PostHogJITFlagProvider(client_factory=lambda: client)).resolve(
        _ALLOWLIST_UID, stage=JITDecisionStage.READ_ONLY
    )
    assert allowlisted_decision.kill_switch == TriState.UNKNOWN
    assert allowlisted_decision.permits_work is True
    assert allowlisted_decision.cache_ttl_seconds == int(UNKNOWN_JIT_ROLLOUT_CACHE_SECONDS)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'evaluation',
    [
        # Exposure flag state is irrelevant to the allowlist; only the kill
        # switch can remove its admission, and here it never definitively is.
        JITFlagEvaluation(TriState.DISABLED, TriState.DISABLED, JITDecisionReason.EVALUATED),
        JITFlagEvaluation(TriState.DISABLED, TriState.DISABLED, JITDecisionReason.FLAG_ABSENT, JITErrorClass.ABSENT),
        JITFlagEvaluation(
            TriState.UNKNOWN, TriState.UNKNOWN, JITDecisionReason.PROVIDER_TIMEOUT, JITErrorClass.TIMEOUT
        ),
        JITFlagEvaluation(TriState.ENABLED, TriState.UNKNOWN, JITDecisionReason.EVALUATED),
    ],
)
async def test_allowlist_uid_is_enabled_when_rollout_is_false_missing_or_provider_is_down(evaluation):
    """The allowlist ignores the exposure flag but still consults the kill switch.

    A provider timeout/outage yields an unknown kill switch, which -- like a
    false or missing exposure flag -- must not remove the allowlist's
    admission. This is the resilience the module docstring promises: 'the
    allowlist still admits when PostHog is down.'
    """

    calls: list[str] = []

    async def provider(uid: str) -> JITFlagEvaluation:
        calls.append(uid)
        return evaluation

    authority = JITRolloutAuthority(provider)
    for uid in (_ALLOWLIST_UID, _OTHER_ALLOWLIST_UID):
        decision = await authority.resolve(uid, stage=JITDecisionStage.READ_ONLY)
        assert decision.permits_work is True
        assert decision.effective == TriState.ENABLED
        assert decision.reason == JITDecisionReason.ROLLOUT_ENABLED
    # Unlike the fully-retired behavior, the provider IS consulted for the
    # allowlist now -- it is the only path that can observe a kill switch.
    assert calls == [_ALLOWLIST_UID, _OTHER_ALLOWLIST_UID]


@pytest.mark.asyncio
async def test_allowlist_uid_is_blocked_when_kill_switch_is_enabled():
    async def provider(_uid: str) -> JITFlagEvaluation:
        return JITFlagEvaluation(TriState.ENABLED, TriState.ENABLED, JITDecisionReason.EVALUATED)

    authority = JITRolloutAuthority(provider)
    for uid in (_ALLOWLIST_UID, _OTHER_ALLOWLIST_UID):
        decision = await authority.resolve(uid, stage=JITDecisionStage.READ_ONLY)
        assert decision.permits_work is False
        assert decision.effective == TriState.DISABLED
        assert decision.reason == JITDecisionReason.KILL_SWITCH_ENABLED
        assert decision.kill_switch == TriState.ENABLED


@pytest.mark.asyncio
async def test_allowlist_uid_sync_path_is_also_resilient_to_a_dead_control_loop(monkeypatch):
    """resolve_jit_rollout_sync's outer scheduling-failure fallback must not block the allowlist."""

    def broken_run_coroutine_threadsafe(coro, *_args, **_kwargs):
        coro.close()  # avoid an unrelated "coroutine was never awaited" warning
        raise RuntimeError('control loop is unavailable')

    monkeypatch.setattr(authority_module.asyncio, 'run_coroutine_threadsafe', broken_run_coroutine_threadsafe)

    decision = resolve_jit_rollout_sync(_ALLOWLIST_UID, stage=JITDecisionStage.READ_ONLY)

    assert decision.permits_work is True
    assert decision.effective == TriState.ENABLED
    assert decision.kill_switch == TriState.UNKNOWN


@pytest.mark.asyncio
async def test_non_allowlist_uid_follows_exposure_flag_and_fails_closed_on_timeout():
    states = iter(
        [
            JITFlagEvaluation(TriState.DISABLED, TriState.DISABLED, JITDecisionReason.EVALUATED),
            JITFlagEvaluation(
                TriState.DISABLED, TriState.DISABLED, JITDecisionReason.FLAG_ABSENT, JITErrorClass.ABSENT
            ),
            JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED),
            JITFlagEvaluation(
                TriState.UNKNOWN, TriState.UNKNOWN, JITDecisionReason.PROVIDER_TIMEOUT, JITErrorClass.TIMEOUT
            ),
            JITFlagEvaluation(
                TriState.UNKNOWN, TriState.UNKNOWN, JITDecisionReason.MALFORMED_RESPONSE, JITErrorClass.MALFORMED
            ),
        ]
    )

    async def provider(_uid: str) -> JITFlagEvaluation:
        return next(states)

    authority = JITRolloutAuthority(provider)
    disabled = await authority.resolve('stranger', stage=JITDecisionStage.READ_ONLY)
    absent = await JITRolloutAuthority(provider).resolve('stranger', stage=JITDecisionStage.READ_ONLY)
    enabled = await JITRolloutAuthority(provider).resolve('stranger', stage=JITDecisionStage.READ_ONLY)
    timed_out = await JITRolloutAuthority(provider).resolve('stranger', stage=JITDecisionStage.READ_ONLY)
    malformed = await JITRolloutAuthority(provider).resolve('stranger', stage=JITDecisionStage.READ_ONLY)

    assert disabled.effective == TriState.DISABLED and disabled.permits_work is False
    assert absent.effective == TriState.DISABLED and absent.permits_work is False
    assert enabled.effective == TriState.ENABLED and enabled.permits_work is True
    assert timed_out.effective == TriState.UNKNOWN and timed_out.permits_work is False
    assert malformed.effective == TriState.UNKNOWN and malformed.permits_work is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('evaluation', 'expected_effective', 'expected_permits', 'expected_reason'),
    [
        (
            JITFlagEvaluation(TriState.ENABLED, TriState.ENABLED, JITDecisionReason.EVALUATED),
            TriState.DISABLED,
            False,
            JITDecisionReason.KILL_SWITCH_ENABLED,
        ),
        (
            JITFlagEvaluation(TriState.ENABLED, TriState.UNKNOWN, JITDecisionReason.EVALUATED),
            TriState.ENABLED,
            True,
            JITDecisionReason.ROLLOUT_ENABLED,
        ),
        (
            JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED),
            TriState.ENABLED,
            True,
            JITDecisionReason.ROLLOUT_ENABLED,
        ),
    ],
)
async def test_non_allowlist_kill_switch_can_only_remove_never_grant_authority(
    evaluation, expected_effective, expected_permits, expected_reason
):
    async def provider(_uid: str) -> JITFlagEvaluation:
        return evaluation

    decision = await JITRolloutAuthority(provider).resolve('stranger', stage=JITDecisionStage.READ_ONLY)

    assert decision.effective == expected_effective
    assert decision.permits_work is expected_permits
    assert decision.reason == expected_reason
    assert decision.kill_switch == evaluation.kill_switch


@pytest.mark.asyncio
async def test_public_helpers_share_one_allowlist_and_one_exposure_flag(monkeypatch):
    async def provider(_uid: str) -> JITFlagEvaluation:
        return JITFlagEvaluation(TriState.DISABLED, TriState.DISABLED, JITDecisionReason.EVALUATED)

    monkeypatch.setattr(authority_module, '_authority', JITRolloutAuthority(provider))
    monkeypatch.setattr(authority_module, '_sync_authority', JITRolloutAuthority(provider))

    allowlisted = await resolve_jit_rollout(_ALLOWLIST_UID, stage=JITDecisionStage.READ_ONLY)
    stranger = await resolve_jit_rollout('stranger', stage=JITDecisionStage.READ_ONLY)
    ingress_stranger = await resolve_jit_rollout('stranger', stage=JITDecisionStage.INGRESS)
    sync_allowlisted = resolve_jit_rollout_sync(_ALLOWLIST_UID, stage=JITDecisionStage.READ_ONLY)

    assert allowlisted.permits_work is True
    assert stranger.permits_work is False
    assert ingress_stranger.permits_work is False
    assert sync_allowlisted.permits_work is True


def test_sync_path_inherits_kill_switch_authority_over_allowlist_and_rollout(monkeypatch):
    """resolve_jit_rollout_sync (the sweep/first-open path) must match the async contract exactly."""

    states = {
        'killed-regular': JITFlagEvaluation(TriState.ENABLED, TriState.ENABLED, JITDecisionReason.EVALUATED),
        'admitted-regular': JITFlagEvaluation(TriState.ENABLED, TriState.DISABLED, JITDecisionReason.EVALUATED),
    }

    async def provider(uid: str) -> JITFlagEvaluation:
        if uid in (_ALLOWLIST_UID, _OTHER_ALLOWLIST_UID):
            return JITFlagEvaluation(TriState.ENABLED, TriState.ENABLED, JITDecisionReason.EVALUATED)
        return states[uid]

    monkeypatch.setattr(authority_module, '_sync_authority', JITRolloutAuthority(provider))

    killed_allowlisted = resolve_jit_rollout_sync(_ALLOWLIST_UID, stage=JITDecisionStage.READ_ONLY)
    killed_regular = resolve_jit_rollout_sync('killed-regular', stage=JITDecisionStage.READ_ONLY)
    admitted_regular = resolve_jit_rollout_sync('admitted-regular', stage=JITDecisionStage.READ_ONLY)

    assert killed_allowlisted.permits_work is False
    assert killed_allowlisted.reason == JITDecisionReason.KILL_SWITCH_ENABLED
    assert killed_regular.permits_work is False
    assert killed_regular.reason == JITDecisionReason.KILL_SWITCH_ENABLED
    assert admitted_regular.permits_work is True


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
async def test_force_refresh_bypasses_stale_posthog_call():
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
                return {JIT_PROCESSING_FLAG_KEY: True, JIT_KILL_SWITCH_FLAG_KEY: False}
            return {JIT_PROCESSING_FLAG_KEY: False, JIT_KILL_SWITCH_FLAG_KEY: True}

    client = SequencedPostHog()
    provider = PostHogJITFlagProvider(timeout_seconds=1, client_factory=lambda: client)
    authority = JITRolloutAuthority(provider)
    stale_call = asyncio.create_task(provider('owner'))
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.001)
    assert started.is_set()

    try:
        refreshed = await authority.resolve('owner', stage=JITDecisionStage.READ_ONLY, force_refresh=True)
    finally:
        release.set()

    stale_result = await stale_call
    assert stale_result.rollout == TriState.ENABLED
    assert stale_result.kill_switch == TriState.DISABLED
    assert client.calls == 2
    assert refreshed.permits_work is False


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


def test_retired_trigger_snapshot_is_authenticated_empty_and_does_not_resolve_flags(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError('retired snapshots must not read rollout or storage')

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', forbidden)
    app = FastAPI()
    app.include_router(jit_rollout.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'owner'
    with TestClient(app) as client:
        response = client.get('/v1/jit/trigger-snapshot')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    body = response.json()
    assert body['owner_id'] == 'owner'
    assert body['complete'] is False
    assert body['rows'] == []
    assert body['account_generation'] == 0
    assert body['head_commit_id'] == body['snapshot_revision'] == ''
    assert body['failure_reason'] == 'rollout_not_enabled'


@pytest.mark.parametrize('path', ['/v1/jit/trigger-feedback', '/v1/jit/proactivity/reservations'])
def test_retired_jit_mutations_are_static_and_do_not_authenticate_or_parse_body(path, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError('retired mutations must not resolve authority')

    monkeypatch.setattr(jit_rollout, 'resolve_jit_rollout', forbidden)
    app = FastAPI()
    app.include_router(jit_rollout.router)
    route = next(route for route in app.routes if route.path == path)
    assert route.dependant.dependencies == []
    assert route.dependant.body_params == []
    with TestClient(app) as client:
        response = client.post(path, content=b'not json', headers={'Authorization': 'Bearer expired'})
    assert response.status_code == 410
    assert response.json()['detail']['error'] == 'feature_retired'

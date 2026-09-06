"""Free-tier processing policy matrix (shard S6 of the local-models free tier).

Flag-agnostic policy: desktop conversations consult S1's Decision exactly once;
non-desktop falls through; identified-basic is terminal (projection or
deterministic minimum); force/reprocess do not rescue basic; any policy error
fails closed onto the deterministic minimum. Funding-owner resolution lives
inside ``decision_for`` so a raise there is ``policy_unavailable``.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from config.plan_catalog import PlanType
from testing.import_isolation import load_module_fresh, stub_modules
from utils.llm.model_config import get_all_configured_features, get_provider
from utils.managed_compute import DECISION_REASONS, Decision, FREE_ALLOWLIST_FEATURES, FREE_ALLOWLIST_PREFIX

_BACKEND = Path(__file__).resolve().parents[2]
_POLICY_PATH = os.path.join(str(_BACKEND), 'utils', 'free_tier_processing_policy.py')
_MC_PATH = os.path.join(str(_BACKEND), 'utils', 'managed_compute.py')

UID = 'uid'
STRUCTURE_FEATURE = 'conv_structure'

# S1 Decision.allowed is True exactly for these reasons (managed_compute._authorize*).
_S1_ALLOWED_REASONS = frozenset(
    {
        'free_allowlist',
        'byok',
        'plan_paid',
        'plan_unknown_fail_open',
    }
)

_S6_PROCESSING_REASONS = frozenset(
    {
        'non_desktop_source',
        'plan_identification_fail_open',
        'policy_unavailable',
    }
)


@pytest.fixture(scope='module')
def policy():
    """A fresh ``utils.free_tier_processing_policy`` against self-contained stubs.

    ``test_omi_qos_tiers`` installs a module-scope ``utils.byok`` stub with a
    partial attribute set. This fixture replaces that (and ``utils.subscription``)
    for the duration of the load so ``Decision`` import always succeeds.
    """
    subscription_stub = ModuleType('utils.subscription')
    setattr(subscription_stub, 'request_has_llm_byok_key', lambda: False)
    byok_stub = ModuleType('utils.byok')
    setattr(byok_stub, 'get_byok_key', lambda _provider: None)
    setattr(byok_stub, 'has_validated_byok_keys', lambda: False)
    fakes: dict[str, ModuleType | None] = {
        'database.users': ModuleType('database.users'),
        'utils.subscription': subscription_stub,
        'utils.byok': byok_stub,
    }
    with stub_modules(fakes):
        load_module_fresh('utils.managed_compute', _MC_PATH)
        yield load_module_fresh('utils.free_tier_processing_policy', _POLICY_PATH)


def _decision(
    *,
    allowed: bool,
    reason: str,
    plan: PlanType | None = None,
    plan_resolved: bool = False,
    funding_owner: str = 'omi',
    feature: str = STRUCTURE_FEATURE,
) -> Decision:
    return Decision(
        allowed=allowed,
        reason=reason,
        feature=feature,
        funding_owner=funding_owner,
        plan=plan,
        plan_resolved=plan_resolved,
    )


def _s1_decision(reason: str) -> Decision:
    """A Decision whose allowed/plan shape matches S1 for ``reason``."""
    allowed = reason in _S1_ALLOWED_REASONS
    plan: PlanType | None = None
    plan_resolved = False
    funding_owner = 'omi'
    if reason == 'plan_paid':
        plan = PlanType.plus
        plan_resolved = True
    elif reason in {'byok', 'free_allowlist', 'basic_not_entitled'}:
        plan = PlanType.basic
        plan_resolved = True
        if reason == 'byok':
            funding_owner = 'byok'
    elif reason in {'byok_not_validated', 'byok_not_enrolled'}:
        funding_owner = 'byok'
    return _decision(
        allowed=allowed,
        reason=reason,
        plan=plan,
        plan_resolved=plan_resolved,
        funding_owner=funding_owner,
    )


def _spy(decision: object) -> Any:
    calls: list[str] = []

    def decision_for(feature: str) -> Decision:
        calls.append(feature)
        if isinstance(decision, BaseException):
            raise decision
        return decision  # type: ignore[return-value]

    decision_for.calls = calls  # type: ignore[attr-defined]
    return decision_for


class _ExplodingDecision:
    """Decision-shaped object that raises inside the policy after decision_for returns."""

    allowed = False
    reason = 'basic_not_entitled'
    plan_resolved = True
    feature = STRUCTURE_FEATURE
    funding_owner = 'omi'

    @property
    def plan(self) -> PlanType:
        raise RuntimeError('plan access boom')


def _resolve(
    policy: Any,
    decision_for: Callable[[str], Decision],
    *,
    source: str | None = 'desktop',
    force_process: bool = False,
    is_reprocess: bool = False,
    has_projection: bool = False,
    uid: str = UID,
) -> Any:
    return policy.resolve_free_tier_processing_plan(
        uid=uid,
        source=source,
        force_process=force_process,
        is_reprocess=is_reprocess,
        has_projection=has_projection,
        decision_for=decision_for,
    )


# --- 1. table-driven policy matrix -------------------------------------------------------------


_MATRIX_CASES: list[tuple[str, dict[str, Any], object, str, str, int]] = [
    (
        'non_desktop',
        {'source': 'omi'},
        None,
        'process_normally',
        'non_desktop_source',
        0,
    ),
    (
        'no_source',
        {'source': None},
        None,
        'process_normally',
        'non_desktop_source',
        0,
    ),
    (
        'fail_open_identification',
        {},
        _decision(
            allowed=True,
            reason='plan_unknown_fail_open',
            plan=None,
            plan_resolved=False,
        ),
        'process_normally',
        'plan_identification_fail_open',
        1,
    ),
    (
        'paid',
        {},
        _decision(
            allowed=True,
            reason='plan_paid',
            plan=PlanType.plus,
            plan_resolved=True,
        ),
        'process_normally',
        'plan_paid',
        1,
    ),
    (
        'byok',
        {},
        _decision(
            allowed=True,
            reason='byok',
            plan=PlanType.basic,
            plan_resolved=True,
            funding_owner='byok',
        ),
        'process_normally',
        'byok',
        1,
    ),
    (
        'free_allowlist',
        {},
        _decision(
            allowed=True,
            reason='free_allowlist',
            plan=PlanType.basic,
            plan_resolved=True,
        ),
        'process_normally',
        'free_allowlist',
        1,
    ),
    (
        'basic_with_projection',
        {'has_projection': True},
        _decision(
            allowed=False,
            reason='basic_not_entitled',
            plan=PlanType.basic,
            plan_resolved=True,
        ),
        'store_projection',
        'basic_not_entitled',
        1,
    ),
    (
        'basic_no_projection',
        {},
        _decision(
            allowed=False,
            reason='basic_not_entitled',
            plan=PlanType.basic,
            plan_resolved=True,
        ),
        'deterministic_minimum',
        'basic_not_entitled',
        1,
    ),
    (
        'basic_force_process',
        {'force_process': True},
        _decision(
            allowed=False,
            reason='basic_not_entitled',
            plan=PlanType.basic,
            plan_resolved=True,
        ),
        'deterministic_minimum',
        'basic_not_entitled',
        1,
    ),
    (
        'basic_is_reprocess',
        {'is_reprocess': True},
        _decision(
            allowed=False,
            reason='basic_not_entitled',
            plan=PlanType.basic,
            plan_resolved=True,
        ),
        'deterministic_minimum',
        'basic_not_entitled',
        1,
    ),
    (
        'denied_authorization_unavailable',
        {},
        _decision(
            allowed=False,
            reason='authorization_unavailable',
            plan=None,
            plan_resolved=False,
        ),
        'deterministic_minimum',
        'authorization_unavailable',
        1,
    ),
    (
        'denied_uid_required',
        {},
        _decision(
            allowed=False,
            reason='uid_required',
            plan=None,
            plan_resolved=False,
        ),
        'deterministic_minimum',
        'uid_required',
        1,
    ),
    (
        'decision_for_raising',
        {},
        RuntimeError('decision_for boom'),
        'deterministic_minimum',
        'policy_unavailable',
        1,
    ),
    (
        'policy_internal_error',
        {},
        _ExplodingDecision(),
        'deterministic_minimum',
        'policy_unavailable',
        1,
    ),
]


# red-proof: `if decision.allowed:` → `if True:` (identified-basic would process_normally)
@pytest.mark.parametrize(
    'case_id, kwargs, decision, expected_mode, expected_reason, expected_calls',
    _MATRIX_CASES,
    ids=[row[0] for row in _MATRIX_CASES],
)
def test_policy_matrix(
    policy,
    case_id,
    kwargs,
    decision,
    expected_mode,
    expected_reason,
    expected_calls,
) -> None:
    del case_id
    if decision is None:

        def decision_for(feature: str) -> Decision:
            raise AssertionError(f'decision_for must not run for non-desktop: {feature}')

        decision_for.calls = []  # type: ignore[attr-defined]
    else:
        decision_for = _spy(decision)
    plan = _resolve(policy, decision_for, **kwargs)
    assert (plan.mode, plan.reason, plan.managed_calls_allowed) == (
        expected_mode,
        expected_reason,
        expected_mode == 'process_normally',
    )
    if expected_reason == 'non_desktop_source':
        assert plan.decision is None
    elif expected_reason == 'policy_unavailable':
        assert plan.decision is None
    else:
        assert plan.decision is decision
    calls = getattr(decision_for, 'calls', [])
    assert len(calls) == expected_calls
    if expected_calls:
        assert calls == [policy.STRUCTURE_FEATURE]


# --- 2. exactly one decision_for call with the structure feature -------------------------------


# red-proof: call decision_for a second time (or pass a different feature)
def test_decision_for_is_called_once_with_the_feature(policy) -> None:
    decision = _decision(
        allowed=True,
        reason='plan_paid',
        plan=PlanType.plus,
        plan_resolved=True,
    )
    decision_for = _spy(decision)
    plan = _resolve(policy, decision_for)
    assert plan.mode == 'process_normally'
    assert decision_for.calls == [policy.STRUCTURE_FEATURE]


# red-proof: let decision_for raise out of resolve_free_tier_processing_plan
def test_raising_decision_for_yields_policy_unavailable(policy) -> None:
    def decision_for(_feature: str) -> Decision:
        raise RuntimeError('owner resolution boom')

    plan = _resolve(policy, decision_for)
    assert plan.mode == 'deterministic_minimum'
    assert plan.reason == 'policy_unavailable'
    assert plan.decision is None
    assert plan.managed_calls_allowed is False


# --- 3. every S1 reason through the policy; produced set equals PROCESSING_REASONS -------------


# red-proof: PROCESSING_REASONS = _S6_PROCESSING_REASONS  (drop `| DECISION_REASONS`)
def test_every_s1_reason_through_the_policy_and_vocabulary_is_closed(policy) -> None:
    assert _S1_ALLOWED_REASONS <= DECISION_REASONS
    assert policy.PROCESSING_REASONS == _S6_PROCESSING_REASONS | DECISION_REASONS

    produced: set[str] = set()
    for reason in sorted(DECISION_REASONS):
        decision = _s1_decision(reason)
        plan = _resolve(policy, _spy(decision))
        produced.add(plan.reason)
        produced.add(reason)
        if reason in _S1_ALLOWED_REASONS:
            assert plan.mode == 'process_normally'
            assert plan.managed_calls_allowed is True
            if reason == 'plan_unknown_fail_open':
                assert plan.reason == 'plan_identification_fail_open'
            else:
                assert plan.reason == reason
        else:
            assert plan.mode == 'deterministic_minimum'
            assert plan.reason == reason
            assert plan.managed_calls_allowed is False

    non_desktop = _resolve(
        policy,
        lambda _feature: (_ for _ in ()).throw(AssertionError('decision_for must not run')),
        source='omi',
    )
    produced.add(non_desktop.reason)

    def exploding(_feature: str) -> Decision:
        raise RuntimeError('policy boom')

    unavailable = _resolve(policy, exploding)
    produced.add(unavailable.reason)

    assert produced == set(policy.PROCESSING_REASONS)
    assert 'defer_first_open' not in produced


# red-proof: drop `'non_desktop_source'` from `_S6_PROCESSING_REASONS`
def test_every_matrix_reason_is_in_the_vocabulary(policy) -> None:
    produced = {row[4] for row in _MATRIX_CASES}
    assert produced <= set(policy.PROCESSING_REASONS)
    assert 'defer_first_open' not in produced


# --- 4. structure feature is configured and not on the free allowlist --------------------------


# red-proof: set STRUCTURE_FEATURE = 'daily_summary' (allowlisted ⇒ S6 would be a no-op)
def test_structure_feature_is_configured_and_not_on_the_free_allowlist(policy) -> None:
    feature = policy.STRUCTURE_FEATURE
    assert feature == STRUCTURE_FEATURE
    assert feature in get_all_configured_features()
    assert feature not in FREE_ALLOWLIST_FEATURES
    assert not feature.startswith(FREE_ALLOWLIST_PREFIX)
    assert get_provider(feature) == 'openai'


# --- 5. rollout helper reads the module constant; env parse is true-only -----------------------


# red-proof: snapshot the flag at import (`return True`) so monkeypatching the constant is ignored
def test_free_tier_local_processing_enabled_reads_module_constant_and_is_monkeypatchable(monkeypatch, policy) -> None:
    monkeypatch.setattr(policy, 'FREE_TIER_LOCAL_PROCESSING', True)
    assert policy.free_tier_local_processing_enabled() is True
    monkeypatch.setattr(policy, 'FREE_TIER_LOCAL_PROCESSING', False)
    assert policy.free_tier_local_processing_enabled() is False
    monkeypatch.setattr(policy, 'free_tier_local_processing_enabled', lambda: True)
    assert policy.free_tier_local_processing_enabled() is True


def _load_policy_with_env(value: str | None) -> ModuleType:
    if value is None:
        os.environ.pop('FREE_TIER_LOCAL_PROCESSING', None)
    else:
        os.environ['FREE_TIER_LOCAL_PROCESSING'] = value
    subscription_stub = ModuleType('utils.subscription')
    setattr(subscription_stub, 'request_has_llm_byok_key', lambda: False)
    byok_stub = ModuleType('utils.byok')
    setattr(byok_stub, 'get_byok_key', lambda _provider: None)
    setattr(byok_stub, 'has_validated_byok_keys', lambda: False)
    fakes: dict[str, ModuleType | None] = {
        'database.users': ModuleType('database.users'),
        'utils.subscription': subscription_stub,
        'utils.byok': byok_stub,
    }
    with stub_modules(fakes):
        load_module_fresh('utils.managed_compute', _MC_PATH)
        return load_module_fresh('utils.free_tier_processing_policy', _POLICY_PATH)


# red-proof: treat `'1'` / `'yes'` as on (`value.lower() in {'true', '1', 'yes'}`)
@pytest.mark.parametrize(
    'value, expected',
    [
        ('true', True),
        ('TRUE', True),
        ('True', True),
        ('false', False),
        ('1', False),
        ('yes', False),
        ('on', False),
        ('', False),
        (None, False),
    ],
)
def test_env_parse_accepts_only_true_case_insensitive(value, expected) -> None:
    previous = os.environ.get('FREE_TIER_LOCAL_PROCESSING')
    try:
        mod = _load_policy_with_env(value)
        assert mod.FREE_TIER_LOCAL_PROCESSING is expected
        assert mod.free_tier_local_processing_enabled() is expected
    finally:
        if previous is None:
            os.environ.pop('FREE_TIER_LOCAL_PROCESSING', None)
        else:
            os.environ['FREE_TIER_LOCAL_PROCESSING'] = previous

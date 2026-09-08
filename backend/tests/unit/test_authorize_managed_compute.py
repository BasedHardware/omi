"""authorize_managed_compute matrix (shard S1 of the local-models free tier).

Request-scoped managed-compute authorization: basic + non-BYOK is allowed only
for the free allowlist (exact names + ``chat_`` prefix). Unknown features deny
for every plan and every funding owner. Plan-lookup failure fail-opens for a
known feature (Target 3); every other dependency failure denies.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from config.plan_catalog import PAID_PLAN_TYPES, PlanType
from testing.import_isolation import load_module_fresh, stub_modules
from utils.llm.model_config import get_all_configured_features

_BACKEND = Path(__file__).resolve().parents[2]

# Enumerated in the test so a new exact-name free feature must be added here
# and in ``FREE_ALLOWLIST_FEATURES``. The ``chat_`` prefix rule is the other half.
EXPLICIT_FREE_ALLOWLIST = frozenset(
    {
        'daily_summary',
        'translation',
        'session_titles',
        'fair_use',
    }
)
CONFIGURED_FEATURES = sorted(get_all_configured_features())
OFF_ALLOWLIST_FEATURE = next(
    f for f in CONFIGURED_FEATURES if f not in EXPLICIT_FREE_ALLOWLIST and not f.startswith('chat_')
)
ON_ALLOWLIST_FEATURE = 'daily_summary'
CHAT_FEATURE = next(f for f in CONFIGURED_FEATURES if f.startswith('chat_'))
UNKNOWN_FEATURE = 'not_a_configured_feature'
# Extracted so pyright does not bidirectional-infer PlanType as pytest.ParameterSet.
_PAID_PLANS: tuple[PlanType, ...] = tuple(sorted(PAID_PLAN_TYPES, key=lambda plan: plan.value))
_UNKNOWN_FEATURE_PLANS: tuple[PlanType, ...] = (PlanType.basic, *_PAID_PLANS)


def _is_test_allowlisted(feature: str) -> bool:
    return feature in EXPLICIT_FREE_ALLOWLIST or feature.startswith('chat_')


@pytest.fixture(scope='module')
def mc():
    """A fresh ``utils.managed_compute`` against self-contained stubs.

    ``test_omi_qos_tiers`` installs a module-scope ``utils.byok`` stub with a
    partial attribute set. This fixture replaces that (and ``utils.subscription``)
    for the duration of the load so ``has_validated_byok_keys`` is always present.
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
        yield load_module_fresh('utils.managed_compute', os.path.join(str(_BACKEND), 'utils', 'managed_compute.py'))


def _situate(
    monkeypatch,
    mc,
    *,
    plan: PlanType | None = PlanType.basic,
    byok_enrolled: bool = False,
    byok_validated: bool = False,
    byok_key_provider: str | None = None,
    subscription_error: BaseException | None = None,
    byok_error: BaseException | None = None,
) -> None:
    def get_sub(_uid: str) -> Any:
        if subscription_error is not None:
            raise subscription_error
        return None if plan is None else SimpleNamespace(plan=plan)

    def is_byok(_uid: str) -> bool:
        if byok_error is not None:
            raise byok_error
        return byok_enrolled

    monkeypatch.setattr(mc.users_db, 'get_user_valid_subscription', get_sub, raising=False)
    monkeypatch.setattr(mc.users_db, 'is_byok_active', is_byok, raising=False)
    monkeypatch.setattr(mc, 'has_validated_byok_keys', lambda: byok_validated)
    monkeypatch.setattr(
        mc,
        'get_byok_key',
        lambda provider: 'user-key' if byok_key_provider and provider == byok_key_provider else None,
    )
    monkeypatch.setattr(mc, 'request_has_llm_byok_key', lambda: bool(byok_validated and byok_key_provider))


def _authorize(mc, feature: str, funding_owner: str = 'omi', uid: str | None = 'uid', **kw: Any):
    return mc.authorize_managed_compute(uid, feature, funding_owner, **kw)


# --- 1. named proof: every configured feature as basic non-BYOK --------------------------------


# red-proof: `return True` in `_is_free_allowlisted` (off-allowlist basic would be allowed)
@pytest.mark.parametrize('feature', CONFIGURED_FEATURES)
def test_basic_non_byok_is_allowed_iff_feature_is_on_the_allowlist(monkeypatch, mc, feature) -> None:
    assert mc.FREE_ALLOWLIST_FEATURES == EXPLICIT_FREE_ALLOWLIST
    _situate(monkeypatch, mc, plan=PlanType.basic)
    decision = _authorize(mc, feature)
    expect_allowed = _is_test_allowlisted(feature)
    assert decision.allowed is expect_allowed
    assert decision.plan is PlanType.basic
    assert decision.plan_resolved is True
    if expect_allowed:
        assert decision.reason == 'free_allowlist'
    else:
        assert decision.reason == 'basic_not_entitled'


# --- 2. unknown feature denied for every plan and funding owner --------------------------------


# red-proof: skip the `feature not in get_all_configured_features()` branch
@pytest.mark.parametrize('plan', _UNKNOWN_FEATURE_PLANS)
@pytest.mark.parametrize(
    'funding_owner, uid',
    [('omi', 'uid'), ('byok', 'uid'), ('system', None)],
)
def test_unknown_feature_is_denied_for_every_plan_and_funding_owner(monkeypatch, mc, plan, funding_owner, uid) -> None:
    _situate(
        monkeypatch,
        mc,
        plan=plan,
        byok_enrolled=True,
        byok_validated=True,
        byok_key_provider='openai',
    )
    decision = _authorize(mc, UNKNOWN_FEATURE, funding_owner, uid=uid)
    assert decision.allowed is False
    assert decision.reason == 'unknown_feature'
    assert decision.plan is None
    assert decision.plan_resolved is False


# --- 3. BYOK: enrolment + validated key, never silent downgrade to omi -------------------------


# red-proof: deny even when enrolled+validated (`allowed=False` on the byok success return)
def test_byok_enrolled_with_validated_key_is_allowed_off_allowlist(monkeypatch, mc) -> None:
    _situate(
        monkeypatch,
        mc,
        plan=PlanType.basic,
        byok_enrolled=True,
        byok_validated=True,
        byok_key_provider='openai',
    )
    monkeypatch.setattr(mc, 'get_provider', lambda _feature: 'openai')
    decision = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'byok')
    assert (decision.allowed, decision.reason) == (True, 'byok')


# red-proof: fall through to omi (`plan_paid`) when funding_owner='byok' has no request key
def test_byok_enrolled_without_key_on_request_is_denied_not_downgraded_to_omi(monkeypatch, mc) -> None:
    _situate(monkeypatch, mc, plan=PlanType.plus, byok_enrolled=True, byok_validated=False)
    decision = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'byok')
    assert (decision.allowed, decision.reason) == (False, 'byok_not_validated')


# red-proof: skip the `if not byok_active` deny (key without enrolment would be allowed)
def test_byok_key_without_enrolment_is_denied(monkeypatch, mc) -> None:
    _situate(
        monkeypatch,
        mc,
        plan=PlanType.basic,
        byok_enrolled=False,
        byok_validated=True,
        byok_key_provider='openai',
    )
    monkeypatch.setattr(mc, 'get_provider', lambda _feature: 'openai')
    decision = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'byok')
    assert (decision.allowed, decision.reason) == (False, 'byok_not_enrolled')


# red-proof: drop `get_byok_key(get_provider(feature))` so any validated key would pass
def test_byok_key_for_the_wrong_provider_is_not_validated(monkeypatch, mc) -> None:
    _situate(
        monkeypatch,
        mc,
        plan=PlanType.basic,
        byok_enrolled=True,
        byok_validated=True,
        byok_key_provider='anthropic',
    )
    monkeypatch.setattr(mc, 'get_provider', lambda _feature: 'openai')
    decision = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'byok')
    assert (decision.allowed, decision.reason) == (False, 'byok_not_validated')


# --- 4. paid plans: every paid PlanType allowed off-allowlist ----------------------------------


# red-proof: drop `plus` (or any paid plan) from PAID_PLAN_TYPES membership so it denies
@pytest.mark.parametrize('plan', _PAID_PLANS)
def test_every_paid_plan_is_allowed_for_an_off_allowlist_known_feature(monkeypatch, mc, plan) -> None:
    _situate(monkeypatch, mc, plan=plan)
    decision = _authorize(mc, OFF_ALLOWLIST_FEATURE)
    assert decision.allowed is True
    assert decision.reason == 'plan_paid'
    assert decision.plan is plan
    assert decision.plan_resolved is True


# --- 5. inactive subscription (None) behaves as basic ------------------------------------------


# red-proof: treat `subscription is None` as paid (`plan_paid`) instead of basic
def test_inactive_subscription_behaves_as_basic(monkeypatch, mc) -> None:
    _situate(monkeypatch, mc, plan=None)
    denied = _authorize(mc, OFF_ALLOWLIST_FEATURE)
    assert denied.allowed is False
    assert denied.reason == 'basic_not_entitled'
    assert denied.plan is PlanType.basic
    assert denied.plan_resolved is True
    allowed = _authorize(mc, ON_ALLOWLIST_FEATURE)
    assert allowed.allowed is True
    assert allowed.reason == 'free_allowlist'
    assert allowed.plan is PlanType.basic


# red-proof: drop the `if not uid` guard (the empty uid reaches the provisioning lookup)
@pytest.mark.parametrize('uid', [None, ''])
@pytest.mark.parametrize('funding_owner', ['omi', 'byok'])
def test_a_user_funded_request_without_a_uid_is_denied_before_any_lookup(monkeypatch, mc, uid, funding_owner) -> None:
    _situate(
        monkeypatch, mc, plan=PlanType.unlimited, byok_enrolled=True, byok_validated=True, byok_key_provider='openai'
    )
    looked_up: list[str] = []
    monkeypatch.setattr(
        mc.users_db,
        'get_user_valid_subscription',
        lambda u: looked_up.append(u) or SimpleNamespace(plan=PlanType.unlimited),
        raising=False,
    )
    decision = _authorize(mc, ON_ALLOWLIST_FEATURE, funding_owner, uid=uid)
    assert (decision.allowed, decision.reason, decision.plan_resolved) == (False, 'uid_required', False)
    assert looked_up == []


# red-proof: skip the non-empty uid check on the system branch (a uid would ride the allowlist)
def test_system_with_a_uid_is_denied_none_and_empty_uid_on_allowlist_are_allowed(monkeypatch, mc) -> None:
    _situate(monkeypatch, mc, plan=PlanType.basic)
    denied = _authorize(mc, ON_ALLOWLIST_FEATURE, 'system', uid='uid')
    assert (denied.allowed, denied.reason, denied.plan_resolved) == (False, 'system_uid_forbidden', False)
    off = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'system', uid='someone')
    assert off.reason == 'system_uid_forbidden'
    for empty in (None, ''):
        allowed = _authorize(mc, ON_ALLOWLIST_FEATURE, 'system', uid=empty)
        assert (allowed.allowed, allowed.reason) == (True, 'free_allowlist')
        denied_off = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'system', uid=empty)
        assert denied_off.reason == 'system_feature_not_free'


# --- 6. plan lookup raising: fail-open for known, still deny unknown ---------------------------


# red-proof: on lookup raise, deny (or deny unknown is skipped so unknown fail-opens)
def test_plan_lookup_raising_fail_opens_for_known_feature_and_still_denies_unknown(monkeypatch, mc) -> None:
    _situate(monkeypatch, mc, plan=PlanType.basic, subscription_error=RuntimeError('firestore unavailable'))
    known = _authorize(mc, OFF_ALLOWLIST_FEATURE)
    assert known.allowed is True
    assert known.reason == 'plan_unknown_fail_open'
    assert known.plan is None
    assert known.plan_resolved is False
    unknown = _authorize(mc, UNKNOWN_FEATURE)
    assert unknown.allowed is False
    assert unknown.reason == 'unknown_feature'


# --- unrecognized / malformed plan: fail-open, never coerce to basic ---------------------------


# red-proof: `_identified_plan` returns `PlanType.basic` for a junk string (off-allowlist would deny)
def test_omi_malformed_plan_string_fail_opens(monkeypatch, mc) -> None:
    _situate(monkeypatch, mc, plan=PlanType.basic)
    monkeypatch.setattr(
        mc.users_db,
        'get_user_valid_subscription',
        lambda _uid: SimpleNamespace(plan='enterprise_v9'),
        raising=False,
    )
    decision = _authorize(mc, OFF_ALLOWLIST_FEATURE)
    assert (decision.allowed, decision.reason, decision.plan, decision.plan_resolved) == (
        True,
        'plan_unknown_fail_open',
        None,
        False,
    )


# red-proof: `_identified_plan` returns `PlanType.basic` for a None plan attribute
def test_omi_none_plan_attribute_fail_opens(monkeypatch, mc) -> None:
    _situate(monkeypatch, mc, plan=PlanType.basic)
    monkeypatch.setattr(
        mc.users_db,
        'get_user_valid_subscription',
        lambda _uid: SimpleNamespace(plan=None),
        raising=False,
    )
    decision = _authorize(mc, OFF_ALLOWLIST_FEATURE)
    assert (decision.allowed, decision.reason, decision.plan, decision.plan_resolved) == (
        True,
        'plan_unknown_fail_open',
        None,
        False,
    )


# red-proof: coerce a pre-read junk plan to basic instead of fail-open
def test_omi_pre_read_junk_plan_fail_opens_without_re_reading(monkeypatch, mc) -> None:
    _situate(monkeypatch, mc, plan=PlanType.basic)

    def never(*_a, **_k):
        raise AssertionError('should not be re-read')

    monkeypatch.setattr(mc.users_db, 'get_user_valid_subscription', never, raising=False)
    decision = _authorize(
        mc,
        OFF_ALLOWLIST_FEATURE,
        'omi',
        subscription=SimpleNamespace(plan=object()),
        byok_active=False,
    )
    assert (decision.allowed, decision.reason, decision.plan, decision.plan_resolved) == (
        True,
        'plan_unknown_fail_open',
        None,
        False,
    )


_NO_OVERRIDE: Any = object()


def _byok_with_pre_read_plan(monkeypatch, mc, plan_value: Any, *, subscription_override: Any = _NO_OVERRIDE):
    _situate(
        monkeypatch,
        mc,
        plan=PlanType.basic,
        byok_enrolled=True,
        byok_validated=True,
        byok_key_provider='openai',
    )
    monkeypatch.setattr(mc, 'get_provider', lambda _feature: 'openai')
    return _authorize(
        mc,
        OFF_ALLOWLIST_FEATURE,
        'byok',
        subscription=(
            SimpleNamespace(plan=plan_value) if subscription_override is _NO_OVERRIDE else subscription_override
        ),
        byok_active=True,
    )


# red-proof: `_plan_if_already_read` returns `(PlanType.basic, True)` for a junk string
def test_byok_malformed_plan_string_is_unresolved(monkeypatch, mc) -> None:
    decision = _byok_with_pre_read_plan(monkeypatch, mc, 'enterprise_v9')
    assert (decision.allowed, decision.reason, decision.plan, decision.plan_resolved) == (True, 'byok', None, False)


# red-proof: `_plan_if_already_read` returns `(PlanType.basic, True)` for a None plan attribute
def test_byok_none_plan_attribute_is_unresolved(monkeypatch, mc) -> None:
    decision = _byok_with_pre_read_plan(monkeypatch, mc, None)
    assert (decision.allowed, decision.reason, decision.plan, decision.plan_resolved) == (True, 'byok', None, False)


# red-proof: `_plan_if_already_read` returns `(PlanType.basic, True)` for a junk plan object
# red-proof: `if not subscription:` instead of `is None` (a falsey `{}` becomes resolved basic)
@pytest.mark.parametrize('falsey', [{}, False, 0, ''])
def test_a_falsey_malformed_subscription_is_not_a_resolved_basic_plan(monkeypatch, mc, falsey) -> None:
    """Only None means "no valid subscription". Any other falsey value is malformed: fail-open on omi
    (paid-path, unresolved), unresolved metadata on BYOK — never a confidently-resolved basic."""
    _situate(monkeypatch, mc, plan=PlanType.basic)
    omi = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'omi', subscription=falsey, byok_active=False)
    assert (omi.allowed, omi.reason, omi.plan, omi.plan_resolved) == (True, 'plan_unknown_fail_open', None, False)
    byok = _byok_with_pre_read_plan(monkeypatch, mc, None, subscription_override=falsey)
    assert (byok.allowed, byok.reason, byok.plan, byok.plan_resolved) == (True, 'byok', None, False)


def test_byok_pre_read_junk_plan_is_unresolved(monkeypatch, mc) -> None:
    decision = _byok_with_pre_read_plan(monkeypatch, mc, object())
    assert (decision.allowed, decision.reason, decision.plan, decision.plan_resolved) == (True, 'byok', None, False)


# --- 7. any other dependency raising → authorization_unavailable -------------------------------


# red-proof: swallow a non-plan exception into `plan_unknown_fail_open` (fail-open onto paid)
@pytest.mark.parametrize(
    'broken',
    ['get_all_configured_features', 'is_byok_active', 'has_validated_byok_keys', 'get_provider'],
)
def test_any_other_dependency_raising_denies_authorization_unavailable(monkeypatch, mc, broken) -> None:
    _situate(
        monkeypatch,
        mc,
        plan=PlanType.basic,
        byok_enrolled=True,
        byok_validated=True,
        byok_key_provider='openai',
    )

    def boom(*_a, **_k):
        raise RuntimeError('dependency unavailable')

    if broken == 'get_all_configured_features':
        monkeypatch.setattr(mc, 'get_all_configured_features', boom)
        decision = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'omi')
    elif broken == 'is_byok_active':
        monkeypatch.setattr(mc, 'get_provider', lambda _feature: 'openai')
        monkeypatch.setattr(mc.users_db, 'is_byok_active', boom, raising=False)
        decision = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'byok')
    elif broken == 'has_validated_byok_keys':
        monkeypatch.setattr(mc, 'has_validated_byok_keys', boom)
        decision = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'byok')
    else:
        monkeypatch.setattr(mc, 'get_provider', boom)
        decision = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'byok')
    assert (decision.allowed, decision.reason) == (False, 'authorization_unavailable')
    assert decision.plan_resolved is False


# --- 8. pre-read subscription= / byok_active= are not re-read ----------------------------------


# red-proof: ignore the kwargs and call the lookups anyway (AssertionError)
def test_pre_read_subscription_and_byok_active_are_not_re_read(monkeypatch, mc) -> None:
    _situate(monkeypatch, mc, plan=PlanType.basic)

    def never(*_a, **_k):
        raise AssertionError('should not be re-read')

    monkeypatch.setattr(mc.users_db, 'get_user_valid_subscription', never, raising=False)
    monkeypatch.setattr(mc.users_db, 'is_byok_active', never, raising=False)
    paid = _authorize(
        mc,
        OFF_ALLOWLIST_FEATURE,
        'omi',
        subscription=SimpleNamespace(plan=PlanType.plus),
        byok_active=False,
    )
    assert (paid.allowed, paid.reason, paid.plan) == (True, 'plan_paid', PlanType.plus)
    inactive = _authorize(mc, OFF_ALLOWLIST_FEATURE, 'omi', subscription=None, byok_active=False)
    assert inactive.reason == 'basic_not_entitled'
    monkeypatch.setattr(mc, 'get_provider', lambda _feature: 'openai')
    monkeypatch.setattr(mc, 'has_validated_byok_keys', lambda: True)
    monkeypatch.setattr(mc, 'get_byok_key', lambda provider: 'user-key' if provider == 'openai' else None)
    monkeypatch.setattr(mc, 'request_has_llm_byok_key', lambda: True)
    byok = _authorize(
        mc,
        OFF_ALLOWLIST_FEATURE,
        'byok',
        subscription=SimpleNamespace(plan=PlanType.basic),
        byok_active=True,
    )
    assert (byok.allowed, byok.reason) == (True, 'byok')
    assert byok.plan is PlanType.basic
    unenrolled = _authorize(
        mc,
        OFF_ALLOWLIST_FEATURE,
        'byok',
        subscription=None,
        byok_active=False,
    )
    assert unenrolled.reason == 'byok_not_enrolled'


# --- 9. raise_if_denied / as_dict --------------------------------------------------------------


# red-proof: `raise_if_denied` returns on deny, or `as_dict` drops `plan_resolved`
def test_raise_if_denied_carries_the_decision_and_as_dict_round_trips(monkeypatch, mc) -> None:
    _situate(monkeypatch, mc, plan=PlanType.basic)
    denied = _authorize(mc, OFF_ALLOWLIST_FEATURE)
    with pytest.raises(mc.ManagedComputeDenied) as exc_info:
        denied.raise_if_denied()
    assert exc_info.value.decision is denied
    assert str(exc_info.value) == 'basic_not_entitled'
    payload = denied.as_dict()
    assert payload == {
        'allowed': False,
        'reason': 'basic_not_entitled',
        'feature': OFF_ALLOWLIST_FEATURE,
        'funding_owner': 'omi',
        'plan': 'basic',
        'plan_resolved': True,
    }
    rebuilt = mc.Decision(
        allowed=payload['allowed'],
        reason=payload['reason'],
        feature=payload['feature'],
        funding_owner=payload['funding_owner'],
        plan=PlanType(payload['plan']) if payload['plan'] is not None else None,
        plan_resolved=payload['plan_resolved'],
    )
    assert rebuilt.as_dict() == payload
    allowed = _authorize(mc, CHAT_FEATURE)
    assert allowed.raise_if_denied() is allowed
    assert allowed.as_dict()['reason'] == 'free_allowlist'


# --- 10. reason vocabulary ---------------------------------------------------------------------


# red-proof: emit a reason not in DECISION_REASONS (e.g. `return 'nope'` from `_authorize_omi`)
def test_every_reason_produced_across_the_matrix_is_in_the_module_constant(monkeypatch, mc) -> None:
    produced: set[str] = set()

    def collect(decision) -> None:
        produced.add(decision.reason)
        assert decision.reason in mc.DECISION_REASONS

    _situate(monkeypatch, mc, plan=PlanType.basic)
    collect(_authorize(mc, UNKNOWN_FEATURE))
    collect(_authorize(mc, ON_ALLOWLIST_FEATURE))
    collect(_authorize(mc, OFF_ALLOWLIST_FEATURE))
    collect(_authorize(mc, OFF_ALLOWLIST_FEATURE, 'system', uid=None))
    collect(_authorize(mc, ON_ALLOWLIST_FEATURE, 'system', uid=None))
    collect(_authorize(mc, ON_ALLOWLIST_FEATURE, 'system', uid='uid'))
    collect(_authorize(mc, OFF_ALLOWLIST_FEATURE, 'not-a-owner'))
    collect(_authorize(mc, ON_ALLOWLIST_FEATURE, 'omi', uid=None))

    _situate(monkeypatch, mc, plan=PlanType.plus)
    collect(_authorize(mc, OFF_ALLOWLIST_FEATURE))

    _situate(
        monkeypatch,
        mc,
        plan=PlanType.basic,
        byok_enrolled=True,
        byok_validated=True,
        byok_key_provider='openai',
    )
    monkeypatch.setattr(mc, 'get_provider', lambda _feature: 'openai')
    collect(_authorize(mc, OFF_ALLOWLIST_FEATURE, 'byok'))

    _situate(monkeypatch, mc, plan=PlanType.basic, byok_enrolled=True, byok_validated=False)
    collect(_authorize(mc, OFF_ALLOWLIST_FEATURE, 'byok'))

    _situate(
        monkeypatch,
        mc,
        plan=PlanType.basic,
        byok_enrolled=False,
        byok_validated=True,
        byok_key_provider='openai',
    )
    monkeypatch.setattr(mc, 'get_provider', lambda _feature: 'openai')
    collect(_authorize(mc, OFF_ALLOWLIST_FEATURE, 'byok'))

    _situate(monkeypatch, mc, plan=PlanType.basic, subscription_error=RuntimeError('blip'))
    collect(_authorize(mc, OFF_ALLOWLIST_FEATURE))

    _situate(monkeypatch, mc, plan=PlanType.basic)
    monkeypatch.setattr(mc, 'get_all_configured_features', lambda: (_ for _ in ()).throw(RuntimeError('down')))
    collect(_authorize(mc, OFF_ALLOWLIST_FEATURE))

    assert produced <= set(mc.DECISION_REASONS)
    expected = {
        'unknown_feature',
        'free_allowlist',
        'basic_not_entitled',
        'system_feature_not_free',
        'system_uid_forbidden',
        'invalid_funding_owner',
        'uid_required',
        'plan_paid',
        'byok',
        'byok_not_validated',
        'byok_not_enrolled',
        'plan_unknown_fail_open',
        'authorization_unavailable',
    }
    assert produced == expected
    assert expected == set(mc.DECISION_REASONS)

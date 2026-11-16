"""One transcription-allowance answer per uid (shard S16 of the local-models free tier).

Two functions used to answer "may this user use Omi's managed STT?" and could
disagree for a user whose subscription is not valid (an inactive basic account;
an absent document is provisioned as basic, and an expired paid one downgraded
to basic, before either is asked):
`has_transcription_credits` said no, `get_remaining_transcription_seconds`
fell back to the basic plan's minutes. Both are now thin wrappers over
`resolve_transcription_allowance`, and this matrix proves no caller can
observe them disagreeing on any row. The resolver never raises: anything it
cannot read resolves to the free local path, never to a billed socket.
"""

from __future__ import annotations

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from models.users import PlanType
from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]
BASIC_CAP = 18_000  # 300 min, the catalog value (and production's overlay value)
PLUS_CAP = 90_000  # 1,500 min


@pytest.fixture(scope='module')
def sub():
    """A fresh `utils.subscription` against stubbed circular-import deps (same pattern as test_subscription_plans)."""
    announcements_stub = ModuleType('database.announcements')
    announcements_stub.compare_versions = lambda a, b: 0
    client_stub = ModuleType('database._client')
    client_stub.get_customer_firestore_client = MagicMock()
    fakes = {
        'database.announcements': announcements_stub,
        'database._client': client_stub,
        'database.users': ModuleType('database.users'),
        'database.user_usage': ModuleType('database.user_usage'),
    }
    with stub_modules(fakes):
        yield load_module_fresh('utils.subscription', os.path.join(str(_BACKEND), 'utils', 'subscription.py'))


def _situate(
    monkeypatch,
    sub,
    *,
    plan: PlanType | None,
    used_seconds: int = 0,
    byok_enrolled: bool = False,
    byok_header: bool = False,
    reviewer: bool = False,
    usage_record: Any = None,
) -> None:
    monkeypatch.setenv('MARKETPLACE_APP_REVIEWERS', 'uid' if reviewer else 'someone-else')

    monkeypatch.setattr(sub.users_db, 'is_byok_active', lambda uid: byok_enrolled, raising=False)
    monkeypatch.setattr(
        sub, 'get_byok_key', lambda provider: 'dg-user-key' if byok_header and provider == 'deepgram' else None
    )
    monkeypatch.setattr(
        sub.users_db,
        'get_user_valid_subscription',
        lambda uid: None if plan is None else SimpleNamespace(plan=plan),
        raising=False,
    )
    record = usage_record if usage_record is not None else {'transcription_seconds': used_seconds}
    monkeypatch.setattr(sub, 'get_monthly_usage_for_subscription', lambda uid: record)


# --- the matrix ----------------------------------------------------------------------------

MATRIX = [
    # (label, situation, expected mode, expected remaining, expected reason)
    (
        'inactive subscription (lookup returns None)',
        dict(plan=None, used_seconds=0),
        'on_device',
        0,
        'subscription_inactive',
    ),
    (
        'basic under cap',
        dict(plan=PlanType.basic, used_seconds=BASIC_CAP - 600),
        'managed',
        600,
        'plan_within_allowance',
    ),
    ('basic at cap', dict(plan=PlanType.basic, used_seconds=BASIC_CAP), 'on_device', 0, 'plan_allowance_exhausted'),
    (
        'basic over cap',
        dict(plan=PlanType.basic, used_seconds=BASIC_CAP + 5_000),
        'on_device',
        0,
        'plan_allowance_exhausted',
    ),
    (
        'basic with no usage recorded yet',
        dict(plan=PlanType.basic, usage_record={}),
        'managed',
        BASIC_CAP,
        'plan_within_allowance',
    ),
    (
        'plus under cap',
        dict(plan=PlanType.plus, used_seconds=PLUS_CAP - 10_000),
        'managed',
        10_000,
        'plan_within_allowance',
    ),
    (
        'plus over cap',
        dict(plan=PlanType.plus, used_seconds=PLUS_CAP + 5_000),
        'on_device',
        0,
        'plan_allowance_exhausted',
    ),
    ('unlimited', dict(plan=PlanType.unlimited, used_seconds=10_000_000), 'managed', None, 'plan_unlimited'),
    ('unlimited_v2', dict(plan=PlanType.unlimited_v2, used_seconds=10_000_000), 'managed', None, 'plan_unlimited'),
    ('operator', dict(plan=PlanType.operator, used_seconds=10_000_000), 'managed', None, 'plan_unlimited'),
    ('architect', dict(plan=PlanType.architect, used_seconds=10_000_000), 'managed', None, 'plan_unlimited'),
    (
        'BYOK enrolled with deepgram header',
        dict(plan=None, byok_enrolled=True, byok_header=True),
        'managed',
        None,
        'byok',
    ),
    (
        'BYOK enrolled, no header (rides Omi key)',
        dict(plan=PlanType.basic, used_seconds=BASIC_CAP + 1, byok_enrolled=True),
        'on_device',
        0,
        'plan_allowance_exhausted',
    ),
    (
        'header but not enrolled',
        dict(plan=PlanType.basic, used_seconds=BASIC_CAP + 1, byok_header=True),
        'on_device',
        0,
        'plan_allowance_exhausted',
    ),
    ('desktop free, no account-age block', dict(plan=PlanType.basic), 'managed', BASIC_CAP, 'plan_within_allowance'),
    (
        'desktop Deepgram BYOK pays Deepgram',
        dict(plan=None, byok_enrolled=True, byok_header=True),
        'managed',
        None,
        'byok',
    ),
    (
        'marketplace reviewer',
        dict(plan=PlanType.basic, used_seconds=BASIC_CAP + 1, reviewer=True),
        'managed',
        None,
        'marketplace_reviewer',
    ),
    (
        'desktop marketplace reviewer',
        dict(plan=PlanType.basic, reviewer=True),
        'managed',
        None,
        'marketplace_reviewer',
    ),
    ('usage record negative (untrusted)', dict(plan=PlanType.basic, used_seconds=-5), 'on_device', 0, 'usage_invalid'),
    (
        'usage record is a string (untrusted)',
        dict(plan=PlanType.basic, usage_record={'transcription_seconds': '12'}),
        'on_device',
        0,
        'usage_invalid',
    ),
    (
        'usage record is null (nothing used)',
        dict(plan=PlanType.basic, usage_record={'transcription_seconds': None}),
        'managed',
        BASIC_CAP,
        'plan_within_allowance',
    ),
    (
        'usage record unreadable (not a dict)',
        dict(plan=PlanType.basic, usage_record=object()),
        'on_device',
        0,
        'usage_invalid',
    ),
]


@pytest.mark.parametrize('label, situation, mode, remaining, reason', MATRIX, ids=[row[0] for row in MATRIX])
def test_the_resolver_answers_every_row_once(monkeypatch, sub, label, situation, mode, remaining, reason) -> None:
    _situate(monkeypatch, sub, **situation)
    allowance = sub.resolve_transcription_allowance('uid', source='desktop')
    assert (allowance.mode, allowance.remaining_seconds, allowance.reason) == (mode, remaining, reason), label


@pytest.mark.parametrize('label, situation, mode, remaining, reason', MATRIX, ids=[row[0] for row in MATRIX])
def test_no_caller_can_observe_the_two_legacy_answers_disagreeing(
    monkeypatch, sub, label, situation, mode, remaining, reason
) -> None:
    """Both legacy questions are projections of the same resolver result, on every row."""
    _situate(monkeypatch, sub, **situation)
    allowance = sub.resolve_transcription_allowance('uid', source='desktop')
    has_credits = sub.has_transcription_credits('uid', source='desktop')
    remaining_seconds = sub.get_remaining_transcription_seconds('uid', source='desktop')
    assert has_credits == (allowance.mode == 'managed'), label
    assert remaining_seconds == allowance.remaining_seconds, label
    # The invariant the shard exists for: "has credits" and "some seconds remain" agree.
    assert has_credits == (remaining_seconds is None or remaining_seconds > 0), label


def test_an_inactive_subscription_has_no_managed_minutes_for_either_question(monkeypatch, sub) -> None:
    """The defect: `has_transcription_credits` said no, `get_remaining_transcription_seconds` said
    "the basic plan's minutes". A subscription the lookup calls invalid (an inactive basic account)
    now has no managed minutes for both — the free local path, never a billed socket."""
    _situate(monkeypatch, sub, plan=None, used_seconds=0)
    assert sub.has_transcription_credits('uid') is False
    assert sub.get_remaining_transcription_seconds('uid') == 0
    assert sub.resolve_transcription_allowance('uid').reason == 'subscription_inactive'


def test_desktop_free_and_release_probe_remain_managed_without_trial_state(monkeypatch, sub) -> None:
    """Both keep the production-disabled trial's managed admission answer."""
    _situate(monkeypatch, sub, plan=PlanType.basic)
    allowance = sub.resolve_transcription_allowance('omi-release-probe', source='desktop')
    assert (allowance.mode, allowance.remaining_seconds, allowance.reason) == ('managed', None, 'release_probe')
    # Ordinary Free accounts keep their managed minutes too.
    ordinary = sub.resolve_transcription_allowance('uid', source='desktop')
    assert (ordinary.mode, ordinary.remaining_seconds, ordinary.reason) == (
        'managed',
        BASIC_CAP,
        'plan_within_allowance',
    )


def test_transient_reasons_cover_only_unresolved_lookups_not_real_exhaustion(sub) -> None:
    """routers/sync.py reads this set to decide whether a failed lookup may durably lock a
    conversation (#15232): a lookup that could not be resolved must not, but a plan that is
    genuinely out of minutes still must. Regression for the set drifting either way.
    """
    assert sub.TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS == {'allowance_unavailable', 'usage_invalid'}
    assert 'plan_allowance_exhausted' not in sub.TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS
    assert 'subscription_inactive' not in sub.TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS


def test_both_wrappers_delegate_to_the_resolver_with_exact_arguments(monkeypatch, sub) -> None:
    """Not merely equivalent logic: the wrappers ARE the resolver's projections."""
    calls: list[tuple] = []
    sentinel = sub.TranscriptionAllowance('managed', 42, 'sentinel')
    monkeypatch.setattr(
        sub,
        'resolve_transcription_allowance',
        lambda uid, source=None, **kw: calls.append((uid, source, kw)) or sentinel,
    )
    assert sub.has_transcription_credits('u', source='omi') is True
    assert sub.get_remaining_transcription_seconds('u', source='desktop') == 42
    assert calls == [('u', 'omi', {}), ('u', 'desktop', {})]


@pytest.mark.parametrize(
    'broken',
    [
        'get_user_valid_subscription',
        'get_monthly_usage_for_subscription',
        'transcription_allowance_seconds',
    ],
)
def test_a_dependency_that_cannot_be_read_resolves_to_the_free_path_not_a_billed_socket(
    monkeypatch, sub, broken
) -> None:
    _situate(monkeypatch, sub, plan=PlanType.basic, used_seconds=0)

    def boom(*_a, **_k):
        raise RuntimeError('firestore unavailable')

    target = sub.users_db if broken == 'get_user_valid_subscription' else sub
    monkeypatch.setattr(target, broken, boom, raising=False)
    allowance = sub.resolve_transcription_allowance('uid', source='desktop')
    assert (allowance.mode, allowance.remaining_seconds, allowance.reason) == ('on_device', 0, 'allowance_unavailable')
    assert sub.has_transcription_credits('uid') is False
    assert sub.get_remaining_transcription_seconds('uid') == 0


def test_a_caller_may_pass_the_subscription_and_usage_it_already_read(monkeypatch, sub) -> None:
    _situate(monkeypatch, sub, plan=PlanType.basic, used_seconds=0)

    def never(*_a, **_k):
        raise AssertionError('should not be re-read')

    monkeypatch.setattr(sub.users_db, 'get_user_valid_subscription', never, raising=False)
    monkeypatch.setattr(sub.users_db, 'is_byok_active', never, raising=False)
    monkeypatch.setattr(sub, 'get_monthly_usage_for_subscription', never)
    allowance = sub.resolve_transcription_allowance(
        'uid',
        subscription=SimpleNamespace(plan=PlanType.plus),
        usage={'transcription_seconds': PLUS_CAP - 7},
        byok_active=False,
    )
    assert (allowance.mode, allowance.remaining_seconds) == ('managed', 7)
    # An explicitly passed None is a real answer (no valid subscription), not "unknown".
    assert (
        sub.resolve_transcription_allowance('uid', subscription=None, byok_active=False).reason
        == 'subscription_inactive'
    )


def test_the_allowance_comes_from_the_catalog_not_the_environment(monkeypatch, sub) -> None:
    """NOW.md item 4: no plan quota may be read from the environment. A divergent overlay must not win."""
    monkeypatch.setenv('BASIC_TIER_MINUTES_LIMIT_PER_MONTH', '1000000')
    monkeypatch.setenv('PLUS_TIER_MINUTES_LIMIT_PER_MONTH', '1000000')
    assert sub.transcription_allowance_seconds(PlanType.basic) == BASIC_CAP
    assert sub.transcription_allowance_seconds(PlanType.plus) == PLUS_CAP
    assert sub.transcription_allowance_seconds(PlanType.unlimited) is None
    _situate(monkeypatch, sub, plan=PlanType.basic, used_seconds=BASIC_CAP + 1)
    assert sub.has_transcription_credits('uid') is False  # the env's million minutes did not apply


def test_the_answer_serialises_for_the_plan_endpoint(monkeypatch, sub) -> None:
    _situate(monkeypatch, sub, plan=PlanType.plus, used_seconds=PLUS_CAP - 10_000)
    assert sub.resolve_transcription_allowance('uid').as_dict() == {
        'mode': 'managed',
        'remaining_seconds': 10_000,
        'reason': 'plan_within_allowance',
    }


@pytest.mark.parametrize('plan,cap', [(PlanType.basic, BASIC_CAP), (PlanType.plus, PLUS_CAP)])
@pytest.mark.parametrize('failure', ['invalid_usage', 'lookup_error'])
def test_closed_result_keeps_known_catalog_total(monkeypatch, sub, plan, cap, failure):
    _situate(monkeypatch, sub, plan=plan, usage_record={'transcription_seconds': -1})
    if failure == 'lookup_error':

        def failed_lookup(uid):
            raise RuntimeError('usage lookup unavailable')

        monkeypatch.setattr(sub, 'get_monthly_usage_for_subscription', failed_lookup)
    result = sub.resolve_transcription_allowance('uid')
    assert result.mode == 'on_device'
    assert result.remaining_seconds == 0
    assert result.limit_seconds == cap
    assert result.reason == ('usage_invalid' if failure == 'invalid_usage' else 'allowance_unavailable')


@pytest.mark.parametrize('launch', [None, 'not-a-date', '2026-99-99'])
@pytest.mark.parametrize('enforce', [False, True])
def test_launch_config_does_not_manufacture_zero_usage_when_enforcing(sub, monkeypatch, launch, enforce):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    if launch is None:
        monkeypatch.delenv('SUBSCRIPTION_LAUNCH_DATE', raising=False)
    else:
        monkeypatch.setenv('SUBSCRIPTION_LAUNCH_DATE', launch)
    if enforce:
        with pytest.raises(ValueError):
            sub.get_monthly_usage_for_subscription('synthetic')
    else:
        assert sub.get_monthly_usage_for_subscription('synthetic') == {}


def test_explicit_future_launch_is_intentionally_unlaunched(sub, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('SUBSCRIPTION_LAUNCH_DATE', '2099-01-01')
    assert sub.get_monthly_usage_for_subscription('synthetic') == {}


def test_funded_request_cannot_use_deepgram_key_for_another_provider(sub, monkeypatch):
    _situate(monkeypatch, sub, plan=PlanType.plus, used_seconds=PLUS_CAP, byok_enrolled=True, byok_header=True)
    assert sub.resolve_transcription_allowance('uid').reason == 'byok'
    assert sub.resolve_transcription_allowance('uid', omi_funded=True).reason == 'plan_allowance_exhausted'


def test_noncohort_owner_keeps_legacy_launch_parity(sub, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'uid:other')
    monkeypatch.delenv('SUBSCRIPTION_LAUNCH_DATE', raising=False)
    assert sub.get_monthly_usage_for_subscription('synthetic') == {}

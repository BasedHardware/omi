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
    paywalled: bool = False,
    reviewer: bool = False,
    usage_record: Any = None,
) -> None:
    monkeypatch.setenv('MARKETPLACE_APP_REVIEWERS', 'uid' if reviewer else 'someone-else')

    def trial_paywalled(uid, source=None, *, required_byok_provider=None, **_kw):
        # Mirrors the real helper: an enrolled BYOK request for the required provider is exempt.
        if required_byok_provider and byok_enrolled and byok_header:
            return False
        return paywalled

    monkeypatch.setattr(sub, 'is_trial_paywalled', trial_paywalled)
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
    ('trial paywalled desktop', dict(plan=PlanType.basic, paywalled=True), 'blocked', 0, 'trial_paywalled'),
    (
        'trial paywalled but Deepgram BYOK (exempt, pays Deepgram)',
        dict(plan=None, paywalled=True, byok_enrolled=True, byok_header=True),
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
        'marketplace reviewer, trial paywalled',
        dict(plan=PlanType.basic, paywalled=True, reviewer=True),
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


def test_a_paywall_lookup_failure_inside_the_real_helper_does_not_open_a_billed_socket(monkeypatch, sub) -> None:
    """`is_trial_paywalled` fails open for every other caller (a Firebase blip never paywalls a paying
    user). The allowance path asks it strictly, so the same blip resolves to the free path."""
    real_is_trial_paywalled = sub.is_trial_paywalled  # captured before _situate replaces it
    _situate(monkeypatch, sub, plan=PlanType.basic, used_seconds=0)
    monkeypatch.setattr(sub, 'is_trial_paywalled', real_is_trial_paywalled)
    monkeypatch.setattr(sub, 'TRIAL_PAYWALL_ENABLED', True)
    monkeypatch.setattr(sub.redis_db, 'get_generic_cache', lambda key: None, raising=False)
    monkeypatch.setattr(sub.redis_db, 'set_generic_cache', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(sub, 'has_validated_byok_keys', lambda: False)
    monkeypatch.setattr(sub.users_db, 'get_byok_state', lambda uid, firestore_client=None: {}, raising=False)
    monkeypatch.setattr(sub.users_db, 'is_byok_active', lambda uid, firestore_client=None: False, raising=False)
    monkeypatch.setattr(
        sub.users_db,
        'get_user_valid_subscription',
        lambda uid, firestore_client=None, provision=True: SimpleNamespace(plan=PlanType.basic, status='active'),
        raising=False,
    )
    monkeypatch.setattr(sub, 'desktop_trial_paywall_eligible', lambda plan, subscription=None: True)

    def firebase_down(uid):
        raise RuntimeError('firebase auth unavailable')

    monkeypatch.setattr(sub, '_get_user', firebase_down)
    # Every other caller still sees the fail-open answer the trial UX relies on.
    assert sub.is_trial_paywalled('uid', 'desktop') is False
    allowance = sub.resolve_transcription_allowance('uid', source='desktop')
    assert (allowance.mode, allowance.remaining_seconds, allowance.reason) == ('on_device', 0, 'allowance_unavailable')


def _real_paywall(monkeypatch, sub, *, byok_enrolled: bool, fingerprints: dict, creation_ms, header: bool) -> None:
    """Run the REAL `is_trial_paywalled` (paywall enabled, redis miss, eligible basic account)."""
    real_is_trial_paywalled = sub.is_trial_paywalled  # captured before _situate replaces it
    _situate(monkeypatch, sub, plan=PlanType.basic, used_seconds=0, byok_enrolled=byok_enrolled, byok_header=header)
    monkeypatch.setattr(sub, 'is_trial_paywalled', real_is_trial_paywalled)
    monkeypatch.setattr(sub, 'TRIAL_PAYWALL_ENABLED', True)
    monkeypatch.setattr(sub.redis_db, 'get_generic_cache', lambda key: None, raising=False)
    monkeypatch.setattr(sub.redis_db, 'set_generic_cache', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(sub, 'has_validated_byok_keys', lambda: header)
    monkeypatch.setattr(
        sub.users_db, 'get_byok_state', lambda uid, firestore_client=None: {'fingerprints': fingerprints}, raising=False
    )
    monkeypatch.setattr(sub.users_db, 'is_byok_active', lambda uid, firestore_client=None: byok_enrolled, raising=False)
    monkeypatch.setattr(
        sub.users_db,
        'get_user_valid_subscription',
        lambda uid, firestore_client=None, provision=True: SimpleNamespace(plan=PlanType.basic, status='active'),
        raising=False,
    )
    monkeypatch.setattr(sub, 'desktop_trial_paywall_eligible', lambda plan, subscription=None: True)
    monkeypatch.setattr(
        sub, '_get_user', lambda uid: SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=creation_ms))
    )


def test_a_stored_deepgram_fingerprint_without_the_header_does_not_lift_the_paywall_for_the_allowance(
    monkeypatch, sub
) -> None:
    """The real helper exempts ordinary callers on a stored fingerprint alone. The allowance path
    must not: without the key on this request the socket would run on Omi's Deepgram key."""
    _real_paywall(
        monkeypatch, sub, byok_enrolled=True, fingerprints={'deepgram': 'fp'}, creation_ms=1_000, header=False
    )
    assert sub.is_trial_paywalled('uid', 'desktop', required_byok_provider='deepgram') is False  # ordinary callers
    allowance = sub.resolve_transcription_allowance('uid', source='desktop')
    assert (allowance.mode, allowance.remaining_seconds, allowance.reason) == ('blocked', 0, 'trial_paywalled')
    assert sub.has_transcription_credits('uid', source='desktop') is False
    # With the validated key on the request, the same account is exempt and pays Deepgram itself.
    _real_paywall(monkeypatch, sub, byok_enrolled=True, fingerprints={'deepgram': 'fp'}, creation_ms=1_000, header=True)
    assert sub.resolve_transcription_allowance('uid', source='desktop').reason == 'byok'


def test_an_ordinary_callers_cached_fail_open_answer_is_never_consumed_by_the_allowance(monkeypatch, sub) -> None:
    """Production caches paywall answers in redis. An ordinary caller (fingerprint-only exemption)
    caches False; the strict allowance path must not read that entry — it has its own key,
    and the invalidator clears it with the others."""
    cache: dict[str, Any] = {}
    _real_paywall(
        monkeypatch, sub, byok_enrolled=True, fingerprints={'deepgram': 'fp'}, creation_ms=1_000, header=False
    )
    monkeypatch.setattr(sub.redis_db, 'get_generic_cache', lambda key: cache.get(key), raising=False)
    monkeypatch.setattr(
        sub.redis_db, 'set_generic_cache', lambda key, value, ttl=None: cache.__setitem__(key, value), raising=False
    )
    deleted: list[str] = []
    monkeypatch.setattr(sub.redis_db, 'delete_generic_cache', deleted.append, raising=False)
    assert sub.is_trial_paywalled('uid', 'desktop', required_byok_provider='deepgram') is False  # ordinary caller
    assert cache == {'trial_paywall:expired:uid:deepgram': False}
    allowance = sub.resolve_transcription_allowance('uid', source='desktop')
    assert (allowance.mode, allowance.reason) == ('blocked', 'trial_paywalled')
    assert cache['trial_paywall:expired:uid:deepgram:strict'] is True
    # The strict answer is cached and reused; a downgrade or BYOK change clears it with the rest.
    sub.clear_trial_paywall_cache('uid')
    assert set(cache) <= set(deleted)


@pytest.mark.parametrize('creation_ms', [None, 0])
def test_an_unreadable_account_record_inside_the_real_helper_does_not_open_a_billed_socket(
    monkeypatch, sub, creation_ms
) -> None:
    _real_paywall(monkeypatch, sub, byok_enrolled=False, fingerprints={}, creation_ms=creation_ms, header=False)
    assert sub.is_trial_paywalled('uid', 'desktop') is False  # ordinary callers keep the fail-open answer
    allowance = sub.resolve_transcription_allowance('uid', source='desktop')
    assert (allowance.mode, allowance.remaining_seconds, allowance.reason) == ('on_device', 0, 'allowance_unavailable')


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
        'is_trial_paywalled',
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


def test_the_paywall_only_fires_for_the_desktop_source(monkeypatch, sub) -> None:
    calls: list = []

    def paywalled(uid, source=None, **_kw):
        calls.append(source)
        return source == 'desktop'

    monkeypatch.setattr(sub, 'is_trial_paywalled', paywalled)
    monkeypatch.setattr(sub.users_db, 'is_byok_active', lambda uid: False, raising=False)
    monkeypatch.setattr(sub, 'get_byok_key', lambda provider: None)
    monkeypatch.setattr(
        sub.users_db, 'get_user_valid_subscription', lambda uid: SimpleNamespace(plan=PlanType.basic), raising=False
    )
    monkeypatch.setattr(sub, 'get_monthly_usage_for_subscription', lambda uid: {})
    assert sub.resolve_transcription_allowance('uid', source='desktop').mode == 'blocked'
    assert sub.resolve_transcription_allowance('uid', source='omi').mode == 'managed'
    assert calls == ['desktop', 'omi']
    # Both wrappers pass the source through: a desktop-paywalled uid is blocked on desktop only.
    assert sub.has_transcription_credits('uid', source='desktop') is False
    assert sub.get_remaining_transcription_seconds('uid', source='desktop') == 0
    assert sub.has_transcription_credits('uid', source='omi') is True
    assert sub.get_remaining_transcription_seconds('uid', source='omi') == BASIC_CAP


def test_the_answer_serialises_for_the_plan_endpoint(monkeypatch, sub) -> None:
    _situate(monkeypatch, sub, plan=PlanType.plus, used_seconds=PLUS_CAP - 10_000)
    assert sub.resolve_transcription_allowance('uid').as_dict() == {
        'mode': 'managed',
        'remaining_seconds': 10_000,
        'reason': 'plan_within_allowance',
    }

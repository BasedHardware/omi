"""Cohort admission + emergency stop for the free-tier rollout flags.

Direction review 2026-09-07 §7 item 3 / flip review F-5: both flags were global
booleans with no remote stop. This suite pins the replacement: a lit flag
admits only the configured cohort, fail-closed on every ambiguity, and two
stops revoke everyone without a cohort edit.

Automatic-or-dead: `test_gate_is_wired_into_every_uid_bearing_flag_site` reads
the production modules and fails if a policy stops consulting the cohort; the
route-level cases below drive the real connector gate and the real sweep
producer, so a cohort that exists but is unwired cannot stay green.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from utils import free_tier_cohort as cohort
from utils import free_tier_memory_policy as memory_policy
from utils import free_tier_processing_policy as processing_policy
from utils.jit_rollout import TriState
from utils.managed_compute import Decision

_BACKEND = Path(__file__).resolve().parents[2]
FLAG = 'FREE_TIER_LOCAL_PROCESSING'
UID = 'cohort-uid-1'
OTHER = 'cohort-uid-2'


@pytest.fixture(autouse=True)
def _quiet_remote(monkeypatch):
    """No PostHog in unit tests: the remote kill switch is UNKNOWN unless a test says otherwise."""
    monkeypatch.setattr(cohort, '_kill_switch_state', lambda _uid: TriState.UNKNOWN)
    monkeypatch.delenv(cohort.EMERGENCY_STOP_ENV_VAR, raising=False)
    monkeypatch.delenv(cohort.cohort_env_name(FLAG), raising=False)
    monkeypatch.delenv(cohort.cohort_env_name('FREE_TIER_MEMORY_SUPPRESSION'), raising=False)
    cohort.reset_kill_switch_cache_for_tests()
    cohort._warned.clear()
    yield


# ----------------------------------------------------------------- grammar


@pytest.mark.parametrize(
    'raw',
    [None, '', '   ', 'uid:', 'pct:', 'pct:abc', 'pct:101', 'pct:-1', 'all', 'uid', '5', 'uid:a,pct:5,pct:6', 'user:a'],
)
def test_unset_empty_or_malformed_admits_nobody(raw, monkeypatch) -> None:
    assert cohort.parse_cohort(raw) is None
    if raw is not None:
        monkeypatch.setenv(cohort.cohort_env_name(FLAG), raw)
    decision = cohort.cohort_decision(FLAG, UID)
    assert decision.admitted is False
    assert decision.reason == ('cohort_malformed' if raw and raw.strip() else 'cohort_unset')


def test_malformed_is_logged_once_per_process(monkeypatch, caplog) -> None:
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), 'all')
    with caplog.at_level(logging.WARNING, logger=cohort.__name__):
        cohort.cohort_decision(FLAG, UID)
        cohort.cohort_decision(FLAG, OTHER)
    assert sum('is malformed' in record.message for record in caplog.records) == 1


def test_uid_list_admits_exactly_the_listed_accounts(monkeypatch) -> None:
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f' uid:{UID} , uid:third ')
    assert cohort.cohort_decision(FLAG, UID) == cohort.CohortDecision(True, 'cohort_uid')
    assert cohort.cohort_decision(FLAG, 'third').admitted is True
    assert cohort.cohort_decision(FLAG, OTHER) == cohort.CohortDecision(False, 'cohort_not_admitted')


def test_percentage_is_a_stable_hash_bucket_shared_by_every_flag() -> None:
    buckets = {uid: cohort.cohort_bucket(uid) for uid in (UID, OTHER, 'a', 'b', 'c')}
    assert all(0 <= bucket < 100 for bucket in buckets.values())
    assert buckets == {uid: cohort.cohort_bucket(uid) for uid in buckets}  # deterministic
    # Known-answer: pin the hash so a salt or algorithm change is a visible test edit.
    assert cohort.cohort_bucket('known-answer-uid') == 22


def test_percentage_admits_below_the_bucket_and_zero_admits_nobody(monkeypatch) -> None:
    bucket = cohort.cohort_bucket(UID)
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f'pct:{bucket + 1}')
    assert cohort.cohort_decision(FLAG, UID) == cohort.CohortDecision(True, 'cohort_pct')
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f'pct:{bucket}')
    assert cohort.cohort_decision(FLAG, UID).admitted is False
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), 'pct:0')
    assert cohort.cohort_decision(FLAG, UID).admitted is False
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), 'pct:100')
    assert cohort.cohort_decision(FLAG, UID).admitted is True


def test_percentage_selects_the_same_accounts_for_both_flags(monkeypatch) -> None:
    for flag in (FLAG, 'FREE_TIER_MEMORY_SUPPRESSION'):
        monkeypatch.setenv(cohort.cohort_env_name(flag), 'pct:50')
    sample = [f'uid-{i}' for i in range(200)]
    first = {uid for uid in sample if cohort.cohort_admits(FLAG, uid)}
    second = {uid for uid in sample if cohort.cohort_admits('FREE_TIER_MEMORY_SUPPRESSION', uid)}
    assert first == second
    assert 60 < len(first) < 140  # roughly half, not all, not none


def test_cohorts_are_per_flag(monkeypatch) -> None:
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f'uid:{UID}')
    assert cohort.cohort_admits(FLAG, UID) is True
    assert cohort.cohort_admits('FREE_TIER_MEMORY_SUPPRESSION', UID) is False


# ------------------------------------------------------------------- stops


def test_no_uid_admits_nobody_and_logs_once(monkeypatch, caplog) -> None:
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), 'pct:100')
    with caplog.at_level(logging.WARNING, logger=cohort.__name__):
        for uid in (None, '', '   '):
            assert cohort.cohort_decision(FLAG, uid) == cohort.CohortDecision(False, 'no_uid')
    assert sum('without a uid' in record.message for record in caplog.records) == 1


@pytest.mark.parametrize('value', ['true', 'TRUE', '1', 'yes'])
def test_environment_emergency_stop_revokes_listed_uids(monkeypatch, value) -> None:
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f'uid:{UID},pct:100')
    monkeypatch.setenv(cohort.EMERGENCY_STOP_ENV_VAR, value)
    assert cohort.cohort_decision(FLAG, UID) == cohort.CohortDecision(False, 'emergency_stop_env')


def test_remote_kill_switch_revokes_only_when_definitively_enabled(monkeypatch) -> None:
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f'uid:{UID}')
    monkeypatch.setattr(cohort, '_kill_switch_state', lambda _uid: TriState.ENABLED)
    assert cohort.cohort_decision(FLAG, UID) == cohort.CohortDecision(False, 'kill_switch_remote')
    for state in (TriState.DISABLED, TriState.UNKNOWN):
        monkeypatch.setattr(cohort, '_kill_switch_state', lambda _uid, state=state: state)
        assert cohort.cohort_decision(FLAG, UID).admitted is True


def test_remote_kill_switch_is_not_consulted_for_a_non_admitted_account(monkeypatch) -> None:
    """A dark fleet makes no provider calls."""
    calls: list[str] = []

    def spy(uid: str) -> TriState:
        calls.append(uid)
        return TriState.ENABLED

    monkeypatch.setattr(cohort, '_kill_switch_state', spy)
    cohort.cohort_decision(FLAG, UID)  # cohort unset
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f'uid:{OTHER}')
    cohort.cohort_decision(FLAG, UID)  # not listed
    assert calls == []
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f'uid:{UID}')
    cohort.cohort_decision(FLAG, UID)
    assert calls == [UID]


def test_remote_kill_switch_failures_are_unknown_never_block_and_back_off(monkeypatch, caplog) -> None:
    """The real reader: provider raising, timing out, or unconfigured is UNKNOWN,
    warned once per class, and followed by a process-wide backoff."""
    monkeypatch.undo()
    monkeypatch.delenv(cohort.cohort_env_name(FLAG), raising=False)
    monkeypatch.delenv(cohort.EMERGENCY_STOP_ENV_VAR, raising=False)
    cohort.reset_kill_switch_cache_for_tests()
    cohort._warned.clear()
    calls: list[str] = []

    def boom(uid: str):
        calls.append(uid)
        raise RuntimeError('provider down')

    monkeypatch.setattr(cohort, '_fetch_kill_switch', boom)
    with caplog.at_level(logging.WARNING, logger=cohort.__name__):
        assert cohort._kill_switch_state(UID) is TriState.UNKNOWN
        assert cohort._kill_switch_state(OTHER) is TriState.UNKNOWN  # backoff: no second call
        assert cohort._kill_switch_state('third') is TriState.UNKNOWN
    assert calls == [UID]
    assert sum('remote kill switch unavailable' in record.message for record in caplog.records) == 1
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f'uid:{UID}')
    assert cohort.cohort_decision(FLAG, UID).admitted is True


def test_remote_kill_switch_unconfigured_is_unknown(monkeypatch) -> None:
    monkeypatch.undo()
    cohort.reset_kill_switch_cache_for_tests()
    cohort._warned.clear()
    monkeypatch.delenv('POSTHOG_PROJECT_API_KEY', raising=False)
    monkeypatch.delenv('POSTHOG_API_KEY', raising=False)
    monkeypatch.setattr(cohort, '_client', None)
    assert cohort._kill_switch_state(UID) is TriState.UNKNOWN
    assert 'kill_switch:unconfigured' in cohort._warned


def test_remote_kill_switch_timeout_is_bounded_and_backs_off(monkeypatch) -> None:
    import threading

    monkeypatch.undo()
    cohort.reset_kill_switch_cache_for_tests()
    cohort._warned.clear()
    monkeypatch.setattr(cohort, '_POSTHOG_RESULT_TIMEOUT_SECONDS', 0.05)
    release = threading.Event()
    started: list[str] = []

    def slow(uid: str):
        started.append(uid)
        release.wait(5)
        return TriState.DISABLED

    monkeypatch.setattr(cohort, '_fetch_kill_switch', slow)
    try:
        t0 = time.monotonic()
        assert cohort._kill_switch_state(UID) is TriState.UNKNOWN
        assert time.monotonic() - t0 < 1.0
        assert cohort._kill_switch_state(OTHER) is TriState.UNKNOWN  # backoff, not a second wait
        assert started == [UID]
    finally:
        release.set()


def test_remote_kill_switch_reads_the_kill_flag_not_the_exposure_flag(monkeypatch) -> None:
    monkeypatch.undo()
    cohort.reset_kill_switch_cache_for_tests()

    class _Client:
        def __init__(self) -> None:
            self.calls = 0

        def get_feature_variants(self, uid: str):
            self.calls += 1
            # Exposure enabled must not admit; kill enabled must stop.
            return {cohort.FREE_TIER_COHORT_FLAG_KEY: True, cohort.FREE_TIER_KILL_SWITCH_FLAG_KEY: True}

    client = _Client()
    monkeypatch.setattr(cohort, '_get_client', lambda: client)
    assert cohort._kill_switch_state(UID) is TriState.ENABLED
    assert cohort._kill_switch_state(UID) is TriState.ENABLED  # cached
    assert client.calls == 1
    monkeypatch.delenv(cohort.cohort_env_name(FLAG), raising=False)
    monkeypatch.delenv(cohort.EMERGENCY_STOP_ENV_VAR, raising=False)
    # Exposure flag alone never admits: cohort unset stays unset.
    assert cohort.cohort_decision(FLAG, UID).reason == 'cohort_unset'
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f'uid:{UID}')
    assert cohort.cohort_decision(FLAG, UID) == cohort.CohortDecision(False, 'kill_switch_remote')


def test_remote_kill_switch_malformed_response_is_unknown(monkeypatch) -> None:
    monkeypatch.undo()
    cohort.reset_kill_switch_cache_for_tests()
    cohort._warned.clear()

    class _Client:
        def get_feature_variants(self, uid: str):
            return ['not', 'a', 'mapping']

    monkeypatch.setattr(cohort, '_get_client', lambda: _Client())
    assert cohort._kill_switch_state(UID) is TriState.UNKNOWN
    assert 'kill_switch:malformed' in cohort._warned


@pytest.mark.parametrize('raw', ['pct:²', 'pct:³', 'pct:١٢', 'pct:１２'])
def test_non_ascii_digits_are_malformed_not_raised(raw, monkeypatch) -> None:
    assert cohort.parse_cohort(raw) is None
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), raw)
    assert cohort.cohort_decision(FLAG, UID) == cohort.CohortDecision(False, 'cohort_malformed')


def test_a_raising_parser_is_malformed_not_raised(monkeypatch) -> None:
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), f'uid:{UID}')

    def boom(_raw):
        raise ValueError('unexpected')

    monkeypatch.setattr(cohort, 'parse_cohort', boom)
    assert cohort.cohort_decision(FLAG, UID) == cohort.CohortDecision(False, 'cohort_malformed')


def test_reasons_are_a_closed_vocabulary() -> None:
    with pytest.raises(ValueError):
        cohort.CohortDecision(False, 'made_up')


# ------------------------------------------------- the policies consult it


def _decision(allowed: bool, *, plan: str = 'basic') -> Decision:
    from config.plan_catalog import PlanType

    return Decision(
        allowed=allowed,
        reason='plan_paid' if allowed else 'plan_basic_denied',
        feature='memories',
        funding_owner='omi',
        plan=PlanType(plan),
        plan_resolved=True,
    )


def test_memory_gate_suppresses_only_the_admitted_cohort(monkeypatch) -> None:
    """Route-level: the real producer gate the connectors call."""
    monkeypatch.setattr(memory_policy, 'FREE_TIER_MEMORY_SUPPRESSION', True)
    monkeypatch.setattr(memory_policy, 'managed_compute_decision_for', lambda _uid: (lambda _f: _decision(False)))
    monkeypatch.setenv(cohort.cohort_env_name('FREE_TIER_MEMORY_SUPPRESSION'), f'uid:{UID}')
    assert memory_policy.managed_memory_formation_suppressed(UID, 'x_connector') is True
    assert memory_policy.managed_memory_formation_suppressed(OTHER, 'x_connector') is False
    monkeypatch.setenv(cohort.EMERGENCY_STOP_ENV_VAR, 'true')
    assert memory_policy.managed_memory_formation_suppressed(UID, 'x_connector') is False


def test_memory_gate_does_no_plan_lookup_for_a_non_admitted_account(monkeypatch) -> None:
    monkeypatch.setattr(memory_policy, 'FREE_TIER_MEMORY_SUPPRESSION', True)
    looked_up: list[str] = []

    def decision_for(uid: str):
        looked_up.append(uid)
        return lambda _f: _decision(False)

    monkeypatch.setattr(memory_policy, 'managed_compute_decision_for', decision_for)
    monkeypatch.setenv(cohort.cohort_env_name('FREE_TIER_MEMORY_SUPPRESSION'), f'uid:{OTHER}')
    assert memory_policy.managed_memory_formation_suppressed(UID, 'twitter_persona') is False
    assert looked_up == []


def test_sweep_producer_skips_only_the_admitted_cohort(monkeypatch) -> None:
    """Route-level: the sweep's own flag read now names the account."""
    from utils.memory import daily_memory_sweep as sweep

    seen: list[str | None] = []

    def flag(uid=None):
        seen.append(uid)
        return memory_policy.free_tier_memory_suppression_enabled(uid)

    monkeypatch.setattr(sweep, 'free_tier_memory_suppression_enabled', flag)
    monkeypatch.setattr(memory_policy, 'FREE_TIER_MEMORY_SUPPRESSION', True)
    monkeypatch.setenv(cohort.cohort_env_name('FREE_TIER_MEMORY_SUPPRESSION'), f'uid:{UID}')
    source = (_BACKEND / 'utils' / 'memory' / 'daily_memory_sweep.py').read_text(encoding='utf-8')
    assert 'free_tier_memory_suppression_enabled(uid)' in source
    assert sweep.free_tier_memory_suppression_enabled(UID) is True
    assert sweep.free_tier_memory_suppression_enabled(OTHER) is False
    assert seen == [UID, OTHER]


def test_processing_flag_admits_only_the_cohort(monkeypatch) -> None:
    monkeypatch.setattr(processing_policy, 'FREE_TIER_LOCAL_PROCESSING', True)
    monkeypatch.setenv(cohort.cohort_env_name(FLAG), 'pct:100')
    assert processing_policy.free_tier_local_processing_enabled(UID) is True
    assert processing_policy.free_tier_local_processing_enabled() is False
    monkeypatch.setattr(cohort, '_kill_switch_state', lambda _uid: TriState.ENABLED)
    assert processing_policy.free_tier_local_processing_enabled(UID) is False


@pytest.mark.parametrize(
    'relpath, needle',
    [
        ('utils/free_tier_processing_policy.py', "cohort_admits('FREE_TIER_LOCAL_PROCESSING', uid)"),
        ('utils/free_tier_memory_policy.py', "cohort_admits('FREE_TIER_MEMORY_SUPPRESSION', uid)"),
        ('utils/free_tier_memory_policy.py', 'free_tier_memory_suppression_enabled(uid)'),
        ('utils/memory/daily_memory_sweep.py', 'free_tier_memory_suppression_enabled(uid)'),
    ],
)
def test_gate_is_wired_into_every_uid_bearing_flag_site(relpath: str, needle: str) -> None:
    """Static tripwire: delete a consult and this fails; the decision tables above would not."""
    source = (_BACKEND / relpath).read_text(encoding='utf-8')
    assert needle in source, f'{relpath} no longer consults the cohort ({needle})'


def test_coordinator_sites_still_read_the_flag_without_a_uid() -> None:
    """Documents the known gap: process_conversation.py passes no uid at either
    site, so with a lit flag those two sites admit nobody until the jit lane
    adds `uid` to the calls (see the overnight evidence record). If this test
    starts failing because the calls now carry `uid`, delete it and the gap
    note together."""
    source = (_BACKEND / 'utils' / 'conversations' / 'process_conversation.py').read_text(encoding='utf-8')
    assert re.search(r'free_tier_local_processing_enabled\(\)', source)
    assert re.search(r'free_tier_memory_suppression_enabled\(\)', source)

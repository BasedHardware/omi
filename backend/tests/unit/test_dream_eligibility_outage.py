"""A cohort outage cannot veto a declared rollout or invent an allowlist grant."""

import pytest

from config import dream_agent, rollout_cohorts as policy
from config.plan_catalog import PAID_PLAN_IDS
from utils import rollout_cohorts as runtime


@pytest.fixture
def outage(monkeypatch):
    def unavailable(*args, **kwargs):
        raise policy.RolloutCohortUnavailable('synthetic unavailable')

    monkeypatch.setattr(policy, '_membership_resolver', unavailable)
    monkeypatch.setattr(policy, '_members_resolver', unavailable)
    monkeypatch.setenv('DREAM_ON_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_PAID_PERCENT', '100')


@pytest.mark.parametrize('policy_name', ['all', 'paid'])
def test_declared_eligibility_survives_cohort_outage(outage, monkeypatch, policy_name):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', policy_name)
    user = {'plan': next(iter(PAID_PLAN_IDS))}
    assert dream_agent.may_be_eligible('synthetic-owner')
    assert dream_agent.eligible('synthetic-owner', user)
    assert dream_agent.admission_for('synthetic-owner') == ('reserved', False)
    assert not dream_agent.eligible('synthetic-owner', {**user, 'deleted': True})


def test_outage_does_not_expand_paid_percent_or_free_entitlement(outage, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'paid')
    assert not dream_agent.eligible('synthetic-owner', {'plan': 'free'})
    monkeypatch.setenv('DREAM_AGENT_PAID_PERCENT', '0')
    assert not dream_agent.may_be_eligible('synthetic-owner')


def test_allowlist_outage_is_loud_without_broadening_authority(outage, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')
    with pytest.raises(policy.RolloutCohortUnavailable):
        dream_agent.may_be_eligible('synthetic-owner')
    with pytest.raises(policy.RolloutCohortUnavailable):
        dream_agent.allowlist_uids()
    assert dream_agent.admission_for('synthetic-owner') == ('reserved', False)


def test_unbound_resolver_is_unknown_instead_of_false(monkeypatch):
    monkeypatch.setattr(policy, '_membership_resolver', None)
    with pytest.raises(policy.RolloutCohortUnavailable):
        dream_agent.allowlisted('synthetic-owner')


def test_runtime_read_error_emits_health_and_is_not_revocation(monkeypatch, caplog):
    def fail(uid):
        raise RuntimeError('private-path-must-not-be-logged')

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setattr(runtime, '_cache', runtime._TTLReads(fail))
    with pytest.raises(policy.RolloutCohortUnavailable):
        runtime._in_rollout_cohort('synthetic-owner', 'dream-agent')
    assert 'event=dream_cohort_health outcome=unavailable' in caplog.text
    assert 'private-path' not in caplog.text
    assert 'synthetic-owner' not in caplog.text


def test_empty_discovery_is_observable_and_explicit_revocation_wins(monkeypatch, caplog):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setattr(runtime, '_cache', runtime._TTLReads(lambda uid: {'prod': {'dream-agent': False}}))
    monkeypatch.setattr(runtime, '_member_cache', runtime._TTLReads(lambda name: (), discovery=True))
    monkeypatch.setattr(policy, '_membership_resolver', runtime._in_rollout_cohort)
    assert runtime._rollout_cohort_members('dream-agent') == ()
    assert 'event=dream_cohort_health outcome=empty' in caplog.text
    assert not runtime._in_rollout_cohort('synthetic-owner', 'dream-agent')

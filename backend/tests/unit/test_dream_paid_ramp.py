"""Paid-owner Dream ramp: a stable percent bucket plus the listed owners."""

import pytest

from config import dream_agent

PAID = {'subscription': {'plan': next(iter(sorted(dream_agent.PAID_PLAN_IDS)))}}
FREE = {'subscription': {'plan': 'basic'}}
UIDS = ['synthetic-owner-' + str(index) for index in range(400)]


@pytest.fixture
def paid(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'paid')
    monkeypatch.setattr(dream_agent, 'allowlist_uids', lambda: ['synthetic-listed-owner'])
    monkeypatch.setattr(dream_agent, '_allowlisted', lambda uid: pytest.fail('paid policy must not read per owner'))
    return monkeypatch


def test_unset_percent_admits_every_paid_owner(paid):
    paid.delenv('DREAM_AGENT_PAID_PERCENT', raising=False)
    assert all(dream_agent.eligible(uid, PAID) for uid in UIDS)
    assert not any(dream_agent.eligible(uid, FREE) for uid in UIDS)


@pytest.mark.parametrize('raw', ['', '-1', '101', 'five', '5.0', '٥'])
def test_malformed_percent_admits_no_ramp_owner(paid, raw):
    paid.setenv('DREAM_AGENT_PAID_PERCENT', raw)
    assert not any(dream_agent.may_be_eligible(uid) for uid in UIDS)
    assert dream_agent.eligible('synthetic-listed-owner', FREE)


def test_percent_is_stable_and_widening_only_adds_owners(paid):
    admitted = {}
    for percent in (0, 5, 25, 100):
        paid.setenv('DREAM_AGENT_PAID_PERCENT', str(percent))
        admitted[percent] = {uid for uid in UIDS if dream_agent.eligible(uid, PAID)}
        assert admitted[percent] == {uid for uid in UIDS if dream_agent.may_be_eligible(uid)}
    assert admitted[0] == set()
    assert admitted[0] <= admitted[5] <= admitted[25] <= admitted[100] == set(UIDS)
    assert 0 < len(admitted[5]) < len(admitted[25]) < len(UIDS)


def test_listed_owner_stays_eligible_at_zero_percent(paid):
    paid.setenv('DREAM_AGENT_PAID_PERCENT', '0')
    assert dream_agent.may_be_eligible('synthetic-listed-owner')
    assert dream_agent.eligible('synthetic-listed-owner', FREE)
    assert not dream_agent.eligible('synthetic-listed-owner', {**PAID, 'deleted': True})

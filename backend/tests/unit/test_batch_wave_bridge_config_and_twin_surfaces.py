"""Config surfaces, twin hints and simulator contracts around the wave bridge.

The wave bridge sits under two runtime kill switches and beside two store
twins. This suite pins: the env-token grammar of the contention flags and
their flag-budget entries; the advisory frontier-hint surface on the sim and
Postgres twins (the retired transactional read must stay retired); the
simulator's label-optional ``run`` and its hint semantics; and the query
driver registry's inventory. None of these surfaces may drift while the chain
budget evolves.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import json
import datetime
from pathlib import Path

import pytest

from config import batch_pipeline as config_batch_pipeline
from database.jobstore.postgres_store import PostgresStore, PostgresTransaction
from testing.pipeline_sim.store import SimStore

BACKEND = Path(__file__).resolve().parents[2]

RETRY_FLAG = 'BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
DAMPER_FLAG = 'BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED'
CONTINUATION_FLAG = 'BATCH_PIPELINE_MAINTENANCE_CONTINUATION_ENABLED'


def make_sim():
    store = SimStore.__new__(SimStore)
    store.rows = {}
    store._controls = set()
    store.transactions = 0
    return store


# --------------------------------------------------------------------------
# Contention flag env-token grammar
# --------------------------------------------------------------------------


@pytest.mark.parametrize('value', ['false', 'False', ' false ', 'FALSE'])
def test_retry_flag_off_tokens(monkeypatch, value):
    monkeypatch.setenv(RETRY_FLAG, value)
    assert config_batch_pipeline.contention_retry_enabled() is False


@pytest.mark.parametrize('value', ['true', 'True', '', '0', 'yes'])
def test_retry_flag_on_tokens(monkeypatch, value):
    monkeypatch.setenv(RETRY_FLAG, value)
    assert config_batch_pipeline.contention_retry_enabled() is True


@pytest.mark.parametrize('value', ['false', 'False', ' false ', 'FALSE'])
def test_damper_flag_off_tokens(monkeypatch, value):
    monkeypatch.setenv(DAMPER_FLAG, value)
    assert config_batch_pipeline.contention_storm_damper_enabled() is False


@pytest.mark.parametrize('value', ['true', 'True', '', '0', 'yes'])
def test_damper_flag_on_tokens(monkeypatch, value):
    monkeypatch.setenv(DAMPER_FLAG, value)
    assert config_batch_pipeline.contention_storm_damper_enabled() is True


def test_flags_read_env_at_call_time(monkeypatch):
    monkeypatch.setenv(DAMPER_FLAG, 'true')
    assert config_batch_pipeline.contention_storm_damper_enabled() is True
    monkeypatch.setenv(DAMPER_FLAG, 'false')
    assert config_batch_pipeline.contention_storm_damper_enabled() is False


def test_both_contention_flags_default_on(monkeypatch):
    for flag in (RETRY_FLAG, DAMPER_FLAG):
        monkeypatch.delenv(flag, raising=False)
    assert config_batch_pipeline.contention_retry_enabled() is True
    assert config_batch_pipeline.contention_storm_damper_enabled() is True


@pytest.mark.parametrize('flag', [RETRY_FLAG, DAMPER_FLAG, CONTINUATION_FLAG])
def test_flag_budget_declares_each_contention_flag(flag):
    data = json.loads((BACKEND / 'config' / 'flag_budget.json').read_text())
    assert flag in data['names']


@pytest.mark.parametrize('flag', [RETRY_FLAG, DAMPER_FLAG, CONTINUATION_FLAG])
def test_flag_budget_entries_are_owned_and_reviewed(flag):
    entry = json.loads((BACKEND / 'config' / 'flag_budget.json').read_text())['names'][flag]
    assert entry.get('owner') == 'batch record lane / rollout lead'
    assert datetime.date.fromisoformat(entry['review_by']) > datetime.date(2026, 11, 1)


def test_flag_budget_count_matches_names():
    data = json.loads((BACKEND / 'config' / 'flag_budget.json').read_text())
    assert data['count'] == len(data['names'])


# --------------------------------------------------------------------------
# The twins' advisory frontier-hint surface (retired transactional read)
# --------------------------------------------------------------------------


def test_postgres_store_exposes_the_advisory_hint():
    assert hasattr(PostgresStore, 'service_frontier_hint')
    assert hasattr(PostgresStore, 'service_frontier_hint_in')


def test_postgres_transaction_has_no_transactional_frontier_read():
    assert not hasattr(PostgresTransaction, 'service_frontier')


def test_sim_store_exposes_the_advisory_hint():
    assert hasattr(SimStore, 'service_frontier_hint')


def test_sim_hint_returns_max_service_across_controls():
    store = make_sim()
    store.rows[('control', 'c1')] = {'p1_service': 2.5}
    store.rows[('control', 'c2')] = {'p1_service': 7.0, 'p2_service': 1.0}
    store._controls = {'c1', 'c2'}
    assert store.service_frontier_hint(1) == 7.0
    assert store.service_frontier_hint(2) == 1.0


def test_sim_hint_of_an_empty_collection_is_zero():
    assert make_sim().service_frontier_hint(0) == 0.0


@pytest.mark.parametrize('priority', [-1, 3, 99])
def test_sim_hint_refuses_unbounded_priorities(priority):
    with pytest.raises(ValueError):
        make_sim().service_frontier_hint(priority)


def test_sim_run_executes_the_body_without_a_budget():
    store = make_sim()
    assert store.run(lambda tx: 'done', operation='batch_fail') == 'done'
    assert store.transactions == 1


def test_sim_run_is_label_optional():
    store = make_sim()
    assert store.run(lambda tx: True) is True


def test_sim_transactions_counter_counts_each_run():
    store = make_sim()
    for _ in range(3):
        store.run(lambda tx: None)
    assert store.transactions == 3


def test_the_driver_registry_lists_the_hint_driver():
    source = (BACKEND / 'tests' / 'support' / 'firestore_query_driver_registry.py').read_text()
    assert 'service_frontier_hint' in source


def test_the_driver_registry_lists_the_retired_transactional_read_nowhere():
    source = (BACKEND / 'tests' / 'support' / 'firestore_query_driver_registry.py').read_text()
    assert 'def service_frontier(' not in source

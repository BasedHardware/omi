"""Control steady-write skip: kill-switch surface and configuration contract.

The skip ships enabled behind a registered kill switch with the same parsing
rules as every other batch contention switch: any rendering of ``false``
disables, everything else — including an unset variable — keeps it enabled.
The flag registry entry, the scheduler wiring and the written docs surface
are part of the contract: an operator must find the switch, its owner, its
review date and its failure class from the repository alone.
"""

import json
from pathlib import Path

import pytest

from tests.unit.control_steady_skip_fleet_helpers import *  # noqa: F401,F403
from tests.unit.test_control_steady_write_skip_ledger import warm_owner  # noqa: F401
import config.batch_pipeline as _cfg
import utils.batch_pipeline.scheduler as _sched

steady_flag = _cfg.control_steady_write_skip_enabled
BACKEND = Path(__file__).resolve().parents[2]
FLAG = 'BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED'
ENV = FLAG


def _env(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, value)
    return steady_flag()


def test_default_is_enabled(monkeypatch):
    assert _env(monkeypatch, None) is True


def test_false_disables(monkeypatch):
    assert _env(monkeypatch, 'false') is False


def test_uppercase_false_disables(monkeypatch):
    assert _env(monkeypatch, 'FALSE') is False


def test_spaced_false_disables(monkeypatch):
    assert _env(monkeypatch, ' false ') is False


def test_trailing_tab_false_disables(monkeypatch):
    assert _env(monkeypatch, 'false\t') is False


def test_zero_is_not_a_false_rendering(monkeypatch):
    assert _env(monkeypatch, '0') is True


def test_mixed_case_false_disables(monkeypatch):
    assert _env(monkeypatch, 'fAlSe') is False


def test_true_keeps_enabled(monkeypatch):
    assert _env(monkeypatch, 'true') is True


def test_uppercase_true_keeps_enabled(monkeypatch):
    assert _env(monkeypatch, 'TRUE') is True


def test_one_keeps_enabled(monkeypatch):
    assert _env(monkeypatch, '1') is True


def test_yes_keeps_enabled(monkeypatch):
    assert _env(monkeypatch, 'yes') is True


def test_on_keeps_enabled(monkeypatch):
    assert _env(monkeypatch, 'on') is True


def test_empty_string_keeps_enabled(monkeypatch):
    assert _env(monkeypatch, '') is True


def test_garbage_keeps_enabled(monkeypatch):
    assert _env(monkeypatch, 'banana') is True


def test_flag_returns_a_bool(monkeypatch):
    assert isinstance(_env(monkeypatch, 'true'), bool)
    assert isinstance(_env(monkeypatch, 'false'), bool)


def test_scheduler_module_imports_the_flag():
    assert callable(_sched.control_steady_write_skip_enabled)


def test_flag_budget_registers_the_flag():
    data = json.loads((BACKEND / 'config' / 'flag_budget.json').read_text())
    assert FLAG in data['names']
    entry = data['names'][FLAG]
    assert entry['owner'] == 'batch record lane / rollout lead'
    assert entry['review_by'] == '2026-12-15'


def test_flag_budget_count_covers_the_registry():
    data = json.loads((BACKEND / 'config' / 'flag_budget.json').read_text())
    assert data['count'] == len(data['names'])


def test_docs_file_names_the_family():
    doc = (BACKEND / 'docs' / 'batch-control-steady-write-skip.md').read_text()
    assert 'Failure-Class: FC-control-document-carries-content-free-append-writes' in doc


def test_docs_file_names_the_switch():
    doc = (BACKEND / 'docs' / 'batch-control-steady-write-skip.md').read_text()
    assert 'BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED' in doc
    assert 'kill switch' in doc


def test_docs_file_states_the_warm_path_is_value_free():
    doc = (BACKEND / 'docs' / 'batch-control-steady-write-skip.md').read_text()
    assert 'byte-identical' in doc
    assert 'service advance' in doc


def test_contract_mentions_the_skip():
    contract = (BACKEND / 'utils' / 'batch_pipeline' / 'CONTRACT.md').read_text()
    assert FLAG in contract
    assert 'activation' in contract


def test_kill_switch_env_matches_the_kill_switch_helper(monkeypatch):
    kill_switch(monkeypatch)
    assert steady_flag() is False


def test_unsetting_after_kill_switch_reenables(monkeypatch):
    kill_switch(monkeypatch)
    monkeypatch.delenv(ENV, raising=False)
    assert steady_flag() is True


def test_warm_append_under_default_env_skips(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('next', owner=OWNER), 50.0)
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_warm_append_under_false_env_writes(monkeypatch):
    monkeypatch.setenv(ENV, 'false')
    store = LedgerStore()
    warm_owner(store)
    Scheduler(store).enqueue(item('next', owner=OWNER), 50.0)
    assert ('control', CONTROL) in store.ledgers[-1]


def test_cold_append_under_false_env_writes(monkeypatch):
    monkeypatch.setenv(ENV, 'false')
    store = LedgerStore()
    assert Scheduler(store).enqueue(item('first', owner=OWNER), 0.0) is True
    assert ('control', CONTROL) in store.ledgers[0]


def test_cold_append_under_true_env_writes(monkeypatch):
    monkeypatch.setenv(ENV, 'true')
    store = LedgerStore()
    assert Scheduler(store).enqueue(item('first', owner=OWNER), 0.0) is True
    assert ('control', CONTROL) in store.ledgers[0]


def test_kill_switch_documents_match_the_default_documents(monkeypatch):
    killed = legacy_stream(('a', 'b', 'c'))
    monkeypatch.delenv(ENV, raising=False)
    store = LedgerStore()
    run_stream(store, ('a', 'b', 'c'))
    assert control_doc(store) == control_doc(killed)
    assert queue_doc(store) == queue_doc(killed)


def test_grant_side_ignores_the_switch(monkeypatch):
    monkeypatch.setenv(ENV, 'false')
    store = LedgerStore()
    run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    assert ('control', CONTROL) in store.ledgers[-1]


def test_env_changes_between_runs_take_effect(monkeypatch):
    store = LedgerStore()
    warm_owner(store)
    monkeypatch.setenv(ENV, 'false')
    Scheduler(store).enqueue(item('legacy', owner=OWNER), 50.0)
    assert ('control', CONTROL) in store.ledgers[-1]
    monkeypatch.setenv(ENV, 'true')
    Scheduler(store).enqueue(item('modern', owner=OWNER), 51.0)
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_probe_grid_helpers_still_bound():
    assert callable(cell) and callable(probe) and callable(sample_control)


def test_ledger_helpers_still_bound():
    assert callable(warm_owner) and callable(queue_doc) and callable(control_doc)

"""Aged first summaries leave the reserved fresh enrichment lane (prod 2026-11-16 backlog)."""

from unittest.mock import Mock

import pytest

from tests.unit.test_enrichment_route import KEY, client, rows, split_binding  # noqa: F401
from tests.unit.test_sync_reprocess_coalesce import state, sweep_query  # noqa: F401
from utils.enrichment import fresh_demotion
from utils.enrichment import outbox as reprocess
from utils.enrichment import consumer as consumer_module


@pytest.fixture
def fresh_row(split_binding, monkeypatch):  # noqa: F811
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    monkeypatch.setattr(reprocess, '_conversation_finished_at', lambda *_: 900)
    monkeypatch.delenv(fresh_demotion.ENV, raising=False)
    reprocess.mark('u', 'c', 'en', now=1000)
    rows, tasks = split_binding
    assert rows[KEY]['dispatch']['queue'] == 'enrichment-fresh'
    tasks.clear()
    return rows, tasks


def test_aged_fresh_delivery_moves_to_primary_under_a_new_token(fresh_row):
    rows, tasks = fresh_row
    token = rows[KEY]['task_token']
    assert fresh_demotion.demote_if_stale(KEY, token, now=10_000)
    row = rows[KEY]
    assert row['dispatch']['queue'] == 'enrichment' and row['fresh_demoted']
    assert row['task_token'] != token and row['first_pending_at'] == 1000
    assert [task['dispatch']['queue'] for task in tasks] == ['enrichment']


def test_recording_that_just_finished_stays_fresh_even_if_its_obligation_is_old(fresh_row, monkeypatch):
    rows, tasks = fresh_row
    # A sync upload opened the obligation at 1000; the recording itself finished 10 minutes ago.
    monkeypatch.setattr(reprocess, '_conversation_finished_at', lambda *_: 10_000 - 600)
    assert not fresh_demotion.demote_if_stale(KEY, rows[KEY]['task_token'], now=10_000)
    assert rows[KEY]['dispatch']['queue'] == 'enrichment-fresh' and not tasks


def test_incomplete_primary_binding_never_unbinds_the_row(fresh_row, monkeypatch):
    rows, tasks = fresh_row
    monkeypatch.setenv('ENRICHMENT_TASKS_QUEUE', '')
    assert not fresh_demotion.demote_if_stale(KEY, rows[KEY]['task_token'], now=10_000)
    assert rows[KEY]['dispatch']['queue'] == 'enrichment-fresh' and not tasks


def test_young_fresh_work_is_never_demoted(fresh_row):
    rows, tasks = fresh_row
    assert not fresh_demotion.demote_if_stale(KEY, rows[KEY]['task_token'], now=1600)
    assert rows[KEY]['dispatch']['queue'] == 'enrichment-fresh' and not tasks


@pytest.mark.parametrize('fence', ['lease', 'token', 'dormant'])
def test_demotion_never_steals_a_worker_or_a_newer_wake(fresh_row, fence):
    rows, tasks = fresh_row
    token = rows[KEY]['task_token']
    if fence == 'lease':
        rows[KEY].update(owner='w', lease_until=20_000)
    elif fence == 'token':
        token = 'f' * 32
    else:
        rows[KEY]['dormant'] = True
    assert not fresh_demotion.demote_if_stale(KEY, token, now=10_000)
    assert rows[KEY]['dispatch']['queue'] == 'enrichment-fresh' and not tasks


def test_unreadable_finish_time_keeps_the_row_in_place(fresh_row, monkeypatch):
    rows, tasks = fresh_row
    monkeypatch.setattr(reprocess, '_conversation_finished_at', Mock(side_effect=TimeoutError()))
    assert not fresh_demotion.demote_if_stale(KEY, rows[KEY]['task_token'], now=10_000)
    assert rows[KEY]['dispatch']['queue'] == 'enrichment-fresh' and not tasks


@pytest.mark.parametrize('setting', ['0'])
def test_kill_switch_disables_demotion(fresh_row, monkeypatch, setting):
    rows, tasks = fresh_row
    monkeypatch.setenv(fresh_demotion.ENV, setting)
    assert not fresh_demotion.demote_if_stale(KEY, rows[KEY]['task_token'], now=10_000)
    assert rows[KEY]['dispatch']['queue'] == 'enrichment-fresh'


@pytest.mark.parametrize(
    'setting,expected', [('', 1800.0), ('45', 2700.0), ('nan', 1800.0), ('-3', 1800.0), ('x', 1800.0)]
)
def test_demotion_age_defaults_to_the_promotion_window(monkeypatch, setting, expected):
    monkeypatch.delenv('ENRICHMENT_FRESH_PROMOTE_MAX_AGE_MIN', raising=False)
    monkeypatch.setenv(fresh_demotion.ENV, setting)
    assert fresh_demotion.demote_after_seconds() == expected


def test_sweep_never_promotes_a_demoted_row_back(fresh_row, sweep_query, monkeypatch):  # noqa: F811
    rows, tasks = fresh_row
    assert fresh_demotion.demote_if_stale(KEY, rows[KEY]['task_token'], now=10_000)
    # Even if the finish clock now looks recent, the demoted row keeps the primary binding.
    monkeypatch.setattr(reprocess, '_conversation_finished_at', lambda *_: 20_000)
    rows[KEY].update(due_at=0, wake_check_after=0)
    reprocess.sweep(now=20_100)
    assert rows[KEY]['dispatch']['queue'] == 'enrichment'


def test_route_demotes_only_fresh_queue_deliveries(fresh_row, client, monkeypatch):  # noqa: F811
    rows, tasks = fresh_row
    process = Mock(side_effect=AssertionError('an aged fresh delivery must not run on a fresh slot'))
    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda _: process)
    monkeypatch.setattr(fresh_demotion, '_now', lambda: 10_000.0)
    token = rows[KEY]['task_token']
    response = client.post(
        '/v2/enrichment/run',
        json={'kind': 'enrichment', 'key': KEY, 'task_token': token},
        headers={'X-CloudTasks-QueueName': 'enrichment-fresh'},
    )
    assert response.status_code == 200
    assert response.json() == {'status': 'deferred', 'reason': 'fresh_demoted'}
    assert rows[KEY]['dispatch']['queue'] == 'enrichment'
    process.assert_not_called()


def test_route_without_fresh_header_never_reads_for_demotion(fresh_row, client, monkeypatch):  # noqa: F811
    rows, _ = fresh_row
    demote = Mock(return_value=False)
    monkeypatch.setattr(fresh_demotion, 'demote_if_stale', demote)
    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda _: Mock(return_value=None))
    client.post(
        '/v2/enrichment/run',
        json={'kind': 'enrichment', 'key': KEY, 'task_token': rows[KEY]['task_token']},
        headers={'X-CloudTasks-QueueName': 'enrichment'},
    )
    demote.assert_not_called()


def test_demoted_counter_passes_the_gmp_sync_allowlist():
    import re
    from pathlib import Path

    import yaml

    config = yaml.safe_load((Path(__file__).parents[2] / 'deploy' / 'cloud_run_gmp_sync.yaml').read_text())
    rules = config['spec']['endpoints'][0]['metricRelabeling']
    keep = [row['regex'] for row in rules if row['action'] == 'keep' and row['sourceLabels'] == ['__name__']]
    assert any(re.fullmatch(pattern, 'omi_enrichment_fresh_demoted_total') for pattern in keep)

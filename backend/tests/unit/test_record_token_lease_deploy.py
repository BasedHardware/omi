"""Offline lease-mode chart wiring salvaged from #24832, without its age grace."""

import json
from pathlib import Path

import pytest

from tests.unit.test_record_seal_cluster_repair_deploy import documents
from tests.unit.test_record_seal_sweeper_deploy import render


def containers(docs):
    return [
        docs[('Deployment', 'record-seal-worker')]['spec']['template']['spec']['containers'][0],
        docs[('CronJob', 'record-seal-repair')]['spec']['jobTemplate']['spec']['template']['spec']['containers'][0],
    ]


def test_lease_chart_defaults_are_dark_and_no_age_grace_remains():
    for container in containers(documents()):
        env = {e['name']: e.get('value') for e in container['env']}
        assert env['RECORD_TOKEN_LEASE_MODE'] == 'off'
        assert env['RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT'] == '0'
        assert env['RECORD_TOKEN_LEASE_SECONDS'] == '3600'
        assert env['RECORD_TOKEN_LEASE_DEPLOYED_AT'] == '0'
        assert not any('LIVE_PRODUCER_GRACE' in k for k in env)


@pytest.mark.parametrize('mode', ['shadow', 'serve'])
def test_all_repair_children_inherit_same_pinned_release_epoch(mode):
    docs = documents(
        '--set', f'recordTokenLease.mode={mode},recordTokenLease.servePercent=10,recordTokenLease.deployedAt=2000000000'
    )
    for container in containers(docs):
        env = {e['name']: e.get('value') for e in container['env']}
        assert env['RECORD_TOKEN_LEASE_MODE'] == mode
        assert env['RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT'] == '10'
        assert env['RECORD_TOKEN_LEASE_DEPLOYED_AT'] == '2000000000'


@pytest.mark.parametrize('mode', ['shadow', 'serve', 'typo'])
def test_enabled_mode_cannot_silently_reanchor_stock_per_process(mode):
    assert render('--set', f'recordTokenLease.mode={mode}').returncode != 0


def test_alerts_use_exported_counters_and_match_the_approved_combined_entries():
    path = Path(__file__).resolve().parents[2] / 'charts/monitoring/alerts/record-token-lease.json'
    rules = json.loads(path.read_text())
    assert {r['uid'] for r in rules} == {'omi-record-token-lease-late-append', 'omi-record-token-lease-backlog'}
    assert (
        rules[0]['data'][0]['model']['expr'] == 'sum(increase(omi_record_token_late_append_total[5m])) > 0 or vector(0)'
    )
    combined = {rule['uid']: rule for rule in json.loads((path.parent.parent / 'alert-rules.json').read_text())}
    assert all(combined[rule['uid']] == rule for rule in rules)
    assert not rules[0]['isPaused']
    assert rules[1]['isPaused'] or rules[1]['labels']['severity'] == 'warning'
    assert rules[0]['labels']['tier'] == 'page'
    assert rules[0]['for'] == '0s'


def test_late_append_page_keeps_fleet_notification_timing():
    path = Path(__file__).resolve().parents[2] / 'charts/monitoring/alerts/record-token-lease.json'
    rule = json.loads(path.read_text())[0]
    assert rule['notification_settings']['group_wait'] == '30s'
    assert rule['notification_settings']['group_interval'] == '5m'
    assert rule['notification_settings']['repeat_interval'] == '4h'
    assert rule['notification_settings']['mute_time_intervals'] == []

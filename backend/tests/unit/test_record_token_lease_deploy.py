"""Offline lease-mode chart wiring salvaged from #24832, without its age grace."""

import json
from pathlib import Path
import re
import runpy
import sys
import subprocess
import urllib.request

import pytest
import yaml

from tests.unit.test_record_seal_cluster_repair_deploy import documents
from tests.unit.test_record_seal_sweeper_deploy import render
from utils.observability import firestore_probe_export as probe
from config import record_seal_rules as lease
from scripts.cross_service_checks import staging as staging_check


def containers(docs):
    return [
        docs[('Deployment', 'record-seal-worker')]['spec']['template']['spec']['containers'][0],
        docs[('CronJob', 'record-seal-repair')]['spec']['jobTemplate']['spec']['template']['spec']['containers'][0],
    ]


@pytest.fixture
def production_render_inputs(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    manifest = root / 'backend/deploy/runtime_env.yaml'
    renderer = runpy.run_path(str(root / 'backend/scripts/render_backend_runtime_env.py'))
    parsed = renderer['_load_yaml'](manifest)
    composer = staging_check._load_composer(root)
    staging = composer.compose_staging(inputs={'STAGING_REDIS_HOST': '10.0.0.7'})
    return_inputs = (root, manifest, renderer, staging, parsed)
    # Match the canonical renderer suite: parse real source during setup, then
    # exercise main and all emitted artifacts in the guarded test call.
    monkeypatch.setitem(renderer['main'].__globals__, '_load_yaml', lambda path: parsed)

    def bind_synthetic_inputs(value):
        if isinstance(value, dict):
            if isinstance(value.get('env_var'), str):
                monkeypatch.setenv(value['env_var'], str(value.get('default') or 'synthetic-rendered-value'))
            for child in value.values():
                bind_synthetic_inputs(child)
        elif isinstance(value, list):
            for child in value:
                bind_synthetic_inputs(child)

    bind_synthetic_inputs(parsed['environments']['prod'])
    for key, entry in parsed['environments']['prod']['gke']['config_map']['entries'].items():
        if entry.get('source') == 'environment':
            monkeypatch.setenv(key, str(entry.get('default', 'synthetic-gke-value')))
    return return_inputs


@pytest.mark.parametrize('frame_seconds', ['1800', '3600', '7200'])
def test_custody_lease_covers_the_rendered_sync_request_timeout(
    monkeypatch, tmp_path, production_render_inputs, frame_seconds
):
    # Actual production renderer outputs and action consumption; no cloud CLI.
    root, manifest, renderer, staging, parsed = production_render_inputs
    workflow_output = tmp_path / 'github-output'
    state_output = tmp_path / 'state.json'
    monkeypatch.setenv('GITHUB_OUTPUT', str(workflow_output))
    monkeypatch.setattr(
        sys, 'argv', ['render', '--env', 'prod', '--manifest', str(manifest), '--state-output', str(state_output)]
    )
    assert renderer['main']() == 0
    emitted = workflow_output.read_text()
    outputs = {}
    for name in ('cloud_run_flags', 'backend_sync_flags'):
        match = re.search(rf'{name}<<([^\n]+)\n(.*?)\n\1\n', emitted, re.DOTALL)
        assert match, f'production renderer did not emit {name}'
        outputs[name] = match[2]
    action = yaml.safe_load((root / '.github/actions/deploy-backend-stack/action.yml').read_text())
    step = next(item for item in action['runs']['steps'] if item.get('id') == 'deploy-backend-sync')
    assert step['uses'] == 'google-github-actions/deploy-cloudrun@v3'
    flags = step['with']['flags']
    for name, value in outputs.items():
        expression = '${{ steps.runtime-env.outputs.' + name + ' }}'
        assert expression in flags, f'backend-sync deploy dropped {name}'
        flags = flags.replace(expression, value)
    timeouts = re.findall(r'(?<!\S)--timeout=(\d+)s?(?!\S)', flags)
    assert len(timeouts) == 1, 'prod backend-sync must declare exactly one request timeout'
    timeout = int(timeouts[0])
    state = json.loads(state_output.read_text())
    assert state['services']['backend-sync']['flags']['--timeout'] == f'{timeout}s'
    overlay = yaml.safe_load((root / 'backend/deploy/runtime_env/prod.overlay.yaml').read_text())
    assert overlay['overlay']['cloud_run']['services']['backend-sync']['flags']['--timeout'] == f'{timeout}s'
    config = json.loads((root / 'backend/config/cloud_run_request_timeouts.json').read_text())
    assert timeout == config['backend-sync'] == lease.custody_request_timeout_seconds()
    monkeypatch.setenv('RECORD_TOKEN_LEASE_SECONDS', frame_seconds)
    duration = lease.custody_token_lease_seconds()
    assert lease.CUSTODY_REQUEST_MARGIN_SECONDS > 0
    assert duration >= timeout + lease.CUSTODY_REQUEST_MARGIN_SECONDS > timeout
    assert lease.token_lease_seconds() == int(frame_seconds)


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


def test_prod_active_repair_scrapes_age_and_release_counters_without_enabling_idle_worker():
    # documents() renders the checked-in production values, not chart defaults.
    docs = documents()
    cron = docs['CronJob', 'record-seal-repair']['spec']
    assert cron['suspend'] is False
    container = cron['jobTemplate']['spec']['template']['spec']['containers'][0]
    env = {e['name']: e.get('value') for e in container['env']}
    assert env['RECORD_SEAL_REPAIR_ENABLED'] == 'true'
    assert container['command'] == ['python', 'scripts/record_seal_repair_job.py']
    assert {'name': 'metrics', 'containerPort': 9090} in container['ports']
    monitor = docs['PodMonitoring', 'record-seal-repair']['spec']
    assert monitor['selector']['matchLabels'] == {'app.kubernetes.io/name': 'record-seal-repair'}
    assert monitor['endpoints'] == [{'port': 'metrics', 'interval': '15s', 'path': '/metrics'}]
    worker = docs['Deployment', 'record-seal-worker']['spec']['template']['spec']['containers'][0]
    worker_env = {e['name']: e.get('value') for e in worker['env']}
    assert worker_env['RECORD_SEAL_REPAIR_ENABLED'] == 'false'
    previous = probe.REPAIR_OLDEST._value.get()
    try:
        probe.REPAIR_OLDEST.set(86400)
        with probe.repair_probe_server(port=0, addr='127.0.0.1') as server:
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/metrics', timeout=5) as response:
                body = response.read().decode()
        assert 'omi_record_seal_oldest_age_seconds 86400.0' in body
        assert 'omi_record_token_lease_expired_sealed_total ' in body
    finally:
        probe.REPAIR_OLDEST.set(previous)
    root = Path(__file__).resolve().parents[2]
    entry = (root / 'scripts/record_seal_repair_job.py').read_text()
    assert 'repair_probe_server()' in entry
    rules = json.loads((root / 'charts/monitoring/alerts/record-token-lease.json').read_text())
    # Aggregate before deriving so CronJob pod replacement does not invent a
    # permanently flat per-pod slope while the global age is actually falling.
    assert (
        'last_over_time((max(omi_record_seal_oldest_age_seconds >= 0))[10m:])' in rules[1]['data'][0]['model']['expr']
    )


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_shared_rollout_inputs_reach_sync_listen_pusher_and_repair(monkeypatch, production_render_inputs, mode):
    root, manifest, renderer, staging, parsed = production_render_inputs
    expected = {
        'RECORD_TOKEN_LEASE_MODE': mode,
        'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': '10',
        'RECORD_TOKEN_LEASE_SECONDS': '3600',
        'RECORD_TOKEN_LEASE_DEPLOYED_AT': '2000000000',
    }
    for key, value in expected.items():
        monkeypatch.setenv(key, value)
    expected_staging = {
        'RECORD_TOKEN_LEASE_MODE': 'off',
        'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': '0',
        'RECORD_TOKEN_LEASE_SECONDS': '3600',
        'RECORD_TOKEN_LEASE_DEPLOYED_AT': '1794268800',
    }
    assert {key for key in staging_check.STAGING_DIFF_ALLOWLIST if key.startswith('RECORD_TOKEN_LEASE_')} == set(
        expected_staging
    )
    for service in staging['cloud_run']['services'].values():
        assert {key: service['env'][key]['value'] for key in expected_staging} == expected_staging
    # run_path's returned _load_yaml still references the original loader,
    # even after patching main.__globals__; reuse the real fixture parse.
    state = renderer['_render_cloud_run_state'](parsed['environments']['prod'])
    sync_env = {entry['name']: entry.get('value') for entry in state['services']['backend-sync']['env']}
    assert {key: sync_env[key] for key in expected} == expected
    config_renderer = runpy.run_path(str(root / 'backend/scripts/render_gke_backend_config.py'))
    monkeypatch.setitem(config_renderer['config_map_entries'].__globals__, '_load_yaml', lambda path: parsed)
    name, config = config_renderer['config_map_entries']('prod', manifest)
    assert {key: config[key] for key in expected} == expected
    if mode == 'off':
        assert_producer_chart_refs(root, name, expected)
    # Repair deliberately has separately typed values.
    docs = documents(
        '--set', f'recordTokenLease.mode={mode},recordTokenLease.servePercent=10,recordTokenLease.deployedAt=2000000000'
    )
    for container in containers(docs):
        env = {entry['name']: entry.get('value') for entry in container['env']}
        assert {key: env[key] for key in expected} == expected


def assert_producer_chart_refs(root, name, expected):
    for chart, values in [
        ('pusher', 'prod_omi_pusher_values.yaml'),
        ('backend-listen', 'prod_omi_backend_listen_values.yaml'),
    ]:
        result = subprocess.run(
            [
                'helm',
                'template',
                'prod-omi-' + chart,
                str(root / 'backend/charts' / chart),
                '-f',
                str(root / 'backend/charts' / chart / values),
                '--set-string',
                'image.digest=sha256:' + 'a' * 64,
                '--set-string',
                'image.tag=',
                '--set-string',
                'image.pullPolicy=IfNotPresent',
            ],
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr
        deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
        env = {item['name']: item for item in deployment['spec']['template']['spec']['containers'][0]['env']}
        for key in expected:
            assert env[key]['valueFrom']['configMapKeyRef'] == {'name': name, 'key': key}
            assert 'value' not in env[key]

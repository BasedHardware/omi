"""Exercise forbidden-env retirement through the real action clone and deploy inputs."""

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
RENDER = runpy.run_path(str(ROOT / 'backend/scripts/render_backend_runtime_env.py'))
RETIRED_DEMAND_ENV = {
    'DEMAND_PROCESSING_ENABLED',
    'DEMAND_PROCESSING_LAZY_ENABLED',
    'DEMAND_PROCESSING_PERCENT',
    'DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED',
    'DEMAND_PROCESSING_TOOL_ENABLED',
    'DEMAND_PROCESSING_UID_ALLOWLIST',
}


def _action(name):
    return yaml.load((ROOT / f'.github/actions/{name}/action.yml').read_text(), Loader=yaml.CSafeLoader)['runs'][
        'steps'
    ]


def _outputs(raw):
    lines = iter(raw.splitlines())
    result = {}
    for line in lines:
        name, separator, delimiter = line.partition('<<')
        if separator:
            values = []
            for value in lines:
                if value == delimiter:
                    break
                values.append(value)
            result[name] = '\n'.join(values)
    return result


@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_all_deploy_paths_remove_manifest_forbidden_keys(stage, monkeypatch, capsys, tmp_path):
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    services = manifest['environments'][stage]['cloud_run']['services']
    demand_services = ['backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration']
    if stage == 'prod':
        demand_services.append('backend-projection-pump')
    for name in demand_services:
        assert RETIRED_DEMAND_ENV <= set(services[name]['forbidden_env'])
        assert RETIRED_DEMAND_ENV.isdisjoint(services[name]['env'])
    # A new forbidden key must reach every path without another action edit.
    for service in services.values():
        service.setdefault('forbidden_env', []).append('FUTURE_RETIRED_KEY')
    # Only render services: unrelated jobs need their own deploy-time inputs.
    manifest['environments'][stage]['cloud_run']['jobs'] = {}
    for config in services.values():
        for entry in config.get('env', {}).values():
            if 'env_var' in entry:
                monkeypatch.setenv(entry['env_var'], str(entry.get('default', 'synthetic-value')))
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'synthetic-network')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'synthetic-subnet')
    github_output = tmp_path / 'github-output'
    github_output.touch()
    monkeypatch.setenv('GITHUB_OUTPUT', str(github_output))
    monkeypatch.setitem(RENDER['main'].__globals__, '_load_yaml', lambda _: manifest)
    monkeypatch.setattr(sys, 'argv', ['render', '--env', stage])
    assert RENDER['main']() == 0
    assert capsys.readouterr().out == ''
    rendered = _outputs(github_output.read_text(encoding='utf-8'))
    stack = _action('deploy-backend-stack')
    worker = next(s for s in stack if s.get('id') == 'sync-backfill')
    for name in ('backend', 'backend-sync', 'backend-integration'):
        prefix = name.replace('-', '_')
        deploy = next(s for s in stack if s.get('id') == f'deploy-{name}')
        expression = '${{ steps.runtime-env.outputs.' + prefix + '_remove_env_extra }}'
        flags = deploy['with']['flags']
        assert expression in flags
        flags = flags.replace(expression, rendered[f'{prefix}_remove_env_extra'])
        removals = _removals(flags)
        assert set(services[name]['forbidden_env']) <= set(removals)
        assert set(RENDER['RETIRED_ENV_NAMES']) <= set(removals)
        assert ('HOSTED_PUSHER_API_URL' in removals) == (name != 'backend')
    if stage == 'prod':
        pump = next(s for s in _action('deploy-projection-pump') if s.get('id') == 'deploy-backend-projection-pump')
        expression = '${{ steps.runtime-env.outputs.backend_projection_pump_remove_env_extra }}'
        flags = pump['with']['flags']
        assert expression in flags
        assert RETIRED_DEMAND_ENV <= set(
            _removals(flags.replace(expression, rendered['backend_projection_pump_remove_env_extra']))
        )
    assert (
        worker['with']['forbidden_env_names']
        == '${{ steps.runtime-env.outputs.backend_sync_backfill_forbidden_env_names }}'
    )
    assert (
        worker['with']['remove_env_extra'] == '${{ steps.runtime-env.outputs.backend_sync_backfill_remove_env_extra }}'
    )
    forbidden = rendered['backend_sync_backfill_forbidden_env_names']
    lifecycle = _action('sync-backfill-lifecycle')
    clone = next(s for s in lifecycle if s.get('id') == 'backfill-runtime')
    deploy = next(s for s in lifecycle if s.get('id') == 'deploy-backend-sync-backfill')
    # Run the actual shell + clone renderer against a fake gcloud service describe.
    source = tmp_path / 'source.json'
    source.write_text(
        json.dumps(
            {
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {
                                    'env': [
                                        *({'name': key, 'value': 'retired'} for key in forbidden.split(',')),
                                        {'name': 'KEEP_UNMODELLED_BINDING', 'value': 'keep'},
                                        {
                                            'name': 'KEEP_SECRET',
                                            'valueFrom': {
                                                'secretKeyRef': {'name': 'synthetic-secret', 'key': 'latest'}
                                            },
                                        },
                                    ]
                                }
                            ]
                        }
                    }
                }
            }
        )
    )
    fake = tmp_path / 'gcloud'
    fake.write_text('#!/bin/sh\ncat "$FAKE_SERVICE"\n')
    fake.chmod(0o755)
    output = tmp_path / 'outputs'
    replacements = {
        '${{ inputs.region }}': 'synthetic-region',
        '${{ inputs.project_id }}': 'synthetic-project',
        '${{ inputs.service }}': 'backend',
    }
    script = (
        clone['run']
        .replace('/tmp/backend-sync-live.json', str(tmp_path / 'sync.json'))
        .replace('/tmp/backend-sync-backfill-live.json', str(tmp_path / 'worker.json'))
    )
    for expression, value in replacements.items():
        script = script.replace(expression, value)
    removals = clone['env']['REMOVE_ENV_VARS'].split('${{', 1)[0]
    env = {
        **os.environ,
        'PATH': f'{tmp_path}:{Path(sys.executable).parent}:{os.environ["PATH"]}',
        'FAKE_SERVICE': str(source),
        'GITHUB_OUTPUT': str(output),
        'DEPLOY_CONTROL_SCRIPTS': str(ROOT / 'backend/scripts'),
        'REMOVE_ENV_VARS': removals,
        'FORBIDDEN_ENV_NAMES': forbidden,
        'IDENTITY_FLAGS': '',
        'ENV_OVERLAY': 'KEEP_OVERLAY=keep\nDEEPGRAM_SELF_HOSTED_ENABLED=true',
        'SECRET_OVERLAY': '',
    }
    subprocess.run(['bash', '-euo', 'pipefail', '-c', script], env=env, check=True, capture_output=True)
    cloned = _outputs(output.read_text())
    assert set(forbidden.split(',')).isdisjoint(line.split('=', 1)[0] for line in cloned['env_vars'].splitlines())
    assert 'KEEP_UNMODELLED_BINDING=keep' in cloned['env_vars']
    assert 'KEEP_OVERLAY=keep' in cloned['env_vars']
    assert 'KEEP_SECRET=synthetic-secret:latest' in cloned['secrets']
    assert clone['env']['FORBIDDEN_ENV_NAMES'] == '${{ inputs.forbidden_env_names }}'
    expression = '${{ inputs.remove_env_extra }}'
    assert expression in deploy['with']['flags']
    flags = deploy['with']['flags'].replace(expression, rendered['backend_sync_backfill_remove_env_extra'])
    assert set(forbidden.split(',')) | {'HOSTED_PUSHER_API_URL'} <= set(_removals(flags))
    # The input's empty default must also be deployable on its own.
    assert set(RENDER['RETIRED_ENV_NAMES']) <= set(_removals(deploy['with']['flags'].replace(expression, '')))


@pytest.mark.parametrize('workflow', ['desktop_backend_auto_dev', 'desktop_backend_prod'])
def test_desktop_backend_removes_retired_demand_env(workflow):
    steps = yaml.safe_load((ROOT / f'.github/workflows/{workflow}.yml').read_text())['jobs']
    deploy = next(
        step
        for job in steps.values()
        for step in job.get('steps', [])
        if step.get('uses', '').startswith('google-github-actions/deploy-cloudrun@')
    )
    assert RETIRED_DEMAND_ENV <= set(_removals(deploy['with']['flags']))
    assert RETIRED_DEMAND_ENV.isdisjoint(line.split('=', 1)[0] for line in deploy['with']['env_vars'].splitlines())


@pytest.mark.parametrize(('deploy_environment', 'stage'), [('development', 'dev'), ('prod', 'prod')])
def test_notifications_job_removes_retired_demand_env(deploy_environment, stage):
    workflow = yaml.load(
        (ROOT / '.github/workflows/gcp_notifications_job.yml').read_text(), Loader=yaml.CBaseLoader
    )
    assert deploy_environment in workflow['on']['workflow_dispatch']['inputs']['environment']['options']
    assert workflow['env']['SERVICE'] == 'notifications-job'
    deploy = next(step for step in workflow['jobs']['deploy']['steps'] if step.get('id') == 'deploy')
    assert deploy['uses'].startswith('google-github-actions/deploy-cloudrun@')
    assert deploy['with']['job'] == '${{ env.SERVICE }}'
    assert RETIRED_DEMAND_ENV <= set(_removals(deploy['with']['flags']))

    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    job = manifest['environments'][stage]['cloud_run']['jobs']['notifications-job']
    assert RETIRED_DEMAND_ENV <= set(job['forbidden_env'])
    assert RETIRED_DEMAND_ENV.isdisjoint(job['env'])
    assert RETIRED_DEMAND_ENV.isdisjoint(job['secrets'])


def _removals(flags):
    # gcloud rejects --remove-env-vars when it names a key twice ("cannot be specified multiple times").
    value = next(word.split('=', 1)[1] for word in flags.split() if word.startswith('--remove-env-vars='))
    names = value.split(',')
    assert all(names), f'empty key in --remove-env-vars={value}'
    assert len(names) == len(set(names)), f'duplicate key in --remove-env-vars={value}'
    return names

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / 'scripts' / 'check_cloud_run_env_drift.py'


@pytest.fixture(autouse=True)
def _native_yaml_fixture_loader(monkeypatch):
    monkeypatch.setattr(yaml, 'safe_load', lambda stream: yaml.load(stream, Loader=yaml.CSafeLoader))
    monkeypatch.setattr(yaml, 'safe_dump', lambda data, *a, **kw: yaml.dump(data, *a, Dumper=yaml.CSafeDumper, **kw))


def load_drift_checker():
    spec = importlib.util.spec_from_file_location('check_cloud_run_env_drift', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def checker():
    return load_drift_checker()


@pytest.fixture(scope='module')
def prod_declared(checker):
    manifest_path = BACKEND_ROOT / 'deploy/runtime_env.yaml'
    _, _, declared = checker.declared_manifest_keys(env='prod', manifest_path=manifest_path)
    return declared


def test_script_runs_standalone_help() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--help'],
        cwd=BACKEND_ROOT.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_drift_check_separates_allowlisted_keys_on_prod_manifest(checker, prod_declared) -> None:
    manifest_path = BACKEND_ROOT / 'deploy/runtime_env.yaml'
    cloud_run_state = {
        'services': {
            'backend': {
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {
                                    'name': 'backend-1',
                                    'env': [
                                        *({'name': k, 'value': 'v'} for k in sorted(prod_declared['backend'])),
                                        {'name': 'OMI_BACKEND_RELEASE_SHA', 'value': 'deadbeef'},
                                        {'name': 'BATCH_PIPELINE_UID_ALLOWLIST', 'value': 'sensitive-uid-123'},
                                    ],
                                },
                                {
                                    'name': 'collector',
                                    'env': [{'name': 'SIDECAR_INTERNAL_ONLY', 'value': 'ignored'}],
                                },
                            ]
                        }
                    }
                }
            },
            'backend-sync': {
                'env': [
                    *({'name': k, 'value': 'v'} for k in sorted(prod_declared['backend-sync'])),
                    {'name': 'FIRST_SUMMARY_UID_ALLOWLIST', 'value': 'sensitive-uid-123'},
                    {'name': 'SYNC_BACKFILL_ORDER_UID_ALLOWLIST', 'value': 'sensitive-uid-123'},
                    {'name': 'SYNC_DURABLE_REDRIVE_GUARD', 'value': 'true'},
                    {'name': 'SYNC_LEGACY_COMPLETION_CONVERGENCE', 'value': 'true'},
                ]
            },
            'backend-sync-backfill': {
                'env': [
                    *({'name': k, 'value': 'v'} for k in sorted(prod_declared['backend-sync-backfill'])),
                    {'name': 'FIRST_SUMMARY_UID_ALLOWLIST', 'value': 'sensitive-uid-123'},
                    {'name': 'SYNC_DURABLE_REDRIVE_GUARD', 'value': 'true'},
                    {'name': 'SYNC_LEGACY_COMPLETION_CONVERGENCE', 'value': 'true'},
                ]
            },
            'backend-integration': {
                'env': [
                    *({'name': k, 'value': 'v'} for k in sorted(prod_declared['backend-integration'])),
                    {'name': 'FIRST_SUMMARY_UID_ALLOWLIST', 'value': 'sensitive-uid-123'},
                ]
            },
        }
    }

    project, region, results = checker.inspect_services_drift(
        env='prod',
        manifest_path=manifest_path,
        cloud_run_state=cloud_run_state,
    )
    assert project == 'based-hardware'
    assert region == 'us-central1'
    by_service = {r.service: r for r in results}
    assert by_service['backend'].allowlisted_live_only == (
        'BATCH_PIPELINE_UID_ALLOWLIST',
        'OMI_BACKEND_RELEASE_SHA',
    )
    assert by_service['backend'].unallowlisted_live_only == ()
    assert by_service['backend-sync'].allowlisted_live_only == (
        'FIRST_SUMMARY_UID_ALLOWLIST',
        'SYNC_BACKFILL_ORDER_UID_ALLOWLIST',
    )
    assert by_service['backend-sync'].unallowlisted_live_only == ()
    assert by_service['backend-sync-backfill'].unallowlisted_live_only == ()
    assert by_service['backend-integration'].allowlisted_live_only == ('FIRST_SUMMARY_UID_ALLOWLIST',)
    assert by_service['backend-integration'].unallowlisted_live_only == ()


def test_drift_check_catches_missing_sync_redrive_flags_and_redacts_values(checker, tmp_path: Path) -> None:
    def service_manifest(*keys: str) -> dict:
        return {'env': {k: {'value': 'true'} for k in keys}}

    old_manifest = {
        'schema_version': 2,
        'environments': {
            'prod': {
                'compute_project': 'based-hardware',
                'region': 'us-central1',
                'cloud_run': {
                    'services': {
                        'backend': service_manifest('BUCKET_TEMPORAL_SYNC_LOCAL'),
                        'backend-sync': service_manifest('FIRST_SUMMARY_DEADLINE_ENABLED'),
                        'backend-sync-backfill': service_manifest('FIRST_SUMMARY_DEADLINE_ENABLED'),
                        'backend-integration': service_manifest('FIRST_SUMMARY_DEADLINE_ENABLED'),
                    }
                },
            }
        },
    }
    new_manifest = {
        'schema_version': 2,
        'environments': {
            'prod': {
                'compute_project': 'based-hardware',
                'region': 'us-central1',
                'cloud_run': {
                    'services': {
                        'backend': service_manifest('BUCKET_TEMPORAL_SYNC_LOCAL'),
                        'backend-sync': service_manifest(
                            'FIRST_SUMMARY_DEADLINE_ENABLED',
                            'SYNC_DURABLE_REDRIVE_GUARD',
                            'SYNC_LEGACY_COMPLETION_CONVERGENCE',
                        ),
                        'backend-sync-backfill': service_manifest(
                            'FIRST_SUMMARY_DEADLINE_ENABLED',
                            'SYNC_DURABLE_REDRIVE_GUARD',
                            'SYNC_LEGACY_COMPLETION_CONVERGENCE',
                        ),
                        'backend-integration': service_manifest('FIRST_SUMMARY_DEADLINE_ENABLED'),
                    }
                },
            }
        },
    }
    cloud_run_state = {
        'services': {
            'backend': {'env': [{'name': 'BUCKET_TEMPORAL_SYNC_LOCAL', 'value': 'syncing-local'}]},
            'backend-sync': {
                'env': [
                    {'name': 'FIRST_SUMMARY_DEADLINE_ENABLED', 'value': 'true'},
                    {'name': 'FIRST_SUMMARY_UID_ALLOWLIST', 'value': 'sensitive-uid-123'},
                    {'name': 'SYNC_DURABLE_REDRIVE_GUARD', 'value': 'true'},
                    {'name': 'SYNC_LEGACY_COMPLETION_CONVERGENCE', 'value': 'true'},
                ]
            },
            'backend-sync-backfill': {
                'env': [
                    {'name': 'FIRST_SUMMARY_DEADLINE_ENABLED', 'value': 'true'},
                    {'name': 'FIRST_SUMMARY_UID_ALLOWLIST', 'value': 'sensitive-uid-123'},
                    {'name': 'SYNC_DURABLE_REDRIVE_GUARD', 'value': 'true'},
                    {'name': 'SYNC_LEGACY_COMPLETION_CONVERGENCE', 'value': 'true'},
                ]
            },
            'backend-integration': {
                'env': [
                    {'name': 'FIRST_SUMMARY_DEADLINE_ENABLED', 'value': 'true'},
                    {'name': 'FIRST_SUMMARY_UID_ALLOWLIST', 'value': 'sensitive-uid-123'},
                ]
            },
        }
    }
    old_manifest_path = tmp_path / 'old_runtime_env.yaml'
    old_manifest_path.write_text(yaml.safe_dump(old_manifest), encoding='utf-8')
    new_manifest_path = tmp_path / 'new_runtime_env.yaml'
    new_manifest_path.write_text(yaml.safe_dump(new_manifest), encoding='utf-8')
    state_file = tmp_path / 'cloud_run_state.json'
    state_file.write_text(json.dumps(cloud_run_state), encoding='utf-8')
    summary_file = tmp_path / 'summary.md'

    assert (
        checker.main(
            [
                '--env',
                'prod',
                '--manifest',
                str(old_manifest_path),
                '--cloud-run-state',
                str(state_file),
                '--summary-file',
                str(summary_file),
            ]
        )
        == 0
    )
    summary_text = summary_file.read_text(encoding='utf-8')
    assert 'SYNC_DURABLE_REDRIVE_GUARD' in summary_text
    assert 'SYNC_LEGACY_COMPLETION_CONVERGENCE' in summary_text
    assert 'sensitive-uid-123' not in summary_text

    assert (
        checker.main(
            [
                '--env',
                'prod',
                '--manifest',
                str(old_manifest_path),
                '--cloud-run-state',
                str(state_file),
                '--strict',
            ]
        )
        == 1
    )
    assert (
        checker.main(
            [
                '--env',
                'prod',
                '--manifest',
                str(new_manifest_path),
                '--cloud-run-state',
                str(state_file),
                '--strict',
            ]
        )
        == 0
    )


def test_deploy_backend_stack_wires_non_blocking_drift_report() -> None:
    action_path = BACKEND_ROOT.parent / '.github/actions/deploy-backend-stack/action.yml'
    action = yaml.load(action_path.read_text(encoding='utf-8'), Loader=yaml.CSafeLoader)
    steps = action['runs']['steps']
    drift_steps = [s for s in steps if 'check_cloud_run_env_drift.py' in str(s.get('run', ''))]
    assert len(drift_steps) == 1
    run_cmd = drift_steps[0]['run']
    assert '--strict' not in run_cmd
    assert '--summary-file "$GITHUB_STEP_SUMMARY"' in run_cmd

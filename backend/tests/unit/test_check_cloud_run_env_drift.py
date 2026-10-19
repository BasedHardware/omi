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
PROD_MANIFEST = BACKEND_ROOT / 'deploy' / 'runtime_env.yaml'


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
    _, _, declared = checker.declared_manifest_keys(env='prod', manifest_path=PROD_MANIFEST)
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
    cloud_run_state = {
        'services': {
            'backend': {
                'env': [
                    *({'name': k, 'value': 'v'} for k in sorted(prod_declared['backend'])),
                    {'name': 'OMI_BACKEND_RELEASE_SHA', 'value': 'deadbeef'},
                    {'name': 'BATCH_PIPELINE_UID_ALLOWLIST', 'value': 'sensitive-uid-123'},
                ]
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
        manifest_path=PROD_MANIFEST,
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
                        'backend': {'env': {'BUCKET_TEMPORAL_SYNC_LOCAL': {'value': 'syncing-local'}}},
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
                        'backend': {'env': {'BUCKET_TEMPORAL_SYNC_LOCAL': {'value': 'syncing-local'}}},
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


# ── 2026-10-18 23:50Z replay: template != serving ──────────────────────────
#
# A plain deploy at 22:16Z created dbb7387 revisions that never took traffic
# (traffic is pinned per revision). Reading `services describe` spec.template
# showed backend-sync "reset" to the manifest values (SYNC_TASKS_QUEUE=sync-jobs,
# SUMMARY_DEBT_REPAIR_ENABLED=true). The operator "restored" them at 23:48Z,
# which only created another non-serving revision, 01241-6g6. All along,
# 01239-rmc served 100% with the operator values intact.

SERVING_REVISION = 'backend-sync-01239-rmc'
TEMPLATE_REVISION = 'backend-sync-dbb7387-39171480834-1'
OPERATOR_QUEUE = 'sync-jobs-fresh'
SENSITIVE_UID = 'uid-sensitive-0001'


def _two_service_manifest(tmp_path: Path) -> Path:
    manifest = {
        'schema_version': 2,
        'environments': {
            'prod': {
                'compute_project': 'based-hardware',
                'region': 'us-central1',
                'cloud_run': {
                    'services': {
                        'backend-sync': {
                            'env': {
                                'SYNC_TASKS_QUEUE': {'value': 'sync-jobs'},
                                'SUMMARY_DEBT_REPAIR_ENABLED': {'value': 'true'},
                                'DEMAND_PROCESSING_UID_ALLOWLIST': {'value': ''},
                                'SYNC_TASKS_HANDLER_URL': {'env_var': 'SYNC_TASKS_HANDLER_URL_FOR_TEST'},
                            },
                            'secrets': {'TYPESENSE_HOST': {'secret': 'TYPESENSE_HOST', 'version': 'latest'}},
                        },
                        'backend': {'env': {'SYNC_TASKS_QUEUE': {'value': 'sync-jobs'}}},
                    }
                },
            }
        },
    }
    path = tmp_path / 'runtime_env.yaml'
    path.write_text(yaml.safe_dump(manifest), encoding='utf-8')
    return path


def _container(env: list[dict]) -> dict:
    return {'name': 'backend-sync-1', 'env': env}


def _sync_env(*, queue: str, repair: str, uid_allowlist: str = '') -> list[dict]:
    return [
        {'name': 'SYNC_TASKS_QUEUE', 'value': queue},
        {'name': 'SUMMARY_DEBT_REPAIR_ENABLED', 'value': repair},
        {'name': 'DEMAND_PROCESSING_UID_ALLOWLIST', 'value': uid_allowlist},
        {'name': 'SYNC_TASKS_HANDLER_URL', 'value': 'https://handler.example/run'},
        {'name': 'TYPESENSE_HOST', 'valueFrom': {'secretKeyRef': {'name': 'TYPESENSE_HOST', 'key': 'latest'}}},
        {'name': 'FIRST_SUMMARY_UID_ALLOWLIST', 'value': SENSITIVE_UID},
    ]


def _replay_state(*, serving_env: list[dict], traffic: list[dict] | None = None) -> dict:
    template_env = _sync_env(queue='sync-jobs', repair='true')
    return {
        'services': {
            'backend-sync': {
                'spec': {
                    'template': {
                        'metadata': {'name': TEMPLATE_REVISION},
                        'spec': {'containers': [_container(template_env), {'name': 'collector', 'env': []}]},
                    },
                    'traffic': [{'revisionName': SERVING_REVISION, 'percent': 100}],
                },
                'status': {
                    'latestCreatedRevisionName': TEMPLATE_REVISION,
                    'latestReadyRevisionName': TEMPLATE_REVISION,
                    'traffic': traffic
                    or [
                        {'revisionName': SERVING_REVISION, 'percent': 100},
                        {'revisionName': TEMPLATE_REVISION, 'percent': 0, 'tag': 'candidate'},
                    ],
                },
            },
        },
        'revisions': {
            SERVING_REVISION: {'spec': {'containers': [_container(serving_env), {'name': 'collector'}]}},
            TEMPLATE_REVISION: {'spec': {'containers': [_container(template_env)]}},
        },
    }


def test_replay_2026_10_18_reads_serving_revision_not_template(checker, tmp_path: Path) -> None:
    manifest_path = _two_service_manifest(tmp_path)
    state = _replay_state(serving_env=_sync_env(queue=OPERATOR_QUEUE, repair='false'))

    _, _, results = checker.inspect_services_drift(
        env='prod', services=('backend-sync',), manifest_path=manifest_path, cloud_run_state=state
    )
    (sync,) = results
    assert sync.error is None
    assert [t.name for t in sync.serving] == [SERVING_REVISION]
    assert sync.template_name == TEMPLATE_REVISION
    assert sync.template_matches_serving is False
    # The serving revision kept the operator values: value drift vs manifest, not a reset.
    mismatches = {m.key: m for m in sync.value_mismatches}
    assert set(mismatches) == {'SYNC_TASKS_QUEUE', 'SUMMARY_DEBT_REPAIR_ENABLED'}
    assert mismatches['SYNC_TASKS_QUEUE'].live_hash == checker.value_hash('value', OPERATOR_QUEUE)
    assert mismatches['SYNC_TASKS_QUEUE'].expected_hash == checker.value_hash('value', 'sync-jobs')
    assert mismatches['SYNC_TASKS_QUEUE'].target == SERVING_REVISION
    assert sync.missing_from_live == ()
    assert sync.allowlisted_live_only == ('FIRST_SUMMARY_UID_ALLOWLIST',)
    assert sync.value_unchecked_keys == 1  # env_var binding without rendered state
    assert sync.status == 'DRIFT'
    # Published fingerprint is the redacted one (a sensitive key is present).
    assert sync.serving[0].display_fingerprint != sync.serving[0].fingerprint

    # The template-reading misread: the template matches the manifest exactly.
    template_only = {'services': {'backend-sync': {'env': _sync_env(queue='sync-jobs', repair='true')}}}
    _, _, (template_view,) = checker.inspect_services_drift(
        env='prod', services=('backend-sync',), manifest_path=manifest_path, cloud_run_state=template_only
    )
    assert template_view.value_mismatches == ()


def test_serving_matching_manifest_is_clean_even_when_template_differs(checker, tmp_path: Path) -> None:
    manifest_path = _two_service_manifest(tmp_path)
    state = _replay_state(serving_env=_sync_env(queue='sync-jobs', repair='true'))
    state['services']['backend-sync']['spec']['template']['spec']['containers'][0]['env'] = _sync_env(
        queue=OPERATOR_QUEUE, repair='false'
    )
    _, _, (sync,) = checker.inspect_services_drift(
        env='prod', services=('backend-sync',), manifest_path=manifest_path, cloud_run_state=state
    )
    assert sync.value_mismatches == ()
    assert sync.template_matches_serving is False
    assert sync.status == 'OK'


def test_latest_revision_traffic_and_split_traffic_are_resolved(checker, tmp_path: Path) -> None:
    manifest_path = _two_service_manifest(tmp_path)
    state = _replay_state(
        serving_env=_sync_env(queue='sync-jobs', repair='true'),
        traffic=[
            {'revisionName': SERVING_REVISION, 'percent': 90},
            {'latestRevision': True, 'percent': 10},
        ],
    )
    _, _, (sync,) = checker.inspect_services_drift(
        env='prod', services=('backend-sync',), manifest_path=manifest_path, cloud_run_state=state
    )
    assert [(t.name, t.weight) for t in sync.serving] == [(SERVING_REVISION, 90), (TEMPLATE_REVISION, 10)]
    assert sync.value_mismatches == ()
    assert sync.template_matches_serving is True


def test_missing_traffic_never_falls_back_to_template(checker, tmp_path: Path) -> None:
    manifest_path = _two_service_manifest(tmp_path)
    state = _replay_state(serving_env=_sync_env(queue='sync-jobs', repair='true'))
    state['services']['backend-sync']['status'].pop('traffic')
    _, _, (sync,) = checker.inspect_services_drift(
        env='prod', services=('backend-sync',), manifest_path=manifest_path, cloud_run_state=state
    )
    assert sync.status == 'ERROR'
    assert 'status.traffic' in (sync.error or '')


def test_offline_template_snapshot_without_status_is_rejected(checker, tmp_path: Path) -> None:
    # A partial `services describe` fixture with spec.template but no status at all
    # must not be compared as if the template were serving.
    manifest_path = _two_service_manifest(tmp_path)
    state = _replay_state(serving_env=_sync_env(queue='sync-jobs', repair='true'))
    state['services']['backend-sync'].pop('status')
    _, _, (sync,) = checker.inspect_services_drift(
        env='prod', services=('backend-sync',), manifest_path=manifest_path, cloud_run_state=state
    )
    assert sync.status == 'ERROR'
    assert 'status.traffic' in (sync.error or '')


def test_unresolved_bindings_are_still_presence_checked(checker, tmp_path: Path) -> None:
    # A deploy-time `env_var` binding with no rendered state is value-unchecked,
    # but its key must still be required on the serving revision.
    manifest_path = _two_service_manifest(tmp_path)
    serving_env = [e for e in _sync_env(queue='sync-jobs', repair='true') if e['name'] != 'SYNC_TASKS_HANDLER_URL']
    state = _replay_state(serving_env=serving_env)
    _, _, (sync,) = checker.inspect_services_drift(
        env='prod', services=('backend-sync',), manifest_path=manifest_path, cloud_run_state=state
    )
    assert sync.missing_from_live == ('SYNC_TASKS_HANDLER_URL',)
    assert sync.value_unchecked_keys == 1
    assert sync.status == 'DRIFT'
    assert checker.exit_code((sync,), strict=True) == 1


def test_live_reads_describe_serving_revisions_with_gcloud(checker, tmp_path: Path) -> None:
    manifest_path = _two_service_manifest(tmp_path)
    state = _replay_state(serving_env=_sync_env(queue=OPERATOR_QUEUE, repair='false'))
    calls: list[list[str]] = []

    def runner(argv, **_kwargs):
        calls.append(argv)
        if argv[:4] == ['gcloud', 'run', 'services', 'describe']:
            doc = state['services'][argv[4]]
        else:
            assert argv[:4] == ['gcloud', 'run', 'revisions', 'describe']
            doc = state['revisions'][argv[4]]
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(doc), stderr='')

    _, _, (sync,) = checker.inspect_services_drift(
        env='prod', services=('backend-sync',), manifest_path=manifest_path, runner=runner
    )
    assert [c[3:5] for c in calls] == [['describe', 'backend-sync'], ['describe', SERVING_REVISION]]
    assert calls[1][2] == 'revisions'
    assert {m.key for m in sync.value_mismatches} == {'SYNC_TASKS_QUEUE', 'SUMMARY_DEBT_REPAIR_ENABLED'}


def test_rendered_state_supplies_exact_expected_values(checker, tmp_path: Path) -> None:
    manifest_path = _two_service_manifest(tmp_path)
    rendered = tmp_path / 'state.json'
    rendered.write_text(
        json.dumps(
            {'services': {'backend-sync': {'env': [{'name': 'SYNC_TASKS_HANDLER_URL', 'value': 'https://other/run'}]}}}
        ),
        encoding='utf-8',
    )
    state = _replay_state(serving_env=_sync_env(queue='sync-jobs', repair='true'))
    _, _, (sync,) = checker.inspect_services_drift(
        env='prod',
        services=('backend-sync',),
        manifest_path=manifest_path,
        rendered_state_path=rendered,
        cloud_run_state=state,
    )
    assert [m.key for m in sync.value_mismatches] == ['SYNC_TASKS_HANDLER_URL']
    assert sync.value_unchecked_keys == 0


def test_rendered_state_file_must_exist_and_have_services(checker, tmp_path: Path) -> None:
    manifest_path = _two_service_manifest(tmp_path)
    with pytest.raises(ValueError, match='not found'):
        checker.expected_cloud_run_env(
            env='prod', manifest_path=manifest_path, rendered_state_path=tmp_path / 'missing.json'
        )
    bad = tmp_path / 'bad.json'
    bad.write_text(json.dumps({'jobs': {}}), encoding='utf-8')
    with pytest.raises(ValueError, match='services'):
        checker.expected_cloud_run_env(env='prod', manifest_path=manifest_path, rendered_state_path=bad)


def test_reports_never_print_values_and_redact_sensitive_hashes(checker, tmp_path: Path, capsys) -> None:
    manifest_path = _two_service_manifest(tmp_path)
    state = _replay_state(serving_env=_sync_env(queue=OPERATOR_QUEUE, repair='false', uid_allowlist=SENSITIVE_UID))
    state_file = tmp_path / 'state.json'
    state_file.write_text(json.dumps(state), encoding='utf-8')
    summary = tmp_path / 'summary.md'
    for fmt in ('markdown', 'json'):
        rc = checker.main(
            [
                '--manifest',
                str(manifest_path),
                '--cloud-run-state',
                str(state_file),
                '--service',
                'backend-sync',
                '--format',
                fmt,
                '--summary-file',
                str(summary),
            ]
        )
        assert rc == 0  # report-only by default
        out = capsys.readouterr().out
        for leaked in (OPERATOR_QUEUE, SENSITIVE_UID, 'https://handler.example/run'):
            assert leaked not in out
        assert 'DEMAND_PROCESSING_UID_ALLOWLIST' in out
        assert checker.value_hash('value', SENSITIVE_UID) not in out
        assert checker.value_hash('value', OPERATOR_QUEUE) in out
        env_map = checker._env_list_to_live(
            _sync_env(queue=OPERATOR_QUEUE, repair='false', uid_allowlist=SENSITIVE_UID), scope='backend-sync'
        )
        assert checker.env_fingerprint(env_map) not in out  # internal full fingerprint never prints
        assert checker.env_fingerprint(env_map, redacted=True) in out  # the published one is the redacted form
    text = summary.read_text(encoding='utf-8')
    assert OPERATOR_QUEUE not in text and SENSITIVE_UID not in text
    assert 'Template `backend-sync-dbb7387-39171480834-1` differs' in text


def test_fingerprint_display_redacts_sensitive_keys(checker) -> None:
    env1 = {'A': 'h1', 'SECRET_TOKEN': 'x1'}
    env2 = {'A': 'h1', 'SECRET_TOKEN': 'x2'}
    assert checker.env_fingerprint(env1) != checker.env_fingerprint(env2)
    assert checker.env_fingerprint(env1, redacted=True) == checker.env_fingerprint(env2, redacted=True)


def test_secret_ref_hash_keeps_project_and_optionality(checker) -> None:
    # A cross-project rebind of the same secret name must change the hash.
    assert checker._secret_ref_hash('projects/a/secrets/x', 'v') != checker._secret_ref_hash(
        'projects/b/secrets/x', 'v'
    )
    assert checker._secret_ref_hash('x', 'v') == checker._secret_ref_hash('x', 'v')
    base = {'valueFrom': {'secretKeyRef': {'name': 'S', 'key': 'K'}}}
    optional_false = {'valueFrom': {'secretKeyRef': {'name': 'S', 'key': 'K', 'optional': False}}}
    optional_true = {'valueFrom': {'secretKeyRef': {'name': 'S', 'key': 'K', 'optional': True}}}
    assert checker.env_entry_hash(base) == checker.env_entry_hash(optional_false)  # normalized default
    assert checker.env_entry_hash(base) != checker.env_entry_hash(optional_true)


def test_strict_exit_codes(checker, tmp_path: Path) -> None:
    manifest_path = _two_service_manifest(tmp_path)

    def run(state: dict, *extra: str) -> int:
        state_file = tmp_path / 'strict.json'
        state_file.write_text(json.dumps(state), encoding='utf-8')
        return checker.main(
            [
                '--manifest',
                str(manifest_path),
                '--cloud-run-state',
                str(state_file),
                '--service',
                'backend-sync',
                *extra,
            ]
        )

    drifted = _replay_state(serving_env=_sync_env(queue=OPERATOR_QUEUE, repair='false'))
    clean = _replay_state(serving_env=_sync_env(queue='sync-jobs', repair='true'))
    broken = _replay_state(serving_env=_sync_env(queue='sync-jobs', repair='true'))
    broken['revisions'].pop(SERVING_REVISION)
    assert run(drifted) == 0
    assert run(drifted, '--strict') == 1
    assert run(clean, '--strict') == 0
    assert run(broken) == 0
    assert run(broken, '--strict') == 2


def test_strict_exit_code_prefers_errors_over_drift(checker) -> None:
    drift = checker.ServiceEnvDrift(
        service='a', manifest_key_count=1, live_key_count=1, allowlisted_live_only=(), unallowlisted_live_only=('X',)
    )
    error = checker.ServiceEnvDrift(
        service='b',
        manifest_key_count=1,
        live_key_count=1,
        allowlisted_live_only=(),
        unallowlisted_live_only=(),
        error='fetch failed',
    )
    assert checker.exit_code((drift,), strict=True) == 1
    assert checker.exit_code((error,), strict=True) == 2
    assert checker.exit_code((drift, error), strict=True) == 2  # incomplete comparison outranks drift
    assert checker.exit_code((drift, error), strict=False) == 0


def test_render_failure_returns_render_error_code(checker, tmp_path: Path, capsys) -> None:
    broken_manifest = tmp_path / 'broken_runtime_env.yaml'
    broken_manifest.write_text('environments: [', encoding='utf-8')
    assert checker.main(['--manifest', str(broken_manifest), '--strict']) == 2
    assert checker.main(['--manifest', str(broken_manifest)]) == 0
    assert 'could not render expected state' in capsys.readouterr().err

    manifest_path = _two_service_manifest(tmp_path)
    assert (
        checker.main(['--manifest', str(manifest_path), '--rendered-state', str(tmp_path / 'nope.json'), '--strict'])
        == 2
    )


def test_no_cloud_run_requires_a_gke_target(checker) -> None:
    with pytest.raises(SystemExit) as excinfo:
        checker.main(['--no-cloud-run', '--strict'])
    assert excinfo.value.code == 2


def test_env_var_default_is_compared_by_name_only(checker, tmp_path: Path) -> None:
    manifest = {
        'schema_version': 2,
        'environments': {
            'prod': {
                'compute_project': 'based-hardware',
                'cloud_run': {
                    'services': {
                        'backend': {'env': {'GATEWAY_URL': {'env_var': 'GATEWAY_URL_FOR_TEST', 'default': 'a'}}}
                    }
                },
            }
        },
    }
    path = tmp_path / 'm.yaml'
    path.write_text(yaml.safe_dump(manifest), encoding='utf-8')
    _, _, expected = checker.expected_cloud_run_env(env='prod', manifest_path=path)
    assert expected['backend'] == {'GATEWAY_URL': None}
    _, _, expected = checker.expected_cloud_run_env(
        env='prod', manifest_path=path, environ={'GATEWAY_URL_FOR_TEST': 'b'}
    )
    assert expected['backend'] == {'GATEWAY_URL': checker.value_hash('value', 'b')}


# ── GKE ─────────────────────────────────────────────────────────────────────


def _replicaset(
    name: str, owner: str, ready: int, env: list[dict], container: str = 'pusher', envfrom: list[dict] | None = None
) -> dict:
    container_doc: dict = {'name': container, 'env': env}
    if envfrom is not None:
        container_doc['envFrom'] = envfrom
    return {
        'metadata': {'name': name, 'ownerReferences': [{'kind': 'Deployment', 'name': owner}]},
        'spec': {'template': {'spec': {'containers': [container_doc]}}},
        'status': {'replicas': ready, 'readyReplicas': ready},
    }


def _prod_configmap_fixture(checker) -> tuple[str, dict[str, str]]:
    cm_name, entries = checker.manifest_config_map('prod', PROD_MANIFEST)
    data = {
        key: (
            str(raw['value'])
            if isinstance(raw, dict) and raw.get('source') == 'literal' and isinstance(raw.get('value'), str)
            else ''
        )
        for key, raw in entries.items()
    }
    return cm_name, data


def test_gke_reads_ready_replicasets_and_flags_template_rollout(checker) -> None:
    cm_name, cm_data = _prod_configmap_fixture(checker)
    envfrom = [{'configMapRef': {'name': cm_name}}]
    expected = {
        'STT_SERVICE_MODELS': checker.value_hash('value', 'dg-nova-3,parakeet'),
        'REDIS_DB_PASSWORD': checker.env_entry_hash(
            {'valueFrom': {'secretKeyRef': {'name': 'prod-omi-backend-secrets', 'key': 'REDIS_DB_PASSWORD'}}}
        ),
    }
    serving_env = [
        {'name': 'STT_SERVICE_MODELS', 'value': 'dg-nova-3'},
        {
            'name': 'REDIS_DB_PASSWORD',
            'valueFrom': {'secretKeyRef': {'name': 'prod-omi-backend-secrets', 'key': 'REDIS_DB_PASSWORD'}},
        },
        {'name': 'OUT_OF_BAND', 'value': 'kubectl-set-env'},
    ]
    template_env = [
        {'name': 'STT_SERVICE_MODELS', 'value': 'dg-nova-3,parakeet'},
        serving_env[1],
    ]
    gke_state = {
        'configmaps': {cm_name: {'data': cm_data}},
        'pusher': {
            'deployment': {
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {'name': 'pusher', 'env': template_env, 'envFrom': envfrom},
                                {'name': 'collector', 'env': []},
                            ]
                        }
                    }
                }
            },
            'replicasets': [
                _replicaset('prod-omi-pusher-new', 'prod-omi-pusher', 0, template_env, envfrom=envfrom),
                _replicaset('prod-omi-pusher-old', 'prod-omi-pusher', 17, serving_env, envfrom=envfrom),
                _replicaset('prod-omi-other-x', 'prod-omi-other', 3, [], envfrom=envfrom),
            ],
        },
    }
    (pusher,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), gke_state=gke_state, expected_overrides={'pusher': expected}
    )
    assert pusher.platform == 'gke'
    assert [(t.name, t.weight) for t in pusher.serving] == [('prod-omi-pusher-old', 17)]
    assert pusher.template_matches_serving is False
    assert [m.key for m in pusher.value_mismatches] == ['STT_SERVICE_MODELS']
    assert pusher.unallowlisted_live_only == ('OUT_OF_BAND',)
    assert pusher.envfrom_refs == (cm_name,)
    assert pusher.envfrom_mismatched_refs == ()
    assert pusher.envfrom_unresolved == ()
    assert pusher.status == 'DRIFT'


def test_gke_envfrom_configmap_keys_are_compared(checker) -> None:
    cm_name, cm_data = _prod_configmap_fixture(checker)
    envfrom = [{'configMapRef': {'name': cm_name}}]
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    overrides = {'pusher': {'X': checker.value_hash('value', 'x')}}

    def run(configmaps: dict | None):
        gke_state = {
            **({'configmaps': configmaps} if configmaps is not None else {}),
            'pusher': {
                'deployment': {
                    'spec': {
                        'template': {
                            'spec': {'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': envfrom}]}
                        }
                    }
                },
                'replicasets': [_replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=envfrom)],
            },
        }
        (result,) = checker.inspect_gke_drift(
            env='prod', workloads=('pusher',), gke_state=gke_state, expected_overrides=overrides
        )
        return result

    ok = run({cm_name: {'data': cm_data}})
    assert ok.status == 'OK', ok
    assert ok.envfrom_refs == (cm_name,)
    assert ok.envfrom_mismatched_refs == ()
    assert ok.envfrom_unresolved == ()
    assert ok.missing_from_live == ()
    assert ok.value_unchecked_keys >= 1  # environment-sourced ConfigMap keys stay name-only

    dropped = {k: v for k, v in cm_data.items() if k != 'GOOGLE_CLIENT_ID'}
    missing = run({cm_name: {'data': dropped}})
    assert missing.status == 'DRIFT'
    assert 'GOOGLE_CLIENT_ID' in missing.missing_from_live
    assert checker.exit_code((missing,), strict=True) == 1

    tampered = dict(cm_data)
    tampered['STT_SERVICE_MODELS'] = 'someone-kubectl-patched-this'
    mismatched = run({cm_name: {'data': tampered}})
    assert mismatched.status == 'DRIFT'
    assert 'STT_SERVICE_MODELS' in {m.key for m in mismatched.value_mismatches}

    unresolved = run(None)
    assert unresolved.status == 'INVENTORY'
    assert unresolved.envfrom_unresolved == (cm_name,)
    assert not unresolved.has_drift
    assert checker.exit_code((unresolved,), strict=True) == 0


def test_gke_envfrom_reference_drift_is_flagged(checker) -> None:
    cm_name, cm_data = _prod_configmap_fixture(checker)
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    overrides = {'pusher': {'X': checker.value_hash('value', 'x')}}
    gke_state = {
        'configmaps': {cm_name: {'data': cm_data}},
        'pusher': {
            'deployment': {
                'spec': {
                    'template': {
                        'spec': {
                            # Serving pods pull a different ConfigMap than the chart declares.
                            'containers': [
                                {
                                    'name': 'pusher',
                                    'env': serving_env,
                                    'envFrom': [{'configMapRef': {'name': 'prod-omi-someone-elses-config'}}],
                                }
                            ]
                        }
                    }
                }
            },
            'replicasets': [
                _replicaset(
                    f'{deployment}-a',
                    deployment,
                    2,
                    serving_env,
                    'pusher',
                    envfrom=[{'configMapRef': {'name': 'prod-omi-someone-elses-config'}}],
                )
            ],
        },
    }
    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), gke_state=gke_state, expected_overrides=overrides
    )
    assert result.envfrom_mismatched_refs == ('prod-omi-backend-config', 'prod-omi-someone-elses-config')
    assert result.status == 'DRIFT'


def test_gke_values_mode_matches_prod_chart_values(checker) -> None:
    cm_name, cm_data = _prod_configmap_fixture(checker)
    envfrom = [{'configMapRef': {'name': cm_name}}]
    for workload in ('backend-listen', 'pusher'):
        spec = checker.GKE_WORKLOADS[workload]
        values = yaml.safe_load((BACKEND_ROOT.parent / spec.values_file.format(env='prod')).read_text(encoding='utf-8'))
        live_env = []
        for entry in values['env']:
            entry = dict(entry)
            if workload == 'backend-listen' and entry['name'] == 'GOOGLE_CLOUD_PROJECT':
                entry['value'] = values['runtimeGcpProjectId']
            ref = (entry.get('valueFrom') or {}).get('configMapKeyRef')
            if ref is not None and values.get('runtimeConfigMapName'):
                entry['valueFrom'] = {'configMapKeyRef': {**ref, 'name': values['runtimeConfigMapName']}}
            live_env.append(entry)
        deployment = spec.deployment.format(env='prod')
        gke_state = {
            'configmaps': {cm_name: {'data': cm_data}},
            workload: {
                'deployment': {
                    'spec': {
                        'template': {
                            'spec': {'containers': [{'name': spec.container, 'env': live_env, 'envFrom': envfrom}]}
                        }
                    }
                },
                'replicasets': [
                    _replicaset(f'{deployment}-a', deployment, 2, live_env, spec.container, envfrom=envfrom)
                ],
            },
        }
        (result,) = checker.inspect_gke_drift(env='prod', workloads=(workload,), gke_state=gke_state)
        assert result.error is None, result.error
        assert result.status == 'OK', (workload, result)
        assert result.envfrom_refs == (cm_name,)
        assert result.manifest_key_count == len({*(e['name'] for e in live_env), *cm_data})


def test_gke_values_mode_reports_inventory_for_template_built_env(checker) -> None:
    deployment = 'prod-omi-batch-pipeline-worker'
    gke_state = {
        'batch-pipeline-worker': {
            'deployment': {},
            'replicasets': [_replicaset(f'{deployment}-a', deployment, 1, [{'name': 'A', 'value': '1'}], 'worker')],
        }
    }
    (worker,) = checker.inspect_gke_drift(env='prod', workloads=('batch-pipeline-worker',), gke_state=gke_state)
    assert worker.status == 'INVENTORY'
    assert worker.unallowlisted_live_only == ()


def test_gke_live_requires_explicit_context(checker) -> None:
    (listen,) = checker.inspect_gke_drift(env='prod', workloads=('backend-listen',))
    assert listen.status == 'ERROR'
    assert '--kube-context' in (listen.error or '')


def test_gke_helm_render_uses_chart_and_values(checker) -> None:
    calls = []
    rendered = yaml.safe_dump_all(
        [
            {'kind': 'Service', 'metadata': {'name': 'prod-omi-pusher'}},
            {
                'kind': 'Deployment',
                'metadata': {'name': 'prod-omi-pusher'},
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {
                                    'name': 'pusher',
                                    'env': [{'name': 'A', 'value': 'x'}],
                                    'envFrom': [{'configMapRef': {'name': 'prod-omi-backend-config'}}],
                                }
                            ]
                        }
                    }
                },
            },
        ]
    )

    def runner(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')

    expected, refs = checker.expected_gke_env_from_helm('pusher', env='prod', runner=runner)
    assert expected == {'A': checker.value_hash('value', 'x')}
    assert refs == ('prod-omi-backend-config',)
    assert calls[0][:3] == ['helm', 'template', 'prod-omi-pusher']
    assert calls[0][4:6] == ['-f', str(BACKEND_ROOT.parent / 'backend/charts/pusher/prod_omi_pusher_values.yaml')]


def test_field_ref_hash_ignores_server_defaulted_api_version(checker) -> None:
    rendered = {'valueFrom': {'fieldRef': {'fieldPath': 'metadata.namespace'}}}
    served = {'valueFrom': {'fieldRef': {'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}}
    assert checker.env_entry_hash(rendered) == checker.env_entry_hash(served)

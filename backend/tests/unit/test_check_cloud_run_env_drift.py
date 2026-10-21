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
            {
                'services': {
                    # The renderer emits every manifest service; a partial state is rejected.
                    'backend': {'env': []},
                    'backend-sync': {'env': [{'name': 'SYNC_TASKS_HANDLER_URL', 'value': 'https://other/run'}]},
                }
            }
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


def test_rendered_state_must_carry_every_checked_service(checker, tmp_path: Path) -> None:
    # A rendered state with a valid top-level services mapping but no entry (or
    # a non-mapping entry) for a checked service must be rejected: falling back
    # to the raw manifest would silently degrade deploy-time bindings to
    # name-only checks while the command claims exact-state validation.
    manifest_path = _two_service_manifest(tmp_path)
    missing = tmp_path / 'missing-service.json'
    missing.write_text(json.dumps({'services': {'backend': {'env': []}}}), encoding='utf-8')
    with pytest.raises(ValueError, match="no valid entry for service 'backend-sync'"):
        checker.expected_cloud_run_env(env='prod', manifest_path=manifest_path, rendered_state_path=missing)
    malformed = tmp_path / 'malformed-service.json'
    malformed.write_text(
        json.dumps({'services': {'backend': {'env': []}, 'backend-sync': 'not-a-mapping'}}), encoding='utf-8'
    )
    with pytest.raises(ValueError, match="no valid entry for service 'backend-sync'"):
        checker.expected_cloud_run_env(env='prod', manifest_path=manifest_path, rendered_state_path=malformed)


def test_rendered_state_env_member_must_be_a_list(checker, tmp_path: Path) -> None:
    # A rendered service entry whose env member is missing, null, or not a list
    # is not renderer output (the renderer always emits an env list); it must be
    # rejected instead of silently re-sourcing expected values from the manifest.
    manifest_path = _two_service_manifest(tmp_path)
    no_env = tmp_path / 'no-env.json'
    no_env.write_text(
        json.dumps({'services': {'backend': {'env': []}, 'backend-sync': {'flags': {}}}}), encoding='utf-8'
    )
    with pytest.raises(ValueError, match="entry for service 'backend-sync' has no env list"):
        checker.expected_cloud_run_env(env='prod', manifest_path=manifest_path, rendered_state_path=no_env)


def test_rendered_state_drops_omitted_provisional_bindings(checker, tmp_path: Path) -> None:
    # The renderer omits a provisional env_var that was unset at deploy time; the
    # exact rendered state must not inherit that key as a name-only requirement.
    manifest = {
        'schema_version': 2,
        'environments': {
            'prod': {
                'compute_project': 'based-hardware',
                'region': 'us-central1',
                'cloud_run': {
                    'services': {
                        'backend': {
                            'env': {
                                'ALWAYS_THERE': {'value': 'a'},
                                'PROVISIONAL_THING': {
                                    'env_var': 'PROVISIONAL_THING_FOR_TEST',
                                    'provisional': True,
                                },
                            }
                        }
                    }
                },
            }
        },
    }
    path = tmp_path / 'm.yaml'
    path.write_text(yaml.safe_dump(manifest), encoding='utf-8')
    rendered = tmp_path / 'state.json'
    rendered.write_text(
        json.dumps({'services': {'backend': {'env': [{'name': 'ALWAYS_THERE', 'value': 'a'}]}}}), encoding='utf-8'
    )
    _, _, expected = checker.expected_cloud_run_env(env='prod', manifest_path=path, rendered_state_path=rendered)
    assert expected['backend'] == {'ALWAYS_THERE': checker.value_hash('value', 'a')}
    # Without rendered state the provisional binding stays a name-only expectation.
    _, _, expected = checker.expected_cloud_run_env(env='prod', manifest_path=path)
    assert expected['backend']['PROVISIONAL_THING'] is None
    # And a serving env that never received it reports clean against exact state.
    state = {'services': {'backend': {'env': [{'name': 'ALWAYS_THERE', 'value': 'a'}]}}}
    _, _, (result,) = checker.inspect_services_drift(
        env='prod', services=('backend',), manifest_path=path, rendered_state_path=rendered, cloud_run_state=state
    )
    assert result.status == 'OK'
    assert result.missing_from_live == ()


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


def test_offline_state_load_failures_are_operational(checker, tmp_path: Path, capsys) -> None:
    manifest_path = _two_service_manifest(tmp_path)
    assert (
        checker.main(['--manifest', str(manifest_path), '--cloud-run-state', str(tmp_path / 'nope.json'), '--strict'])
        == 2
    )
    bad = tmp_path / 'bad_state.json'
    bad.write_text('{', encoding='utf-8')
    assert checker.main(['--manifest', str(manifest_path), '--cloud-run-state', str(bad), '--strict']) == 2
    assert 'could not render expected state' in capsys.readouterr().err
    assert checker.main(['--manifest', str(manifest_path), '--cloud-run-state', str(tmp_path / 'nope.json')]) == 0


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


def test_gke_envfrom_prefix_is_part_of_the_reference(checker) -> None:
    # A prefixed envFrom source yields X_KEY, not KEY: both the reference
    # identity and the expanded key names must carry the prefix.
    cm_name, cm_data = _prod_configmap_fixture(checker)
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    overrides = {'pusher': {'X': checker.value_hash('value', 'x')}}
    prefixed = [{'prefix': 'CFG_', 'configMapRef': {'name': cm_name}}]

    def run(envfrom: list[dict]):
        gke_state = {
            'configmaps': {cm_name: {'data': cm_data}},
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

    prefixed_result = run(prefixed)
    # The chart declares the unprefixed reference; the symmetric difference flags both.
    assert prefixed_result.envfrom_mismatched_refs == (cm_name, f'{cm_name}#CFG_')
    assert prefixed_result.status == 'DRIFT'
    assert prefixed_result.missing_from_live  # CFG_-prefixed names are absent from the unprefixed expectations
    # Sanity: the same fixture without the prefix is OK (covered fully below).
    unprefixed = run([{'configMapRef': {'name': cm_name}}])
    assert unprefixed.status == 'OK'


def test_gke_live_envfrom_data_is_unproven_and_reports_inventory(checker) -> None:
    # Live reads cannot prove the current ConfigMap data matches what running
    # pods resolved at container start; keys must not be asserted (P1).
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    cm_doc = {'data': {'GOOGLE_CLIENT_ID': 'id'}}
    calls: list[list[str]] = []

    def runner(argv, **_kwargs):
        calls.append(argv)
        if 'replicasets' in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        'items': [
                            _replicaset(
                                f'{deployment}-a',
                                deployment,
                                2,
                                serving_env,
                                'pusher',
                                envfrom=[{'configMapRef': {'name': 'prod-omi-backend-config'}}],
                            )
                        ]
                    }
                ),
                stderr='',
            )
        if 'configmap' in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(cm_doc), stderr='')
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {'spec': {'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env}]}}}}
            ),
            stderr='',
        )

    overrides = {'pusher': {'X': checker.value_hash('value', 'x')}}
    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), kube_context='gke_ctx', runner=runner, expected_overrides=overrides
    )
    assert result.error is None, result.error
    assert result.envfrom_unproven == ('prod-omi-backend-config',)
    assert result.status == 'INVENTORY'
    assert result.missing_from_live == ()  # envFrom keys not asserted against unproven data
    assert result.value_mismatches == ()
    assert not result.has_drift
    assert checker.exit_code((result,), strict=True) == 0


def test_gke_live_explicit_env_shadowing_envfrom_is_compared(checker) -> None:
    # An explicit env entry on the serving ReplicaSet shadows envFrom (K8s
    # precedence) and its spec is immutable, so its value is knowable even when
    # the live ConfigMap data is unproven: a stale serving literal must fail
    # --strict, not hide behind the envFrom INVENTORY downgrade. Keys whose
    # effective value comes only from envFrom stay unasserted.
    deployment = 'prod-omi-pusher'
    serving_env = [
        {'name': 'X', 'value': 'x'},
        # Stale explicit literal; the chart (and manifest ConfigMap contract) say otherwise.
        {'name': 'STT_SERVICE_MODELS', 'value': 'dg-nova-3'},
    ]
    cm_doc = {
        'data': {
            'STT_SERVICE_MODELS': 'someone-updated-the-configmap-after-pod-start',
            'GOOGLE_CLIENT_ID': 'id',
        }
    }

    def runner(argv, **_kwargs):
        if 'replicasets' in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        'items': [
                            _replicaset(
                                f'{deployment}-a',
                                deployment,
                                2,
                                serving_env,
                                'pusher',
                                envfrom=[{'configMapRef': {'name': 'prod-omi-backend-config'}}],
                            )
                        ]
                    }
                ),
                stderr='',
            )
        if 'configmap' in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(cm_doc), stderr='')
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {'spec': {'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env}]}}}}
            ),
            stderr='',
        )

    overrides = {
        'pusher': {
            'X': checker.value_hash('value', 'x'),
            'STT_SERVICE_MODELS': checker.value_hash('value', 'modulate-velma-2,soniox,parakeet'),
        }
    }
    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), kube_context='gke_ctx', runner=runner, expected_overrides=overrides
    )
    assert result.error is None, result.error
    assert result.envfrom_unproven == ('prod-omi-backend-config',)
    assert [m.key for m in result.value_mismatches] == ['STT_SERVICE_MODELS']
    assert result.value_mismatches[0].target == f'{deployment}-a'
    assert result.status == 'DRIFT'
    assert result.has_drift
    assert checker.exit_code((result,), strict=True) == 1
    # The envFrom-only key keeps the unproven downgrade: never asserted either way.
    assert 'GOOGLE_CLIENT_ID' not in {m.key for m in result.value_mismatches}
    assert 'GOOGLE_CLIENT_ID' not in result.missing_from_live


def test_gke_live_envfrom_only_keys_added_after_pod_start_are_not_live_only_drift(checker) -> None:
    # Thread 1: a key kubectl-added to the live ConfigMap after the ready pods
    # started merges into env_map but is in neither declared nor the expected
    # envFrom keys; it must not be reported as unallowlisted live-only drift,
    # and --strict must stay 0 for the envFrom part.
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    cm_doc = {'data': {'GOOGLE_CLIENT_ID': 'id', 'ADDED_AFTER_POD_START': 'late'}}
    overrides = {'pusher': {'X': checker.value_hash('value', 'x')}}

    def runner(argv, **_kwargs):
        if 'replicasets' in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        'items': [
                            _replicaset(
                                f'{deployment}-a',
                                deployment,
                                2,
                                serving_env,
                                'pusher',
                                envfrom=[{'configMapRef': {'name': 'prod-omi-backend-config'}}],
                            )
                        ]
                    }
                ),
                stderr='',
            )
        if 'configmap' in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(cm_doc), stderr='')
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {'spec': {'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env}]}}}}
            ),
            stderr='',
        )

    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), kube_context='gke_ctx', runner=runner, expected_overrides=overrides
    )
    assert result.error is None, result.error
    assert 'ADDED_AFTER_POD_START' not in result.unallowlisted_live_only
    assert 'ADDED_AFTER_POD_START' not in result.allowlisted_live_only
    assert result.unallowlisted_live_only == ()
    # An explicit env entry (out-of-band kubectl-set-env) is still live-only drift.
    rs_env_with_extra = [*serving_env, {'name': 'OUT_OF_BAND', 'value': 'y'}]

    def runner_extra(argv, **_kwargs):
        if 'replicasets' in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        'items': [
                            _replicaset(
                                f'{deployment}-a',
                                deployment,
                                2,
                                rs_env_with_extra,
                                'pusher',
                                envfrom=[{'configMapRef': {'name': 'prod-omi-backend-config'}}],
                            )
                        ]
                    }
                ),
                stderr='',
            )
        if 'configmap' in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(cm_doc), stderr='')
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {'spec': {'template': {'spec': {'containers': [{'name': 'pusher', 'env': rs_env_with_extra}]}}}}
            ),
            stderr='',
        )

    (extra,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), kube_context='gke_ctx', runner=runner_extra, expected_overrides=overrides
    )
    assert extra.error is None, extra.error
    assert extra.unallowlisted_live_only == ('OUT_OF_BAND',)


def test_gke_envfrom_reference_drift_on_one_serving_target_is_flagged(checker) -> None:
    # Thread 3: during a mixed rollout, the new ReplicaSet carries the expected
    # envFrom reference while an older still-serving ReplicaSet has none. The
    # union of references equals the expected set, but the old target's absence
    # is real drift (or at least must not be excused by the new target's unproven
    # ref); per-target comparison flags it instead of INVENTORY.
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    overrides = {'pusher': {'X': checker.value_hash('value', 'x')}}

    def runner(argv, **_kwargs):
        if 'replicasets' in argv:
            items = [
                _replicaset(
                    f'{deployment}-new',
                    deployment,
                    3,
                    serving_env,
                    'pusher',
                    envfrom=[{'configMapRef': {'name': 'prod-omi-backend-config'}}],
                ),
                _replicaset(f'{deployment}-old', deployment, 17, serving_env, 'pusher', envfrom=[]),
            ]
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({'items': items}), stderr='')
        if 'configmap' in argv:
            return subprocess.CompletedProcess(
                argv, 0, stdout=json.dumps({'data': {'GOOGLE_CLIENT_ID': 'id'}}), stderr=''
            )
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {'spec': {'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env}]}}}}
            ),
            stderr='',
        )

    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), kube_context='gke_ctx', runner=runner, expected_overrides=overrides
    )
    assert result.error is None, result.error
    assert len(result.serving) == 2
    # Per-target: the old ReplicaSet without the reference is reference drift.
    assert result.envfrom_mismatched_refs == ('prod-omi-backend-config',)
    assert result.status == 'DRIFT'
    assert result.has_drift
    assert checker.exit_code((result,), strict=True) == 1


def test_gke_expected_configmap_keys_expand_with_envfrom_prefix(checker) -> None:
    # Thread 2: when the expected side declares a prefixed envFrom source
    # (helm render here), the expected ConfigMap keys must expand with the
    # prefix (CFG_<key>). Before the fix the `name#prefix` identity never
    # matched the bare manifest ConfigMap name, so the reference was reported
    # unresolved and the same prefixed keys from a matching serving ReplicaSet
    # became phantom unallowlisted live-only drift.
    cm_name, cm_data = _prod_configmap_fixture(checker)
    deployment = 'prod-omi-pusher'
    prefixed = [{'prefix': 'CFG_', 'configMapRef': {'name': cm_name}}]
    rendered = yaml.safe_dump_all(
        [
            {
                'kind': 'Deployment',
                'metadata': {'name': deployment},
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {'name': 'pusher', 'env': [{'name': 'X', 'value': 'x'}], 'envFrom': prefixed}
                            ]
                        }
                    }
                },
            }
        ]
    )

    def runner(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')

    gke_state = {
        'configmaps': {cm_name: {'data': cm_data}},
        'pusher': {
            'deployment': {},
            'replicasets': [
                _replicaset(f'{deployment}-a', deployment, 2, [{'name': 'X', 'value': 'x'}], 'pusher', envfrom=prefixed)
            ],
        },
    }
    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), render='helm', gke_state=gke_state, runner=runner
    )
    assert result.error is None, result.error
    assert result.envfrom_refs == (f'{cm_name}#CFG_',)
    assert result.envfrom_mismatched_refs == ()
    assert result.envfrom_unresolved == ()
    assert result.unallowlisted_live_only == ()
    assert result.status == 'OK', result
    assert checker.exit_code((result,), strict=True) == 0


def test_gke_envfrom_ref_identity_includes_optionality(checker) -> None:
    # Thread 4: omitted optional and explicit optional:false are identical;
    # optional:true on the serving side is reference drift even with the same
    # name and prefix.
    cm_name, cm_data = _prod_configmap_fixture(checker)
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    overrides = {'pusher': {'X': checker.value_hash('value', 'x')}}

    def run(envfrom: list[dict]):
        gke_state = {
            'configmaps': {cm_name: {'data': cm_data}},
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

    # Explicit optional:false matches the chart's omitted optional.
    assert run([{'configMapRef': {'name': cm_name, 'optional': False}}]).status == 'OK'
    # optional:true changes the reference's meaning: a missing ConfigMap stops
    # blocking the pod, so it is drift, not the same reference.
    optional_true = run([{'configMapRef': {'name': cm_name, 'optional': True}}])
    assert optional_true.envfrom_mismatched_refs == (cm_name, f'{cm_name}?optional')
    assert optional_true.status == 'DRIFT'


def test_gke_envfrom_reference_order_is_compared(checker) -> None:
    # Thread: K8s resolves the last envFrom source when several export the same
    # key, so swapping the order of two references changes the effective env.
    # A set-based comparison sees the same refs and reports no drift. Both refs
    # are opaque to the repository (no manifest entry), so the same-order case
    # is INVENTORY; only the swap may turn it into DRIFT.
    cm_a = 'fixture-config-a'
    cm_b = 'fixture-config-b'
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]

    def run(expected_order, live_order):
        rendered = yaml.safe_dump_all(
            [
                {
                    'kind': 'Deployment',
                    'metadata': {'name': deployment},
                    'spec': {
                        'template': {
                            'spec': {
                                'containers': [
                                    {
                                        'name': 'pusher',
                                        'env': serving_env,
                                        'envFrom': [
                                            {'configMapRef': {'name': expected_order[0]}},
                                            {'configMapRef': {'name': expected_order[1]}},
                                        ],
                                    }
                                ]
                            }
                        }
                    },
                }
            ]
        )

        def runner(argv, **_kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')

        gke_state = {
            'pusher': {
                'deployment': {},
                'replicasets': [
                    _replicaset(
                        f'{deployment}-a',
                        deployment,
                        2,
                        serving_env,
                        'pusher',
                        envfrom=[
                            {'configMapRef': {'name': live_order[0]}},
                            {'configMapRef': {'name': live_order[1]}},
                        ],
                    )
                ],
            },
        }
        (result,) = checker.inspect_gke_drift(
            env='prod', workloads=('pusher',), render='helm', gke_state=gke_state, runner=runner
        )
        return result

    # Same refs, same order: no drift (unresolvable refs degrade to INVENTORY).
    same = run([cm_a, cm_b], [cm_a, cm_b])
    assert same.error is None, same.error
    assert same.status == 'INVENTORY', same
    assert same.envfrom_mismatched_refs == ()
    assert not same.has_drift
    assert checker.exit_code((same,), strict=True) == 0
    # Same refs, swapped order: the last source wins, so this is reference drift.
    swapped = run([cm_a, cm_b], [cm_b, cm_a])
    assert swapped.error is None, swapped.error
    assert swapped.envfrom_mismatched_refs == (cm_a, cm_b)
    assert swapped.status == 'DRIFT'
    assert checker.exit_code((swapped,), strict=True) == 1


def test_rendered_state_env_entries_must_be_well_formed(checker, tmp_path: Path) -> None:
    # The renderer emits only {name, value/valueFrom} mappings; a corrupted
    # entry (null, non-mapping, or missing name) must be rejected rather than
    # silently skipped, which would keep the manifest's expectation for that key.
    manifest_path = _two_service_manifest(tmp_path)
    for bad_entry in (None, 'not-a-mapping', {'value': 'nameless'}):
        rendered = tmp_path / 'corrupt.json'
        rendered.write_text(
            json.dumps({'services': {'backend': {'env': []}, 'backend-sync': {'env': [bad_entry]}}}),
            encoding='utf-8',
        )
        with pytest.raises(ValueError, match='malformed env entry'):
            checker.expected_cloud_run_env(env='prod', manifest_path=manifest_path, rendered_state_path=rendered)


def test_gke_envfrom_duplicate_sources_are_preserved(checker) -> None:
    # K8s resolves the last envFrom source for overlapping keys, so `A, B, A`
    # and `A, B` are different effective environments even though the deduped
    # reference sets are equal.
    cm_a = 'fixture-config-a'
    cm_b = 'fixture-config-b'
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]

    def run(expected_envfrom, live_envfrom):
        rendered = yaml.safe_dump_all(
            [
                {
                    'kind': 'Deployment',
                    'metadata': {'name': deployment},
                    'spec': {
                        'template': {
                            'spec': {
                                'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': expected_envfrom}]
                            }
                        }
                    },
                }
            ]
        )

        def runner(argv, **_kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')

        gke_state = {
            'pusher': {
                'deployment': {},
                'replicasets': [
                    _replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=live_envfrom)
                ],
            },
        }
        (result,) = checker.inspect_gke_drift(
            env='prod', workloads=('pusher',), render='helm', gke_state=gke_state, runner=runner
        )
        return result

    ref = lambda name: {'configMapRef': {'name': name}}  # noqa: E731
    # Same deduped set, different sequences: drift.
    duplicated = run([ref(cm_a), ref(cm_b), ref(cm_a)], [ref(cm_a), ref(cm_b)])
    assert duplicated.error is None, duplicated.error
    assert duplicated.envfrom_mismatched_refs == (cm_a, cm_b)
    assert duplicated.status == 'DRIFT'
    # Identical sequences including duplicates: no drift.
    same = run([ref(cm_a), ref(cm_b), ref(cm_a)], [ref(cm_a), ref(cm_b), ref(cm_a)])
    assert same.error is None, same.error
    assert same.envfrom_mismatched_refs == ()
    assert same.status == 'INVENTORY', same  # unresolvable fixture refs, no manifest entry


def test_gke_optional_envfrom_missing_configmap_is_not_an_error(checker) -> None:
    # An optional envFrom reference whose ConfigMap does not exist is legal
    # K8s: the pod runs without it. The workload must compare (INVENTORY, empty
    # contribution) rather than fail with a workload-wide fetch ERROR.
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]

    def runner(argv, **_kwargs):
        if argv[0] == 'helm':
            rendered = yaml.safe_dump_all(
                [
                    {
                        'kind': 'Deployment',
                        'metadata': {'name': deployment},
                        'spec': {
                            'template': {
                                'spec': {
                                    'containers': [
                                        {
                                            'name': 'pusher',
                                            'env': serving_env,
                                            'envFrom': [
                                                {'configMapRef': {'name': 'fixture-gone-config', 'optional': True}}
                                            ],
                                        }
                                    ]
                                }
                            }
                        },
                    }
                ]
            )
            return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')
        if 'replicasets' in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        'items': [
                            _replicaset(
                                f'{deployment}-a',
                                deployment,
                                2,
                                serving_env,
                                'pusher',
                                envfrom=[{'configMapRef': {'name': 'fixture-gone-config', 'optional': True}}],
                            )
                        ]
                    }
                ),
                stderr='',
            )
        if 'configmap' in argv:
            raise subprocess.CalledProcessError(
                1, argv, output='', stderr='Error from server (NotFound): configmaps "fixture-gone-config" not found'
            )
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {'spec': {'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env}]}}}}
            ),
            stderr='',
        )

    (result,) = checker.inspect_gke_drift(
        env='prod',
        workloads=('pusher',),
        render='helm',
        kube_context='gke_ctx',
        runner=runner,
    )
    assert result.error is None, result.error
    assert result.envfrom_refs == ('fixture-gone-config?optional',)
    assert result.envfrom_unproven == ('fixture-gone-config?optional',)
    assert result.status == 'INVENTORY'
    assert checker.exit_code((result,), strict=True) == 0


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

    expected, refs, _keyrefs = checker.expected_gke_env_from_helm('pusher', env='prod', runner=runner)
    assert expected == {'A': checker.value_hash('value', 'x')}
    assert refs == ('prod-omi-backend-config',)
    assert calls[0][:3] == ['helm', 'template', 'prod-omi-pusher']
    assert calls[0][4:6] == ['-f', str(BACKEND_ROOT.parent / 'backend/charts/pusher/prod_omi_pusher_values.yaml')]


def test_field_ref_hash_ignores_server_defaulted_api_version(checker) -> None:
    rendered = {'valueFrom': {'fieldRef': {'fieldPath': 'metadata.namespace'}}}
    served = {'valueFrom': {'fieldRef': {'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}}
    assert checker.env_entry_hash(rendered) == checker.env_entry_hash(served)


def test_gke_expected_envfrom_keys_suppress_only_the_degraded_source(checker) -> None:
    # Thread: when a workload has multiple expected envFrom references and only
    # one is degraded (here: offline snapshot proving ConfigMap A's data while
    # omitting external ConfigMap B), the missing-key suppression must cover
    # only the degraded source's keys. Before the fix every expected envFrom
    # key was skipped, so a required key missing from the *proven* A snapshot
    # went unreported and --strict stayed 0 despite known drift.
    cm_name, cm_data = _prod_configmap_fixture(checker)
    dropped_key = sorted(cm_data)[0]
    snapshot_data = {key: value for key, value in cm_data.items() if key != dropped_key}
    cm_b = 'fixture-config-b'
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    envfrom = [{'configMapRef': {'name': cm_name}}, {'configMapRef': {'name': cm_b}}]
    rendered = yaml.safe_dump_all(
        [
            {
                'kind': 'Deployment',
                'metadata': {'name': deployment},
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {
                                    'name': 'pusher',
                                    'env': serving_env,
                                    'envFrom': envfrom,
                                }
                            ]
                        }
                    }
                },
            }
        ]
    )

    def runner(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')

    # Offline snapshot carries ConfigMap A (with data missing one required key)
    # but omits ConfigMap B entirely.
    gke_state = {
        'configmaps': {cm_name: {'data': snapshot_data}},
        'pusher': {
            'deployment': {},
            'replicasets': [_replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=envfrom)],
        },
    }
    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), render='helm', gke_state=gke_state, runner=runner
    )
    assert result.error is None, result.error
    assert result.envfrom_unresolved == (cm_b,)
    # The proven source's required key is absent from the serving snapshot:
    # real drift, not suppressed by the degraded sibling reference.
    assert result.missing_from_live == (dropped_key,)
    assert result.status == 'DRIFT'
    assert result.has_drift
    assert checker.exit_code((result,), strict=True) == 1


def test_gke_template_comparison_includes_envfrom_identities(checker) -> None:
    # Thread: the Deployment template and a ready ReplicaSet may reference
    # different ConfigMaps whose current data is identical; expanding only the
    # data gives them the same fingerprint, so the report said
    # "Template = serving: yes" and masked the rebind. The ordered envFrom
    # identities must join the template comparison.
    cm_a = 'fixture-config-a'
    cm_b = 'fixture-config-b'
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    shared_data = {'GOOGLE_CLIENT_ID': 'id'}

    def run(template_envfrom, rs_envfrom):
        gke_state = {
            'configmaps': {cm_a: {'data': shared_data}, cm_b: {'data': shared_data}},
            'pusher': {
                'deployment': {
                    'spec': {
                        'template': {
                            'spec': {
                                'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': template_envfrom}]
                            }
                        }
                    }
                },
                'replicasets': [
                    _replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=rs_envfrom)
                ],
            },
        }
        (result,) = checker.inspect_gke_drift(
            env='prod', workloads=('pusher',), gke_state=gke_state, expected_overrides={'pusher': {'X': None}}
        )
        return result

    ref = lambda name: {'configMapRef': {'name': name}}  # noqa: E731
    # Same reference: template matches.
    same = run([ref(cm_a)], [ref(cm_a)])
    assert same.error is None, same.error
    assert same.template_matches_serving is True
    # Rebind A -> B with identical data: fingerprint alone is blind; the
    # identities must expose the divergence.
    rebound = run([ref(cm_b)], [ref(cm_a)])
    assert rebound.error is None, rebound.error
    assert rebound.template_matches_serving is False


def test_gke_helm_render_accepts_deployed_override_args(checker, tmp_path: Path, monkeypatch) -> None:
    # Thread: the listen deploy workflow appends dispatch --set-string
    # env[i].value=... tokens (and private -f values) that a repository-default
    # `helm template` never sees; an intentionally overridden rollout then read
    # as value drift. The checker must accept the exact deployed tokens and
    # forward them to the render.
    deployment = 'prod-omi-pusher'
    rendered_override = yaml.safe_dump_all(
        [
            {
                'kind': 'Deployment',
                'metadata': {'name': deployment},
                'spec': {
                    'template': {
                        'spec': {'containers': [{'name': 'pusher', 'env': [{'name': 'X', 'value': 'override'}]}]}
                    }
                },
            }
        ]
    )
    calls: list[list[str]] = []

    def runner(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout=rendered_override, stderr='')

    gke_state = {
        'pusher': {
            'deployment': {},
            'replicasets': [
                _replicaset(f'{deployment}-a', deployment, 2, [{'name': 'X', 'value': 'override'}], 'pusher')
            ],
        },
    }
    # The argv file format written by listen_helm_env_overrides.py: one token
    # per line.
    argv_file = tmp_path / 'overrides.argv'
    argv_file.write_text('--set-string\nenv[0].value=override\n', encoding='utf-8')

    (result,) = checker.inspect_gke_drift(
        env='prod',
        workloads=('pusher',),
        render='helm',
        gke_state=gke_state,
        runner=runner,
        helm_args_for={'pusher': ('--set-string', 'env[0].value=override')},
    )
    assert result.error is None, result.error
    # The override tokens reached the render invocation.
    assert calls[0][calls[0].index('--set-string') + 1] == 'env[0].value=override'
    # Serving value matches the override-informed expected state: no drift.
    assert [m.key for m in result.value_mismatches] == []
    assert result.status == 'OK', result

    # main() plumbing: --gke-helm-arg-file tokens (the argv format
    # listen_helm_env_overrides.py writes in the deploy workflow) join any
    # --gke-helm-arg tokens and reach the render.
    argv_file = tmp_path / 'overrides.argv'
    argv_file.write_text('--set-string\nenv[0].value=override\n', encoding='utf-8')
    state_file = tmp_path / 'gke.json'
    state_file.write_text(json.dumps(gke_state), encoding='utf-8')
    captured: dict[str, list[str]] = {}

    def helm_spy(workload, *, env, root, runner, helm_args=()):
        captured['helm_args'] = list(helm_args or ())
        return ({'X': checker.value_hash('value', 'override')}, ())

    monkeypatch.setattr(checker, 'expected_gke_env_from_helm', helm_spy)
    rc = checker.main(
        [
            '--no-cloud-run',
            '--gke-workload',
            'pusher',
            '--gke-render',
            'helm',
            # Values that start with "-" need the --opt=value form.
            '--gke-helm-arg=-f',
            f'--gke-helm-arg={tmp_path / "private-values.yaml"}',
            '--gke-helm-arg-workload',
            'pusher',
            '--gke-helm-arg-file',
            str(argv_file),
            '--gke-state',
            str(state_file),
        ]
    )
    assert rc == 0
    # Only this workload's tokens reach its render; the argv-file tokens ride
    # along because the workload scope matches.
    assert captured['helm_args'] == [
        '-f',
        str(tmp_path / 'private-values.yaml'),
        '--set-string',
        'env[0].value=override',
    ]

    # Scoping: the same invocation scoped to another workload forwards nothing
    # to this workload's render (the argv encodes backend-listen env indices).
    rc = checker.main(
        [
            '--no-cloud-run',
            '--gke-workload',
            'pusher',
            '--gke-render',
            'helm',
            '--gke-helm-arg=--set-string',
            '--gke-helm-arg',
            'env[80].value=listen-only',
            '--gke-helm-arg-workload',
            'backend-listen',
            '--gke-state',
            str(state_file),
        ]
    )
    assert rc == 0
    assert captured['helm_args'] == []


def test_gke_helm_failure_never_discloses_override_values(checker) -> None:
    # Thread: a failing `helm template` used to surface CalledProcessError's
    # default str(), which embeds the full argv — including literal
    # --set-string values — into the markdown/JSON/summary reports. The
    # re-raised error must carry no literal override value.
    secret = 'super-secret-override-value'

    def runner(argv, **_kwargs):
        raise subprocess.CalledProcessError(
            1,
            argv,
            output='',
            stderr=f'Error: UPGRADE FAILED: parse error at {secret} near "env[0]"',
        )

    with pytest.raises(ValueError) as excinfo:
        checker.expected_gke_env_from_helm('pusher', env='prod', runner=runner, helm_args=(f'env[0].value={secret}',))
    assert secret not in str(excinfo.value)
    assert '<redacted>' in str(excinfo.value)


def test_gke_template_optional_envfrom_missing_configmap_is_not_an_error(checker) -> None:
    # Thread: the Deployment-template path used to resolve envFrom sources
    # without their optionality, so an optional ConfigMap absent from the
    # cluster turned into a workload-wide fetch ERROR (strict exit 2) although
    # K8s legally runs the workload without it. The template read must treat a
    # missing optional map as an empty contribution, like the ReplicaSet loop.
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    optional_envfrom = [{'configMapRef': {'name': 'fixture-gone-config', 'optional': True}}]

    def runner(argv, **_kwargs):
        if argv[0] == 'helm':
            rendered = yaml.safe_dump_all(
                [
                    {
                        'kind': 'Deployment',
                        'metadata': {'name': deployment},
                        'spec': {
                            'template': {
                                'spec': {
                                    'containers': [
                                        {
                                            'name': 'pusher',
                                            'env': serving_env,
                                            'envFrom': optional_envfrom,
                                        }
                                    ]
                                }
                            }
                        },
                    }
                ]
            )
            return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')
        if 'replicasets' in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        'items': [
                            _replicaset(
                                f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=optional_envfrom
                            )
                        ]
                    }
                ),
                stderr='',
            )
        if 'configmap' in argv:
            raise subprocess.CalledProcessError(
                1, argv, output='', stderr='Error from server (NotFound): configmaps "fixture-gone-config" not found'
            )
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    'spec': {
                        'template': {
                            'spec': {
                                'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': optional_envfrom}]
                            }
                        }
                    }
                }
            ),
            stderr='',
        )

    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), render='helm', kube_context='gke_ctx', runner=runner
    )
    assert result.error is None, result.error
    assert result.envfrom_unproven == ('fixture-gone-config?optional',)
    assert result.status == 'INVENTORY'  # optional ref unproven, not a fetch error


def test_gke_template_envfrom_identity_compared_when_template_drops_sources(checker) -> None:
    # Thread: the identity comparison used to be skipped when the template had
    # no envFrom sources at all, so a template that dropped the reference while
    # a serving ReplicaSet still bulk-loads an empty (or fully shadowed)
    # ConfigMap read as "Template = serving: yes". The comparison must hold
    # unconditionally: an empty identity list vs a referencing ReplicaSet is
    # divergence the next rollout would apply.
    cm_name, _cm_data = _prod_configmap_fixture(checker)
    empty_cm_data: dict[str, str] = {}  # zero keys: contributes nothing to the fingerprint
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]

    gke_state = {
        'configmaps': {cm_name: {'data': empty_cm_data}},
        'pusher': {
            'deployment': {
                'spec': {
                    'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env}]}}  # envFrom dropped
                }
            },
            'replicasets': [
                _replicaset(
                    f'{deployment}-a',
                    deployment,
                    2,
                    serving_env,
                    'pusher',
                    envfrom=[{'configMapRef': {'name': cm_name}}],
                )
            ],
        },
    }
    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), gke_state=gke_state, expected_overrides={'pusher': {'X': None}}
    )
    assert result.error is None, result.error
    assert result.template_matches_serving is False


def test_json_report_keys_results_by_platform_and_name(checker) -> None:
    # Thread: --service pusher --gke-workload pusher produced two results both
    # keyed "pusher" in the JSON services object, silently dropping the Cloud
    # Run entry. Keys must disambiguate by platform.
    cloud_run = checker.ServiceEnvDrift(
        service='pusher', manifest_key_count=1, live_key_count=1, allowlisted_live_only=(), unallowlisted_live_only=()
    )
    gke = checker.ServiceEnvDrift(
        service='pusher',
        manifest_key_count=2,
        live_key_count=2,
        allowlisted_live_only=(),
        unallowlisted_live_only=(),
        platform='gke',
    )
    report = json.loads(checker.render_json_report(env='prod', project='p', region='r', results=(cloud_run, gke)))
    assert set(report['services']) == {'cloud_run:pusher', 'gke:pusher'}
    assert report['services']['cloud_run:pusher']['manifest_key_count'] == 1
    assert report['services']['gke:pusher']['manifest_key_count'] == 2


def test_gke_live_explicit_configmap_keyref_values_stay_unproven(checker) -> None:
    # Thread: an explicit env entry bound through valueFrom.configMapKeyRef
    # proves only the reference in the immutable pod spec. The value the
    # container resolved at start cannot be re-read (ConfigMap updates need a
    # pod restart), so a live read must not value-compare the key: a stale
    # running value with a matching reference hash would otherwise pass as a
    # verified OK. The key reports INVENTORY instead.
    deployment = 'prod-omi-pusher'
    serving_env = [
        {'name': 'X', 'value': 'x'},
        {
            'name': 'REDIS_DB_HOST',
            'valueFrom': {'configMapKeyRef': {'name': 'prod-omi-backend-config', 'key': 'REDIS_DB_HOST'}},
        },
    ]
    cm_doc = {'data': {'REDIS_DB_HOST': 'someone-updated-the-configmap-without-a-rollout'}}

    def runner(argv, **_kwargs):
        if 'replicasets' in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        'items': [
                            _replicaset(
                                f'{deployment}-a',
                                deployment,
                                2,
                                serving_env,
                                'pusher',
                                envfrom=[{'configMapRef': {'name': 'prod-omi-backend-config'}}],
                            )
                        ]
                    }
                ),
                stderr='',
            )
        if 'configmap' in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(cm_doc), stderr='')
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {'spec': {'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env}]}}}}
            ),
            stderr='',
        )

    # The expected value deliberately differs from anything the reference could
    # resolve today; the old code subtracted every explicit key from the
    # unproven set and asserted this hash, reporting DRIFT/OK from data it
    # cannot know.
    overrides = {
        'pusher': {
            'X': checker.value_hash('value', 'x'),
            'REDIS_DB_HOST': checker.value_hash('value', 'db.internal.example'),
        }
    }
    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), kube_context='gke_ctx', runner=runner, expected_overrides=overrides
    )
    assert result.error is None, result.error
    assert result.value_mismatches == ()
    assert result.explicit_unproven_keys == ('REDIS_DB_HOST',)
    assert result.status == 'INVENTORY'
    assert not result.has_drift
    assert checker.exit_code((result,), strict=True) == 0
    # Key presence is still proven: a target lacking the key entirely drifts.
    assert 'REDIS_DB_HOST' not in result.missing_from_live


def test_gke_live_configmap_cache_keeps_optional_miss_distinct_from_required(checker) -> None:
    # Thread: an optional reference to a missing ConfigMap cached {} under the
    # name; a later REQUIRED reference to the same name then read the cached
    # empty mapping and reported INVENTORY/0 instead of the operational
    # ERROR/2 for an absent required ConfigMap. The NotFound fact must be
    # cached separately so required callers still fail.
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    envfrom = [
        {'configMapRef': {'name': 'fixture-gone-config', 'optional': True}},
        {'configMapRef': {'name': 'fixture-gone-config'}},
    ]

    def runner(argv, **_kwargs):
        if 'replicasets' in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {'items': [_replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=envfrom)]}
                ),
                stderr='',
            )
        if 'configmap' in argv:
            raise subprocess.CalledProcessError(
                1, argv, output='', stderr='Error from server (NotFound): configmaps "fixture-gone-config" not found'
            )
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    'spec': {
                        'template': {
                            'spec': {'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': envfrom}]}
                        }
                    }
                }
            ),
            stderr='',
        )

    (result,) = checker.inspect_gke_drift(
        env='prod',
        workloads=('pusher',),
        kube_context='gke_ctx',
        runner=runner,
        expected_overrides={'pusher': {'X': None}},
    )
    assert result.status == 'ERROR'
    assert 'not found (required by this reference)' in (result.error or '')
    assert checker.exit_code((result,), strict=True) == 2


def test_helm_failure_redacts_inline_flag_and_equals_bearing_values(checker) -> None:
    # Thread: an inline `--set-string=NAME=value` token was skipped solely
    # because it starts with `-`, so a helm error echoing it disclosed the raw
    # value. Values containing `=` (base64 padding, connection strings) must
    # redact in full in both the inline and the bare argv shape.
    inline_secret = 'pk=abc123=='
    bare_secret = 'ws://h:1/x=a=b'

    def runner(argv, **_kwargs):
        raise subprocess.CalledProcessError(
            1,
            argv,
            output='',
            stderr=f'Error: UPGRADE FAILED: parse error near "env[0]" ({inline_secret}) ({bare_secret})',
        )

    with pytest.raises(ValueError) as excinfo:
        checker.expected_gke_env_from_helm(
            'pusher',
            env='prod',
            runner=runner,
            helm_args=(f'--set-string=env[0].value={inline_secret}', f'env[1].value={bare_secret}'),
        )
    message = str(excinfo.value)
    assert inline_secret not in message
    assert bare_secret not in message
    assert 'abc123==' not in message  # no partial tail leak from `=`-bearing values
    assert 'a=b' not in message
    assert '<redacted>' in message


def test_rendered_state_rejects_omitted_required_env_var_binding(checker, tmp_path: Path) -> None:
    # Thread: an exact --rendered-state that omits a manifest env_var binding
    # silently dropped it from the expected set regardless of provisionality,
    # so a truncated state file could hide a required deploy-time variable and
    # still report OK. The renderer fails rather than omit a required binding,
    # so only explicitly provisional omissions may drop out.
    manifest = {
        'schema_version': 2,
        'environments': {
            'prod': {
                'compute_project': 'based-hardware',
                'region': 'us-central1',
                'cloud_run': {
                    'services': {
                        'backend': {
                            'env': {
                                'ALWAYS_THERE': {'value': 'a'},
                                'REQUIRED_THING': {'env_var': 'REQUIRED_THING_FOR_TEST'},
                            }
                        }
                    }
                },
            }
        },
    }
    path = tmp_path / 'm.yaml'
    path.write_text(yaml.safe_dump(manifest), encoding='utf-8')
    rendered = tmp_path / 'state.json'
    rendered.write_text(
        json.dumps({'services': {'backend': {'env': [{'name': 'ALWAYS_THERE', 'value': 'a'}]}}}), encoding='utf-8'
    )
    with pytest.raises(ValueError, match="omits required env_var binding 'REQUIRED_THING'"):
        checker.expected_cloud_run_env(env='prod', manifest_path=path, rendered_state_path=rendered)


def test_sensitive_key_detection_is_case_insensitive(checker) -> None:
    # Thread: the sensitive-name regex was case-sensitive, so lowercase or
    # mixed-case names (api_key, dbPassword) published a deterministic digest
    # of the raw value in mismatch reports and display fingerprints.
    assert checker.display_hash('api_key', 'abcdef123456') == 'redacted'
    assert checker.display_hash('dbPassword', 'abcdef123456') == 'redacted'
    assert checker.display_hash('MyServiceToken', 'abcdef123456') == 'redacted'
    assert checker.display_hash('API_KEY', 'abcdef123456') == 'redacted'
    assert checker.display_hash('plain_setting', 'abcdef123456') == 'abcdef123456'
    fp_one = checker.env_fingerprint({'api_key': 'aaaa'}, redacted=True)
    fp_two = checker.env_fingerprint({'api_key': 'bbbb'}, redacted=True)
    assert fp_one == fp_two  # redacted fingerprint cannot encode the raw value


def test_sensitive_key_detection_covers_manifest_secret_names(checker) -> None:
    # Thread: after the case-insensitive fix, declared secrets bound in the
    # manifest as *_KEY (ADMIN_KEY, FAL_KEY) or as credential blobs
    # (MCP_OAUTH_CLIENTS_JSON) still published their value hashes when a
    # mismatch or fingerprint rendered them; if accidentally deployed as
    # literals their digests must be redacted like every other credential.
    for name in ('ADMIN_KEY', 'FAL_KEY', 'MCP_OAUTH_CLIENTS_JSON'):
        assert checker.display_hash(name, 'abcdef123456') == 'redacted', name
    # Key-shaped names with no credential meaning stay publishable.
    assert checker.display_hash('BATCH_PIPELINE_WORKER', 'abcdef123456') == 'abcdef123456'
    assert checker.display_hash('STT_SERVICE_MODELS', 'abcdef123456') == 'abcdef123456'
    assert checker.display_hash('REDIS_DB_HOST', 'abcdef123456') == 'abcdef123456'


def test_rendered_state_rejects_entries_without_value_source(checker, tmp_path: Path) -> None:
    # Thread: after the name validation, an entry such as {"name": "X"} was
    # still accepted and hashed as an empty literal, so a corrupted state
    # matching an empty serving value reported OK. The renderer always emits
    # exactly one of value or valueFrom.secretKeyRef; anything else is an
    # operational input error.
    manifest = {
        'schema_version': 2,
        'environments': {
            'prod': {
                'compute_project': 'based-hardware',
                'region': 'us-central1',
                'cloud_run': {
                    'services': {
                        'backend': {
                            'env': {
                                'ALWAYS_THERE': {'value': 'a'},
                                'EMPTY_LOOKING': {'env_var': 'EMPTY_LOOKING_FOR_TEST', 'provisional': True},
                            }
                        }
                    }
                },
            }
        },
    }
    path = tmp_path / 'm.yaml'
    path.write_text(yaml.safe_dump(manifest), encoding='utf-8')
    # Neither value nor valueFrom.
    no_source = tmp_path / 'no_source.json'
    no_source.write_text(
        json.dumps(
            {'services': {'backend': {'env': [{'name': 'ALWAYS_THERE', 'value': 'a'}, {'name': 'EMPTY_LOOKING'}]}}}
        ),
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='exactly one of value or valueFrom'):
        checker.expected_cloud_run_env(env='prod', manifest_path=path, rendered_state_path=no_source)
    # Both value and valueFrom is equally not renderer output.
    both = tmp_path / 'both.json'
    both.write_text(
        json.dumps(
            {
                'services': {
                    'backend': {
                        'env': [
                            {'name': 'ALWAYS_THERE', 'value': 'a'},
                            {
                                'name': 'EMPTY_LOOKING',
                                'value': 'x',
                                'valueFrom': {'secretKeyRef': {'name': 's', 'key': 'k'}},
                            },
                        ]
                    }
                }
            }
        ),
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='exactly one of value or valueFrom'):
        checker.expected_cloud_run_env(env='prod', manifest_path=path, rendered_state_path=both)


def test_gke_unresolved_expected_envfrom_keys_are_not_live_only_drift(checker) -> None:
    # Thread: when the chart references an external ConfigMap the repository
    # cannot enumerate and the offline snapshot carries that ConfigMap's data,
    # its keys were classed as unallowlisted live-only drift even though the
    # expected and serving reference identities match exactly. The bulk-load
    # is exactly what the chart declared; the workload reports INVENTORY.
    cm_name, cm_data = _prod_configmap_fixture(checker)
    cm_b = 'fixture-external-config'
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    envfrom = [{'configMapRef': {'name': cm_name}}, {'configMapRef': {'name': cm_b}}]
    rendered = yaml.safe_dump_all(
        [
            {
                'kind': 'Deployment',
                'metadata': {'name': deployment},
                'spec': {
                    'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': envfrom}]}}
                },
            }
        ]
    )

    def runner(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')

    gke_state = {
        'configmaps': {cm_name: {'data': cm_data}, cm_b: {'data': {'EXTERNAL_KEY': 'external-value'}}},
        'pusher': {
            'deployment': {
                'spec': {
                    'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': envfrom}]}}
                }
            },
            'replicasets': [_replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=envfrom)],
        },
    }
    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), render='helm', gke_state=gke_state, runner=runner
    )
    assert result.error is None, result.error
    assert result.envfrom_unresolved == (cm_b,)
    assert result.envfrom_mismatched_refs == ()
    assert result.unallowlisted_live_only == ()
    assert not result.has_drift
    assert result.status == 'INVENTORY'
    assert checker.exit_code((result,), strict=True) == 0


def test_gke_envfrom_secret_refs_join_identity_comparison(checker) -> None:
    # Thread: envFrom.secretRef sources were silently discarded, so an
    # unexpected serving Secret could bulk-inject environment variables while
    # the comparison (and --strict) stayed green. Secret identities now join
    # the reference comparison — contents are never read — and the Deployment
    # template comparison includes them too.
    cm_name, cm_data = _prod_configmap_fixture(checker)
    secret = {'secretRef': {'name': 'prod-omi-backend-secrets'}}
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]

    def run(template_envfrom, rs_envfrom):
        expected_envfrom = [{'configMapRef': {'name': cm_name}}, secret]
        rendered = yaml.safe_dump_all(
            [
                {
                    'kind': 'Deployment',
                    'metadata': {'name': deployment},
                    'spec': {
                        'template': {
                            'spec': {
                                'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': expected_envfrom}]
                            }
                        }
                    },
                }
            ]
        )

        def runner(argv, **_kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')

        gke_state = {
            'configmaps': {cm_name: {'data': cm_data}},
            'pusher': {
                'deployment': {
                    'spec': {
                        'template': {
                            'spec': {
                                'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': template_envfrom}]
                            }
                        }
                    }
                },
                'replicasets': [
                    _replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=rs_envfrom)
                ],
            },
        }
        (result,) = checker.inspect_gke_drift(
            env='prod', workloads=('pusher',), render='helm', gke_state=gke_state, runner=runner
        )
        return result

    declared_envfrom = [{'configMapRef': {'name': cm_name}}, secret]
    # Chart-declared Secret present on template and serving: no reference
    # drift; the Secret stays opaque so the workload is INVENTORY, and the
    # template comparison (which must include secret identities) still matches.
    matching = run(declared_envfrom, declared_envfrom)
    assert matching.error is None, matching.error
    assert matching.envfrom_mismatched_refs == ()
    assert 'secret:prod-omi-backend-secrets' in matching.envfrom_unresolved
    assert matching.template_matches_serving is True
    assert matching.status == 'INVENTORY'
    assert checker.exit_code((matching,), strict=True) == 0
    # An unexpected serving Secret bulk-load is reference drift, not silence.
    injected = run(declared_envfrom, [*declared_envfrom, {'secretRef': {'name': 'attacker-extra-secret'}}])
    assert injected.error is None, injected.error
    assert 'secret:attacker-extra-secret' in injected.envfrom_mismatched_refs
    assert injected.status == 'DRIFT'
    assert checker.exit_code((injected,), strict=True) == 1
    # Spec order is part of the identity list: ConfigMap/Secret interleavings
    # resolve differently under last-source-wins and must not compare equal.
    reordered = run(declared_envfrom, [secret, {'configMapRef': {'name': cm_name}}])
    assert reordered.error is None, reordered.error
    assert reordered.envfrom_mismatched_refs != ()
    assert reordered.template_matches_serving is False


def test_gke_live_explicit_keyref_binding_drift_is_provable(checker, monkeypatch) -> None:
    # Thread: when a live ReplicaSet binds an explicit key to a *different*
    # ConfigMap name or key than the chart declares, the key used to fall into
    # explicit_unproven and the comparison degraded to INVENTORY with
    # --strict exit 0 — the immutable pod spec proves the binding identity, so
    # a rebind is drift. Only a *matching* binding stays value-unproven.
    deployment = 'prod-omi-pusher'
    cm_name = 'prod-omi-backend-config'
    chart_binding = {'configMapKeyRef': {'name': cm_name, 'key': 'REDIS_DB_HOST'}}
    serving_env = [
        {'name': 'X', 'value': 'x'},
        {
            'name': 'REDIS_DB_HOST',
            'valueFrom': {'configMapKeyRef': {'name': 'attacker-other-config', 'key': 'REDIS_DB_HOST'}},
        },
    ]
    envfrom = [{'configMapRef': {'name': cm_name}}]

    def runner(argv, **_kwargs):
        if 'replicasets' in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {'items': [_replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=envfrom)]}
                ),
                stderr='',
            )
        if 'configmap' in argv:
            return subprocess.CompletedProcess(
                argv, 0, stdout=json.dumps({'data': {'REDIS_DB_HOST': 'irrelevant-live-data'}}), stderr=''
            )
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    'spec': {
                        'template': {
                            'spec': {'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': envfrom}]}
                        }
                    }
                }
            ),
            stderr='',
        )

    workload_values = {
        'env': [{'name': 'X', 'value': 'x'}, {'name': 'REDIS_DB_HOST', 'valueFrom': chart_binding}],
        'runtimeConfigMapName': cm_name,
    }
    monkeypatch.setattr(checker, '_load_values', lambda _path: workload_values)
    monkeypatch.setattr(
        checker,
        'manifest_config_map',
        lambda _env, _manifest_path=None: (cm_name, {'REDIS_DB_HOST': {'source': 'literal', 'value': 'repo'}}),
    )

    (result,) = checker.inspect_gke_drift(env='prod', workloads=('pusher',), kube_context='gke_ctx', runner=runner)
    assert result.error is None, result.error
    # The binding mismatch is proven from the immutable pod spec and reported
    # as a value mismatch on the identity hashes (not the unknowable data).
    (mismatch,) = result.value_mismatches
    assert mismatch.key == 'REDIS_DB_HOST'
    assert mismatch.expected_hash == checker.env_entry_hash({'name': 'REDIS_DB_HOST', 'valueFrom': chart_binding})
    assert mismatch.live_hash == checker.env_entry_hash(serving_env[1])
    assert result.status == 'DRIFT'
    assert checker.exit_code((result,), strict=True) == 1


def test_gke_matching_explicit_keyref_binding_stays_inventory(checker, monkeypatch) -> None:
    # Companion to the rebind test: when the live binding *matches* the chart
    # exactly, the key still cannot be value-compared on a live read (the
    # container resolved the ConfigMap data at start), so the workload reports
    # INVENTORY with --strict exit 0 — the binding comparison must not fire.
    deployment = 'prod-omi-pusher'
    cm_name = 'prod-omi-backend-config'
    binding = {'configMapKeyRef': {'name': cm_name, 'key': 'REDIS_DB_HOST'}}
    serving_env = [{'name': 'X', 'value': 'x'}, {'name': 'REDIS_DB_HOST', 'valueFrom': binding}]
    envfrom = [{'configMapRef': {'name': cm_name}}]

    def runner(argv, **_kwargs):
        if 'replicasets' in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {'items': [_replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=envfrom)]}
                ),
                stderr='',
            )
        if 'configmap' in argv:
            return subprocess.CompletedProcess(
                argv, 0, stdout=json.dumps({'data': {'REDIS_DB_HOST': 'someone-updated-the-configmap'}}), stderr=''
            )
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    'spec': {
                        'template': {
                            'spec': {'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': envfrom}]}
                        }
                    }
                }
            ),
            stderr='',
        )

    workload_values = {
        'env': serving_env,
        'runtimeConfigMapName': cm_name,
    }
    monkeypatch.setattr(checker, '_load_values', lambda _path: workload_values)
    monkeypatch.setattr(
        checker,
        'manifest_config_map',
        lambda _env, _manifest_path=None: (cm_name, {'REDIS_DB_HOST': {'source': 'literal', 'value': 'repo'}}),
    )

    (result,) = checker.inspect_gke_drift(env='prod', workloads=('pusher',), kube_context='gke_ctx', runner=runner)
    assert result.error is None, result.error
    assert result.value_mismatches == ()
    assert result.explicit_unproven_keys == ('REDIS_DB_HOST',)
    assert result.status == 'INVENTORY'
    assert not result.has_drift
    assert checker.exit_code((result,), strict=True) == 0


def test_gke_snapshot_unresolved_external_source_shadowing_key_excluded(checker) -> None:
    # Thread: in an offline snapshot where expected sources [A, B] match the
    # ReplicaSet, A is the repository ConfigMap, external B is last, and both
    # export X, Kubernetes resolves X from B (last source wins). The checker
    # must not compare that value against A's manifest digest and report false
    # drift/strict exit 1 — X degrades with the unresolved reference instead.
    cm_name, cm_data = _prod_configmap_fixture(checker)
    shadowed = next(k for k, v in cm_data.items() if v)
    cm_b = 'fixture-external-config'
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': 'X', 'value': 'x'}]
    envfrom = [{'configMapRef': {'name': cm_name}}, {'configMapRef': {'name': cm_b}}]
    rendered = yaml.safe_dump_all(
        [
            {
                'kind': 'Deployment',
                'metadata': {'name': deployment},
                'spec': {
                    'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': envfrom}]}}
                },
            }
        ]
    )

    def runner(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')

    gke_state = {
        # B exports the same key A declares, with a different value: K8s
        # last-source-wins resolves the pod's X from B.
        'configmaps': {cm_name: {'data': cm_data}, cm_b: {'data': {shadowed: 'external-value'}}},
        'pusher': {
            'deployment': {
                'spec': {
                    'template': {'spec': {'containers': [{'name': 'pusher', 'env': serving_env, 'envFrom': envfrom}]}}
                }
            },
            'replicasets': [_replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=envfrom)],
        },
    }
    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), render='helm', gke_state=gke_state, runner=runner
    )
    assert result.error is None, result.error
    # No value mismatch may be reported for the shadowed key: its effective
    # source is the external ConfigMap the repository cannot enumerate.
    assert [m.key for m in result.value_mismatches if m.key == shadowed] == []
    assert result.envfrom_unresolved == (cm_b,)
    assert result.status == 'INVENTORY'
    assert not result.has_drift
    assert checker.exit_code((result,), strict=True) == 0


def test_gke_snapshot_explicit_entry_overrides_unresolved_source_still_compared(checker) -> None:
    # Companion: an explicit env entry for the same key shadows envFrom, so
    # even when an unresolved external source exports the key, the explicit
    # value is what the container runs and must stay value-compared.
    cm_name, cm_data = _prod_configmap_fixture(checker)
    shadowed = next(k for k, v in cm_data.items() if v)
    cm_b = 'fixture-external-config'
    deployment = 'prod-omi-pusher'
    serving_env = [{'name': shadowed, 'value': 'explicit-live-value'}]
    template_env = [{'name': shadowed, 'value': 'chart-declared-value'}]
    envfrom = [{'configMapRef': {'name': cm_name}}, {'configMapRef': {'name': cm_b}}]
    rendered = yaml.safe_dump_all(
        [
            {
                'kind': 'Deployment',
                'metadata': {'name': deployment},
                'spec': {
                    'template': {'spec': {'containers': [{'name': 'pusher', 'env': template_env, 'envFrom': envfrom}]}}
                },
            }
        ]
    )

    def runner(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=rendered, stderr='')

    gke_state = {
        'configmaps': {cm_name: {'data': cm_data}, cm_b: {'data': {shadowed: 'external-value'}}},
        'pusher': {
            'deployment': {
                'spec': {
                    'template': {'spec': {'containers': [{'name': 'pusher', 'env': template_env, 'envFrom': envfrom}]}}
                }
            },
            'replicasets': [_replicaset(f'{deployment}-a', deployment, 2, serving_env, 'pusher', envfrom=envfrom)],
        },
    }
    (result,) = checker.inspect_gke_drift(
        env='prod', workloads=('pusher',), render='helm', gke_state=gke_state, runner=runner
    )
    assert result.error is None, result.error
    # The explicit entry is the effective value and drifts from the manifest
    # digest: real drift, not excused by the unresolved sibling source.
    assert [m.key for m in result.value_mismatches] == [shadowed]
    assert result.has_drift
    assert checker.exit_code((result,), strict=True) == 1


def test_sensitive_key_detection_covers_salt_named_credentials(checker) -> None:
    # Thread: DREAM_AGENT_FEEDBACK_SALT is declared as a secret in the
    # production manifest, but the sensitive-name regex did not match SALT; if
    # that binding were accidentally deployed as a literal, mismatch output
    # and the display fingerprint would publish its deterministic digest,
    # letting candidate salts be tested offline. Salt-named credentials
    # redact like every other credential.
    assert checker.display_hash('DREAM_AGENT_FEEDBACK_SALT', 'abcdef123456') == 'redacted'
    assert checker.display_hash('PW_SALT', 'abcdef123456') == 'redacted'
    # Salting-adjacent words with no credential meaning stay publishable.
    assert checker.display_hash('BCRYPT_HASH_ROUNDS', 'abcdef123456') != 'redacted'


def test_values_render_rejects_override_tokens_as_operational_error(checker, tmp_path: Path) -> None:
    # Thread: --gke-render values (chosen explicitly, or by auto falling back
    # when helm is absent) reads the chart values file directly and cannot
    # honor --gke-helm-arg / --gke-helm-arg-file override tokens. Silently
    # ignoring them compares a legitimately overridden rollout against
    # repository defaults and reports false drift with --strict exit 1. The
    # incompatible invocation is rejected as an operational error (exit 2)
    # instead, per workload, so token-free workloads still report.
    state = {
        'pusher': {
            'deployment': {},
            'replicasets': [
                _replicaset('prod-omi-pusher-a', 'prod-omi-pusher', 2, [{'name': 'X', 'value': 'x'}], 'pusher')
            ],
        },
    }
    state_file = tmp_path / 'gke.json'
    state_file.write_text(json.dumps(state), encoding='utf-8')
    rc = checker.main(
        [
            '--no-cloud-run',
            '--gke-workload',
            'pusher',
            '--gke-render',
            'values',
            '--gke-helm-arg=--set-string',
            '--gke-helm-arg=env[0].value=deployed-secret',
            '--gke-helm-arg-workload',
            'pusher',
            '--gke-state',
            str(state_file),
            '--strict',
        ],
    )
    assert rc == 2  # operational error, not false drift
    # Sanity: the same invocation without override tokens still reports.
    rc = checker.main(
        [
            '--no-cloud-run',
            '--gke-workload',
            'pusher',
            '--gke-render',
            'values',
            '--gke-state',
            str(state_file),
            '--strict',
        ],
    )
    assert rc in (0, 1)

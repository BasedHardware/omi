"""scripts/ops/drift_check.py: live vs source, live staging vs live prod (lessons 7-9).

Fixtures reproduce the three staging misses (batch serving leader at min-instances 0, recovery off,
backfill on backend-sync's task audience) and the prod live-only setting
(BATCH_PIPELINE_RECOVERY_ALL_ADMITTED=true on backend-integration, absent from source).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ops import drift_check as dc
from scripts.ops.drift_check import Finding, SourceService

FAKE_UID = 'Zq3xV9kLm2Pw8sRt5YbN1cHd7Ef4'  # 28 chars, the shape of a Firebase UID; never real

PROD_URLS = {
    'backend-sync': 'https://backend-sync-prodhash-uc.a.run.app',
    'backend-sync-backfill': 'https://backend-sync-backfill-prodhash-uc.a.run.app',
    'backend-integration': 'https://backend-integration-prodhash-uc.a.run.app',
}
STAGING_URLS = {
    'backend-sync': 'https://backend-sync-staging-devhash-uc.a.run.app',
    'backend-sync-backfill': 'https://backend-sync-backfill-staging-devhash-uc.a.run.app',
    'backend-integration': 'https://backend-integration-staging-devhash-uc.a.run.app',
}
SCALE = {'service_min': None, 'service_max': None, 'revision_max': 40, 'concurrency': 20, 'cpu': '2', 'memory': '8Gi'}


def _svc(env: dict[str, str], *, url: str, min_instances: int | None = 1, **scale) -> dict:
    return {
        'revision': 'rev-1',
        'urls': [url],
        'env': {k: dc.plain(k, v) for k, v in env.items()},
        'scale': {**SCALE, 'revision_min': min_instances, **scale},
    }


def _prod() -> dict:
    return {
        'schema': dc.SNAPSHOT_SCHEMA,
        'services': {
            'backend-sync': _svc(
                {'BATCH_PIPELINE_ENABLED': 'true', 'SYNC_TASKS_AUDIENCE': PROD_URLS['backend-sync']},
                url=PROD_URLS['backend-sync'],
            ),
            'backend-sync-backfill': _svc(
                {'BATCH_PIPELINE_ENABLED': 'true', 'SYNC_TASKS_AUDIENCE': PROD_URLS['backend-sync-backfill']},
                url=PROD_URLS['backend-sync-backfill'],
            ),
            'backend-integration': _svc(
                {'BATCH_PIPELINE_SERVING_ENABLED': 'true', 'BATCH_PIPELINE_RECOVERY_ALL_ADMITTED': 'true'},
                url=PROD_URLS['backend-integration'],
                min_instances=3,
            ),
        },
    }


def _staging_mirrored() -> dict:
    """Staging as it should be: prod's config with self-referential URLs and a warm leader."""
    prod = _prod()['services']
    out: dict[str, Any] = {'schema': dc.SNAPSHOT_SCHEMA, 'services': {}}
    for name, svc in prod.items():
        env = {k: v['value'] for k, v in svc['env'].items()}
        if 'SYNC_TASKS_AUDIENCE' in env:
            env['SYNC_TASKS_AUDIENCE'] = STAGING_URLS[name]
        out['services'][f'{name}-staging'] = _svc(env, url=STAGING_URLS[name], min_instances=1)
    return out


def _unexplained(findings: list[Finding]) -> list[str]:
    return [f.line() for f in findings if not f.explained]


# ------------------------------------------------------------------------------------------------
# staging-vs-prod: the three staging misses
# ------------------------------------------------------------------------------------------------


def test_a_mirrored_staging_passes():
    assert _unexplained(dc.compare_staging_prod(_staging_mirrored(), _prod())) == []


def test_cold_batch_serving_leader_fails():
    staging = _staging_mirrored()
    staging['services']['backend-integration-staging']['scale']['revision_min'] = 0

    assert _unexplained(dc.compare_staging_prod(staging, _prod())) == [
        'backend-integration-staging/min_instances: staging 0, prod 3 (rule: warm whenever prod is)'
    ]


def test_recovery_off_in_staging_fails():
    staging = _staging_mirrored()
    staging['services']['backend-integration-staging']['env']['BATCH_PIPELINE_RECOVERY_ALL_ADMITTED'] = dc.plain(
        'BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'false'
    )

    assert _unexplained(dc.compare_staging_prod(staging, _prod())) == [
        'backend-integration-staging/BATCH_PIPELINE_RECOVERY_ALL_ADMITTED: value differs (staging false, prod true)'
    ]


def test_backfill_on_backend_syncs_audience_fails_although_audiences_are_allowlisted():
    staging = _staging_mirrored()
    staging['services']['backend-sync-backfill-staging']['env']['SYNC_TASKS_AUDIENCE'] = dc.plain(
        'SYNC_TASKS_AUDIENCE', STAGING_URLS['backend-sync']
    )

    assert _unexplained(dc.compare_staging_prod(staging, _prod())) == [
        'backend-sync-backfill-staging/SYNC_TASKS_AUDIENCE: points at backend-sync; prod points at backend-sync-backfill'
    ]


def test_staging_pointing_at_a_prod_service_fails():
    staging = _staging_mirrored()
    staging['services']['backend-sync-staging']['env']['SYNC_TASKS_AUDIENCE'] = dc.plain(
        'SYNC_TASKS_AUDIENCE', PROD_URLS['backend-sync']
    )

    assert _unexplained(dc.compare_staging_prod(staging, _prod())) == [
        'backend-sync-staging/SYNC_TASKS_AUDIENCE: points at a prod service (backend-sync)'
    ]


def test_staging_may_be_smaller_but_not_larger_or_differently_shaped():
    staging = _staging_mirrored()
    staging['services']['backend-sync-staging']['scale'].update(revision_max=4)  # smaller: fine
    staging['services']['backend-sync-backfill-staging']['scale'].update(revision_max=80, concurrency=6)

    assert _unexplained(dc.compare_staging_prod(staging, _prod())) == [
        'backend-sync-backfill-staging/max_instances: staging 80 > prod 40',
        'backend-sync-backfill-staging/concurrency: staging 6, prod 20',
    ]


def test_ramp_keys_are_judged_by_ramp_position_not_equality():
    """Staging may lead prod on the ramp, but each environment must sit on one coherent set."""
    ramp_sets = {
        '5_percent': {
            s: {'BATCH_PIPELINE_RECOVERY_ALL_ADMITTED': 'false', 'BATCH_PIPELINE_PERCENT': '0'} for s in PROD_URLS
        },
        '100_percent': {
            s: {'BATCH_PIPELINE_RECOVERY_ALL_ADMITTED': 'true', 'BATCH_PIPELINE_PERCENT': '100'} for s in PROD_URLS
        },
    }
    prod, staging = _prod(), _staging_mirrored()
    for name in PROD_URLS:
        for key, value in ramp_sets['5_percent'][name].items():
            prod['services'][name]['env'][key] = dc.plain(key, value)
        for key, value in ramp_sets['100_percent'][name].items():
            staging['services'][f'{name}-staging']['env'][key] = dc.plain(key, value)
    assert _unexplained(dc.compare_staging_prod(staging, prod, ramp_sets)) == []

    # The 10-20 staging miss: one service's recovery flag off its set.
    staging['services']['backend-integration-staging']['env']['BATCH_PIPELINE_RECOVERY_ALL_ADMITTED'] = dc.plain(
        'X', 'false'
    )
    assert _unexplained(dc.compare_staging_prod(staging, prod, ramp_sets)) == [
        'staging:backend-integration/BATCH_PIPELINE_RECOVERY_ALL_ADMITTED: ramp key off its set 100_percent'
    ]


def test_staging_may_not_lag_prod_on_the_ramp():
    ramp_sets = {
        '5_percent': {s: {'BATCH_PIPELINE_PERCENT': '5'} for s in PROD_URLS},
        '100_percent': {s: {'BATCH_PIPELINE_PERCENT': '100'} for s in PROD_URLS},
    }
    prod, staging = _prod(), _staging_mirrored()
    for name in PROD_URLS:
        prod['services'][name]['env']['BATCH_PIPELINE_PERCENT'] = dc.plain('X', '100')
        staging['services'][f'{name}-staging']['env']['BATCH_PIPELINE_PERCENT'] = dc.plain('X', '5')

    assert _unexplained(dc.compare_staging_prod(staging, prod, ramp_sets)) == [
        "staging/ramp: on 5_percent, neither prod's 100_percent nor 100_percent"
    ]


def test_no_covering_ramp_set_fails_and_keys_a_set_does_not_judge_are_compared():
    partial = {'restore': {'backend-sync': {'BATCH_PIPELINE_PERCENT': '0'}}}
    assert _unexplained(dc.compare_staging_prod(_staging_mirrored(), _prod(), partial)) == [
        'staging/ramp: no ramp set covers every snapshotted service',
        'prod/ramp: no ramp set covers every snapshotted service',
    ]

    # A winning set that omits the recovery flag must not hide it: it is compared by equality.
    narrow = {'5_percent': {s: {'BATCH_PIPELINE_ENABLED': 'true'} for s in PROD_URLS}}
    prod, staging = _prod(), _staging_mirrored()
    for snapshot, suffix in ((prod, ''), (staging, '-staging')):
        for name in PROD_URLS:
            snapshot['services'][name + suffix]['env']['BATCH_PIPELINE_ENABLED'] = dc.plain('X', 'true')
    staging['services']['backend-integration-staging']['env']['BATCH_PIPELINE_RECOVERY_ALL_ADMITTED'] = dc.plain(
        'X', 'false'
    )
    assert _unexplained(dc.compare_staging_prod(staging, prod, narrow)) == [
        'backend-integration-staging/BATCH_PIPELINE_RECOVERY_ALL_ADMITTED: value differs (staging false, prod true)'
    ]


def test_staging_idles_by_design_except_the_serving_leader():
    staging = _staging_mirrored()
    for name in ('backend-sync-staging', 'backend-sync-backfill-staging'):
        staging['services'][name]['scale']['revision_min'] = 0  # overlay scale_flags: --min-instances 0
    assert _unexplained(dc.compare_staging_prod(staging, _prod())) == []


def test_an_annotation_split_cannot_hide_a_cold_leader_or_a_higher_cap():
    staging = _staging_mirrored()
    leader = staging['services']['backend-integration-staging']['scale']
    leader.update(service_min=0, revision_min=3)  # service-level 0 wins when it is set
    sync = staging['services']['backend-sync-staging']['scale']
    sync.update(service_max=80, revision_max=4)  # service-level cap above prod's 40

    assert _unexplained(dc.compare_staging_prod(staging, _prod())) == [
        'backend-integration-staging/min_instances: staging 0, prod 3 (rule: warm whenever prod is)',
        'backend-sync-staging/max_instances: staging 80 > prod 40',
    ]


def test_same_service_audience_on_a_different_path_fails():
    prod, staging = _prod(), _staging_mirrored()
    prod['services']['backend-sync']['env']['SYNC_TASKS_AUDIENCE'] = dc.plain(
        'X', PROD_URLS['backend-sync'] + '/v2/sync-jobs/run'
    )
    staging['services']['backend-sync-staging']['env']['SYNC_TASKS_AUDIENCE'] = dc.plain(
        'X', STAGING_URLS['backend-sync'] + '/v1/sync-jobs/run'
    )

    assert _unexplained(dc.compare_staging_prod(staging, prod)) == [
        'backend-sync-staging/SYNC_TASKS_AUDIENCE: points at backend-sync on a different path than prod'
    ]


def test_known_prod_live_only_keys_missing_in_staging_are_explained():
    prod = _prod()
    prod['services']['backend-sync']['env']['LEGACY_FLAG'] = dc.plain('LEGACY_FLAG', 'on')

    assert _unexplained(dc.compare_staging_prod(_staging_mirrored(), prod)) == [
        'backend-sync-staging/LEGACY_FLAG: only in prod'
    ]
    known = {('backend-sync', 'LEGACY_FLAG'): 'stale'}
    assert _unexplained(dc.compare_staging_prod(_staging_mirrored(), prod, known_prod=known)) == []


# ------------------------------------------------------------------------------------------------
# source: the prod live-only setting
# ------------------------------------------------------------------------------------------------


def _source(ops_env: dict[str, str] | None = None) -> dict[str, SourceService]:
    return {
        'backend-integration': SourceService(
            env={'BATCH_PIPELINE_SERVING_ENABLED': dc.plain('X', 'true'), 'API_KEY': {'secret': ''}},
            scale={'revision_min': 3, 'concurrency': 20},
            ops_env=ops_env or {},
            ops_scale={'service_min': None, 'service_max': None},
        )
    }


def _live_integration(**env: str) -> dict:
    svc = _svc({'BATCH_PIPELINE_SERVING_ENABLED': 'true', **env}, url=PROD_URLS['backend-integration'], min_instances=3)
    svc['env']['API_KEY'] = {'secret': 'prod-omi-backend-secrets'}
    return {'schema': dc.SNAPSHOT_SCHEMA, 'services': {'backend-integration': svc}}


def test_prod_live_only_setting_fails_against_source():
    live = _live_integration(BATCH_PIPELINE_RECOVERY_ALL_ADMITTED='true')

    assert _unexplained(dc.compare_source(live, _source(), ramp={})) == [
        'backend-integration/BATCH_PIPELINE_RECOVERY_ALL_ADMITTED: live-only (not in source)'
    ]


def test_ramp_owned_and_uid_cohort_keys_are_explained():
    live = _live_integration(BATCH_PIPELINE_RECOVERY_ALL_ADMITTED='true', FIRST_SUMMARY_UID_ALLOWLIST=FAKE_UID)
    ramp = {'backend-integration': {'BATCH_PIPELINE_RECOVERY_ALL_ADMITTED'}}

    findings = dc.compare_source(live, _source(), ramp)

    assert _unexplained(findings) == []
    assert {f.explained for f in findings} == {
        'ramp-owned: infra/rollout/ramp_env.json',
        'live-managed UID cohort (*_UID_ALLOWLIST)',
    }


def test_an_ops_file_key_is_judged_strictly_even_when_ramp_owned():
    live = _live_integration(SUMMARY_DEBT_REPAIR_ENABLED='false')
    ramp = {'backend-integration': {'SUMMARY_DEBT_REPAIR_ENABLED'}}

    findings = dc.compare_source(live, _source({'SUMMARY_DEBT_REPAIR_ENABLED': 'true'}), ramp)

    assert _unexplained(findings) == [
        'backend-integration/SUMMARY_DEBT_REPAIR_ENABLED: value differs from source (ops file not applied)'
    ]


def test_known_live_only_ratchet_explains_and_fails_when_an_entry_is_gone():
    live = _live_integration(LEGACY_FLAG='on')
    known = {('backend-integration', 'LEGACY_FLAG'): 'stale', ('backend-integration', 'REVERTED_FLAG'): 'stale'}

    assert _unexplained(dc.compare_source(live, _source(), {}, known)) == [
        'backend-integration/REVERTED_FLAG: known live-only (stale) is gone: remove it from live_only.yaml'
    ]


def test_source_scale_flags_and_secret_bindings():
    live = _live_integration()
    live['services']['backend-integration']['scale']['revision_min'] = 0
    live['services']['backend-integration']['env']['API_KEY'] = dc.plain('API_KEY', 'inline')

    assert _unexplained(dc.compare_source(live, _source(), {})) == [
        'backend-integration/API_KEY: source binds a secret; live has a plain value',
        'backend-integration/revision_min: scale: live 0 != deploy flag 3',
    ]


# ------------------------------------------------------------------------------------------------
# Snapshot: redaction and live reads
# ------------------------------------------------------------------------------------------------


def _gcloud_service(url: str, traffic: list[dict]) -> dict:
    return {
        'metadata': {'annotations': {'run.googleapis.com/minScale': '1', 'run.googleapis.com/urls': json.dumps([url])}},
        'status': {'url': url, 'traffic': traffic},
    }


def _gcloud_revision() -> dict:
    return {
        'metadata': {'name': 'backend-sync-00002', 'annotations': {'autoscaling.knative.dev/minScale': '5'}},
        'spec': {
            'containerConcurrency': 20,
            'containers': [
                {'name': 'collector', 'env': [{'name': 'SIDECAR_ONLY', 'value': 'x'}]},
                {
                    'name': 'backend-1',
                    'ports': [{'containerPort': 8080}],
                    'resources': {'limits': {'cpu': '2000m', 'memory': '8Gi'}},
                    'env': [
                        {'name': 'BATCH_PIPELINE_PERCENT', 'value': '5'},
                        {'name': 'EMPTY_FLAG'},
                        {'name': 'FIRST_SUMMARY_UID_ALLOWLIST', 'value': FAKE_UID},
                        {'name': 'INNOCENT_NAME', 'value': f'prefix-{FAKE_UID}'},
                        {'name': 'SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'value': 'true'},
                        {'name': 'OPENAI_API_KEY', 'valueFrom': {'secretKeyRef': {'name': 'openai', 'key': 'latest'}}},
                    ],
                },
            ],
        },
    }


def test_snapshot_keeps_no_sensitive_value_and_reads_the_serving_revision():
    calls: list[list[str]] = []
    service = _gcloud_service(
        PROD_URLS['backend-sync'],
        [{'revisionName': 'backend-sync-00001', 'percent': 10}, {'revisionName': 'backend-sync-00002', 'percent': 90}],
    )

    def read(args: list[str]):
        calls.append(args)
        return service if args[2] == 'services' else _gcloud_revision()

    snap = dc.take_snapshot(project='based-hardware', region='us-central1', services=['backend-sync'], read=read)

    assert calls[1][:5] == ['gcloud', 'run', 'revisions', 'describe', 'backend-sync-00002']
    assert FAKE_UID not in json.dumps(snap)
    env = snap['services']['backend-sync']['env']
    assert env['BATCH_PIPELINE_PERCENT'] == {'value': '5'}
    assert env['EMPTY_FLAG'] == {'value': ''}  # Cloud Run omits an empty value
    assert set(env['FIRST_SUMMARY_UID_ALLOWLIST']) == {'digest'}
    assert set(env['INNOCENT_NAME']) == {'digest'}  # secret-looking value under an innocent name
    assert env['SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED'] == {'value': 'true'}  # ASSIGNMENT is not SIGN
    assert env['OPENAI_API_KEY'] == {'secret': 'openai'}
    assert 'SIDECAR_ONLY' not in env
    assert snap['services']['backend-sync']['scale'] == {
        'service_min': 1,
        'service_max': None,
        'revision_min': 5,
        'revision_max': None,
        'concurrency': 20,
        'cpu': '2000m',
        'memory': '8Gi',
    }


def test_serving_revision_fails_closed_without_traffic():
    with pytest.raises(ValueError, match='no revision'):
        dc.serving_revision({'status': {'traffic': []}})


def test_k8s_snapshot_needs_an_explicit_context_and_keeps_config_map_key_names_only():
    with pytest.raises(ValueError, match='kube-context'):
        dc.take_snapshot(project='p', region='r', services=[], k8s=['ns/dep:app'], read=lambda a: {})

    deployment = {
        'metadata': {'annotations': {'deployment.kubernetes.io/revision': '7'}},
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {
                            'name': 'app',
                            'envFrom': [{'configMapRef': {'name': 'cfg'}}],
                            'env': [{'name': 'FLAG', 'value': 'on'}],
                            'resources': {'limits': {'cpu': 2, 'memory': '3584Mi'}},
                        }
                    ]
                }
            }
        },
    }
    calls: list[list[str]] = []

    def read(args: list[str]):
        calls.append(args)
        kind = args[6]
        if kind == 'hpa':
            raise subprocess.CalledProcessError(1, args)
        return {'data': {'REDIS_DB_HOST': '10.1.2.3'}} if kind == 'configmap' else deployment

    snap = dc.take_snapshot(project='p', region='r', services=[], k8s=['ns/dep:app'], kube_context='ctx', read=read)

    assert all(call[:3] == ['kubectl', '--context', 'ctx'] for call in calls)
    assert '10.1.2.3' not in json.dumps(snap)
    assert snap['services']['app']['env'] == {'REDIS_DB_HOST': {'from': 'configMap:cfg'}, 'FLAG': {'value': 'on'}}
    assert dc.quantity(snap['services']['app']['scale']['memory']) == dc.quantity('3.5Gi')


def test_printable_shows_flags_and_numbers_only():
    assert dc.printable('X_ENABLED', {'value': 'true'}) == 'true'
    assert dc.printable('X_URL', {'value': 'https://a.example'}) == '<value>'
    assert dc.printable('X_UID_ALLOWLIST', {'digest': 'sha256:0'}) == '<digest>'
    assert dc.quantity('2000m') == dc.quantity('2') and dc.quantity('8Gi') != dc.quantity('8G')


# ------------------------------------------------------------------------------------------------
# Source model on this tree, ramp file, and the reviewed inventory file
# ------------------------------------------------------------------------------------------------


def test_prod_source_model_reads_deploy_flags_and_the_ops_file():
    model = dc.source_model('prod')

    integration = model['backend-integration']
    assert integration.scale['revision_min'] == 3 and integration.scale['concurrency'] == 40
    assert integration.ops_env['SUMMARY_DEBT_REPAIR_ENABLED'] == 'true'
    assert model['backend-sync-backfill'].ops_scale['service_max'] == {
        'owner': 'redis_guard',
        'floor': 8,
        'ceiling': 40,
    }
    assert dc.LISTEN in model and model[dc.LISTEN].scale['service_min'] is not None


def test_staging_source_model_composes():
    model = dc.source_model('staging')

    assert model['backend-integration'].ops_env['SUMMARY_DEBT_REPAIR_ENABLED'] == 'true'
    assert model['backend-sync-backfill'].scale['concurrency'] == 6
    # The overlay's scale_flags reach the source model, so a cold staging leader fails `source`.
    assert model['backend-integration'].scale['revision_min'] == 1
    assert model['backend-sync'].scale['revision_min'] == 0


def test_staging_ops_values_pass_the_staging_fence():
    from utils import staging_fence

    staging = yaml.safe_load((dc.BACKEND / 'deploy' / 'ops' / 'staging.yaml').read_text(encoding='utf-8'))
    for service, cfg in staging['cloud_run'].items():
        env = {k: str(v) for k, v in (cfg.get('env') or {}).items()}
        violations = staging_fence.staging_violations({'OMI_DEPLOYMENT': 'staging', **env})
        assert [v for v in violations if v[1] in env] == [], service


def test_a_value_mismatch_with_source_fails_when_not_ramp_owned():
    """The real tree declares BATCH_PIPELINE_RECOVERY_ALL_ADMITTED=false; prod serves true."""
    source = _source()
    source['backend-integration'].env['BATCH_PIPELINE_RECOVERY_ALL_ADMITTED'] = dc.plain('X', 'false')
    live = _live_integration(BATCH_PIPELINE_RECOVERY_ALL_ADMITTED='true')

    assert _unexplained(dc.compare_source(live, source, ramp={})) == [
        'backend-integration/BATCH_PIPELINE_RECOVERY_ALL_ADMITTED: value differs from source'
    ]


@pytest.mark.parametrize(
    'value',
    [
        'https://user:s3cret@redis.example:6379/0',
        'https://hooks.example/notify?sig=abc',
        f'https://api.example/v1/{FAKE_UID}',
    ],
)
def test_credential_bearing_urls_are_redacted(value: str):
    assert set(dc.plain('UPSTREAM_URL', value)) == {'digest'}
    assert dc.plain('SYNC_TASKS_AUDIENCE', PROD_URLS['backend-sync'] + '/v2/sync-jobs/run') == {
        'value': PROD_URLS['backend-sync'] + '/v2/sync-jobs/run'
    }


def test_live_only_inventory_is_well_formed_and_disjoint_from_source():
    doc = yaml.safe_load(dc.KNOWN_LIVE_ONLY.read_text(encoding='utf-8'))
    known = dc.load_known(dc.KNOWN_LIVE_ONLY, 'prod')
    model = dc.source_model('prod')

    assert set(doc) == {'prod'} and set(doc['prod']) == {'manifest', 'stale', 'review'}
    assert known
    for (service, key), _ in known.items():
        assert service in model, service
        src = model[service]
        assert (
            key not in src.env and key not in src.ops_env
        ), f'{service}/{key} is in source; drop it from live_only.yaml'


def test_ramp_keys_map_gke_targets_to_container_names(tmp_path: Path):
    path = tmp_path / 'ramp_env.json'
    path.write_text(
        json.dumps(
            {'on': {'cloud_run/backend-sync': {'A': '1'}, 'gke/prod-omi-backend-listen/backend-listen': {'B': '1'}}}
        )
    )

    assert dc.ramp_keys(path) == {'backend-sync': {'A'}, 'backend-listen': {'B'}}
    assert dc.load_ramp_sets(path) == {'on': {'backend-sync': {'A': '1'}}}


def test_cli_exit_codes(tmp_path: Path, capsys):
    staging, prod = tmp_path / 'staging.json', tmp_path / 'prod.json'
    prod.write_text(json.dumps(_prod()))
    staging.write_text(json.dumps(_staging_mirrored()))
    assert dc.main(['staging-vs-prod', '--staging', str(staging), '--prod', str(prod), '--known', '/dev/null']) == 0

    cold = _staging_mirrored()
    cold['services']['backend-integration-staging']['scale']['revision_min'] = 0
    staging.write_text(json.dumps(cold))
    assert dc.main(['staging-vs-prod', '--staging', str(staging), '--prod', str(prod), '--known', '/dev/null']) == 1
    assert '1 unexplained difference(s)' in capsys.readouterr().out

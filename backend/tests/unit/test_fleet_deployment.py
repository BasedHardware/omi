"""Fleet upload ASGI semantics and the reviewed sidecar deployment boundary."""

import asyncio
import importlib.util
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from utils.byok import BYOKMiddleware
from utils.other import endpoints
import utils.byok as byok
from utils.observability.fleet import UPLOADS
from utils.observability.sync_upload import SyncUploadMetricsMiddleware

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    'status,outcome', [(200, 'completed'), (202, 'accepted'), (207, 'failed'), (409, 'failed'), (503, 'failed')]
)
def test_upload_middleware_records_one_attempt_and_one_terminal(status, outcome):
    app = FastAPI()
    app.add_middleware(SyncUploadMetricsMiddleware)

    @app.post('/v2/sync-local-files')
    async def upload():
        return Response(status_code=status)

    started = UPLOADS.labels('started', 'android', 'beta')
    terminal = UPLOADS.labels(outcome, 'android', 'beta')
    before = (started._value.get(), terminal._value.get())
    with TestClient(app) as client:
        assert (
            client.post(
                '/v2/sync-local-files', headers={'X-App-Platform': 'android', 'X-Build-Channel': 'beta'}
            ).status_code
            == status
        )
        assert client.get('/v2/sync-local-files').status_code == 405
    assert (started._value.get(), terminal._value.get()) == (before[0] + 1, before[1] + 1)


def test_upload_exceptions_and_untrusted_labels():
    async def fail(scope, receive, send):
        raise RuntimeError('private')

    middleware = SyncUploadMetricsMiddleware(fail)
    scope = {
        'type': 'http',
        'method': 'POST',
        'path': '/v1/sync-local-files',
        'headers': [(b'x-app-platform', b'raw-private-label')],
    }
    child = UPLOADS.labels('failed', 'unknown', 'unknown')
    before = child._value.get()
    with pytest.raises(RuntimeError):
        asyncio.run(middleware(scope, None, None))
    assert child._value.get() == before + 1


@pytest.fixture(scope="module")
def contracts():
    return {
        name: yaml.safe_load((ROOT / path).read_text())
        for name, path in {
            "action": ".github/actions/deploy-backend-stack/action.yml",
            "lifecycle": ".github/actions/sync-backfill-lifecycle/action.yml",
            "manifest": "backend/deploy/runtime_env.yaml",
        }.items()
    }


def test_sidecars_attach_before_readiness_and_promotion_for_all_three_services(contracts):
    action = contracts['action']
    steps = action['runs']['steps']
    attach = next(
        i
        for i, step in enumerate(steps)
        if step['name'] == 'Attach Managed Prometheus to sync and integration candidates'
    )
    readiness = next(
        i for i, step in enumerate(steps) if step['name'] == 'Wait for Cloud Run revisions to become ready'
    )
    assert attach < readiness
    script = steps[attach]['run']
    for name in ('backend-sync', 'backend-sync-backfill', 'backend-integration'):
        assert name in script
    assert '--expected-env-state=' in script
    assert '--base-revision="$service-${{ steps.image-tag.outputs.revision_suffix }}-base"' in script
    assert '--final-revision="$service-${{ steps.image-tag.outputs.revision_suffix }}"' in script
    for service in ('sync', 'integration'):
        step = next(step for step in steps if step.get('id') == 'deploy-backend-' + service)
        assert '--revision-suffix=${{ steps.image-tag.outputs.revision_suffix }}-base' in step['with']['flags']
        assert step['with']['no_traffic'] is True
    lifecycle = contracts['lifecycle']
    deploy = next(step for step in lifecycle['runs']['steps'] if step.get('id') == 'deploy-backend-sync-backfill')
    assert '--revision-suffix=${{ inputs.revision_suffix }}-base' in deploy['with']['flags']
    manifest = contracts['manifest']
    for env in ('dev', 'prod'):
        for name in ('backend-sync', 'backend-sync-backfill', 'backend-integration'):
            assert (
                manifest['environments'][env]['cloud_run']['services'][name]['env']['PROMETHEUS_SIDECAR_PORT']['value']
                == '9090'
            )
        exporter = (
            ROOT
            / f'backend/charts/monitoring/prometheus-stackdriver-exporter/{env}_sync_omi_cloud_run_metrics_exporter.yaml'
        ).read_text()
        assert '"backend-integration"' in exporter


def test_unnamed_backfill_ingress_validates_then_gets_named_by_patcher():
    path = ROOT / 'backend/scripts/attach_cloud_run_gmp_sidecar.py'
    spec = importlib.util.spec_from_file_location('fleet_attach_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    service = {
        'spec': {'template': {'spec': {'containers': [{'image': 'example', 'env': [{'name': 'A', 'value': 'on'}]}]}}}
    }
    assert module._ingress_literal_env(service, ingress_container_name='backend-1') == {'A': 'on'}
    service['spec']['template']['spec']['containers'].append({'name': 'other'})
    with pytest.raises(ValueError, match='unambiguous'):
        module._ingress_literal_env(service, ingress_container_name='backend-1')


def test_upload_metrics_include_byok_admission_rejection(monkeypatch):
    monkeypatch.setattr(endpoints, 'verify_token', lambda token: 'local-only')
    monkeypatch.setattr(byok, '_validated_byok_keys', lambda uid, keys: ({}, 'mismatch'))
    app = FastAPI()
    app.add_middleware(BYOKMiddleware)
    app.add_middleware(SyncUploadMetricsMiddleware)
    main = (ROOT / 'backend/main.py').read_text()
    assert main.index('app.add_middleware(SyncUploadMetricsMiddleware)') > main.index(
        'app.add_middleware(BYOKMiddleware)'
    )
    children = [UPLOADS.labels(outcome, 'unknown', 'unknown') for outcome in ('started', 'failed')]
    before = [child._value.get() for child in children]
    with TestClient(app) as client:
        response = client.post(
            '/v2/sync-local-files', headers={'Authorization': 'Bearer local', 'X-BYOK-OpenAI': 'local'}
        )
    assert response.status_code == 403
    assert [child._value.get() for child in children] == [value + 1 for value in before]

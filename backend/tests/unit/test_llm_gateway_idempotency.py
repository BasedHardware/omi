import asyncio
from pathlib import Path
import shutil
import sqlite3
import subprocess
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
import yaml

from database import _client as firestore_clients

from llm_gateway.gateway import idempotency, idempotency_store
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import FakeChatCompletionProvider
from llm_gateway.main import app
from llm_gateway.routers import dependencies
from scripts.batch_pipeline_ttl import ttl_resources
from utils.executors import db_executor

CHAT = '/v1/chat/completions'
POST = f'{CHAT}/operations'
BODY = {'model': 'omi:auto:conv-structure', 'messages': [{'role': 'user', 'content': 'synthetic prompt'}]}


@pytest.fixture
def gateway(monkeypatch):
    provider = FakeChatCompletionProvider()
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'test-gateway-service-token')
    monkeypatch.delenv('LLM_GATEWAY_IDEMPOTENCY_ENABLED', raising=False)
    monkeypatch.setenv(idempotency.ENVIRONMENT_SETTING, 'prod')
    monkeypatch.setitem(
        app.dependency_overrides, dependencies.get_provider_registry, lambda: ProviderRegistry({'openai': provider})
    )
    headers = {
        'Authorization': 'Bearer test-gateway-service-token',
        'X-Omi-Service-Caller': 'backend',
        'X-Omi-User-Uid': 'test-owner',
        'Idempotency-Key': str(uuid4()),
    }
    with TestClient(app) as client:
        yield client, headers, provider


def test_kill_switch_fails_keyed_calls_closed_and_leaves_legacy_open(gateway, monkeypatch):
    client, headers, provider = gateway
    monkeypatch.setenv('LLM_GATEWAY_IDEMPOTENCY_ENABLED', 'off')
    assert client.post(POST, json=BODY, headers=headers).json()['error']['code'] == 'idempotency_disabled'
    assert client.get(f'{POST}/{headers["Idempotency-Key"]}', headers=headers).status_code == 503
    assert provider.calls == []
    headers.pop('Idempotency-Key')
    assert client.post(CHAT, json=BODY, headers=headers).status_code == 200
    assert len(provider.calls) == 1


def test_keyed_request_bounds_reject_before_storage_or_provider(gateway, monkeypatch):
    client, headers, provider = gateway
    monkeypatch.setattr(idempotency, 'MAX_REQUEST_BYTES', 256)

    def no_storage(*args):
        pytest.fail('invalid request reached storage')

    monkeypatch.setattr(idempotency, '_claim', no_storage)
    assert client.post(POST, json=BODY, headers={**headers, 'Idempotency-Key': 'bad'}).status_code == 400
    for malformed in (True, None, 0, 1, 'false', [], {}):
        rejected = client.post(POST, json={**BODY, 'stream': malformed}, headers=headers)
        assert rejected.status_code == 400
        assert rejected.json()['error']['code'] == 'idempotency_nonstreaming_object_required'
    ordinary = client.post(CHAT, json=BODY, headers=headers)
    assert ordinary.status_code == 400
    assert ordinary.json()['error']['code'] == 'idempotency_operations_route_required'
    assert client.post(POST, content=b'x' * 257, headers=headers).status_code == 413
    headers.pop('Idempotency-Key')
    assert client.post(POST, json=BODY, headers=headers).status_code == 400
    assert provider.calls == []


def test_ttl_policy_covers_exactly_the_gateway_claim_and_result_collections():
    policy = Path(__file__).resolve().parents[2] / 'deploy' / 'llm-gateway' / 'retention.json'
    resources = [
        f'projects/demo-gateway/databases/(default)/collectionGroups/{collection}/fields/expires_at'
        for collection in (idempotency_store.CLAIMS, idempotency_store.RESULTS)
    ]
    assert sorted(ttl_resources('demo-gateway', policy_path=policy)) == sorted(resources)


@pytest.fixture
def rendered_dev_gateway_env():
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('requires Helm to render the development gateway')
    backend = Path(__file__).resolve().parents[2]
    chart = backend / 'charts' / 'llm-gateway'
    manifest = subprocess.check_output(
        [
            helm,
            'template',
            'dev-omi-llm-gateway',
            str(chart),
            '-f',
            str(chart / 'dev_omi_llm_gateway_values.yaml'),
            '--set',
            'image.tag=test',
            '--show-only',
            'templates/deployment.yaml',
        ],
        text=True,
        timeout=15,
    )
    env = yaml.safe_load(manifest)['spec']['template']['spec']['containers'][0]['env']
    customer = yaml.safe_load((backend / 'deploy' / 'runtime_env' / 'dev.overlay.yaml').read_text())[
        'data_plane_project'
    ]
    return {entry['name']: entry for entry in env}, customer


def test_rendered_dev_gateway_uses_customer_firestore(gateway, monkeypatch, rendered_dev_gateway_env):
    client, headers, provider = gateway
    env, customer = rendered_dev_gateway_env
    compute = env['GOOGLE_CLOUD_PROJECT']['value']
    assert compute == 'based-hardware-dev'
    assert env[idempotency_store.DATA_PLANE_ENV]['value'] == customer == 'based-hardware'
    assert env[idempotency.ENVIRONMENT_SETTING]['value'] == 'dev'
    for entry in (idempotency_store.ACTIVE_SECRET_ENV, idempotency_store.SECONDARY_SECRET_ENV):
        assert env[entry]['valueFrom']['secretKeyRef'] == {
            'name': 'dev-omi-llm-gateway-idempotency-keys',
            'key': entry,
            'optional': True,
        }
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', compute)
    monkeypatch.setenv(idempotency_store.DATA_PLANE_ENV, customer)
    monkeypatch.delenv('FIRESTORE_DATABASE_ID', raising=False)
    monkeypatch.setattr(firestore_clients, 'customer_entitlement_service_account', lambda: None)
    monkeypatch.setattr(firestore_clients, 'prepare_google_credentials', lambda: None)
    monkeypatch.setattr(
        firestore_clients,
        '_pinned_data_plane_firestore_client',
        firestore_clients._build_pinned_data_plane_firestore_client,
    )
    construct = Mock(return_value=SimpleNamespace(project=customer))
    monkeypatch.setattr(firestore_clients.firestore, 'Client', construct)
    assert idempotency_store._customer_firestore_client().project == customer
    construct.assert_called_once_with(project=customer)

    # A resolved compute client, or an absent pin, must fail before any collection access.
    construct.return_value = SimpleNamespace(project=compute)
    assert client.post(POST, json=BODY, headers=headers).status_code == 503
    monkeypatch.delenv(idempotency_store.DATA_PLANE_ENV)
    construct.reset_mock()
    assert client.post(POST, json=BODY, headers=headers).status_code == 503
    assert client.get(f'{POST}/{headers["Idempotency-Key"]}', headers=headers).status_code == 503
    construct.assert_not_called()
    assert not provider.calls


def test_saturated_keyed_storage_is_rejected_without_blocking_legacy(gateway):
    client, headers, provider = gateway
    release = Event()
    executor = idempotency.gateway_idempotency_executor
    # Fill all worker and queue slots with synthetic storage work.
    futures = [executor.submit(release.wait, 10) for _ in range(16)]
    try:
        for response in (
            client.post(POST, json=BODY, headers=headers),
            client.get(f'{POST}/{headers["Idempotency-Key"]}', headers=headers),
        ):
            assert response.status_code == 503
            assert response.json()['error']['code'] == 'idempotency_store_busy'
            assert response.headers['Retry-After'] == '2'
        assert not provider.calls
        assert db_executor.submit(lambda: 'available').result(timeout=2) == 'available'
        ordinary_headers = {key: value for key, value in headers.items() if key != 'Idempotency-Key'}
        assert client.post(CHAT, json=BODY, headers=ordinary_headers).status_code == 200
    finally:
        release.set()
        for future in futures:
            assert future.result(timeout=2)


def test_no_settlement_permit_rejects_before_claim(gateway, monkeypatch):
    client, headers, provider = gateway

    def no_claim(*args):
        pytest.fail('request without a settlement permit reached claim')

    monkeypatch.setattr(idempotency, '_claim', no_claim)
    permits = idempotency._settlement_slots
    count = idempotency.GATEWAY_SETTLEMENT_WORKERS
    for _ in range(count):
        assert permits.acquire(blocking=False)
    try:
        response = client.post(POST, json=BODY, headers=headers)
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'idempotency_store_busy'
        assert response.headers['Retry-After'] == '2'
        assert not provider.calls
    finally:
        for _ in range(count):
            permits.release()


def test_post_counter_uses_bounded_writer_environment(gateway, monkeypatch):
    client, headers, provider = gateway
    monkeypatch.setattr(idempotency, '_claim', lambda *_: pytest.fail('bad environment reached claim'))
    for value, label in (('prod', 'prod'), ('dev', 'dev'), ('unexpected', 'unknown')):
        monkeypatch.setenv(idempotency.ENVIRONMENT_SETTING, value)
        counter = idempotency.KEYED_POSTS.labels(label)
        previous = counter._value.get()
        if label == 'unknown':
            response = client.post(POST, json=BODY, headers=headers)
            assert response.status_code == 503
            assert response.json()['error']['code'] == 'idempotency_environment_unavailable'
        else:
            response = client.post(POST, json=BODY, headers={**headers, 'Idempotency-Key': 'invalid'})
            assert response.status_code == 400
        assert counter._value.get() == previous + 1
    assert not provider.calls


def test_readback_excludes_confirmed_boundary_scope_and_other_environments():
    guide = Path(__file__).resolve().parents[2] / 'docs' / 'llm_gateway.mdx'
    readback = guide.read_text().split('### Rollout readback', 1)[1]
    query = readback.split('```sql\n', 1)[1].split('```', 1)[0]
    db = sqlite3.connect(':memory:')
    try:
        db.executescript("""
            CREATE TABLE claims (scope TEXT, state TEXT, started_at INTEGER, environment TEXT);
            CREATE TABLE attempts (scope TEXT, attempt_id TEXT, occurred_at INTEGER, environment TEXT);
            CREATE TABLE claim_lookup (scope TEXT, started_at INTEGER, environment TEXT);
            INSERT INTO claims VALUES ('prod', 'committed', 11, 'prod'), ('dev', 'pending', 11, 'dev');
            INSERT INTO attempts VALUES ('prod', 'paid', 12, 'prod'), ('boundary', 'late', 12, 'prod'),
                ('prod', 'other-environment-replay', 12, 'dev'), ('dev', 'dev-only', 12, 'dev');
            INSERT INTO claim_lookup VALUES ('boundary', 9, 'prod');
            """)
        args = dict(environment='prod', window_start=10, window_end=20, keyed_posts=1000)
        assert db.execute(query, args).fetchone() == (0, 0, 1, 0)
        db.execute("INSERT INTO attempts VALUES ('orphan', 'missing', 12, 'prod')")
        assert db.execute(query, args).fetchone() == (0, 1, 1, None)
        db.execute("INSERT INTO claims VALUES ('silent-crash', 'pending', 14, 'prod')")
        db.execute("INSERT INTO attempts VALUES ('prod', 'second-late-attempt', 22, 'prod')")
        assert db.execute(query, args).fetchone() == (1, 2, 2, None)
    finally:
        db.close()


def test_cancellation_does_not_release_a_running_settlement_permit(monkeypatch):
    monkeypatch.setenv(idempotency.ENVIRONMENT_SETTING, 'local')
    monkeypatch.delenv('LLM_GATEWAY_IDEMPOTENCY_ENABLED', raising=False)
    entered, release = Event(), Event()
    permits = idempotency._settlement_slots

    def finish(_saved):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(idempotency, '_claim', lambda *_: (SimpleNamespace(finish=finish), None))

    async def receive():
        return {'type': 'http.request', 'body': b'{}'}

    async def invoke(_body, _keyed):
        return JSONResponse({'synthetic': True})

    async def exercise():
        caller = ServiceCaller(name='backend', user_uid='test-owner')
        request = Request({'type': 'http', 'headers': [(b'idempotency-key', str(uuid4()).encode())]}, receive)
        task = asyncio.create_task(
            idempotency.complete(request, caller, build_omi_managed_credential_context(caller), invoke)
        )
        held = 0
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            while permits.acquire(blocking=False):
                held += 1
            assert held == idempotency.GATEWAY_SETTLEMENT_WORKERS - 1
            release.set()
            async with asyncio.timeout(3):
                while not permits.acquire(blocking=False):
                    await asyncio.sleep(0.01)
            held += 1
        finally:
            release.set()
            for _ in range(held):
                permits.release()

    asyncio.run(exercise())

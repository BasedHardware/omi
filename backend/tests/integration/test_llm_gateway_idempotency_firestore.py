"""Exercise gateway replicas through the HTTP contract and a real Firestore transaction."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from threading import Barrier, Event
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import account_deletion_marker
from llm_gateway.gateway import idempotency, idempotency_store
from llm_gateway.gateway.accounting import build_accounting_event
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import FakeChatCompletionProvider, ProviderFailure
from llm_gateway.gateway.schemas import FailureClass, RetryPolicy
from llm_gateway.main import app
from llm_gateway.routers import dependencies, openai_compatible

pytestmark = pytest.mark.integration
POST = '/v1/chat/completions/operations'
BODY = {'model': 'omi:auto:conv-structure', 'messages': [{'role': 'user', 'content': 'synthetic prompt'}]}


@pytest.fixture
def db(monkeypatch) -> Iterator[firestore.Client]:
    endpoint = os.getenv('FIRESTORE_EMULATOR_HOST')
    if not endpoint:
        pytest.skip('requires Firestore emulator')
    assert urlsplit('http://' + endpoint).hostname in {'127.0.0.1', 'localhost', '::1'}
    client = firestore.Client(project='demo-gateway-idempotency', credentials=AnonymousCredentials())
    monkeypatch.setattr(idempotency_store, '_customer_firestore_client', lambda: client)
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'test-gateway-service-token')
    monkeypatch.delenv('LLM_GATEWAY_IDEMPOTENCY_ENABLED', raising=False)
    monkeypatch.setenv(idempotency.ENVIRONMENT_SETTING, 'prod')
    yield client
    client.close()


@pytest.fixture
def headers():
    return {
        'Authorization': 'Bearer test-gateway-service-token',
        'X-Omi-Service-Caller': 'backend',
        'X-Omi-User-Uid': f'test-{uuid4()}',
        'Idempotency-Key': str(uuid4()),
    }


def lookup(headers):
    return f'{POST}/{headers["Idempotency-Key"]}'


def use_providers(monkeypatch, provider, fallback=None):
    monkeypatch.setitem(
        app.dependency_overrides,
        dependencies.get_provider_registry,
        lambda: ProviderRegistry({'openai': provider, 'openrouter': fallback or FakeChatCompletionProvider()}),
    )


def docs(db, headers, collection):
    return db.collection('users').document(headers['X-Omi-User-Uid']).collection(collection)


def test_replay_and_lookup_use_one_dispatch_across_clients(db, headers, monkeypatch):
    import asyncio

    entered, release = Event(), Event()
    traces = []

    class HeldProvider(FakeChatCompletionProvider):
        async def create_chat_completion(self, request, **kwargs):
            entered.set()
            assert await asyncio.to_thread(release.wait, 12)
            return await super().create_chat_completion(request, **kwargs)

    provider = HeldProvider()
    use_providers(monkeypatch, provider)
    monkeypatch.setattr(openai_compatible, 'schedule_attempt_trace', lambda ctx, trace: traces.append((ctx, trace)))

    with TestClient(app) as client, TestClient(app) as other, ThreadPoolExecutor() as workers:
        first = workers.submit(client.post, POST, json=BODY, headers=headers)
        try:
            assert entered.wait(10)
            pending = other.post(POST, json=BODY, headers=headers)
            assert pending.status_code == 409
            assert pending.json()['error']['code'] == 'idempotency_pending'
            assert pending.headers['Retry-After'] == '2'
            assert other.get(lookup(headers), headers=headers).json()['error']['code'] == 'idempotency_pending'
            conflict = other.post(POST, json={**BODY, 'temperature': 0.7}, headers=headers)
            assert conflict.json()['error']['code'] == 'idempotency_conflict'
        finally:
            release.set()
        committed = first.result(timeout=10)
        assert committed.status_code == 200
        assert committed.headers['X-Omi-Idempotency-Key'] == headers['Idempotency-Key']
        replay = other.post(POST, json=dict(reversed(list(BODY.items()))), headers=headers)
        assert replay.content == committed.content
        assert other.get(lookup(headers), headers=headers).content == committed.content
        assert other.get(lookup(headers), headers={**headers, 'X-Omi-User-Uid': 'other-test-user'}).status_code == 404
        assert other.get(lookup(headers)).status_code == 401
        changed_credential = other.post(POST, json=BODY, headers={**headers, 'X-Omi-Byok-Openai-Key': 'test-key'})
        assert changed_credential.json()['error']['code'] == 'idempotency_conflict'

    assert len(provider.calls) == 1
    assert len(traces) == 1
    context, trace = traces[0]
    assert context.request_id == headers['Idempotency-Key'] and len(trace.attempts) == 1
    claims = list(docs(db, headers, idempotency_store.CLAIMS).stream())
    results = list(docs(db, headers, idempotency_store.RESULTS).stream())
    assert context.idempotency_scope == claims[0].id == results[0].id
    row = build_accounting_event(context, trace.attempts[0]).as_dict()
    assert row['idempotency_environment'] == 'prod'
    assert row['idempotency_scope'] == claims[0].id
    claim = claims[0].to_dict()
    assert claim['environment'] == 'prod'
    result = results[0].to_dict()
    assert set(claim) == {
        'state',
        'fingerprint',
        'key_version',
        'environment',
        'claim_token',
        'started_at',
        'expires_at',
        'result_expires_at',
    }
    assert claim['expires_at'] - claim['started_at'] == timedelta(days=30)
    assert result['expires_at'] == claim['result_expires_at']
    assert timedelta(hours=24) <= result['expires_at'] - claim['started_at'] < timedelta(hours=24, minutes=1)
    assert committed.content not in result['sealed']


def test_provider_timeout_and_result_expiry_keep_the_claim(db, headers, monkeypatch):
    provider = FakeChatCompletionProvider([ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT)])
    fallback = FakeChatCompletionProvider()
    use_providers(monkeypatch, provider, fallback)
    resolve = openai_compatible.resolve_chat_completion_route

    def resolve_with_retries(*args):
        route = resolve(*args)
        retry = RetryPolicy(max_attempts=3)
        return replace(
            route,
            active_route=route.active_route.model_copy(update={'retry': retry}),
            last_known_good_route=route.last_known_good_route.model_copy(update={'retry': retry}),
        )

    monkeypatch.setattr(openai_compatible, 'resolve_chat_completion_route', resolve_with_retries)

    with TestClient(app) as client:
        initial = client.post(POST, json=BODY, headers=headers)
        assert initial.status_code == 502
        for response in (client.post(POST, json=BODY, headers=headers), client.get(lookup(headers), headers=headers)):
            assert response.status_code == 409
            assert response.json()['error']['code'] == 'idempotency_indeterminate'
        assert len(provider.calls) == 1
        assert fallback.calls == []

        (claim,) = docs(db, headers, idempotency_store.CLAIMS).stream()
        claim.reference.update(
            {'state': 'pending', 'started_at': datetime.now(timezone.utc) - idempotency_store.PENDING_WINDOW}
        )
        assert client.post(POST, json=BODY, headers=headers).json()['error']['code'] == 'idempotency_indeterminate'
        assert len(provider.calls) == 1

        fresh = {**headers, 'Idempotency-Key': str(uuid4())}
        assert client.post(POST, json=BODY, headers=fresh).status_code == 200
        for snapshot in docs(db, headers, idempotency_store.RESULTS).stream():
            docs(db, headers, idempotency_store.CLAIMS).document(snapshot.id).update(
                {'result_expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}
            )
            snapshot.reference.delete()
        assert client.get(lookup(fresh), headers=fresh).status_code == 410
        assert client.post(POST, json=BODY, headers=fresh).status_code == 410
        assert len(provider.calls) == 2


def test_failed_commit_and_account_deletion_fail_closed(db, headers, monkeypatch):
    provider = FakeChatCompletionProvider()
    use_providers(monkeypatch, provider)

    def fail_after_commit(store, *args):
        finish(store, *args)
        raise RuntimeError('synthetic lost commit acknowledgement')

    finish = idempotency_store.Store.finish
    monkeypatch.setattr(idempotency_store.Store, 'finish', fail_after_commit)
    with TestClient(app) as client:
        first = client.post(POST, json=BODY, headers=headers)
        assert first.status_code == 503
        committed = client.get(lookup(headers), headers=headers)
        assert committed.status_code == 200
        assert client.post(POST, json=BODY, headers=headers).content == committed.content
        assert len(provider.calls) == 1

        account_deletion_marker.account_deletion_document(headers['X-Omi-User-Uid'], firestore_client=db).set(
            {'wipe_status': 'pending_deletion'}
        )
        assert client.get(lookup(headers), headers=headers).status_code == 403
        assert client.post(POST, json=BODY, headers=headers).status_code == 403
        fresh = {**headers, 'Idempotency-Key': str(uuid4())}
        assert client.post(POST, json=BODY, headers=fresh).status_code == 403
        assert len(provider.calls) == 1


def test_oversized_result_is_never_returned_or_dispatched_again(db, headers, monkeypatch):
    provider = FakeChatCompletionProvider()
    use_providers(monkeypatch, provider)
    monkeypatch.setattr(idempotency_store, 'MAX_RESULT_BYTES', 16)
    with TestClient(app) as client:
        first = client.post(POST, json=BODY, headers=headers)
        assert first.json()['error']['code'] == 'idempotency_indeterminate'
        assert client.post(POST, json=BODY, headers=headers).content == first.content
        assert len(provider.calls) == 1
        assert list(docs(db, headers, idempotency_store.RESULTS).stream()) == []


def test_deletion_started_during_dispatch_prevents_settlement(db, headers, monkeypatch):
    class DeletingProvider(FakeChatCompletionProvider):
        async def create_chat_completion(self, request, **kwargs):
            response = await super().create_chat_completion(request, **kwargs)
            account_deletion_marker.account_deletion_document(headers['X-Omi-User-Uid'], firestore_client=db).set(
                {'wipe_status': 'pending_deletion'}
            )
            return response

    provider = DeletingProvider()
    use_providers(monkeypatch, provider)
    with TestClient(app) as client:
        assert client.post(POST, json=BODY, headers=headers).status_code == 403
        assert client.get(lookup(headers), headers=headers).status_code == 403
        assert len(provider.calls) == 1
        assert list(docs(db, headers, idempotency_store.RESULTS).stream()) == []


def test_claim_expiry_does_not_renew_or_allow_a_stale_settlement(db, headers):
    operation = idempotency_store.Operation(headers['X-Omi-User-Uid'], uuid4().hex)
    original = idempotency_store.Store(operation, client=db)
    canonical = b'test-request'
    response = idempotency_store.StoredResponse(200, b'{}')
    assert original.claim_or_replay(canonical, 'local') is None
    expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    original.claim.update({'expires_at': expires_at})
    replacement = idempotency_store.Store(operation, client=db)

    for invoke in (
        lambda: replacement.claim_or_replay(canonical, 'local'),
        replacement.lookup,
        lambda: original.finish(response),
    ):
        with pytest.raises(idempotency_store.IdempotencyError, match='idempotency_expired'):
            invoke()
    assert original.claim.get().to_dict()['expires_at'] == expires_at

    # The emulator does not run the Firestore TTL sweeper. Model its deletion.
    original.claim.delete()
    assert replacement.claim_or_replay(canonical, 'local') is None
    with pytest.raises(idempotency_store.IdempotencyError, match='idempotency_indeterminate'):
        original.finish(response)
    replacement.finish(response)
    assert replacement.lookup() == response


def test_concurrent_fresh_claims_have_one_winner(db, headers):
    operation = idempotency_store.Operation(headers['X-Omi-User-Uid'], uuid4().hex)
    stores = [idempotency_store.Store(operation, client=db) for _ in range(2)]
    start = Barrier(2, timeout=10)

    def compete(store):
        start.wait()
        try:
            assert store.claim_or_replay(b'same-request', 'local') is None
        except idempotency_store.IdempotencyError as exc:
            assert exc.status == 409
            return exc.code
        return 'claimed'

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(compete, store) for store in stores]
        assert sorted(future.result(timeout=20) for future in futures) == ['claimed', 'idempotency_pending']


@pytest.mark.parametrize('marker', [{'X-Omi-Llm-Feature': 'proactivity_v2_memory'}, {'X-Omi-Proactivity-Item': ''}])
@pytest.mark.parametrize('marked_first', [False, True])
def test_proactivity_is_rejected_before_claim_or_replay(db, headers, monkeypatch, marker, marked_first):
    provider = FakeChatCompletionProvider()
    use_providers(monkeypatch, provider)
    with TestClient(app) as client:
        if not marked_first:
            assert client.post(POST, json=BODY, headers=headers).status_code == 200
        rejected = client.post(POST, json=BODY, headers={**headers, **marker})
        assert rejected.status_code == 400
        assert rejected.json()['error']['code'] == 'idempotency_proactivity_unsupported'
        if marked_first:
            assert list(docs(db, headers, idempotency_store.CLAIMS).stream()) == []
            assert not provider.calls
            assert client.post(POST, json={**BODY, 'stream': False}, headers=headers).status_code == 200
        assert len(provider.calls) == 1


def test_rotation_preserves_replay_across_mixed_replicas(db, headers, monkeypatch):
    provider = FakeChatCompletionProvider()
    use_providers(monkeypatch, provider)
    old_secret, new_secret = 'old-test-secret-' * 3, 'new-test-secret-' * 3
    active, secondary = idempotency_store.ACTIVE_SECRET_ENV, idempotency_store.SECONDARY_SECRET_ENV
    monkeypatch.delenv(active, raising=False)
    monkeypatch.setenv('ENCRYPTION_SECRET', old_secret)
    monkeypatch.setenv(secondary, new_secret)
    with TestClient(app) as client:
        old_result = client.post(POST, json=BODY, headers=headers)
        assert old_result.status_code == 200
        (old_claim,) = docs(db, headers, idempotency_store.CLAIMS).stream()

        monkeypatch.setenv(active, new_secret)
        monkeypatch.setenv(secondary, old_secret)
        assert client.post(POST, json=BODY, headers=headers).content == old_result.content
        assert client.get(lookup(headers), headers=headers).content == old_result.content
        assert client.post(POST, json={**BODY, 'temperature': 0.8}, headers=headers).status_code == 409
        fresh = {**headers, 'Idempotency-Key': str(uuid4())}
        new_result = client.post(POST, json=BODY, headers=fresh)
        assert new_result.status_code == 200
        versions = {doc.get('key_version') for doc in docs(db, headers, idempotency_store.CLAIMS).stream()}
        assert old_claim.get('key_version') in versions and len(versions) == 2

        monkeypatch.delenv(active)
        monkeypatch.setenv(secondary, new_secret)
        assert client.post(POST, json=BODY, headers=fresh).content == new_result.content
        assert client.get(lookup(fresh), headers=fresh).content == new_result.content
        monkeypatch.delenv(secondary)
        assert client.post(POST, json=BODY, headers=fresh).status_code == 503
        assert client.get(lookup(fresh), headers=fresh).status_code == 503
        assert len(provider.calls) == 2


def test_inflight_completion_settles_when_claim_and_lookup_pool_is_full(db, headers, monkeypatch):
    import asyncio

    entered, provider_release, storage_release = Event(), Event(), Event()

    class HeldProvider(FakeChatCompletionProvider):
        async def create_chat_completion(self, request, **kwargs):
            entered.set()
            assert await asyncio.to_thread(provider_release.wait, 15)
            return await super().create_chat_completion(request, **kwargs)

    provider = HeldProvider()
    use_providers(monkeypatch, provider)
    with TestClient(app) as client, TestClient(app) as other, ThreadPoolExecutor(max_workers=1) as caller:
        request = caller.submit(client.post, POST, json=BODY, headers=headers)
        try:
            assert entered.wait(10)
            pool = idempotency.gateway_idempotency_executor
            occupied = [pool.submit(storage_release.wait, 20) for _ in range(16)]
            try:
                assert other.get(lookup(headers), headers=headers).json()['error']['code'] == 'idempotency_store_busy'
                provider_release.set()
                committed = request.result(timeout=10)
                assert committed.status_code == 200
                assert committed.headers['X-Omi-Idempotency-Key'] == headers['Idempotency-Key']
            finally:
                storage_release.set()
                for worker in occupied:
                    assert worker.result(timeout=2)
        finally:
            provider_release.set()
        assert other.post(POST, json=BODY, headers=headers).content == committed.content
        assert other.get(lookup(headers), headers=headers).content == committed.content
    assert len(provider.calls) == 1


def test_schema_property_order_conflicts_but_envelope_order_replays(db, headers, monkeypatch):
    provider = FakeChatCompletionProvider()
    use_providers(monkeypatch, provider)
    inner = {'a': {'type': 'string'}, 'b': {'type': 'boolean'}}
    nested = {'type': 'object', 'properties': inner, 'required': ['a', 'b'], 'additionalProperties': False}
    properties = {'first': {'type': 'string'}, 'second': nested}
    schema = {
        'type': 'object',
        'properties': properties,
        'required': ['first', 'second'],
        'additionalProperties': False,
    }

    def payload(definition):
        return {
            **BODY,
            'model': 'omi:auto:chat-structured',
            'response_format': {
                'type': 'json_schema',
                'json_schema': {'name': 'ordered_pair', 'strict': True, 'schema': definition},
            },
        }

    with TestClient(app) as client:
        committed = client.post(POST, json=payload(schema), headers=headers)
        assert committed.status_code == 200
        reordered_envelope = dict(reversed(list(payload(dict(reversed(list(schema.items())))).items())))
        assert client.post(POST, json=reordered_envelope, headers=headers).content == committed.content
        changed = payload({**schema, 'properties': dict(reversed(list(properties.items())))})
        conflict = client.post(POST, json=changed, headers=headers)
        assert conflict.status_code == 409
        assert conflict.json()['error']['code'] == 'idempotency_conflict'
        changed_nested = payload(
            {
                **schema,
                'properties': {**properties, 'second': {**nested, 'properties': dict(reversed(list(inner.items())))}},
            }
        )
        assert client.post(POST, json=changed_nested, headers=headers).json()['error']['code'] == 'idempotency_conflict'
    assert len(provider.calls) == 1

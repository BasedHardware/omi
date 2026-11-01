"""Opt-in public action-item API proof with real Pinecone and loopback Firestore.

Run directly to avoid unrelated integration-suite Firebase bootstrapping:
RUN_LIVE_PINECONE_USER_PATH=1 PYTHONPATH=backend python this_file.py
Only synthetic owners in memories-backend-dev may be mutated.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlparse
from uuid import uuid4

import pytest


def _secret(name: str) -> str:
    return subprocess.check_output(
        ['gcloud', 'secrets', 'versions', 'access', 'latest', f'--secret={name}', '--project=based-hardware'],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def test_real_action_item_user_path(monkeypatch):
    if os.getenv('RUN_LIVE_PINECONE_USER_PATH') != '1':
        pytest.skip('explicit live synthetic-user proof only')
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:10791')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('only loopback Firestore is allowed')
    run_id = uuid4().hex[:10]
    project = f'demo-pinecone-api-{run_id}'
    index_name = 'memories-backend-dev'
    pinecone_key, openai_key = _secret('PINECONE_API_KEY'), _secret('OPENAI_API_KEY')
    for name in (
        'GOOGLE_APPLICATION_CREDENTIALS',
        'SERVICE_ACCOUNT_JSON',
        'FIREBASE_AUTH_CREDENTIALS_PATH',
        'PINECONE_API_KEY',
        'HTTP_PROXY',
        'HTTPS_PROXY',
        'ALL_PROXY',
        'http_proxy',
        'https_proxy',
        'all_proxy',
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in {
        'PYTHON_DOTENV_DISABLED': '1',
        'FIRESTORE_EMULATOR_HOST': host,
        'GOOGLE_CLOUD_PROJECT': project,
        'OMI_FIRESTORE_DATA_PLANE_PROJECT': project,
        'LOCAL_DEVELOPMENT': 'true',
        'OMI_ENV_STAGE': 'local',
        'OPENAI_API_KEY': openai_key,
        'ENCRYPTION_SECRET': 'synthetic-partition-api-proof-key-32',
        'DREAM_AGENT_ENABLED': 'false',
        'REDIS_DB_HOST': '127.0.0.1',
        'REDIS_DB_PORT': '6379',
        'ACTION_ITEMS_LIST_CACHE_TTL_SECONDS': '0',
        'PINECONE_INDEX_NAME': index_name,
    }.items():
        monkeypatch.setenv(name, value)

    from fastapi import FastAPI, HTTPException, Request
    from fastapi.testclient import TestClient
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from langchain_openai import OpenAIEmbeddings
    from pinecone import Pinecone
    from pinecone.exceptions import NotFoundException

    from database import _client, vector_db
    from database import pinecone_partition_state as state
    from database.pinecone_partition_migration import OwnerMigration, PartitionTransport
    from routers import action_items

    db = firestore.Client(project=project, credentials=AnonymousCredentials())
    for name in ('_firestore_client', '_customer_firestore_client', '_data_plane_firestore_client'):
        monkeypatch.setattr(_client, name, db)
    pc = Pinecone(api_key=pinecone_key)
    description = pc.describe_index(index_name)
    assert description.name == index_name
    assert description.dimension == 3072
    index = pc.Index(host=description.host)
    monkeypatch.setattr(vector_db, 'index', index)
    monkeypatch.setattr(vector_db, '_pinecone_index_name', index_name)
    embedding_client = OpenAIEmbeddings(model='text-embedding-3-large', api_key=openai_key)
    monkeypatch.setattr(vector_db, 'embeddings', embedding_client)
    embedding_calls = []
    original_embed_query = type(embedding_client).embed_query

    def observe_embedding(self, text, *args, **kwargs):
        values = original_embed_query(self, text, *args, **kwargs)
        embedding_calls.append((text, list(values)))
        return values

    # Observe the actual OpenAI response used by the HTTP mutation. A separate
    # embedding request can differ numerically and is not a storage oracle.
    monkeypatch.setattr(type(embedding_client), 'embed_query', observe_embedding)

    # Keep the real router, persistence, provider mutation and hydration paths.
    # Suppress only outbound notifications, external task exports and telemetry.
    for name in (
        'submit_with_context',
        'sync_action_item_reminder',
        'send_action_item_deletion_message',
        'send_action_item_data_message',
        'record_product_event',
        'emit_product_event',
    ):
        monkeypatch.setattr(action_items, name, lambda *a, **k: None)

    owner = f'partition-api-{run_id}-owner'
    owner_key = state.PartitionKey(index_name, 'ns4', owner)
    other = next(
        candidate
        for i in range(10_000)
        if (candidate := f'partition-api-{run_id}-other-{i}')
        and state.PartitionKey(index_name, 'ns4', candidate).partition_namespace == owner_key.partition_namespace
    )
    owners = (owner, other)
    for uid in owners:
        db.collection('users').document(uid).set({'name': 'Synthetic partition API fixture'})

    allowed_hosts = {'127.0.0.1', 'localhost', '::1', 'api.openai.com', 'api.pinecone.io', description.host}
    real_resolver = socket.getaddrinfo

    def resolve(hostname, *args, **kwargs):
        if hostname not in allowed_hosts:
            raise AssertionError(f'Unexpected outbound host in synthetic proof: {hostname}')
        return real_resolver(hostname, *args, **kwargs)

    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    app = FastAPI()
    app.include_router(action_items.router)

    def synthetic_owner(request: Request):
        uid = request.headers.get('X-Partition-Test-Owner')
        if uid not in owners:
            raise HTTPException(403, 'synthetic owner only')
        return uid

    app.dependency_overrides[action_items.auth.get_current_user_uid] = synthetic_owner
    evidence = {
        'started_at': datetime.now(timezone.utc).isoformat(),
        'run_id': run_id,
        'index': index_name,
        'firestore_project': project,
        'owners': list(owners),
        'family': 'ns4',
        'checks': [],
        'http': [],
        'source_sha256': {
            name: sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
            for name in (
                'database/vector_db.py',
                'database/pinecone_partition_state.py',
                'database/pinecone_partition_index.py',
                'database/pinecone_partition_migration.py',
                'routers/action_items.py',
            )
        },
        'scope': 'real public HTTP router + Firestore emulator + OpenAI embeddings + Pinecone dev index',
        'excluded': ['production deployment', 'mobile UI', 'Firebase token verification', 'other six vector families'],
    }
    transport = PartitionTransport(description.host, pinecone_key)
    output = Path(
        os.getenv(
            'PINECONE_USER_PATH_EVIDENCE',
            '/Users/kodjimini/mobile-ux-agent/metrics/pinecone-partition-rollout-2026-11-01/user-api-proof.json',
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + '\n')
    output.chmod(0o600)

    try:
        with TestClient(app) as client:

            def request(method, path, uid=owner, **kwargs):
                response = client.request(method, path, headers={'X-Partition-Test-Owner': uid}, **kwargs)
                evidence['http'].append(
                    {
                        'method': method,
                        'path': path,
                        'uid': uid,
                        'status': response.status_code,
                        'response': response.json() if response.content else None,
                    }
                )
                assert response.status_code < 400, (method, path, response.status_code, response.text)
                return response

            def verify_provider(item_id, expected_values=None, absent=False):
                provider_id = f'{owner}-ai-{item_id}'
                deadline = time.monotonic() + 60
                while True:
                    namespaces = (
                        (owner_key.family, owner_key.partition_namespace)
                        if absent
                        else (owner_key.partition_namespace,)
                    )
                    records = [
                        index.fetch(namespace=namespace, ids=[provider_id]).vectors.get(provider_id)
                        for namespace in namespaces
                    ]
                    if absent:
                        complete = all(record is None for record in records)
                    else:
                        record = records[0]
                        values = (
                            [] if record is None else record['values'] if isinstance(record, dict) else record.values
                        )
                        complete = len(values) == len(expected_values) and all(
                            math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-7) for a, b in zip(values, expected_values)
                        )
                    if complete:
                        return
                    if time.monotonic() >= deadline:
                        raise AssertionError('Provider projection did not match successful HTTP mutation')
                    time.sleep(1)

            def search(uid, query, required_id=None, absent_id=None, expected_text=None):
                deadline = time.monotonic() + 60
                while True:
                    items = request('GET', '/v1/action-items/search', uid, params={'query': query}).json()[
                        'action_items'
                    ]
                    ids = {item['id'] for item in items}
                    if (required_id is None or required_id in ids) and (absent_id is None or absent_id not in ids):
                        if expected_text is not None:
                            assert (
                                next(item for item in items if item['id'] == required_id)['description']
                                == expected_text
                            )
                        return items
                    if time.monotonic() >= deadline:
                        raise AssertionError(f'Expected API search visibility did not converge: {ids}')
                    time.sleep(1)

            seeded = {}
            for uid in owners:
                title = f'Synthetic {run_id}: prepare the cobalt observatory invoice'
                row = request('POST', '/v1/action-items', uid, json={'description': title}).json()
                seeded[uid] = row['id']
                search(uid, title, required_id=row['id'], expected_text=title)
            for uid in owners:
                key = state.PartitionKey(index_name, 'ns4', uid)
                proof = OwnerMigration(key, transport, firestore_client=db).qualify(uuid4().hex, dimension=3072)
                route = state.cutover(key, proof['migration_token'], proof['revision'], proof, firestore_client=db)
                assert route.mode == 'partitioned'
                evidence['checks'].append(
                    {'kind': 'cutover', 'uid': uid, 'records': proof['records'], 'namespace': route.primary_namespace}
                )
                search(uid, 'cobalt observatory invoice', required_id=seeded[uid])

            for repeat in range(3):
                title = f'Synthetic {run_id} run {repeat}: deliver the cobalt observatory invoice'
                created = request('POST', '/v1/action-items', json={'description': title}).json()
                item_id = created['id']
                search(owner, title, required_id=item_id, expected_text=title)
                search(other, title, absent_id=item_id, required_id=seeded[other])
                updated = f'Synthetic {run_id} run {repeat}: deliver the amber telescope receipt'
                before_update = len(embedding_calls)
                changed = request('PATCH', f'/v1/action-items/{item_id}', json={'description': updated}).json()
                assert changed['description'] == updated
                update_embeddings = embedding_calls[before_update:]
                assert len(update_embeddings) == 1 and update_embeddings[0][0] == updated
                expected_values = update_embeddings[0][1]
                search(owner, updated, required_id=item_id, expected_text=updated)
                verify_provider(item_id, expected_values=expected_values)
                foreign = client.patch(
                    f'/v1/action-items/{item_id}',
                    headers={'X-Partition-Test-Owner': other},
                    json={'description': 'Forbidden foreign edit'},
                )
                assert foreign.status_code == 404
                assert request('GET', f'/v1/action-items/{item_id}').json()['description'] == updated
                assert request('DELETE', f'/v1/action-items/{item_id}').status_code == 204
                search(owner, updated, absent_id=item_id)
                verify_provider(item_id, absent=True)
                assert (
                    client.get(f'/v1/action-items/{item_id}', headers={'X-Partition-Test-Owner': owner}).status_code
                    == 404
                )
                evidence['checks'].append(
                    {'kind': 'create-search-update-delete-owner-isolation', 'repeat': repeat + 1, 'passed': True}
                )
            evidence['passed'] = True
    finally:
        cleanup = []
        for uid in owners:
            key = state.PartitionKey(index_name, 'ns4', uid)
            for namespace in (key.family, key.partition_namespace):
                try:
                    index.delete(namespace=namespace, filter={'uid': {'$eq': uid}})
                    deadline = time.monotonic() + 60
                    while True:
                        response = index.query(
                            namespace=namespace, vector=[1.0] + [0.0] * 3071, filter={'uid': {'$eq': uid}}, top_k=1
                        )
                        if not response['matches']:
                            break
                        if time.monotonic() >= deadline:
                            raise AssertionError('synthetic cleanup not visible')
                        time.sleep(1)
                    cleanup.append({'uid': uid, 'namespace': namespace, 'empty_verified': True})
                except NotFoundException as exc:
                    if 'Namespace not found' not in str(exc):
                        raise
                    cleanup.append({'uid': uid, 'namespace': namespace, 'absent_namespace': True})
                except Exception as exc:
                    cleanup.append({'uid': uid, 'namespace': namespace, 'error': type(exc).__name__})
        evidence['cleanup'] = cleanup
        evidence['cleanup_verified'] = all('error' not in entry for entry in cleanup)
        evidence['finished_at'] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(evidence, indent=2) + '\n')
        output.chmod(0o600)
        transport.client.close()
        db.close()
    assert evidence['cleanup_verified'], evidence['cleanup']
    print(
        json.dumps(
            {'passed': evidence.get('passed', False), 'evidence': str(output), 'checks': len(evidence['checks'])}
        )
    )


if __name__ == '__main__':
    with pytest.MonkeyPatch.context() as monkeypatch:
        test_real_action_item_user_path(monkeypatch)

"""Opt-in dev-provider/API experiment. No migration or production admission.

Run as a standalone script with RUN_EXACT_CANDIDATE_LIVE=1, loopback Firestore,
a unique demo-* project, and explicit PINECONE_API_KEY/OPENAI_API_KEY. Results
go to EXACT_CANDIDATE_EVIDENCE. Only exact-candidate-* fixture records change.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import struct
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

if os.getenv('RUN_EXACT_CANDIDATE_LIVE') != '1':
    pytest.skip('Explicit dev-provider experiment only', allow_module_level=True)

from fastapi import FastAPI, HTTPException
from fastapi import Request as FastAPIRequest
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from pinecone import Pinecone

from database import _client, vector_db
from database import pinecone_partition_state as state
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.pinecone_partition_index import owner_index
from database.pinecone_partition_migration import PartitionTransport
from routers import action_items
from testing.pinecone_exact_candidate import CandidateRejected, ExactFixtureOwnerIndex, ReadAuthority


def float32(value):
    return struct.unpack('!f', struct.pack('!f', value))[0]


def run(monkeypatch):
    host = os.environ['FIRESTORE_EMULATOR_HOST']
    project = os.environ['OMI_FIRESTORE_DATA_PLANE_PROJECT']
    assert urlparse(f'//{host}').hostname in {'127.0.0.1', 'localhost', '::1'}
    assert project.startswith('demo-exact-candidate-')
    output = Path(os.environ['EXACT_CANDIDATE_EVIDENCE'])
    assert not output.exists()
    run_id = uuid4().hex[:12]
    uid = f'exact-candidate-{run_id}'
    key = state.PartitionKey('memories-backend-dev', 'ns4', uid)
    db = firestore.Client(project=project, credentials=AnonymousCredentials())
    for name in ('_firestore_client', '_customer_firestore_client', '_data_plane_firestore_client'):
        monkeypatch.setattr(_client, name, db)
    pc = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
    description = pc.describe_index(key.index_name)
    assert description.name == key.index_name and description.metric == 'cosine' and description.dimension == 3072
    index = pc.Index(host=description.host)
    transport = PartitionTransport(description.host, os.environ['PINECONE_API_KEY'])
    monkeypatch.setattr(vector_db, 'index', index)
    monkeypatch.setattr(vector_db, '_pinecone_index_name', key.index_name)
    query_text = 'Prepare the observatory invoice for the telescope delivery'
    vector = vector_db.embeddings.embed_query(query_text)
    norm = math.sqrt(math.fsum(v * v for v in vector))
    unit = [v / norm for v in vector]
    axis = min(range(len(unit)), key=lambda i: abs(unit[i]))
    perpendicular = [-unit[axis] * v for v in unit]
    perpendicular[axis] += 1
    norm = math.sqrt(math.fsum(v * v for v in perpendicular))
    perpendicular = [v / norm for v in perpendicular]
    rows = []
    now = datetime.now(timezone.utc)
    for name, cosine in (
        ('tie-a', 0.9),
        ('tie-z', 0.9),
        ('above-dedup', 0.6001),
        ('below-dedup', 0.5999),
        ('above-search', 0.30013625507732045),
        ('below-search', 0.2999),
        ('low', 0.1),
        ('negative', -0.1),
    ):
        values = [float32(cosine * a + math.sqrt(1 - cosine * cosine) * b) for a, b in zip(unit, perpendicular)]
        rows.append({'id': f'{uid}-ai-{name}', 'values': values, 'metadata': {'uid': uid, 'action_item_id': name}})
    route_ref = db.collection(state.COLLECTION).document(key.document_id)
    deletion_ref = db.collection('account_deletions').document(uid)

    @firestore.transactional
    def authority(transaction):
        snapshot = route_ref.get(transaction=transaction)
        marker = deletion_ref.get(transaction=transaction)
        route = state._route(state._snapshot_row(snapshot, key))
        return ReadAuthority(
            key.index_name,
            uid,
            route.primary_namespace,
            route.revision,
            route.migration_token,
            route.pending_count,
            route.uncertain_count,
            snapshot.exists,
            account_deletion_marker_blocks_access(
                marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('status')
            ),
        )

    read_authority = lambda: authority(db.transaction())
    app = FastAPI()
    app.include_router(action_items.router)

    def authenticate(request: FastAPIRequest):
        if request.headers.get('X-Exact-Fixture') != uid:
            raise HTTPException(403, 'Fixture owner only')
        return uid

    app.dependency_overrides[action_items.auth.get_current_user_uid] = authenticate
    snapshots = {}

    def exact_index(raw_index, requested_uid, *, index_name):
        assert raw_index is index and requested_uid == uid and index_name == key.index_name
        return snapshots[uid]

    monkeypatch.setattr(vector_db, 'owner_index', exact_index)
    evidence = {
        'started_at': now.isoformat(),
        'index': key.index_name,
        'uid': uid,
        'completeness_basis': 'Fixture owns every write; expected IDs and float32 payloads are known',
        'scope': 'Real action-item HTTP router, hydration, OpenAI query embeddings, Pinecone dev records, loopback Firestore',
        'production_ready': False,
        'runtime_enabled': False,
        'checks': [],
        'cleanup': [],
        'provider_operations_attempted': {'fixture_upserts': 0, 'owner_mutations': 0, 'cleanup_deletes': 0},
        'billing_usage': 'UNMEASURED: REST usage is incomplete and SDK/embedding calls are not metered here',
        'source_sha256': {
            name: sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
            for name in (
                'testing/pinecone_exact_candidate.py',
                'tests/integration/test_pinecone_exact_candidate_live.py',
            )
        },
        'limitations': [
            'ns4 UID-only filters',
            '128 records maximum',
            'No production manifest authority or renewal',
            'Current consumers swallow snapshot rejection as empty results',
            'No mobile UI proof',
        ],
    }
    try:
        db.collection('users').document(uid).set({'name': 'Exact retrieval synthetic fixture'})
        for row in rows:
            item_id = row['metadata']['action_item_id']
            db.collection('users').document(uid).collection('action_items').document(item_id).set(
                {
                    'description': f'Synthetic exact retrieval task {item_id}',
                    'completed': False,
                    'created_at': now,
                    'updated_at': now,
                    'is_locked': False,
                }
            )
        with TestClient(app) as client:
            for generation, namespace in enumerate((key.family, key.partition_namespace), start=1):
                evidence['provider_operations_attempted']['fixture_upserts'] += 1
                write_lsn = transport.write('vectors/upsert', namespace, vectors=rows)
                indexed_lsn = transport.await_indexed(namespace, uid, vector, write_lsn)
                fetched = [r for page in transport.owned_pages(namespace, uid) for r in page]
                expected = {r['id']: r for r in rows}
                assert set(expected) == {r['id'] for r in fetched} and len(fetched) == len(rows)
                for row in fetched:
                    original = expected[row['id']]
                    assert row['metadata'] == original['metadata']
                    assert [float32(v) for v in row['values']] == original['values']
                # Provider's JSON float spelling may differ from Python's even
                # for the same IEEE float32. The owned write manifest above is
                # checked bit-for-bit before using its fetched representation.
                route_ref.set(
                    {
                        'schema_version': 1,
                        'index_name': key.index_name,
                        'family': 'ns4',
                        'uid': uid,
                        'mode': 'legacy' if namespace == 'ns4' else 'partitioned',
                        'primary_namespace': namespace,
                        'revision': generation,
                        'pending': {},
                        'uncertain_count': 0,
                        'latest_write_lsn': write_lsn,
                        'unknown_freshness': False,
                    }
                )
                snapshot = ExactFixtureOwnerIndex(
                    authority=read_authority(),
                    read_authority=read_authority,
                    manifest=fetched,
                    fetched=fetched,
                    provider_namespace=namespace,
                    write_lsn=write_lsn,
                    indexed_lsn=indexed_lsn,
                )
                snapshots[uid] = snapshot
                for repeat in range(3):
                    started = time.monotonic()
                    response = client.get(
                        '/v1/action-items/search', params={'query': query_text}, headers={'X-Exact-Fixture': uid}
                    )
                    assert response.status_code == 200, response.text
                    items = response.json()['action_items']
                    ids = [r['id'] for r in items]
                    assert ids == ['tie-a', 'tie-z', 'above-dedup', 'below-dedup', 'above-search'], ids
                    dedup = vector_db.find_similar_action_items(uid, query_text)
                    assert [r['action_item_id'] for r in dedup] == ['tie-a', 'tie-z', 'above-dedup'], dedup
                    assert all(r['description'].startswith('Synthetic exact retrieval task') for r in items)
                    evidence['checks'].append(
                        {
                            'namespace': namespace,
                            'repeat': repeat + 1,
                            'ids': ids,
                            'dedup_ids': [r['action_item_id'] for r in dedup],
                            'search_and_dedup_seconds': time.monotonic() - started,
                        }
                    )
            deletion_ref.set({'status': 'pending'})
            with pytest.raises(CandidateRejected):
                snapshot.query(namespace='ns4', vector=vector, top_k=10, filter={'uid': uid})
            deletion_ref.delete()
            route_data = route_ref.get().to_dict()
            route_ref.delete()
            with pytest.raises(CandidateRejected):
                snapshot.query(namespace='ns4', vector=vector, top_k=10, filter={'uid': uid})
            assert not route_ref.get().exists
            route_ref.set(route_data)
            changed = dict(rows[0], values=rows[5]['values'])
            assert changed['values'] != rows[0]['values']
            evidence['provider_operations_attempted']['owner_mutations'] += 1
            owner_index(index, uid, index_name=key.index_name, firestore_client=db).upsert(
                vectors=[changed], namespace='ns4'
            )
            with pytest.raises(CandidateRejected):
                snapshot.query(namespace='ns4', vector=vector, top_k=10, filter={'uid': uid})
            degraded = client.get(
                '/v1/action-items/search', params={'query': query_text}, headers={'X-Exact-Fixture': uid}
            )
            assert degraded.status_code == 200 and degraded.json()['action_items'] == []
            assert vector_db.find_similar_action_items(uid, query_text) == []
            evidence['invalidated_snapshot_rejected'] = True
            evidence['consumer_empty_result_blocker_reproduced'] = True
            evidence['candidate_experiment_passed'] = True
    except Exception as error:
        evidence['experiment_error_type'] = type(error).__name__
        raise
    finally:
        for namespace in (key.family, key.partition_namespace):
            try:
                evidence['provider_operations_attempted']['cleanup_deletes'] += 1
                index.delete(namespace=namespace, filter={'uid': uid})
                deadline = time.monotonic() + 60
                while index.fetch(namespace=namespace, ids=[r['id'] for r in rows]).vectors:
                    assert time.monotonic() < deadline, 'Fixture deletion not visible'
                    time.sleep(1)
                evidence['cleanup'].append({'namespace': namespace, 'all_fixture_ids_absent': True})
            except Exception as error:
                evidence['cleanup'].append({'namespace': namespace, 'error_type': type(error).__name__})
        try:
            purge = f'http://{host}/emulator/v1/projects/{project}/databases/(default)/documents'
            with urlopen(Request(purge, method='DELETE'), timeout=30) as response:
                assert response.status == 200
            assert not list(db.collections())
            evidence['emulator_project_empty'] = True
        except Exception as error:
            evidence['emulator_cleanup_error_type'] = type(error).__name__
        finally:
            evidence['cleanup_verified'] = evidence.get('emulator_project_empty', False) and all(
                'error_type' not in x for x in evidence['cleanup']
            )
            evidence['finished_at'] = datetime.now(timezone.utc).isoformat()
            try:
                output.write_text(json.dumps(evidence, indent=2) + '\n')
                output.chmod(0o600)
            finally:
                try:
                    transport.client.close()
                finally:
                    db.close()
    assert evidence['cleanup_verified']
    print(json.dumps({'passed': evidence.get('candidate_experiment_passed', False), 'evidence': str(output)}))


if __name__ == '__main__':
    with pytest.MonkeyPatch.context() as patches:
        run(patches)

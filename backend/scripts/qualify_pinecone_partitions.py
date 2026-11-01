"""Exercise the real provider plus Firestore emulator, using synthetic owners only.

Requires PINECONE_API_KEY, PINECONE_INDEX_NAME ending in -dev, and a loopback
FIRESTORE_EMULATOR_HOST. Emits counts/LSNs only; never account content or keys.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from pinecone import Pinecone

from database import pinecone_partition_state as state
from database.pinecone_partition_index import owner_index
from database.pinecone_partition_migration import IDENTITY_FIELDS, OwnerMigration, PartitionTransport


def run(output: Path) -> None:
    index_name = os.environ['PINECONE_INDEX_NAME']
    emulator = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not index_name.endswith('-dev') or not emulator.startswith(('127.0.0.1:', 'localhost:')):
        raise RuntimeError('This qualification permits only a dev index and loopback Firestore emulator')
    api_key = os.environ['PINECONE_API_KEY']
    control = Pinecone(api_key=api_key)
    description = control.describe_index(index_name)
    raw = control.Index(host=description.host)
    db = firestore.Client(project='demo-pinecone-partitions', credentials=AnonymousCredentials())
    transport = PartitionTransport(description.host, api_key)
    uid = 'partition-qa-' + uuid4().hex
    other = None
    bucket = state.PartitionKey(index_name, 'ns1', uid).partition_namespace
    for i in range(10000):
        candidate = uid + f'-other-{i}'
        if state.PartitionKey(index_name, 'ns1', candidate).partition_namespace == bucket:
            other = candidate
            break
    if other is None:
        raise RuntimeError('No deliberate bucket collision found')
    evidence = {'index': index_name, 'owners': [uid, other], 'checks': [], 'cleanup': []}
    handles = {owner: owner_index(raw, owner, index_name=index_name, firestore_client=db) for owner in (uid, other)}
    vector = [1.0] + [0.0] * (description.dimension - 1)
    try:
        for family in sorted(state.FAMILIES):
            ids = {owner: owner + '-fixture-' + family for owner in handles}
            for owner, handle in handles.items():
                metadata = {'uid': owner, **{field: ids[owner] for field in IDENTITY_FIELDS[family]}}
                if family == 'ns_tchunks':
                    metadata['chunk_index'] = 0
                if family == 'workstream-association-v1':
                    metadata['account_generation'] = 0
                handle.upsert(namespace=family, vectors=[{'id': ids[owner], 'values': vector, 'metadata': metadata}])
                key = state.PartitionKey(index_name, family, owner)
                transport.await_indexed(
                    family, owner, vector, state.get_route(key, firestore_client=db).latest_write_lsn
                )
            key = state.PartitionKey(index_name, family, uid)
            other_key = state.PartitionKey(index_name, family, other)
            other_token = uuid4().hex
            other_receipt = OwnerMigration(other_key, transport, firestore_client=db).qualify(
                other_token, dimension=description.dimension
            )
            state.cutover(
                other_key,
                other_token,
                expected_revision=other_receipt['revision'],
                receipt=other_receipt,
                firestore_client=db,
            )
            migrator = OwnerMigration(key, transport, firestore_client=db)
            for repetition in range(3):
                token = uuid4().hex
                receipt = migrator.qualify(token, dimension=description.dimension)
                state.cutover(key, token, expected_revision=receipt['revision'], receipt=receipt, firestore_client=db)
                handle = handles[uid]
                result = handle.query(namespace=family, vector=vector, top_k=10, filter={'uid': uid})
                if [hit['id'] for hit in result['matches']] != [ids[uid]]:
                    raise AssertionError('User query did not return its own migrated fixture')
                handle.update(ids[uid], namespace=family, set_metadata={'qa_revision': repetition})
                route = state.get_route(key, firestore_client=db)
                transport.await_indexed(route.primary_namespace, uid, vector, route.latest_write_lsn)
                result = handle.fetch(namespace=family, ids=[ids[uid]])
                if result.vectors[ids[uid]].metadata['qa_revision'] != repetition:
                    raise AssertionError('Updated fixture metadata was not visible')
                other_result = handles[other].query(namespace=family, vector=vector, top_k=10, filter={'uid': other})
                if [hit['id'] for hit in other_result['matches']] != [ids[other]]:
                    raise AssertionError('Other owner changed during migration')
                rollback = uuid4().hex
                rollback_receipt = migrator.qualify(rollback, dimension=description.dimension, rollback=True)
                state.cutover(
                    key,
                    rollback,
                    expected_revision=rollback_receipt['revision'],
                    receipt=rollback_receipt,
                    firestore_client=db,
                )
                result = handle.fetch(namespace=family, ids=[ids[uid]])
                if result.vectors[ids[uid]].metadata['qa_revision'] != repetition:
                    raise AssertionError('Rollback did not preserve the newest update')
                evidence['checks'].append(
                    {'family': family, 'repeat': repetition, 'migration': receipt, 'rollback': rollback_receipt}
                )
            print(json.dumps({'family': family, 'cycles': 3, 'shared_bucket_exercised': True}), flush=True)
    finally:
        for family in sorted(state.FAMILIES):
            for owner, handle in handles.items():
                try:
                    handle.delete_all_copies(namespace=family, filter={'uid': owner})
                    handle.verify_empty_all_copies(namespace=family, filter={'uid': owner})
                    evidence['cleanup'].append({'family': family, 'owner': owner, 'passed': True})
                except Exception as error:
                    evidence['cleanup'].append(
                        {'family': family, 'owner': owner, 'passed': False, 'error_type': type(error).__name__}
                    )
        output.write_text(json.dumps(evidence, indent=2) + '\n')
        output.chmod(0o600)
    if not all(row['passed'] for row in evidence['cleanup']):
        raise AssertionError('Fixture cleanup was not verified; inspect evidence before retrying')
    print(json.dumps({'cycles': len(evidence['checks']), 'cleanup_checks': len(evidence['cleanup']), 'passed': True}))


if __name__ == '__main__':
    run(Path(sys.argv[1]))

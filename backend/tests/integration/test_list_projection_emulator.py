"""Server Commit proof for projection-expanded source/delete batches (no cloud access)."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.types import CommitRequest

from config.list_projection import ROW_COLLECTIONS, STATE_COLLECTION
from database import action_item_versions
from database._client import delete_collection_recursive

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('family', ['conversations', 'action_items'])
@pytest.mark.parametrize('source_count', [450, 499])
def test_projection_expanded_commit_and_recursive_delete(monkeypatch, family, source_count):
    emulator = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not emulator:
        pytest.skip('requires the dedicated local Firestore emulator')
    assert urlsplit('http://' + emulator).hostname in {'127.0.0.1', 'localhost', '::1'}
    assert os.getenv('GCLOUD_PROJECT') == 'demo-fs-p1'
    monkeypatch.setenv('OMI_LIST_PROJECTION_WRITER_ENABLED', 'true')
    # This proof measures the real Firestore Commit surface. Never connect to
    # the unrelated Redis cache while running an isolated emulator fixture.
    monkeypatch.setattr(action_item_versions, 'begin', lambda uid: ('synthetic-ticket', True))
    monkeypatch.setattr(action_item_versions, 'finish', lambda uid, ticket: None)
    client = firestore.Client(project='demo-fs-p1', credentials=AnonymousCredentials())
    uid = 'projection-emulator-' + uuid4().hex
    user = client.collection('users').document(uid)
    source = user.collection(family)
    records = []
    api = client._firestore_api
    commit = api.commit

    def record_commit(*, request, **kwargs):
        size = CommitRequest.pb(CommitRequest(**request)).ByteSize()
        records.append({'writes': len(request['writes']), 'bytes': size})
        return commit(request=request, **kwargs)

    monkeypatch.setattr(api, 'commit', record_commit)
    try:
        batch = client.batch()
        for index in range(source_count):
            batch.set(source.document(str(index)), {'status': 'completed', 'completed': True})
        results = batch.commit(timeout=30)
        expected = 2 * source_count + 1
        assert len(results) == source_count  # SDK callers still see source results only.
        assert records[-1]['writes'] == expected and expected > 500
        assert records[-1]['bytes'] < 10 * 1024 * 1024
        assert len(list(user.collection(ROW_COLLECTIONS[family]).stream())) == source_count
        assert len(user.collection(STATE_COLLECTION).document(family).get().to_dict()['version']) == 32
        before_delete = len(records)
        delete_collection_recursive(source, client=client, batch_size=source_count)
        assert records[before_delete]['writes'] == expected
        assert not list(source.limit(1).stream())
        assert not list(user.collection(ROW_COLLECTIONS[family]).limit(1).stream())
        receipt = {
            'family': family,
            'source_count': source_count,
            'commit_writes': expected,
            'max_request_bytes': max(item['bytes'] for item in records),
        }
        target = os.getenv('LIST_PROJECTION_EMULATOR_RECEIPT')
        if target:
            with Path(target).open('a') as handle:
                handle.write(json.dumps(receipt) + '\n')
    finally:
        # Namespace is unique and synthetic; never enumerate another test's data.
        delete_collection_recursive(source, client=client, batch_size=source_count)
        delete_collection_recursive(user.collection(ROW_COLLECTIONS[family]), client=client)
        user.delete()
        client.close()

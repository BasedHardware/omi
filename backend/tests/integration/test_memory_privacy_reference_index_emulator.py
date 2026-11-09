"""SDK pagination and atomic reference-union proofs; synthetic loopback data only."""

from concurrent.futures import ThreadPoolExecutor
import os
from urllib.parse import urlparse
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.query import Query
import pytest

from database import memory_ledger as ledger
from database import memory_privacy_reference_index as index


@pytest.fixture
def harness(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'localhost', '127.0.0.1', '::1'}:
        pytest.fail('A loopback Firestore emulator is required')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'privacy_reference_emulator_key_32_bytes')
    monkeypatch.setenv('MEMORY_PRIVACY_REFERENCE_INDEX', 'on')
    monkeypatch.setattr(ledger, 'MEMORY_COMMIT_PRIVACY_PURGE_PAGE_SIZE', 2)
    db = firestore.Client(project='demo-omi-isolated-tests', credentials=AnonymousCredentials())
    uid = f'privacy-proof-{uuid4().hex}'
    refs = []

    def seed(owner, collection, doc_id, payload):
        ref = db.collection('users').document(owner).collection(collection).document(doc_id)
        refs.append(ref)
        ref.set(payload)
        return ref

    try:
        yield db, uid, seed
    finally:
        for ref in refs:
            ref.delete()
        db.close()


@pytest.mark.parametrize('collection', index.PRIVACY_HISTORY_COLLECTIONS)
def test_indexed_candidates_paginate_chunk_and_deduplicate(harness, collection, capsys, monkeypatch):
    db, uid, seed = harness
    targets = {f'memory-{n}' for n in range(65)}
    budget = collection == 'jit_proactivity_daily_budgets'
    payload = {'planned_by_trigger': {key: 1 for key in targets}} if budget else {'nested': sorted(targets)}
    indexed = index.with_privacy_reference_tokens(uid, payload, budget=budget)
    for n in range(7):
        seed(uid, collection, f'row-{n}', indexed)
    seed(uid, collection, 'unrelated', index.with_privacy_reference_tokens(uid, {'memory_id': 'unrelated'}))
    # Even identical tokens under another owner must never enter owner-local reads.
    seed(f'{uid}-peer', collection, 'peer', indexed)
    query = db.collection('users').document(uid).collection(collection)
    stream = Query.stream
    page_sizes = []

    def observed_stream(self, *args, **kwargs):
        page = list(stream(self, *args, **kwargs))
        page_sizes.append(len(page))
        return iter(page)

    monkeypatch.setattr(Query, 'stream', observed_stream)
    candidates = list(ledger._iter_privacy_history_candidates(query, uid, targets))
    assert [doc.id for doc in candidates] == [f'row-{n}' for n in range(7)]
    assert page_sizes == [2, 2, 2, 1] * 3
    assert all(doc.reference.path.rsplit('/', 1)[0] == f'users/{uid}/{collection}' for doc in candidates)
    exhaustive = list(ledger._iter_collection_documents(query))
    assert len(exhaustive) == 8
    assert {doc.id for doc in candidates} == {
        doc.id
        for doc in exhaustive
        if set(doc.to_dict().get(index.PRIVACY_REFERENCE_TOKENS, [])).intersection(
            index.privacy_reference_tokens(uid, targets)
        )
    }
    with capsys.disabled():
        print(
            f'PASS pagination {collection}: 7 unique matches, 12 SDK pages, page_size=2, 65 targets/3 chunks, owner isolated'
        )


@pytest.mark.parametrize('collection', index.PRIVACY_HISTORY_COLLECTIONS)
def test_array_union_is_atomic_and_idempotent(harness, collection, capsys):
    _, uid, seed = harness
    original = index.with_privacy_reference_tokens(uid, {'memory_id': 'original'})
    ref = seed(uid, collection, 'union', original)
    patches = [index.privacy_reference_patch(uid, {f'ref_{n}': f'memory-{n}', 'shared': 'shared'}) for n in range(8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(ref.update, patches))
    expected = index.privacy_reference_tokens(uid, {'original', 'shared', *(f'memory-{n}' for n in range(8))})
    stored = ref.get().to_dict()
    assert sorted(stored[index.PRIVACY_REFERENCE_TOKENS]) == expected
    for n in range(8):
        assert stored[f'ref_{n}'] == f'memory-{n}'
    for patch in patches:
        ref.update(patch)
    assert ref.get().to_dict() == stored
    # The SDK transform also initializes arrays on unindexed retained rows.
    unindexed = seed(uid, collection, 'unindexed', {'memory_id': 'legacy'})
    unindexed.update(patches[0])
    assert sorted(unindexed.get().to_dict()[index.PRIVACY_REFERENCE_TOKENS]) == index.privacy_reference_tokens(
        uid, {'memory-0', 'shared'}
    )
    with capsys.disabled():
        print(
            f'PASS ArrayUnion {collection}: 8 concurrent patches, 10 unique tokens, replay unchanged, absent array initialized'
        )

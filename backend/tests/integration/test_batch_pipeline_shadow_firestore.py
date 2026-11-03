"""Real transaction races for shadow offers/spend. Loopback emulator only."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import os
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_shadow import ShadowStore
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.scheduler import owner_key

pytestmark = pytest.mark.integration


@pytest.fixture
def repository(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('owned loopback emulator required; no cloud fallback')
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR', '3')
    client = firestore.Client(project='demo-batch-shadow', credentials=AnonymousCredentials())
    store = FirestoreStore(f'batch_pipeline_test_{uuid4().hex}', firestore_client=client)
    client.collection('users').document('synthetic-shadow').set({'data_protection_level': 'enhanced'})
    yield ShadowStore(store, clock=lambda: 7200)
    # Only this test's unique namespace, on this explicitly bound emulator.
    for table in ('shadow_jobs', 'shadow_slots', 'shadow_spend'):
        for document in client.collection(f'{store.namespace}_{table}').stream():
            document.reference.delete()
    client.close()


def recovering(repository, segment):
    item = WorkItem(segment, 'synthetic-shadow', 1, 'synthetic:audio', 300, 2, shadow=True, privacy_generation=0)
    repository.store.run(
        lambda tx: tx.put(
            'shadow_jobs',
            segment,
            {
                'shadow': True,
                'state': 'recovering',
                'owner_key': owner_key(item.owner_id),
                'class': 'deep',
                'item': asdict(item),
            },
        )
    )


def test_concurrent_calls_never_exceed_shared_cap(repository):
    for index in range(8):
        recovering(repository, f'sh_{index}')
    replicas = [ShadowStore(repository.store, clock=repository.clock) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda index: replicas[index].paid(f'sh_{index}', 'modulate'), range(8)))
    assert sum(results) <= 3
    budget = repository.store.run(lambda tx: tx.get('shadow_spend', '2'))
    assert sum(results) <= budget['units'] <= 3
    # Contention is allowed to reject spend conservatively, never to exceed the
    # budget. With contention gone the remaining permits can be filled exactly.
    for index in range(8):
        repository.paid(f'sh_{index}', 'modulate')
    assert repository.store.run(lambda tx: tx.get('shadow_spend', '2'))['units'] == 3


def test_duplicate_provider_race_reserves_once(repository):
    recovering(repository, 'sh_same')
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: repository.paid('sh_same', 'modulate'), range(4)))
    assert sum(results) == 1
    assert repository.store.run(lambda tx: tx.get('shadow_spend', '2'))['units'] == 1


def test_two_uploads_cannot_consume_one_idle_offer(repository):
    repository.offer('synthetic-worker')
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(lambda content: repository.reserve('synthetic-shadow', content, 'fresh'), ['one', 'two'])
        )
    assert sum(result is not None for result in results) == 1
    outcomes = list(repository.store.client.collection(f'{repository.store.namespace}_shadow_jobs').stream())
    assert sorted(row.to_dict()['state'] for row in outcomes) == ['settled', 'staging']

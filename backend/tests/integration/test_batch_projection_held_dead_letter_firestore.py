"""Loopback-only expiry CAS and flag-off nightly release; no production fallback."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_release import ProjectionReleaseStore
from database.batch_pipeline_quarantine_recovery import held_expired_stock
from database.batch_pipeline_store import FirestoreStore
from tests.unit.test_batch_pipeline_projection_release import rows, OWNER, TARGET
from utils.batch_pipeline.held_dead_letter import ProjectionHeldDeadLetter

pytestmark = pytest.mark.integration


@pytest.fixture
def held(monkeypatch):
    if not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback emulator required; no cloud fallback')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    client = firestore.Client(project=f'demo-held-projection-{uuid4().hex[:10]}', credentials=AnonymousCredentials())
    store = FirestoreStore('batch_pipeline_prod', firestore_client=client)
    for path, value in rows(discarded=True, held_deadline_at=1, payload={'words': ['retained']}).items():
        client.document('/'.join(path)).set(value)
    yield store, ProjectionStore(store)
    client.close()


@pytest.mark.parametrize('attempts', [0, 3])
def test_expiry_content_preserved_and_nightly_flag_off_release_cas(held, monkeypatch, attempts):
    store, projection = held
    result = projection.ref('results', 'held')
    result.update({'projection_release_attempts': attempts, 'projection_redriven_at': 0.5 if attempts else None})
    before = deepcopy(result.get().to_dict())
    job = projection.ref('jobs', 'held').get().to_dict()

    def expire(_):
        release = ProjectionReleaseStore(projection)
        release.release('held', 2)
        return release.expired

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(expire, range(2))) == [False, True]
    expired = result.get().to_dict()
    assert expired == {
        **before,
        'held_expired_reason': 'held_expired',
        'held_expired_at': 2,
        **({'held_expired_release_attempts': 3, 'projection_release_attempts': 0} if attempts == 3 else {}),
    }
    assert projection.ref('jobs', 'held').get().to_dict() == job
    assert held_expired_stock(store.client, store.namespace) == 1
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    assert ProjectionHeldDeadLetter(store).tick(86401) == 0
    assert result.get().to_dict() == expired
    target = store.client.collection('users').document(OWNER).collection('conversations').document(TARGET)
    target.update({'discarded': False})
    # Completed nightly passes wait until the next UTC day, including restarts.
    assert ProjectionHeldDeadLetter(store).tick(86701) == 0
    assert ProjectionHeldDeadLetter(store).tick(172801) == 1
    assert result.get().to_dict()['projection_state'] == 'pending'
    assert result.get().to_dict()['payload'] == before['payload']
    assert held_expired_stock(store.client, store.namespace) == 0
    assert ProjectionHeldDeadLetter(store).tick(173101) == 0


def test_duplicate_nightly_release_increments_attempts_once(held):
    _, projection = held
    result = projection.ref('results', 'held')
    ProjectionReleaseStore(projection).release('held', 2)
    target = projection.client.collection('users').document(OWNER).collection('conversations').document(TARGET)
    target.update({'discarded': False})
    with ThreadPoolExecutor(max_workers=2) as pool:
        released = list(
            pool.map(lambda _: ProjectionReleaseStore(projection).release('held', 86401, dead_before=86400), range(2))
        )
    assert sorted(released) == [False, True]
    assert result.get().to_dict()['projection_release_attempts'] == 1


@pytest.mark.parametrize('attempts', [0, 3])
def test_pre_change_scan_and_release_recovers_expired_row_with_flag_off(held, monkeypatch, attempts):
    from tests.unit.fixtures.legacy_projection_release import (
        ProjectionReleaseStore as LegacyReleaseStore,
        held_page_ids,
    )

    store, projection = held
    result = projection.ref('results', 'held')
    result.update({'projection_release_attempts': attempts, 'projection_redriven_at': 0.5 if attempts else None})
    payload = result.get().to_dict()['payload']
    assert not ProjectionReleaseStore(projection).release('held', 2)
    expired = result.get().to_dict()
    assert expired['projection_state'] == 'quarantine_held'
    assert expired['held_expired_reason'] == 'held_expired'
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    assert held_page_ids(store.client, store.namespace, 128, None) == ['held']
    assert not LegacyReleaseStore(projection).release('held', 3)
    assert result.get().to_dict() == expired
    projection.client.collection('users').document(OWNER).collection('conversations').document(TARGET).update(
        {'discarded': False}
    )
    assert LegacyReleaseStore(projection).release('held', 4)
    assert result.get().to_dict()['projection_state'] == 'pending'
    assert result.get().to_dict()['payload'] == payload
    assert held_expired_stock(store.client, store.namespace) == 0

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.account_cutover as account_cutover_db
import database.context_buckets as context_buckets_db
import routers.context_buckets as context_buckets_router
from utils.other.endpoints import get_current_user_uid

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def client(monkeypatch):
    """Drive the real routes with auth and rate limiting stubbed out.

    Rate limiting is a Redis round trip; the policies themselves are asserted
    separately so this suite stays hermetic.
    """

    monkeypatch.setattr(
        context_buckets_router.auth,
        'with_rate_limit',
        lambda dependency, policy_name: dependency,
    )
    app = FastAPI()
    app.include_router(context_buckets_router.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'u1'
    return TestClient(app)


def sync_payload(fact_id='fact-1'):
    return {
        'device_id': 'macos_abc',
        'buckets': [
            {
                'bucket_id': 'bucket-1',
                'subject_kind': 'document',
                'device_updated_at': NOW.isoformat(),
                'facts': [
                    {
                        'fact_id': fact_id,
                        'statement': 'Ship the parity pack',
                        'confidence': 0.9,
                        'device_updated_at': NOW.isoformat(),
                    }
                ],
            }
        ],
    }


def stub_generation(monkeypatch, generation=3):
    monkeypatch.setattr(
        account_cutover_db,
        'get_account_cutover_record',
        lambda uid, **kwargs: SimpleNamespace(account_generation=generation),
    )


def test_sync_rejects_a_generation_the_account_does_not_hold(client, monkeypatch):
    """The header states a belief; the account record is the fence."""

    stub_generation(monkeypatch, generation=4)
    calls = []
    monkeypatch.setattr(context_buckets_db, 'sync_context_buckets', lambda *a, **k: calls.append(a))

    response = client.post('/v1/context-buckets/sync', json=sync_payload(), headers={'X-Account-Generation': '3'})

    assert response.status_code == 409
    assert calls == []


def test_sync_collects_expired_facts_so_the_sweep_is_not_dead_code(client, monkeypatch):
    stub_generation(monkeypatch)
    swept = []
    monkeypatch.setattr(
        context_buckets_db,
        'sync_context_buckets',
        lambda *a, **k: context_buckets_db.ContextBucketSyncReport(
            buckets_written=1, buckets_skipped_stale=0, facts_written=1, facts_skipped_stale=0
        ),
    )
    monkeypatch.setattr(context_buckets_db, 'collect_expired_context_facts', lambda uid, **k: swept.append(uid))

    response = client.post('/v1/context-buckets/sync', json=sync_payload(), headers={'X-Account-Generation': '3'})

    assert response.status_code == 200
    assert swept == ['u1']


def test_a_failed_sweep_never_fails_the_sync_it_rode_along_with(client, monkeypatch):
    stub_generation(monkeypatch)
    monkeypatch.setattr(
        context_buckets_db,
        'sync_context_buckets',
        lambda *a, **k: context_buckets_db.ContextBucketSyncReport(
            buckets_written=1, buckets_skipped_stale=0, facts_written=1, facts_skipped_stale=0
        ),
    )

    def explode(uid, **kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(context_buckets_db, 'collect_expired_context_facts', explode)

    response = client.post('/v1/context-buckets/sync', json=sync_payload(), headers={'X-Account-Generation': '3'})

    assert response.status_code == 200
    assert response.json()['facts_written'] == 1


def test_purge_needs_no_generation_so_a_device_can_always_retract(client, monkeypatch):
    purged = []
    monkeypatch.setattr(
        context_buckets_db,
        'purge_context_buckets',
        lambda uid, bucket_ids, **k: purged.append((uid, bucket_ids))
        or context_buckets_db.ContextBucketPurgeReport(buckets_deleted=1, facts_deleted=2),
    )

    response = client.post('/v1/context-buckets/purge', json={'bucket_ids': ['bucket-1']})

    assert response.status_code == 200
    assert purged == [('u1', ['bucket-1'])]


def test_the_write_routes_declare_a_rate_limit_policy():
    """These routes cost far more than a plain write, so they must be bounded."""

    from utils.rate_limit_config import RATE_POLICIES

    assert 'context_buckets:sync' in RATE_POLICIES
    assert 'context_buckets:purge' in RATE_POLICIES

# LIFECYCLE: permanent
"""PL-505/461: warm privacy hints cannot authorize work after revocation.

Use the real external-write and deletion-marker authorities with retained jobs
on old Firestore, replacement Postgres and the simulator. Firestore supplies
real server revisions; the strict customer fixture for sim/Postgres receives
explicit synthetic revisions, as it has no server clock. Redis is isolated.
Require OMI_REQUIRE_STORE_BACKENDS=all for complete qualification.
"""

from __future__ import annotations

from contextvars import Context
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

pytest_plugins = ['tests.conftest']

import fakeredis
import pytest

from database import account_deletion_marker as marker
from database import batch_pipeline_privacy as privacy
from database import fsr_read_cache as cache
from database import legal_holds, privacy_check_metrics as metrics, privacy_ttl_cache as ttl_cache
from database.batch_privacy_attempt import token_version
from testing.store_fixtures import StoreHarness, store_backend  # noqa: F401
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.scheduler import Scheduler

pytestmark = pytest.mark.integration
T0 = 1_000_000.0


class UncertifiedPrivacyAllow(AssertionError):
    """The exact stale-ALLOW defect tracked by #25011, never a setup failure."""


@dataclass
class World:
    harness: StoreHarness
    uid: str
    clock: list
    revision: list
    reads: list
    retained: dict

    @property
    def client(self):
        return self.harness.customer.client

    def document(self, collection, key):
        return self.client.collection(collection).document(key)

    def revoke(self):
        """Commit marker + changed certification before the next decision.

        Intentionally lose Redis invalidations for PL-505: a durable token is
        the authorizing fence, while Redis and the TTL remain hints.
        """
        rows = [
            (marker.ACCOUNT_DELETION_COLLECTION, self.uid, {'wipe_status': 'pending_deletion'}),
            (
                privacy.PRIVACY_COLLECTION,
                privacy.privacy_owner_key(self.uid),
                {'generation': 1, 'blocked': False, 'purging': False, 'memo_token': 'b' * 32, 'memo_schema': 1},
            ),
        ]
        if self.harness.name == 'emulator':
            batch = self.client.batch()
            for collection, key, payload in rows:
                batch.set(self.document(collection, key), payload)
            batch.commit()
        else:
            self.client.rows.update({(collection, key): payload for collection, key, payload in rows})
        self.revision[0] += timedelta(seconds=1)
        self.clock[0] += 1

    def assert_retained(self):
        assert self.harness.store.run(lambda tx: tx.get('jobs', 'retained')) == self.retained
        assert self.harness.store.run(lambda tx: tx.get('results', 'retained')) == {}


@pytest.fixture
def world(store_backend, monkeypatch):
    h = store_backend
    uid = h.seed_user('revocation')
    redis = fakeredis.FakeRedis()
    clock = [T0]
    revision = [datetime(2026, 11, 10, tzinfo=timezone.utc)]
    reads = []
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    monkeypatch.setattr(cache, '_redis', lambda: redis)
    monkeypatch.setattr(ttl_cache, '_read_kill_flag', lambda: False)
    monkeypatch.setattr(ttl_cache.DECISIONS, 'clock', lambda: clock[0])
    ttl_cache.reset_for_tests()
    cache._configs.clear()
    privacy.PROCESS_DECISIONS.clear()
    original_get = StrictFirestoreDocument.get

    def strict_get(ref, *args, **kwargs):
        snapshot = original_get(ref, *args, **kwargs)
        if ref._database is h.customer.client:
            snapshot.update_time = revision[0] if snapshot.exists else None
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', strict_get)
    original_read = metrics.read_snapshot

    def observe(family, reference, *args, **kwargs):
        reads.append((family, reference.id))
        return original_read(family, reference, *args, **kwargs)

    monkeypatch.setattr(metrics, 'read_snapshot', observe)
    privacy_ref = h.customer.client.collection(privacy.PRIVACY_COLLECTION).document(privacy.privacy_owner_key(uid))
    certification = {'generation': 0, 'blocked': False, 'purging': False, 'memo_token': 'a' * 32, 'memo_schema': 1}
    if h.name == 'emulator':
        privacy_ref.set(certification)

        def cleanup():
            h.customer.client.collection(marker.ACCOUNT_DELETION_COLLECTION).document(uid).delete()
            # Durable privacy authority must survive deletion. The private
            # emulator owns disposal of this synthetic certification document.
            h.customer.client.collection('users').document(uid).delete()

        h.cleanup_steps.append(cleanup)
    else:
        h.customer.client.rows[(privacy.PRIVACY_COLLECTION, privacy.privacy_owner_key(uid))] = certification
    assert token_version(privacy_ref.get()) is not None, 'the cache controls must have usable certification'
    item = WorkItem('retained', uid, T0, 'gs://synthetic/retained', 30.0, Priority.FRESH, privacy_generation=0)
    assert Scheduler(h.store).enqueue(item, T0)
    saved = deepcopy(h.store.run(lambda tx: tx.get('jobs', 'retained')))
    try:
        yield World(h, uid, clock, revision, reads, saved)
    finally:
        ttl_cache.reset_for_tests()
        privacy.PROCESS_DECISIONS.clear()
        cache._configs.clear()
        redis.close()


def enable(monkeypatch, *names):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(dict.fromkeys(names, 100)))


@pytest.mark.parametrize(
    'mode',
    [
        'live',
        'legal_hold_fence_cache',
        pytest.param(
            'privacy_ttl60',
            marks=pytest.mark.xfail(
                strict=True,
                raises=UncertifiedPrivacyAllow,
                reason='PL-505: uncertified TTL ALLOW survives revoke; https://github.com/BasedHardware/omi/pull/25011',
            ),
        ),
    ],
)
def test_pl505_warm_allow_cannot_authorize_external_work_after_durable_revocation(world, monkeypatch, mode):
    w = world
    enable(monkeypatch, *([] if mode == 'live' else [mode]))
    for warm in range(2):
        w.reads.clear()
        with legal_holds.external_write_fence(w.uid, firestore_client=w.client):
            pass
        if warm and mode != 'live':
            assert ('external', w.uid) not in w.reads, 'exercise an actual warm cache, not a live-read control'
        else:
            assert ('external', w.uid) in w.reads

    w.revoke()
    w.reads.clear()
    external_effects = []
    try:
        with legal_holds.external_write_fence(w.uid, firestore_client=w.client):
            external_effects.append('would-start-provider-write')
    except legal_holds.DestructiveOperationInProgress:
        assert not external_effects
        assert ('external', w.uid) in w.reads, 'changed certification must force the live marker check'
    else:
        # Only this fully reproduced stale-ALLOW shape is an expected gap.
        # Setup, certification, Store, authority and unrelated failures stay red.
        assert mode == 'privacy_ttl60'
        assert w.document(marker.ACCOUNT_DELETION_COLLECTION, w.uid).get().to_dict() == {
            'wipe_status': 'pending_deletion'
        }
        assert ('external', w.uid) not in w.reads
        w.assert_retained()
        raise UncertifiedPrivacyAllow('PL-505: provider boundary reused ALLOW one second after committed revocation')

    assert Scheduler(w.harness.store).pull(T0 + 2) == []
    w.assert_retained()


@pytest.mark.asyncio
@pytest.mark.parametrize('shared_cache', [False, True], ids=['request-only', 'request-and-redis'])
async def test_pl461_inflight_request_observes_another_requests_deletion_before_dispatch(
    world, monkeypatch, shared_cache
):
    w = world
    enable(monkeypatch, 'request_read_dedupe', *(['deletion_marker_cache'] if shared_cache else []))
    scope = cache.request_read_scope()
    await anext(scope)
    try:
        assert marker.get_user_deletion_wipe_status(w.uid, firestore_client=w.client) is None
        assert not marker.account_deletion_blocks_user_work(w.uid, firestore_client=w.client)

        def other_request():
            with cache.writing('deletion_marker_cache', w.uid):
                w.revoke()

        # A genuinely separate Context cannot clear the first request's memo.
        Context().run(other_request)
        w.reads.clear()
        effects = []
        if not marker.account_deletion_blocks_user_work(w.uid, firestore_client=w.client):
            effects.append('would-dispatch')
        assert effects == [], 'the post-auth check must not reuse request-local absence'
        assert marker.get_user_deletion_wipe_status(w.uid, firestore_client=w.client) == 'pending_deletion'
        assert ('deletion_marker', w.uid) in w.reads
        assert Scheduler(w.harness.store).pull(T0 + 2) == []
        w.assert_retained()
    finally:
        await scope.aclose()

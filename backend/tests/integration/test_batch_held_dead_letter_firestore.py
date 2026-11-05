"""Loopback-only worker-fail -> held -> expire -> nightly CAS requeue proof."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from prometheus_client import CollectorRegistry

from database.batch_pipeline_quarantine_recovery import RecoveryStore, dead_held_candidates, held_expired_stock
from tests.integration.test_batch_pipeline_projection_firestore import lane  # noqa: F401
from testing.lifecycle_sim.clock import age_job_row
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.held_dead_letter import HeldDeadLetter
from utils.batch_pipeline.metrics import QueueMetrics

pytestmark = pytest.mark.integration


def test_worker_fail_expire_and_nightly_redrive_keep_audio_and_cold_queue_integrity(lane):
    batch = lane.seed()
    sid = batch.ids[0]
    ref = lane.client.collection(f'{lane.store.namespace}_jobs').document(sid)
    assert lane.queue.fail(sid, batch.leases[sid].token, 10, quarantine=True)
    held = ref.get().to_dict()
    assert held['held_deadline_at'] > 10
    assert held['state'] == 'quarantined'
    age_job_row(ref, 10 * 86400)
    recovery = RecoveryStore(lane.store)
    # Both racers read the same row; exactly one terminal transition commits.
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: recovery.expire_held(sid, 86400), range(2)))
    assert sorted(results) == ['expired', 'held']
    expired = ref.get().to_dict()
    assert expired['audio_uri'] == held['audio_uri']
    assert expired['attempt'] == held['attempt']
    assert 'expires_at' not in expired
    assert dead_held_candidates(lane.client, lane.store.namespace) == [(sid, expired)]
    assert held_expired_stock(lane.client, lane.store.namespace) == 1
    metrics = QueueMetrics(CollectorRegistry())
    assert HeldDeadLetter(lane.store, metrics=metrics).tick(172800) == {'expired': 0, 'requeued': 1}
    before = deepcopy(ref.get().to_dict())
    assert not recovery.requeue_quarantined(sid, 172800)
    assert ref.get().to_dict() == before
    leases = lane.queue.pull(172800)
    assert len(leases) == 1 and leases[0].item.segment_id == sid
    # The new lease fences the old token, then normal ordered publication works.
    result = WorkResult(sid, 'gs://synthetic/requeued-result')
    assert not lane.queue.complete(result, batch.leases[sid].token, 172801)
    assert lane.queue.complete(result, leases[0].token, 172801)
    assert lane.merge.commit_next(batch.binding.owner_id, 172802)['segment_id'] == sid
    assert held_expired_stock(lane.client, lane.store.namespace) == 0


def test_two_forced_requeues_append_once_in_real_firestore(lane):
    batch = lane.seed()
    sid = batch.ids[0]
    assert lane.queue.fail(sid, batch.leases[sid].token, 10, quarantine=True)
    recovery = RecoveryStore(lane.store)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: recovery.requeue_quarantined(sid, 11), range(2)))
    assert sorted(results) == [False, True]
    assert [v.item.segment_id for v in lane.queue.pull(12, 2)] == [sid]

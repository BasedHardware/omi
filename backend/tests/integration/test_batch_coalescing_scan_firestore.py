"""Real emulator contention/handover evidence, isolated synthetic namespace."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Lock
import time

import pytest

from config.batch_pipeline_leader import UPLOAD_COALESCING_SCAN
from database import batch_pipeline_coalescing as rows
from database.batch_pipeline_leader import LeaseLost
from tests.integration.test_batch_upload_coalescing_firestore import runtime, upload_args
from tests.unit.test_batch_pipeline_leader import Clock
from utils.batch_pipeline import upload_coalescing, intake, artifact_policy
from utils.batch_pipeline.leader import LEASE_EVENTS, LeaderLease

pytestmark = pytest.mark.integration


def lease(store, clock, holder):
    return LeaderLease(store, UPLOAD_COALESCING_SCAN, ttl_seconds=6, clock=clock, holder=holder)


@pytest.mark.asyncio
async def test_35_contenders_one_scanner_and_fixed_operation_budget(runtime, monkeypatch, record_property):
    store, *_ = runtime
    # Retire the fixture's heartbeat-only setup scanner, using a synthetic clock.
    clock = Clock(time.time() + 10)
    counts, lock = Counter(), Lock()
    original = store.run

    def counted(body):
        def attempt(tx):
            get, put = tx.get, tx.put
            seen = set()

            def read(table, key):
                if (table, key) not in seen:
                    with lock:
                        counts['read_' + table] += 1
                    seen.add((table, key))
                return get(table, key)

            def write(table, key, value):
                with lock:
                    counts['attempt_write_' + table] += 1
                return put(table, key, value)

            tx.get, tx.put = read, write
            return body(tx)

        return original(attempt)

    monkeypatch.setattr(store, 'run', counted)
    candidates = [lease(store, clock, str(index)) for index in range(35)]
    with ThreadPoolExecutor(max_workers=35) as pool:
        winners = list(pool.map(lambda candidate: candidate.acquire(), candidates))
    assert sum(winners) == 1
    elected = candidates[winners.index(True)]
    query = rows.due

    def due(*args, **kwargs):
        counts['query'] += 1
        return query(*args, **kwargs)

    monkeypatch.setattr(rows, 'due', due)
    counts.clear()  # Separate startup contention from steady-state operations.
    for candidate in candidates:
        await upload_coalescing.drain(store, leader=candidate)
    assert counts['query'] == 1
    assert counts['read_coalesce_quota'] == 2
    assert counts['attempt_write_coalesce_quota'] == 1
    assert counts['read_leases'] == 37  # 35 elections + two token fences.
    assert counts['attempt_write_leases'] == 0  # Still inside half-TTL.
    record_property('steady_attempt_operations', json.dumps(dict(counts), sort_keys=True))
    record_property('contenders', 35)
    record_property('successful_empty_scans', 1)
    # Renewal is the steady-state write that must not move the storm to leases.
    errors = LEASE_EVENTS.labels(role=UPLOAD_COALESCING_SCAN, outcome='error')._value.get()
    clock.now += 4
    counts.clear()
    with ThreadPoolExecutor(max_workers=35) as pool:
        renewed = list(pool.map(lambda candidate: candidate.acquire(), candidates))
    assert sum(renewed) == 1 and candidates[renewed.index(True)] is elected
    assert LEASE_EVENTS.labels(role=UPLOAD_COALESCING_SCAN, outcome='error')._value.get() == errors
    assert store.run(lambda tx: tx.get('leases', UPLOAD_COALESCING_SCAN))['expires_at'] == clock.now + 6
    record_property('renewal_with_35_contenders', 'PASS')
    # Death/takeover: only the replacement can advance the cursor or heartbeat.
    stale = elected.guard()
    clock.now += 7
    replacement = next(candidate for candidate in candidates if candidate is not elected)
    assert replacement.acquire()
    for operation in (
        lambda: rows.note_scan(store, producer_enabled=True, scan=stale),
        lambda: rows.advance_scan(store, 0, {'id': 'stale', 'scan_at': 1}, scan=stale),
        lambda: rows.claim(store, 'stale', clock.now, producer_enabled=True, scan=stale),
    ):
        with pytest.raises(LeaseLost):
            operation()
    await upload_coalescing.drain(store, leader=replacement)
    record_property('takeover_and_stale_writer_fencing', 'PASS')


@pytest.mark.asyncio
@pytest.mark.parametrize('off', [False, True])
async def test_elected_full_path_drains_originals_and_off_queue(runtime, tmp_path, monkeypatch, off):
    store, artifacts, objects, uid, cid = runtime
    first, _ = upload_args(tmp_path, uid, cid, 0)
    second, _ = upload_args(tmp_path, uid, cid, 1)
    responses = [await intake.accept_upload(**args) for args in (first, second)]
    assert [response.status_code for response in responses] == [202, 202]
    rows.release_for_open(store, uid, 'bp_' + first['job_id'], time.time())
    if off:
        monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', 'false')
    monkeypatch.setattr(artifact_policy, 'artifacts_for', lambda _: artifacts)
    clock = Clock(time.time() + 10)
    leader = lease(store, clock, 'new-process')
    await upload_coalescing.drain(store, leader=leader)
    quota = store.run(lambda tx: tx.get('coalesce_quota', 'global'))
    assert quota['groups'] == 0
    jobs = list(store.client.collection(store.namespace + '_jobs').stream())
    assert len(jobs) == (2 if off else 1)
    assert sum(job.to_dict()['duration_seconds'] for job in jobs) == 2
    assert objects.downloads >= 2
    await upload_coalescing.drain(store, leader=leader)
    assert len(list(store.client.collection(store.namespace + '_jobs').stream())) == len(jobs)


@pytest.mark.asyncio
async def test_slow_claimed_audio_finishes_but_expired_scanner_cannot_publish_health(runtime, tmp_path, monkeypatch):
    store, artifacts, objects, uid, cid = runtime
    args, _ = upload_args(tmp_path, uid, cid, 0)
    assert (await intake.accept_upload(**args)).status_code == 202
    rows.release_for_open(store, uid, 'bp_' + args['job_id'], time.time())
    monkeypatch.setattr(artifact_policy, 'artifacts_for', lambda _: artifacts)
    clock = Clock(time.time() + 10)
    old, replacement = lease(store, clock, 'old'), lease(store, clock, 'replacement')
    heartbeat = store.run(lambda tx: tx.get('coalesce_quota', 'global'))['last_scan_at']
    fetch = artifacts.fetch_audio

    def slow_fetch(item):
        clock.now += 7
        assert replacement.acquire()
        return fetch(item)

    monkeypatch.setattr(artifacts, 'fetch_audio', slow_fetch)
    await upload_coalescing.drain(store, leader=old)
    # Already claimed source converts under its independent custody token.
    quota = store.run(lambda tx: tx.get('coalesce_quota', 'global'))
    assert quota['groups'] == 0 and quota['last_scan_at'] == heartbeat
    assert len(list(store.client.collection(store.namespace + '_jobs').stream())) == 1
    # Replacement resumes discovery without duplicating converted audio.
    await upload_coalescing.drain(store, leader=replacement)
    assert store.run(lambda tx: tx.get('coalesce_quota', 'global'))['last_scan_at'] == clock.now
    assert len(list(store.client.collection(store.namespace + '_jobs').stream())) == 1

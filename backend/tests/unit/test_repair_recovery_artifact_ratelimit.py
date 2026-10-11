"""Hermetic GCS object mutation quotas at the repair artifact boundary."""

from concurrent.futures import ThreadPoolExecutor
import json
import threading

import pytest
from google.api_core.exceptions import ServiceUnavailable, TooManyRequests

from scripts import repair_recovery_dead_letter_untitled as repair
from tests.unit.test_repair_recovery_dead_letter_untitled import (
    FakeBlob,
    FakeStorage,
    ROW_PATH,
    TEXT,
    UID,
    artifact,
    artifact_cli,
    assert_durable_before_updates,
    durable_objects,
    durable_run,
    evaluate,
    setup,
)


def assert_paced(storage):
    assert storage.rate_rejections == 0
    assert all(b - a >= 2 for times in storage.mutation_times.values() for a, b in zip(times, times[1:]))


def test_rate_limited_gcs_bootstrap_reconcile_and_snapshots_keep_lease(tmp_path):
    _, runtime, log = setup(tmp_path)
    storage = FakeStorage(enforce_rate_limit=True)
    durable_run(log, storage, storage.server_clock)
    repair.reconcile_pending(runtime, log)
    log.mirror()
    log.artifacts.lease.renew(require_ready=True)
    assert not log.artifacts.lease.lost
    assert_paced(storage)


def test_fake_rejects_more_than_one_mutation_per_second():
    storage = FakeStorage()
    blob = storage.bucket('test-bucket').blob('one-object')
    blob.upload_from_string(b'one', if_generation_match=0)
    storage.server_clock.advance(0.5)
    with pytest.raises(TooManyRequests):
        blob.upload_from_string(b'two', if_generation_match=blob.generation)
    storage.server_clock.advance(0.5)
    blob.upload_from_string(b'two', if_generation_match=blob.generation)


def test_concurrent_checks_coalesce_one_half_ttl_renewal(tmp_path):
    _, _, log = setup(tmp_path)
    storage = FakeStorage()
    mirror = durable_run(log, storage, storage.server_clock)
    key = ('test-bucket', mirror.lease.blob.name)
    original_generation = mirror.lease.generation
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: mirror.lease.renew(require_ready=True), range(40)))
    assert mirror.lease.generation == original_generation
    assert len(storage.mutation_times[key]) == 1
    storage.server_clock.advance(61)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: mirror.lease.renew(require_ready=True), range(40)))
    assert len(storage.mutation_times[key]) == 2
    assert mirror.lease.generation != original_generation
    assert_paced(storage)


@pytest.mark.parametrize('apply', [False, True])
def test_five_minute_heartbeat_reconcile_snapshot_run_is_paced(tmp_path, monkeypatch, capsys, apply):
    client, runtime, log = setup(tmp_path, apply=apply)
    storage = FakeStorage()
    mirror = durable_run(log, storage, storage.server_clock)
    observed = assert_durable_before_updates(monkeypatch, client, storage)
    completed = threading.Event()
    ticks = []
    renew = mirror.lease.renew

    class ControlledWait(threading.Event):
        def __init__(self):
            super().__init__()
            self.step = threading.Event()

        def wait(self, timeout=None):
            self.step.wait(timeout=0.05)
            self.step.clear()
            return self.is_set()

    mirror.lease.stop = ControlledWait()

    def heartbeat(**kwargs):
        result = renew(**kwargs)
        if threading.current_thread().name == 'repair-artifact-lease':
            ticks.append(mirror.lease.generation)
            completed.set()
        return result

    monkeypatch.setattr(mirror.lease, 'renew', heartbeat)
    repair._stage_last.clear()
    repair._stage_counts.clear()
    started = storage.server_clock()
    mirror.lease.start()
    try:
        evaluate(runtime, log)
        for step in range(30):
            storage.server_clock.advance(10)
            if step % 4 == 0:
                completed.clear()
                mirror.lease.stop.step.set()
                assert completed.wait(timeout=2)
            with repair.observed_stage('reconcile'):
                repair.reconcile_pending(runtime, log)
            log.save('summary.json', {'processed': step})
            with repair.observed_stage('page'):
                log.mirror()
            mirror.lease.renew(require_ready=True)
        assert storage.server_clock() - started >= 300
        assert ticks and len(set(ticks)) >= 2
        assert not mirror.lease.lost and not mirror.lease.failed
        assert mirror.lease.expires > storage.server_clock()
        assert len(storage.mutation_times[('test-bucket', mirror.lease.blob.name)]) <= 7
        assert len(observed) == (1 if apply else 0)
        assert client.rows[ROW_PATH]['discarded'] is apply
        assert len(durable_objects(storage, 'intents')) == 1
    finally:
        mirror.lease.close()
    assert_paced(storage)
    logs = capsys.readouterr().err
    events = [json.loads(line) for line in logs.splitlines()]
    assert any(event.get('lease_writes', 0) > 0 for event in events)
    assert all(event.get('max_object_write_rate', 0) <= 0.5 for event in events)
    assert UID not in logs and TEXT not in logs and mirror.lease.owner not in logs


@pytest.mark.parametrize('error_type', [TooManyRequests, ServiceUnavailable])
@pytest.mark.parametrize('object_kind', ['lease', 'probe', 'manifest'])
def test_rejected_write_backs_off_then_recovers(tmp_path, monkeypatch, error_type, object_kind):
    _, _, log = setup(tmp_path)
    storage = FakeStorage()
    mirror = durable_run(log, storage, storage.server_clock)
    storage.server_clock.advance(61)
    upload = FakeBlob.upload_from_string
    attempts = []

    def reject_once(blob, *args, **kwargs):
        target = (
            blob.name.endswith('/lease.json')
            if object_kind == 'lease'
            else '/clock/' in blob.name if object_kind == 'probe' else blob.name.endswith('/manifest.json')
        )
        if target:
            attempts.append(storage.server_clock())
            if len(attempts) == 1:
                raise error_type(UID + TEXT)
        return upload(blob, *args, **kwargs)

    monkeypatch.setattr(FakeBlob, 'upload_from_string', reject_once)
    started = storage.server_clock()
    if object_kind == 'manifest':
        log.save('summary.json', {'processed': 1})
        log.mirror()
    else:
        mirror.lease.renew(require_ready=True)
    assert len(attempts) >= 2 and attempts[1] - attempts[0] >= 2.5
    assert storage.server_clock() - started < repair.ArtifactIO.WRITE_BUDGET
    assert not mirror.lease.lost and not mirror.lease.failed
    assert_paced(storage)


@pytest.mark.parametrize('error_type', [TooManyRequests, ServiceUnavailable])
def test_rejected_lease_write_reconciles_actual_takeover_before_retry(tmp_path, monkeypatch, error_type):
    client, runtime, log = setup(tmp_path, apply=True)
    storage = FakeStorage()
    mirror = durable_run(log, storage, storage.server_clock)
    storage.server_clock.advance(61)
    upload = FakeBlob.upload_from_string
    attempts = []

    def takeover_then_lose_response(blob, data, **kwargs):
        if blob.name.endswith('/lease.json'):
            attempts.append(storage.server_clock())
            changed = json.loads(data)
            changed['owner'] = 'different-owner'
            upload(blob, json.dumps(changed), **kwargs)
            raise error_type(UID + TEXT)
        return upload(blob, data, **kwargs)

    monkeypatch.setattr(FakeBlob, 'upload_from_string', takeover_then_lose_response)
    with pytest.raises(repair.LeaseLost):
        evaluate(runtime, log)
    assert len(attempts) == 1 and mirror.lease.lost
    assert not client.transactions and not client.rows[ROW_PATH]['discarded']
    assert not durable_objects(storage, 'intents')
    assert_paced(storage)


def test_persistent_429_stops_as_io_failure_without_claiming_takeover(tmp_path, monkeypatch):
    client, runtime, log = setup(tmp_path, apply=True)
    storage = FakeStorage()
    mirror = durable_run(log, storage, storage.server_clock)
    storage.server_clock.advance(61)
    upload = FakeBlob.upload_from_string

    def unavailable(blob, *args, **kwargs):
        if blob.name.endswith('/lease.json'):
            raise TooManyRequests('unavailable')
        return upload(blob, *args, **kwargs)

    monkeypatch.setattr(FakeBlob, 'upload_from_string', unavailable)
    started = storage.server_clock()
    with pytest.raises(repair.ArtifactError) as caught:
        evaluate(runtime, log)
    assert not isinstance(caught.value, repair.LeaseLost)
    assert mirror.lease.failed and not mirror.lease.lost
    assert storage.server_clock() - started <= repair.ArtifactIO.WRITE_BUDGET
    assert not client.transactions and not durable_objects(storage, 'intents')


def test_generation_read_detects_takeover_between_coalesced_renewals(tmp_path):
    storage = FakeStorage()
    mirror = artifact(storage)
    mirror.create()
    generation = mirror.lease.generation
    storage.server_clock.advance(2)
    blob = storage.bucket('test-bucket').blob(mirror.lease.blob.name)
    blob.upload_from_string(json.dumps({'owner': 'different-owner'}), if_generation_match=generation)
    with pytest.raises(repair.LeaseLost):
        mirror.lease.renew(require_ready=True)
    assert mirror.lease.lost


def test_same_owner_unexpected_generation_stops_as_unresolved_io(tmp_path):
    storage = FakeStorage()
    mirror = artifact(storage)
    mirror.create()
    key = ('test-bucket', mirror.lease.blob.name)
    generation, data = storage.objects[key]
    storage.server_clock.advance(2)
    blob = storage.bucket('test-bucket').blob(mirror.lease.blob.name)
    blob.upload_from_string(data, if_generation_match=generation)
    with pytest.raises(repair.ArtifactError) as caught:
        mirror.lease.renew()
    assert not isinstance(caught.value, repair.LeaseLost)
    assert mirror.lease.failed and not mirror.lease.lost


def test_object_pacing_waits_after_slow_rpc_completion(tmp_path, monkeypatch):
    storage = FakeStorage()
    mirror = artifact(storage)
    mirror.create()
    upload = FakeBlob.upload_from_string

    def slow_upload(blob, *args, **kwargs):
        storage.server_clock.advance(0.75)
        return upload(blob, *args, **kwargs)

    monkeypatch.setattr(FakeBlob, 'upload_from_string', slow_upload)
    mirror.publish({'one': 1})
    mirror.publish({'two': 2})
    assert_paced(storage)
    assert mirror.io.max_write_rate <= 0.5


def test_probe_retry_reads_fresh_server_time_and_detects_actual_expiry(tmp_path, monkeypatch):
    storage = FakeStorage()
    mirror = artifact(storage)
    mirror.create()
    storage.server_clock.advance(repair.RunLease.TTL - 10)
    upload = FakeBlob.upload_from_string
    rejected = []

    def delayed_probe(blob, *args, **kwargs):
        if '/clock/' in blob.name and not rejected:
            rejected.append(True)
            # A rejection itself supplies no server timestamp; sample GCS time
            # after recovery rather than assuming the old lease is still valid.
            storage.server_clock.advance(11)
            raise TooManyRequests('delayed clock probe')
        return upload(blob, *args, **kwargs)

    monkeypatch.setattr(FakeBlob, 'upload_from_string', delayed_probe)
    with pytest.raises(repair.LeaseLost):
        mirror.lease.renew()
    assert mirror.lease.lost and not mirror.lease.failed


def test_error_exit_reports_final_write_counts_per_stage_privately(tmp_path, monkeypatch, capsys):
    client, _, _ = setup(tmp_path)
    storage = FakeStorage()
    repair._stage_last.clear()
    repair._stage_counts.clear()
    artifact_cli(
        monkeypatch,
        storage,
        client,
        ['--run-dir=' + str(tmp_path / 'cli'), '--artifact-uri=gs://test-bucket/repair/run'],
    )

    def fail(*args, **kwargs):
        raise ValueError(UID + TEXT)

    monkeypatch.setattr(repair, 'run', fail)
    with pytest.raises(ValueError):
        repair.main()
    logs = capsys.readouterr().err
    events = [json.loads(line) for line in logs.splitlines()]
    shutdown = next(event for event in events if event['stage'] == 'shutdown' and event['event'] == 'end')
    counts = {
        event['stage']: event['lease_writes']
        for event in events
        if event['event'] == 'end' and event.get('check') == 'write'
    }
    assert counts == {'artifact_create': 1, 'lease_release': 1}
    assert shutdown['lease_writes'] == sum(counts.values())
    assert shutdown['object_writes'] >= shutdown['lease_writes']
    assert shutdown['max_object_write_rate'] <= 0.5
    assert UID not in logs and TEXT not in logs and 'repair/run' not in logs
    assert_paced(storage)

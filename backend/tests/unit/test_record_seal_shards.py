"""Disjoint proof ownership, independent encrypted checkpoints and a CPU-only ramp."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path

import pytest

from config import record_seal_repair as config
from utils.batch_pipeline import record_seal_cluster_repair as cluster, record_seal_backlog as backlog
from utils.batch_pipeline.record_seal_budget import SweepBudget
from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor
from tests.unit.test_record_seal_cluster_repair import OrderedJobsClient, pending_job, CursorClient
from tests.unit.test_record_seal_cluster_repair_deploy import documents
from tests.unit.test_record_seal_sweeper_deploy import render, CHART


@pytest.mark.parametrize('count', [1, 5])
@pytest.mark.parametrize('fresh', [False, True])
def test_every_canonical_row_belongs_to_exactly_one_shard_in_each_lane(count, fresh):
    stamp = datetime.now(timezone.utc).timestamp()
    docs = [pending_job(i, stamp - (90 if fresh else 8000) - i) for i in range(350)]
    all_paths = set()
    for index in range(count):
        client = OrderedJobsClient(docs)
        after, paths = None, []
        while True:
            rows, saturated, after = cluster.discover_jobs(
                client,
                budget=SweepBudget(10),
                fresh=fresh,
                newest=not fresh,
                shard=index,
                shards=count,
                after=after,
                max_rows=128,
            )
            paths.extend(p for p, _ in rows)
            if not saturated:
                break
        assert not all_paths.intersection(paths)
        assert [int(p.rsplit('-', 1)[-1]) for p in paths] == sorted(int(p.rsplit('-', 1)[-1]) for p in paths)
        all_paths.update(paths)
    assert all_paths == {f'users/synthetic/conversations/capture-{i}' for i in range(350)}


def test_index_and_count_are_fail_closed_before_cloud_io(tmp_path):
    from scripts.record_seal_repair_job import partition_arguments

    path = tmp_path / 'index'
    for count, index in [(0, 0), (9, 0), (5, 5), (5, -1)]:
        path.write_text(str(index))
        with pytest.raises(ValueError):
            partition_arguments(['--shards', str(count), '--shard-index-file', str(path)])
    path.write_text('2')
    assert partition_arguments(['--shards', '5', '--shard-index-file', str(path)]) == (2, 5)
    assert partition_arguments([]) == (0, 1)
    with pytest.raises(ValueError):
        partition_arguments(['--shards', '5'])
    with pytest.raises(ValueError):
        cluster.run(shard=5, shards=5)


def test_shards_use_separate_frontiers_without_overwriting_the_single_pod_cursor():
    refs = {}

    def document(name):
        if name not in refs:
            refs[name] = CursorClient()
        return refs[name]

    client = SimpleNamespace(collection=lambda _: SimpleNamespace(document=document))
    cursors = [RepairCursor(client, b'x' * 32, jobs=True, backlog=True, partition=(i, 5)) for i in range(5)]
    single = RepairCursor(client, b'x' * 32, jobs=True, backlog=True)
    for i, cursor in enumerate(cursors):
        value = {
            'path': f'batch_pipeline_prod_jobs/synthetic-{i}',
            'enqueued_at': i,
            'horizon': datetime.now(timezone.utc),
        }
        cursor.write(value, SweepBudget(10))
        assert cursor.read(SweepBudget(10)) == value
    assert len(refs) == 6
    assert single.read(SweepBudget(10)) is None
    assert len({cursor.read(SweepBudget(10))['path'] for cursor in cursors}) == 5


def test_five_shards_are_cpu_only_spread_and_do_not_change_gpu_deployments():
    before = documents('--set', 'recordSealRepair.shards=1')
    after = documents(
        '--set-string',
        'recordSealRepair.imageRepository=synthetic/backend',
        '--set-string',
        'recordSealRepair.imageDigest=sha256:' + 'b' * 64,
    )
    assert [key for key in before if before[key] != after[key]] == [('CronJob', 'record-seal-repair')]
    job = after['CronJob', 'record-seal-repair']['spec']['jobTemplate']['spec']
    assert job['completionMode'] == 'Indexed' and job['completions'] == job['parallelism'] == 5
    assert job['backoffLimit'] == 5
    assert job['backoffLimitPerIndex'] == 0 and job['maxFailedIndexes'] == 5
    assert before['CronJob', 'record-seal-repair']['spec']['jobTemplate']['spec']['backoffLimit'] == 0
    pod = job['template']['spec']
    assert 'tolerations' not in pod
    affinity = pod['affinity']
    assert affinity['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms'][0][
        'matchExpressions'
    ][0]['values'] == ['api-pool']
    assert (
        affinity['podAntiAffinity']['requiredDuringSchedulingIgnoredDuringExecution'][0]['topologyKey']
        == 'kubernetes.io/hostname'
    )
    container = pod['containers'][0]
    assert container['resources'] == {
        'requests': {'cpu': '3', 'memory': '4Gi'},
        'limits': {'cpu': '4', 'memory': '8Gi'},
    }
    assert container['args'] == ['--shards', '5', '--shard-index-file', '/etc/repair-partition/index']
    partition = next(volume for volume in pod['volumes'] if volume['name'] == 'partition')
    assert (
        partition['downwardAPI']['items'][0]['fieldRef']['fieldPath']
        == "metadata.annotations['batch.kubernetes.io/job-completion-index']"
    )
    assert container['image'] == 'synthetic/backend@sha256:' + 'b' * 64
    worker = after['Deployment', 'record-seal-worker']['spec']['template']['spec']['containers'][0]
    assert next(e['value'] for e in worker['env'] if e['name'] == 'RECORD_SEAL_REPAIR_ENABLED') == 'false'


@pytest.mark.parametrize(
    'argument', ['recordSealRepair.shards=-1', 'recordSealRepair.shards=0', 'recordSealRepair.shards=9']
)
def test_parallel_chart_rejects_invalid_partition_and_missing_job_discovery(argument):
    assert render('--set', argument).returncode != 0


def test_duplicate_index_pods_cannot_run_the_same_proofs_and_old_release_is_fenced():
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.batch_pipeline.record_seal_run_lease import RepairRunLease

    client = StrictFirestore({})
    first, duplicate = RepairRunLease(client, 0, 5), RepairRunLease(client, 0, 5)
    other = RepairRunLease(client, 1, 5)
    assert first.acquire(100)
    assert not duplicate.acquire(101)
    assert other.acquire(101)
    assert duplicate.acquire(1900)
    first.release()  # A late old owner cannot clear its successor's claim.
    assert not RepairRunLease(client, 0, 5).acquire(1901)
    duplicate.release()
    assert RepairRunLease(client, 0, 5).acquire(1901)


def test_lease_released_after_coordinator_unwinds(monkeypatch):
    from database import _client
    from utils.batch_pipeline import record_seal_sweeper, record_seal_run_lease

    lease = Mock()
    lease.acquire.return_value = True
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: {})
    monkeypatch.setattr(config, 'settings', lambda: (8, 270, 1500, 'apply'))
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: object())
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', lambda: {})
    monkeypatch.setattr(record_seal_sweeper, 'require_fresh_proof', lambda _: None)
    monkeypatch.setattr(record_seal_run_lease, 'RepairRunLease', lambda *a: lease)
    monkeypatch.setattr(cluster, '_run', Mock(side_effect=RuntimeError('synthetic interruption')))
    with pytest.raises(RuntimeError):
        cluster.run(shard=0, shards=5)
    lease.release.assert_called_once_with()
    lease.reset_mock()
    lease.acquire.return_value = False
    assert cluster.run(shard=0, shards=5)['outcome'] == 'overlap_refused'
    lease.release.assert_not_called()


def test_legacy_conversation_and_job_discovery_have_identical_partition_ownership():
    stamp = datetime.now(timezone.utc)
    docs = [pending_job(i, stamp.timestamp() - 8000) for i in range(100)]
    all_paths = set()
    for shard in range(5):
        client = CursorClient(
            [
                SimpleNamespace(
                    reference=SimpleNamespace(path=f'users/synthetic/conversations/capture-{i}'),
                    to_dict=lambda: {'finished_at': stamp},
                )
                for i in range(100)
            ]
        )
        rows, _, _ = cluster.discover(client, budget=SweepBudget(10), shard=shard, shards=5)
        jobs, _, _ = cluster.discover_jobs(
            OrderedJobsClient(docs), budget=SweepBudget(10), newest=True, shard=shard, shards=5, max_rows=128
        )
        paths = {p for p, _ in rows}
        assert paths == {p for p, _ in jobs}
        assert not paths.intersection(all_paths)
        all_paths.update(paths)
    assert len(all_paths) == 100


@pytest.mark.parametrize('count', [1, 2, 5])
@pytest.mark.parametrize(
    'patch',
    [
        {'owner_id': None},
        {'owner_id': 42},
        {'owner_id': 'bad/path'},
        {'conversation_id': None},
        {'conversation_id': []},
        {'conversation_id': 'bad/path'},
        {'record_content_id': None},
        {'owner_id': 'wrong-canonical-owner'},
    ],
)
def test_malformed_pending_has_exactly_one_counted_owner_and_no_user_path(count, patch):
    stamp = datetime.now(timezone.utc).timestamp()
    doc = pending_job(0, stamp - 8000, **patch)
    events = []
    for shard in range(count):
        rows, _, _ = cluster.discover_jobs(
            OrderedJobsClient([doc]),
            budget=SweepBudget(10),
            newest=True,
            shard=shard,
            shards=count,
            progress=events.append,
        )
        assert rows == []
    refusals = [e for e in events if e.get('outcome') == 'malformed_pending']
    assert sum(e['count'] for e in refusals) == 1
    assert all(set(e) == {'event', 'outcome', 'count'} for e in refusals)


def test_process_deadline_counts_cold_start_and_reserves_cleanup(monkeypatch):
    from scripts.record_seal_repair_job import process_deadline

    minute = 30000000
    now = minute * 60 + 600  # Ten minutes spent waiting for node/image.
    assert process_deadline(100, f'record-seal-repair-{minute}-2', now, 105) == 1125
    assert process_deadline(100, 'local-fixture', now, 105) == 1660
    monkeypatch.setenv('KUBERNETES_SERVICE_HOST', 'synthetic')
    with pytest.raises(ValueError):
        process_deadline(100, 'unrecognized', now, 105)


@pytest.mark.parametrize(
    'hostname',
    [
        pytest.param('record-seal-repair-29912640-0', id='indexed-hostname-0'),
        pytest.param('record-seal-repair-29912640-2', id='indexed-hostname-2'),
        pytest.param('record-seal-repair-29912640-4', id='indexed-hostname-4'),
        pytest.param('record-seal-repair-29912640-abcde', id='ordinary-hostname'),
        pytest.param('record-seal-repair-29912640-2-abcde', id='indexed-metadata-name-not-hostname'),
    ],
)
def test_scheduled_deadline_accepts_literal_indexed_and_ordinary_hostnames(monkeypatch, hostname):
    from scripts.record_seal_repair_job import process_deadline

    monkeypatch.setenv('KUBERNETES_SERVICE_HOST', 'synthetic')
    now = 29912640 * 60 + 600
    assert process_deadline(100, hostname, now, 105) == 1125


def test_indexed_hostname_cannot_supply_a_future_scheduled_clock(monkeypatch):
    from scripts.record_seal_repair_job import process_deadline

    monkeypatch.setenv('KUBERNETES_SERVICE_HOST', 'synthetic')
    with pytest.raises(ValueError, match='invalid scheduled repair clock'):
        process_deadline(100, 'record-seal-repair-29912640-2', 29912640 * 60 - 61, 105)


def test_projection_callback_is_inside_lease_and_not_run_for_duplicate(monkeypatch):
    from database import _client
    from utils.batch_pipeline import record_seal_sweeper, record_seal_run_lease

    lease = Mock()
    lease.acquire.return_value = False
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: {})
    monkeypatch.setattr(config, 'settings', lambda: (8, 270, 1500, 'apply'))
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: object())
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', lambda: {})
    monkeypatch.setattr(record_seal_sweeper, 'require_fresh_proof', lambda _: None)
    monkeypatch.setattr(record_seal_run_lease, 'RepairRunLease', lambda *a: lease)
    before = Mock()
    cluster.run(shard=0, shards=5, before=before)
    before.assert_not_called()


def test_nested_io_budget_cannot_extend_outer_process_deadline(monkeypatch):
    from utils.batch_pipeline import record_seal_budget as budgets

    timer = [0.0, 0.0]
    now = [0.0]
    monkeypatch.setattr(budgets.signal, 'signal', lambda *a: None)
    monkeypatch.setattr(budgets.signal, 'getitimer', lambda *a: tuple(timer))
    monkeypatch.setattr(
        budgets.signal,
        'setitimer',
        lambda kind, seconds, interval=0: timer.__setitem__(slice(None), [seconds, interval]),
    )
    with budgets.SweepBudget(10, clock=lambda: now[0]).interrupt_io():
        assert timer[0] == 10
        with budgets.SweepBudget(60, clock=lambda: now[0]).interrupt_io():
            assert timer[0] == 10
            now[0] = 3
        assert timer[0] == 7
    assert timer[0] == 0


@pytest.mark.parametrize('count', [1, 2, 5])
def test_malformed_refusals_emit_once_per_run_across_repeated_discovery_legs(monkeypatch, count):
    stamp = datetime.now(timezone.utc).timestamp()
    docs = [pending_job(0, stamp - 100, owner_id=None), pending_job(1, stamp - 100, record_content_id=None)]
    events = []
    monkeypatch.setattr(config, 'enabled', lambda: True)
    monkeypatch.setattr(config, 'settings', lambda: (8, 270, 1500, 'plan'))

    def run_legs(*, progress, **kwargs):
        client = OrderedJobsClient(docs)
        lane = cluster.FreshLane(client, progress=progress, **kwargs)
        refill = backlog.BacklogLane(
            client, SimpleNamespace(read=lambda _: None), mode='plan', progress=progress, **kwargs
        )
        for _ in range(4):
            cluster.discover_jobs(client, budget=SweepBudget(10), progress=progress, **kwargs)
            assert lane(set()) == []
            assert refill(set()) == []
        assert not events_for_run  # Deferred until the run's single summary.
        return {'outcome': 'ok'}

    monkeypatch.setattr(cluster, '_run', run_legs)
    for shard in range(count):
        events_for_run = []
        cluster.run(shard=shard, shards=count, progress=events_for_run.append)
        refusals = [e for e in events_for_run if e.get('outcome') == 'malformed_pending']
        assert len(refusals) <= 1
        events.extend(refusals)
    assert sum(e['count'] for e in events) == 2
    assert all(set(e) == {'event', 'outcome', 'count'} for e in events)


def test_ledger_misses_are_aggregated_without_changing_seal_disposition():
    import io
    import json
    from tests.unit.test_record_seal_cluster_repair import FakeProcess

    clock = [0.0]

    def launch(*args):
        child = FakeProcess(clock, 0, 'sealed')
        child.stdout = io.BytesIO(json.dumps({'disposition': 'sealed', 'ledger_misses': 1}).encode())
        return child

    report = cluster.coordinate(
        [('synthetic', 100)],
        workers=1,
        row_seconds=270,
        run_seconds=10,
        mode='apply',
        launch=launch,
        clock=lambda: clock[0],
        pause=lambda t: clock.__setitem__(0, clock[0] + t),
    )
    assert report['dispositions'] == {'sealed': 1}
    assert report['ledger_misses'] == 1

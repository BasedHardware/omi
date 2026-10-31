"""Hermetic cluster repair composition and bounded child lifecycle."""

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import record_seal_repair as config
from utils.batch_pipeline import record_seal_nojob as nojob, record_seal_cluster_repair as cluster
from utils.batch_pipeline import record_producer_proof as producer
from utils.batch_pipeline.record_seal_budget import SweepBudget
from utils.batch_pipeline.record_seal_reasons import TAIL_GAP_BUCKETS
from tests.unit.test_record_seal_nojob import source, SCOPE, SERVER, PATH, JOB_PATH
from tests.unit.test_record_producer_proof import inventory


@pytest.fixture
def proof():
    def build():
        return producer.parse_pusher_pod_proof(
            json.dumps(inventory([])).encode(), datetime.fromtimestamp(999, timezone.utc).isoformat()
        )

    return build


def settle(source, proof, mode='apply'):
    store, _, artifacts = source
    return cluster.repair_one(
        store, object(), artifacts, SCOPE[0], flags=SERVER, inventory=proof, budget=SweepBudget(240), mode=mode
    )


def test_repairs_no_job_then_pending_with_canonical_transactions(source, proof):
    assert settle(source, proof) == 'sealed_registered'
    client = source[1]
    assert client.rows[PATH]['record_audio_closed']
    assert client.rows[JOB_PATH]['state'] == 'record_pending'
    client.rows[PATH]['record_audio_closed'] = False
    assert settle(source, proof) == 'sealed'
    assert client.rows[PATH]['record_audio_closed']
    assert client.rows[PATH]['content'] == 'untouched'


def test_plan_mode_performs_no_writes(source, proof):
    assert settle(source, proof, mode='plan') == 'eligible'
    assert all(not tx.updates and not tx.sets for tx in source[1].transactions)


@pytest.mark.parametrize('change', [{'private_cloud_sync_enabled': False}, {'deleted': True}, {'discarded': True}])
def test_privacy_refused_never_applies(source, proof, change):
    source[1].rows[PATH].update(change)
    assert settle(source, proof) == 'privacy_refused'
    assert all(not tx.updates and not tx.sets for tx in source[1].transactions)


def test_current_user_privacy_refusal_is_respected(source, proof):
    source[1].rows[('users', 'synthetic')]['private_cloud_sync_enabled'] = False
    assert settle(source, proof) == 'privacy_refused'
    assert all(not tx.updates and not tx.sets for tx in source[1].transactions)


def test_each_row_gets_its_own_inventory(source, proof):
    read = Mock(side_effect=proof)
    assert settle(source, read, mode='plan') == 'eligible'
    assert settle(source, read, mode='plan') == 'eligible'
    assert read.call_count == 2


def test_stale_proof_skips_before_any_read(source, proof):
    value = proof()
    value['captured_at'] = 699
    with pytest.raises(ValueError):
        settle(source, lambda: value)
    assert not source[1].transactions


def test_partial_pod_list_cannot_prove_absence(source):
    def partial():
        raw = inventory([])
        raw['metadata']['continue'] = 'private-continuation'
        return producer.parse_pusher_pod_proof(
            json.dumps(raw).encode(), datetime.fromtimestamp(999, timezone.utc).isoformat()
        )

    with pytest.raises(ValueError):
        settle(source, partial)
    assert not source[1].transactions


def test_proof_expiring_during_tail_read_never_applies(source, proof, monkeypatch):
    from utils.batch_pipeline import record_seal_repair

    def tail(*_, **kwargs):
        monkeypatch.setattr(producer.time, 'time', lambda: 1400)
        return 'opaque-proof'

    monkeypatch.setattr(nojob, 'retained_tail_proof', tail)
    monkeypatch.setattr(record_seal_repair, 'retained_tail_proof', tail)
    with pytest.raises(ValueError):
        settle(source, proof)
    assert all(not tx.updates and not tx.sets for tx in source[1].transactions)


def test_unknown_disposition_grants_no_apply_authority(source, proof, monkeypatch):
    apply = Mock()
    monkeypatch.setattr(
        nojob, 'plan_backfill', lambda *a, **k: {'entries': [{'disposition': 'private@example.invalid'}]}
    )
    monkeypatch.setattr(nojob, 'apply_backfill', apply)
    assert settle(source, proof) == 'unknown'
    apply.assert_not_called()


def test_kill_switch_off_does_not_touch_cloud(monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_ENABLED', 'false')
    monkeypatch.setattr(config, 'settings', Mock(side_effect=AssertionError('must not read configuration')))
    assert cluster.run() == {'event': 'record_seal_repair', 'outcome': 'disabled'}


def test_missing_flag_map_refuses(monkeypatch):
    monkeypatch.delenv('RECORD_SEAL_REPAIR_SERVER_FLAGS', raising=False)
    with pytest.raises(KeyError):
        config.server_flags()


def test_cli_disabled_uses_shared_json_logging_without_cloud():
    script = Path(__file__).resolve().parents[2] / 'scripts/record_seal_repair_job.py'
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, 'RECORD_SEAL_REPAIR_ENABLED': 'false', 'OMI_LOG_FORMAT': 'json'},
    )
    assert result.returncode == 0 and not result.stderr
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(records) == 1 and records[0]['logger'] == 'record-seal-repair'
    assert json.loads(records[0]['message']) == {'event': 'record_seal_repair', 'outcome': 'disabled'}


def test_native_and_dependency_diagnostics_never_reach_cli_output(tmp_path):
    entrypoint = Path(__file__).resolve().parents[2] / 'scripts/record_seal_repair_job.py'
    script = tmp_path / 'output_boundary.py'
    private = 'private@example.invalid ' + 'A' * 28 + ' users/private/conversations/private'
    script.write_text(
        'import runpy, sys, os, logging\n'
        f'entry = runpy.run_path({str(entrypoint)!r})\n'
        'def run(**kwargs):\n'
        f'    os.write(1, {private.encode()!r})\n'
        f'    os.write(2, {private.encode()!r})\n'
        f'    logging.error({private!r})\n'
        '    return {"event": "record_seal_repair", "outcome": "ok", "rows": 0}\n'
        'entry["repair"].run = run\n'
        f'sys.argv = [{str(entrypoint)!r}]\n'
        'raise SystemExit(entry["main"]())\n'
    )
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, env={**os.environ, 'OMI_LOG_FORMAT': 'json'}
    )
    assert result.returncode == 0 and not result.stderr
    assert private not in result.stdout
    assert json.loads(json.loads(result.stdout)['message'])['rows'] == 0


class FakeProcess:
    def __init__(self, clock, finish, result='sealed', exitcode=0):
        self.clock, self.finish, self.exitcode = clock, finish, exitcode
        self.returncode, self.reaped, self.killed = None, False, False
        self.stdout = io.BytesIO(json.dumps({'disposition': result}).encode())

    def poll(self):
        if self.clock[0] >= self.finish and self.returncode is None:
            self.returncode = self.exitcode
        return self.returncode

    def kill(self):
        self.killed, self.returncode = True, -9

    def wait(self):
        self.reaped = True
        return self.returncode


def scheduling(rows, *, workers=8, row_seconds=2, run_seconds=100, outcomes=None):
    clock, children, peak, order, progress = [0], [], [0], [], []

    def launch(path, seconds, mode):
        assert mode == 'apply'
        order.append(path)
        finish, result, exitcode = (outcomes or {}).get(path, (clock[0] + 0.2, 'sealed', 0))
        process = FakeProcess(clock, finish, result, exitcode)
        children.append(process)
        peak[0] = max(peak[0], sum(not p.reaped for p in children))
        return process

    def pause(seconds):
        clock[0] += seconds

    report = cluster.coordinate(
        rows,
        workers=workers,
        row_seconds=row_seconds,
        run_seconds=run_seconds,
        mode='apply',
        launch=launch,
        clock=lambda: clock[0],
        pause=pause,
        progress=progress.append,
    )
    return report, children, peak[0], order, progress


def test_concurrency_cap_one_row_failing_and_oldest_order_preserved():
    rows = [(str(i), 100 - i) for i in range(20)]
    report, children, peak, order, _ = scheduling(rows, outcomes={'0': (0.1, 'error', 1)})
    assert peak == 8 and order == [path for path, _ in rows]
    assert report['dispositions'] == {'error': 1, 'sealed': 19}
    assert all(p.reaped for p in children)


def test_hung_row_is_killed_and_slot_reused():
    report, children, peak, _, _ = scheduling(
        [('hung', 500), ('good', 200)], workers=1, outcomes={'hung': (float('inf'), 'sealed', 0)}
    )
    assert report['dispositions'] == {'budget_exhausted': 1, 'sealed': 1}
    assert children[0].killed and all(p.reaped for p in children) and peak == 1


def test_global_deadline_reaps_children_and_counts_deferred():
    report, children, _, _, _ = scheduling(
        [(str(i), 100) for i in range(10)],
        run_seconds=0.1,
        outcomes={str(i): (float('inf'), 'sealed', 0) for i in range(10)},
    )
    assert report['dispositions'] == {'budget_exhausted': 8, 'deferred': 2}
    assert all(p.killed and p.reaped for p in children)


def test_real_hung_subprocess_is_killed_and_reaped(tmp_path):
    script = tmp_path / 'hang.py'
    script.write_text('import time\ntime.sleep(30)\n')
    children = []

    def launch(*_):
        child = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        children.append(child)
        return child

    started = time.monotonic()
    report = cluster.coordinate(
        [('private-path', 100)], workers=1, row_seconds=0.1, run_seconds=5, mode='apply', launch=launch
    )
    assert report['dispositions'] == {'budget_exhausted': 1}
    assert time.monotonic() - started < 5
    assert children[0].returncode is not None and children[0].stdout.closed


def test_row_process_kills_decoder_descendant_even_after_leader_exit(tmp_path):
    sleeper, leader, pid_file = tmp_path / 'sleeper.py', tmp_path / 'leader.py', tmp_path / 'decoder-pid'
    sleeper.write_text('import time\ntime.sleep(30)\n')
    leader.write_text(
        'import subprocess, sys\nfrom pathlib import Path\n'
        f'child = subprocess.Popen([sys.executable, {str(sleeper)!r}], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n'
        f'Path({str(pid_file)!r}).write_text(str(child.pid))\n'
    )
    process = cluster.RowProcess(
        [sys.executable, str(leader)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True
    )
    try:
        assert process.wait(timeout=5) == 0
        descendant = int(pid_file.read_text())
        cluster.stop(process)
        # A killed orphan may briefly remain a zombie until init reaps it.
        state = subprocess.run(['ps', '-o', 'stat=', '-p', str(descendant)], capture_output=True, text=True)
        assert not state.stdout.strip() or state.stdout.strip().startswith('Z')
    finally:
        cluster.stop(process)


def test_callback_failure_also_reaps_every_live_child():
    clock, children = [0], []

    def launch(*_):
        process = FakeProcess(clock, 0 if not children else float('inf'))
        children.append(process)
        return process

    def failed(_):
        raise RuntimeError('private failure must not escape cleanup')

    with pytest.raises(RuntimeError):
        cluster.coordinate(
            [('a', 100), ('b', 90)],
            workers=2,
            row_seconds=1,
            run_seconds=5,
            mode='apply',
            launch=launch,
            clock=lambda: clock[0],
            progress=failed,
        )
    assert all(p.reaped for p in children) and children[1].killed


@pytest.mark.parametrize('private', ['A' * 28, 'private@example.invalid', 'users/private/conversations/private'])
def test_child_output_never_becomes_a_log_label(private):
    report, _, _, _, progress = scheduling([('private-input', 100)], outcomes={'private-input': (0.1, private, 0)})
    assert report['dispositions'] == {'error': 1}
    assert private not in json.dumps([report, progress])


def test_discovery_pages_past_closed_rows_and_preserves_oldest_order():
    class Query:
        def __init__(self):
            self.page = 0
            self.orders = []

        def where(self, **kw):
            return self

        def order_by(self, field):
            self.orders.append(field)
            return self

        def select(self, fields):
            assert fields == ('finished_at', 'record_audio_closed')
            return self

        def limit(self, _):
            return self

        def start_after(self, cursor):
            self.page += 1
            return self

        def stream(self, **kw):
            finish = datetime.fromtimestamp(100, timezone.utc)
            if self.page == 0:
                return [
                    SimpleNamespace(
                        reference=SimpleNamespace(path='closed'),
                        to_dict=lambda: {'finished_at': finish, 'record_audio_closed': True},
                    )
                ] * 128
            return [SimpleNamespace(reference=SimpleNamespace(path='oldest'), to_dict=lambda: {'finished_at': finish})]

    query = Query()
    rows, saturated, cursor = cluster.discover(
        SimpleNamespace(collection_group=lambda _: query, document=lambda path: path), budget=SweepBudget(60)
    )
    assert [path for path, _ in rows] == ['oldest'] and not saturated
    assert query.orders == ['finished_at', '__name__'] * 2
    assert cursor is None


class CursorClient:
    def __init__(self, documents=()):
        self.documents, self.state, self.writes = list(documents), None, 0

    def collection(self, name):
        assert name == 'batch_pipeline_prod_maintenance'
        return SimpleNamespace(document=lambda _: self)

    def get(self, **kwargs):
        return SimpleNamespace(exists=self.state is not None, to_dict=lambda: self.state)

    def set(self, state, **kwargs):
        self.state, self.writes = state, self.writes + 1

    def document(self, path):
        return SimpleNamespace(path=path)

    def collection_group(self, name):
        assert name == 'conversations'
        client = self

        class Query:
            def __init__(self):
                self.offset, self.cap = 0, 128
                self.horizon = None

            def where(self, **kwargs):
                field = kwargs['filter']
                if field.field_path == 'finished_at':
                    assert field.op_string == '<='
                    self.horizon = field.value
                return self

            def order_by(self, field):
                return self

            def select(self, fields):
                return self

            def limit(self, cap):
                self.cap = cap
                return self

            def start_after(self, cursor):
                self.offset = next(
                    i + 1 for i, doc in enumerate(client.documents) if doc.reference.path == cursor['__name__'].path
                )
                assert client.documents[self.offset - 1].to_dict()['finished_at'] == cursor['finished_at']
                return self

            def stream(self, **kwargs):
                return [
                    doc
                    for doc in client.documents[self.offset :]
                    if self.horizon is None or doc.to_dict()['finished_at'] <= self.horizon
                ][: self.cap]

        return Query()


def test_encrypted_cursor_passes_1024_refused_rows_then_eligible_and_wraps():
    from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor

    finished = datetime(2026, 10, 1, tzinfo=timezone.utc)
    paths = [f'users/synthetic/conversations/refused-{i:04d}' for i in range(1024)] + [
        'users/synthetic/conversations/zz-eligible'
    ]
    client = CursorClient(
        [
            SimpleNamespace(
                reference=SimpleNamespace(path=path),
                to_dict=lambda: {'finished_at': finished, 'record_audio_closed': False},
            )
            for path in paths
        ]
    )
    budget = SweepBudget(60)
    frontier = RepairCursor(client, b'synthetic-local-key' * 2)
    rows, saturated, cursor = cluster.discover(client, budget=budget, after=frontier.read(budget), advance_rows=8)
    assert saturated and len(rows) == 1024 and all('refused-' in path for path, _ in rows)
    frontier.write(cursor, budget)  # Durable before the entire prefix is refused.
    assert b'synthetic' not in client.state['cursor'] and 'path' not in client.state
    rows, saturated, cursor = cluster.discover(client, budget=budget, after=frontier.read(budget), advance_rows=8)
    assert not saturated and paths[-1] in [path for path, _ in rows]
    # Once the frontier reaches the tail, exhaustion wraps to revisit refusals.
    rows, saturated, cursor = cluster.discover(
        client, budget=budget, after={'path': paths[-1], 'finished_at': finished}, advance_rows=8
    )
    assert not rows and not saturated and cursor is None
    frontier.write(cursor, budget)
    assert frontier.read(budget) is None


def test_cursor_preserves_firestore_nanoseconds_and_refuses_tampering():
    from cryptography.exceptions import InvalidTag
    from google.api_core.datetime_helpers import DatetimeWithNanoseconds
    from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor

    client, budget = CursorClient(), SweepBudget(60)
    cursor = RepairCursor(client, b'synthetic-local-key' * 2)
    finished = DatetimeWithNanoseconds(2026, 10, 1, nanosecond=123456789, tzinfo=timezone.utc)
    cursor.write({'path': 'users/synthetic/conversations/old', 'finished_at': finished}, budget)
    assert cursor.read(budget)['finished_at'].timestamp_pb().nanos == 123456789
    blob = client.state['cursor']
    client.state['cursor'] = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(InvalidTag):
        cursor.read(budget)


def test_closed_row_scan_cap_also_advances_without_skipping_the_tail():
    finished = datetime(2026, 10, 1, tzinfo=timezone.utc)
    documents = [
        SimpleNamespace(
            reference=SimpleNamespace(path=f'users/synthetic/conversations/{i:04d}'),
            to_dict=lambda: {'finished_at': finished, 'record_audio_closed': True},
        )
        for i in range(20)
    ]
    documents.append(
        SimpleNamespace(
            reference=SimpleNamespace(path='users/synthetic/conversations/zz-eligible'),
            to_dict=lambda: {'finished_at': finished},
        )
    )
    client = CursorClient(documents)
    rows, saturated, cursor = cluster.discover(client, budget=SweepBudget(60), max_scan=16)
    assert not rows and saturated and cursor['path'] == documents[15].reference.path
    rows, saturated, cursor = cluster.discover(client, budget=SweepBudget(60), max_scan=16, after=cursor)
    assert [path for path, _ in rows] == [documents[-1].reference.path]
    assert not saturated and cursor is None


@pytest.mark.parametrize('mode,writes', [('apply', 1), ('plan', 0)])
def test_frontier_advances_before_work_and_plan_never_writes(source, proof, monkeypatch, mode, writes):
    from database import _client
    from utils.batch_pipeline import record_seal_sweeper

    client = CursorClient()
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', proof)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: SERVER)
    monkeypatch.setattr(config, 'settings', lambda: (8, 240, 1500, mode))

    def work(*args, **kwargs):
        assert client.writes == writes
        return {'rows': 0, 'dispositions': {}}

    monkeypatch.setattr(cluster, 'coordinate', work)
    assert cluster.run()['outcome'] == 'ok' and client.writes == writes


def test_run_budget_deferral_cannot_reset_the_unattempted_tail(source, proof, monkeypatch):
    from database import _client
    from utils.batch_pipeline import record_seal_sweeper

    finished = datetime(2026, 10, 1, tzinfo=timezone.utc)
    paths = [f'users/synthetic/conversations/{i:04d}' for i in range(10)]
    client = CursorClient(
        [
            SimpleNamespace(reference=SimpleNamespace(path=path), to_dict=lambda: {'finished_at': finished})
            for path in paths
        ]
    )
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', proof)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: SERVER)
    monkeypatch.setattr(config, 'settings', lambda: (2, 240, 1500, 'apply'))
    attempted = []

    def time_limited(rows, **kwargs):
        attempted.extend(path for path, _ in rows[:2])
        for path, _ in rows[:2]:
            kwargs['attempted'](path)
        return {'rows': len(rows), 'dispositions': {'budget_exhausted': len(rows[:2]), 'deferred': len(rows[2:])}}

    monkeypatch.setattr(cluster, 'coordinate', time_limited)
    for _ in range(5):
        cluster.run()
    assert attempted == paths


def test_admitted_registration_succeeds_at_zero_and_full_ramp_but_policy_changes(source):
    store, _, artifacts = source
    plans = []
    for percent in ('0', '100'):
        flags = {
            **SERVER,
            'BATCH_PIPELINE_ENABLED': 'true',
            'BATCH_PIPELINE_LIVE_ADMISSION_ENABLED': 'true',
            'BATCH_PIPELINE_PERCENT': percent,
            'BATCH_LIVE_STT_RETIRE_PERCENT': percent,
        }
        plan = nojob.plan_backfill(store, SCOPE, object(), artifacts, server_flags=flags)
        assert plan['entries'][0]['disposition'] == 'eligible'
        job = plan['entries'][0]['job']
        assert job['policy']['batch_enabled'] and job['policy']['live_record_enabled']
        plans.append(job['policy'])
    assert plans[0]['batch_percent'] == plans[0]['retire_percent'] == 0
    assert plans[1]['batch_percent'] == plans[1]['retire_percent'] == 100
    assert plans[0]['live_stt_retired'] is False and plans[1]['live_stt_retired'] is True
    assert plans[0]['policy_id'] != plans[1]['policy_id']


def test_last_attempt_checkpoint_skips_refused_prefix_and_wrap_revisits_oldest(source, proof, monkeypatch):
    from database import _client
    from utils.batch_pipeline import record_seal_sweeper

    finished = datetime(2026, 10, 1, tzinfo=timezone.utc)
    paths = [f'users/synthetic/conversations/{i:04d}' for i in range(12)]
    client = CursorClient(
        [
            SimpleNamespace(reference=SimpleNamespace(path=path), to_dict=lambda: {'finished_at': finished})
            for path in paths
        ]
    )
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', proof)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: SERVER)
    monkeypatch.setattr(config, 'settings', lambda: (2, 1, 2.1, 'apply'))
    original = cluster.coordinate
    attempts = []

    def work(rows, **kwargs):
        clock = [0]

        def launch(path, *_):
            attempts.append(path)
            # Refusals and exhausted rows remain unclosed on every cycle.
            finish = clock[0] + 0.4 if int(path[-1]) % 2 else float('inf')
            return FakeProcess(clock, finish, result='proof_refused')

        def pause(seconds):
            clock[0] += seconds

        return original(rows, **kwargs, launch=launch, clock=lambda: clock[0], pause=pause)

    monkeypatch.setattr(cluster, 'coordinate', work)
    for _ in range(8):
        cluster.run()
        if len(attempts) > len(paths):
            break
    assert attempts[: len(paths)] == paths
    assert attempts[len(paths)] == paths[0]
    assert b'synthetic' not in client.state['cursor']


@pytest.mark.parametrize('candidate', ['tail_lagging', 'A' * 28, 'private@example.invalid'])
def test_child_proof_reason_is_allowlisted(candidate):
    process = FakeProcess([0], 0, result='proof_refused')
    process.stdout = io.BytesIO(json.dumps({'disposition': 'proof_refused', 'proof_reason': candidate}).encode())
    progress = []
    report = cluster.coordinate(
        [('private-path', 100)],
        workers=1,
        row_seconds=1,
        run_seconds=1,
        mode='apply',
        launch=lambda *_: process,
        progress=progress.append,
    )
    expected = candidate if candidate == 'tail_lagging' else 'other'
    assert report['proof_reasons'] == {expected: 1}
    assert progress[0]['proof_reason'] == expected


def test_frozen_pass_boundary_wraps_despite_continuous_newer_inflow():
    from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor

    finished = datetime(2026, 10, 1, tzinfo=timezone.utc)
    horizon = datetime(2026, 10, 2, tzinfo=timezone.utc)
    newer = datetime(2026, 10, 3, tzinfo=timezone.utc)

    def doc(i, stamp):
        return SimpleNamespace(
            reference=SimpleNamespace(path=f'users/synthetic/conversations/{i:04d}'),
            to_dict=lambda: {'finished_at': stamp},
        )

    client = CursorClient([doc(i, finished) for i in range(8)])
    cursor = {'path': client.documents[0].reference.path, 'finished_at': finished, 'horizon': horizon}
    budget = SweepBudget(60)
    frontier = RepairCursor(client, b'synthetic-local-key' * 2)
    seen = []
    for cycle in range(4):
        client.documents.extend(doc(100 + cycle * 10 + j, newer) for j in range(10))
        rows, _, checkpoint = cluster.discover(client, budget=budget, after=cursor, max_rows=2)
        seen.extend(path for path, _ in rows)
        frontier.write(checkpoint, budget)
        cursor = frontier.read(budget)
    assert seen == [doc(i, finished).reference.path for i in range(1, 8)]
    assert cursor is None  # Next pass starts at oldest, despite 40 new rows.


def test_row_refusal_reason_survives_canonical_planner(source, proof):
    source[1].rows[PATH]['finished_at'] = None
    reason = {}
    assert (
        cluster.repair_one(
            source[0],
            object(),
            source[2],
            SCOPE[0],
            flags=SERVER,
            inventory=proof,
            budget=SweepBudget(270),
            reason_out=reason,
        )
        == 'proof_refused'
    )
    assert reason == {'proof_reason': 'finish_missing'}


@pytest.mark.parametrize('pending_job', [False, True])
@pytest.mark.parametrize('precheck', [False, True])
def test_row_tail_gap_survives_both_canonical_planners(source, proof, pending_job, precheck, monkeypatch):
    if not precheck:
        from utils.batch_pipeline import record_seal_repair as repair

        monkeypatch.setattr(repair, 'precheck_record_tail', lambda *a, **k: None)
    if pending_job:
        assert settle(source, proof) == 'sealed_registered'
        source[1].rows[PATH]['record_audio_closed'] = False
    source[1].rows[PATH]['finished_at'] = datetime.fromtimestamp(132, timezone.utc)
    reason = {}
    assert (
        cluster.repair_one(
            source[0],
            object(),
            source[2],
            SCOPE[0],
            flags=SERVER,
            inventory=proof,
            budget=SweepBudget(270),
            reason_out=reason,
        )
        == 'proof_refused'
    )
    assert reason == {'proof_reason': 'tail_lagging', 'tail_gap_bucket': '30_to_120s'}
    assert not source[1].rows[PATH].get('record_audio_closed')


@pytest.mark.parametrize('candidate', [*sorted(TAIL_GAP_BUCKETS), 'A' * 28, 'private@example.invalid', None])
def test_child_gap_bucket_is_allowlisted(candidate):
    process = FakeProcess([0], 0, result='proof_refused')
    process.stdout = io.BytesIO(
        json.dumps(
            {
                'disposition': 'proof_refused',
                'proof_reason': 'tail_lagging',
                'tail_gap_bucket': candidate,
            }
        ).encode()
    )
    progress = []
    report = cluster.coordinate(
        [('private-path', 100)],
        workers=1,
        row_seconds=1,
        run_seconds=1,
        mode='apply',
        launch=lambda *_: process,
        progress=progress.append,
    )
    expected = candidate if candidate in TAIL_GAP_BUCKETS else 'negative_or_unknown'
    assert report['tail_gap_buckets'] == {expected: 1}
    assert progress[0]['tail_gap_bucket'] == expected
    assert set(progress[0]) == {
        'event',
        'count',
        'disposition',
        'seal_age_seconds',
        'proof_reason',
        'tail_gap_bucket',
        'trimmed_divergent_overlaps',
    }


def test_upload_failed_skips_proof_cost_and_gap(source, proof, monkeypatch):
    from utils.batch_pipeline import record_seal_repair as repair

    monkeypatch.setenv('RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED', 'false')
    source[1].rows[PATH]['record_upload_failed'] = True
    read = Mock(side_effect=AssertionError('must not read audio'))
    monkeypatch.setattr(repair, 'list_audio_chunks', read)
    reason = {}
    assert (
        cluster.repair_one(
            source[0],
            object(),
            source[2],
            SCOPE[0],
            flags=SERVER,
            inventory=proof,
            budget=SweepBudget(270),
            reason_out=reason,
        )
        == 'upload_failed'
    )
    assert reason == {}
    read.assert_not_called()
    assert source[1].rows[PATH]['record_upload_failed'] is True


@pytest.mark.parametrize('pending_job', [False, True])
def test_repair_clears_upload_failed_only_with_complete_proof(source, proof, pending_job):
    if pending_job:
        assert settle(source, proof) == 'sealed_registered'
    row = source[1].rows[PATH]
    row.update(record_upload_failed=True, record_audio_closed=False)
    assert settle(source, proof) == 'upload_failed_cleared'
    assert row['record_audio_closed']
    assert row['record_upload_failed'] is False
    assert source[1].rows[JOB_PATH]['state'] == 'record_pending'


@pytest.mark.parametrize('pending_job', [False, True])
def test_failed_row_with_missing_tail_stays_failed_in_repair(source, proof, pending_job):
    if pending_job:
        assert settle(source, proof) == 'sealed_registered'
    row = source[1].rows[PATH]
    row.update(
        record_upload_failed=True, record_audio_closed=False, finished_at=datetime.fromtimestamp(150, timezone.utc)
    )
    assert settle(source, proof) == 'proof_refused'
    assert row['record_upload_failed']
    assert not row['record_audio_closed']


@pytest.mark.parametrize('pending_job', [False, True])
def test_repeated_failure_landing_during_proof_fences_both_repair_paths(source, proof, pending_job, monkeypatch):
    from database.record_audio import mark_record_upload_failed
    from utils.batch_pipeline import record_seal_repair as repair

    if pending_job:
        assert settle(source, proof) == 'sealed_registered'
    row = source[1].rows[PATH]
    row.update(record_upload_failed=True, record_audio_closed=False)
    original = repair.retained_tail_proof

    def remark(*args, **kwargs):
        result = original(*args, **kwargs)
        mark_record_upload_failed('synthetic', 'capture', firestore_client=source[1])
        return result

    monkeypatch.setattr(repair, 'retained_tail_proof', remark)
    monkeypatch.setattr(nojob, 'retained_tail_proof', remark)
    assert settle(source, proof) == 'state_changed'
    assert row['record_upload_failed']
    assert not row['record_audio_closed']


@pytest.mark.parametrize('candidate,expected', [(3, 3), (-1, 0), (4097, 0), ('3', 0), (True, 0)])
def test_trim_count_row_log_is_bounded_and_numeric(candidate, expected):
    process = FakeProcess([0], 0, result='upload_failed_cleared')
    process.stdout = io.BytesIO(
        json.dumps({'disposition': 'upload_failed_cleared', 'trimmed_divergent_overlaps': candidate}).encode()
    )
    progress = []
    report = cluster.coordinate(
        [('synthetic', 100)],
        workers=1,
        row_seconds=1,
        run_seconds=1,
        mode='apply',
        launch=lambda *_: process,
        progress=progress.append,
    )
    assert progress[0]['trimmed_divergent_overlaps'] == expected
    assert progress[0]['seal_age_seconds'] >= 100
    assert report['dispositions'] == {'upload_failed_cleared': 1}


def test_non_tail_child_cannot_emit_gap():
    process = FakeProcess([0], 0, result='upload_failed')
    process.stdout = io.BytesIO(
        json.dumps(
            {
                'disposition': 'upload_failed',
                'proof_reason': 'tail_lagging',
                'tail_gap_bucket': 'over_120s',
            }
        ).encode()
    )
    progress = []
    report = cluster.coordinate(
        [('private-path', 100)],
        workers=1,
        row_seconds=1,
        run_seconds=1,
        mode='apply',
        launch=lambda *_: process,
        progress=progress.append,
    )
    assert report['tail_gap_buckets'] == {}
    assert 'tail_gap_bucket' not in progress[0]

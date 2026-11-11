"""Hermetic cluster repair composition and bounded child lifecycle."""

from datetime import datetime, timezone
import io
import math
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import re

from config import record_seal_repair as config
from database import _client, record_token_lease_metrics
from utils.batch_pipeline import record_seal_nojob as nojob, record_seal_cluster_repair as cluster
from utils.batch_pipeline import record_producer_proof as producer
from utils.batch_pipeline import record_seal_sweeper
from utils.batch_pipeline.record_seal_budget import SweepBudget
from utils.batch_pipeline.record_seal_reasons import TAIL_GAP_BUCKETS
from tests.unit.test_record_seal_nojob import source, SCOPE, SERVER, PATH, JOB_PATH
from tests.unit.test_record_producer_proof import inventory, pod


@pytest.mark.parametrize('fail', [False, True])
def test_repair_child_terminal_reads_reach_parent_registry_once(fail):
    from database.firestore_document_probe import FIRESTORE_BILLED_READS, FIRESTORE_BILLED_READS_BY_CALLER
    from utils.batch_pipeline.record_seal_worker import Metrics
    from utils.observability import firestore_probe_export as export

    billed = FIRESTORE_BILLED_READS.labels('other', 'query', 'unattributed')
    caller = FIRESTORE_BILLED_READS_BY_CALLER.labels('other', 'query', 'tests:repair_child_export')
    before = (billed._value.get(), caller._value.get())
    entrypoint = Path(__file__).resolve().parents[2] / 'scripts/record_seal_repair_job.py'
    # Run the real entrypoint/finally in a separate interpreter, replacing only
    # the row's cloud work with synthetic counter increments.
    code = (
        'import runpy, sys\n'
        f'entry = runpy.run_path({str(entrypoint)!r})\n'
        'from database.firestore_document_probe import FIRESTORE_BILLED_READS, FIRESTORE_BILLED_READS_BY_CALLER\n'
        'def row(*args, **kwargs):\n'
        '    FIRESTORE_BILLED_READS.labels("other", "query", "unattributed").inc(11)\n'
        '    FIRESTORE_BILLED_READS_BY_CALLER.labels("other", "query", "tests:repair_child_export").inc(11)\n'
        + ('    raise RuntimeError("private synthetic error")\n' if fail else '    return {"disposition":"sealed"}\n')
        + 'entry["repair"].row_main = row\n'
        'sys.argv = ["record_seal_repair_job.py", "--row"]\n'
        'sys.exit(entry["main"]())\n'
    )
    process = export.launch_with_probe(
        cluster.RowProcess,
        [sys.executable, '-c', code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(b'{}', timeout=30)
        assert process.returncode == int(fail)
        assert not stderr and b'private synthetic error' not in stdout
        # communicate closes stdout; stop's normal contract owns an open pipe.
        process.stdout = io.BytesIO(stdout)
        cluster.stop(process)
        assert (billed._value.get(), caller._value.get()) == (before[0] + 11, before[1] + 11)
        export.collect_child_probe(process)
        assert (billed._value.get(), caller._value.get()) == (before[0] + 11, before[1] + 11)
        assert (
            Metrics('r', 'n').registry.get_sample_value(
                'omi_firestore_billed_reads_by_caller_total',
                {'collection': 'other', 'kind': 'query', 'caller': 'tests:repair_child_export'},
            )
            == before[1] + 11
        )
    finally:
        if process.poll() is None:
            cluster.stop(process)


def test_launch_row_passes_terminal_fd_without_changing_row_output(monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_ENABLED', 'false')
    process = cluster.launch_row('users/synthetic/conversations/synthetic', 1, 'plan')
    output = process._firestore_probe_output
    try:
        process.wait(timeout=30)
        assert process.returncode == 0
        records = [json.loads(line) for line in process.stdout.read().splitlines()]
        assert records[-1]['disposition'] == 'disabled'
        assert not any('firestore_probe' in json.dumps(record) for record in records)
        output.seek(0)
        assert json.load(output) == []
    finally:
        cluster.stop(process)
    assert output.closed and process._firestore_probe_output is None


def test_missing_or_invalid_child_aggregate_does_not_change_cleanup(caplog):
    import tempfile
    from utils.observability import firestore_probe_export as export

    for data in (b'', b'not-json', b'[["unknown_total",{},1]]'):
        output = tempfile.TemporaryFile()
        output.write(data)
        process = SimpleNamespace(_firestore_probe_output=output)
        export.collect_child_probe(process)
        assert output.closed and process._firestore_probe_output is None
    assert sum(json.loads(record.message).get('outcome') == 'unavailable' for record in caplog.records) == 3


def test_terminal_transport_failure_preserves_launch_and_original_exception(monkeypatch, caplog):
    from utils.observability import firestore_probe_export as export

    def unavailable(**_):
        raise OSError('synthetic fd exhaustion')

    monkeypatch.setattr(export.tempfile, 'TemporaryFile', unavailable)
    process = SimpleNamespace()
    factory = Mock(return_value=process)
    assert export.launch_with_probe(factory, ['synthetic-child'], stdout=subprocess.PIPE) is process
    factory.assert_called_once_with(['synthetic-child'], stdout=subprocess.PIPE)
    assert process._firestore_probe_output is None
    records = len(caplog.records)
    with pytest.raises(RuntimeError, match='original job error'):
        with export.terminal_probe_totals(fd='not-a-file-descriptor'):
            raise RuntimeError('original job error')
    assert len(caplog.records) == records  # No telemetry diagnostics on the child's result pipe.


def test_spawn_failure_closes_terminal_transport(monkeypatch):
    import tempfile
    from utils.observability import firestore_probe_export as export

    output = tempfile.TemporaryFile()
    monkeypatch.setattr(export.tempfile, 'TemporaryFile', lambda **_: output)
    with pytest.raises(OSError, match='synthetic launch failure'):
        export.launch_with_probe(Mock(side_effect=OSError('synthetic launch failure')), ['synthetic-child'])
    assert output.closed


def test_counter_sample_map_matches_served_counter_metadata():
    from database.firestore_document_probe import FIRESTORE_BILLED_READS, FIRESTORE_BILLED_READS_BY_CALLER
    from utils.observability.firestore_probe_export import COUNTER_SAMPLES

    FIRESTORE_BILLED_READS.labels(collection='x', kind='query', tier='unattributed').inc(1)
    FIRESTORE_BILLED_READS_BY_CALLER.labels(collection='x', kind='query', caller='tests:probe_export_pin').inc(1)
    seen = {}
    for collector, _label_keys in COUNTER_SAMPLES.values():
        for family in collector.collect():
            for sample in family.samples:
                if sample.name.endswith('_total'):
                    seen[sample.name] = frozenset(sample.labels)
    assert seen == {name: frozenset(label_keys) for name, (_collector, label_keys) in COUNTER_SAMPLES.items()}


def test_repair_coordinator_terminal_totals_escape_dependency_silencing(tmp_path):
    entrypoint = Path(__file__).resolve().parents[2] / 'scripts/record_seal_repair_job.py'
    script = tmp_path / 'terminal_boundary.py'
    script.write_text(
        'import runpy, sys\n'
        f'entry = runpy.run_path({str(entrypoint)!r})\n'
        'from database.firestore_document_probe import FIRESTORE_BILLED_READS_BY_CALLER\n'
        'def run(**kwargs):\n'
        '    FIRESTORE_BILLED_READS_BY_CALLER.labels("other", "query", "tests:coordinator_terminal").inc(13)\n'
        '    return {"event":"record_seal_repair","outcome":"ok"}\n'
        'entry["repair"].run = run\n'
        'sys.argv = ["record_seal_repair_job.py"]\n'
        'sys.exit(entry["main"]())\n'
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, 'RECORD_SEAL_REPAIR_ENABLED': 'false'},
    )
    assert result.returncode == 0 and not result.stderr
    messages = [json.loads(json.loads(line)['message']) for line in result.stdout.splitlines()]
    assert any(
        message.get('event') == 'firestore_probe_terminal_sample'
        and message['labels'].get('caller') == 'tests:coordinator_terminal'
        and message['value'] == 13
        for message in messages
    )


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


def test_stale_proof_skips_before_planning_or_writes(source, proof):
    value = proof()
    value['captured_at'] = 699
    with pytest.raises(ValueError):
        settle(source, lambda: value)
    assert all(not tx.updates and not tx.sets for tx in source[1].transactions)


def test_partial_pod_list_cannot_prove_absence(source):
    def partial():
        raw = inventory([])
        raw['metadata']['continue'] = 'private-continuation'
        return producer.parse_pusher_pod_proof(
            json.dumps(raw).encode(), datetime.fromtimestamp(999, timezone.utc).isoformat()
        )

    with pytest.raises(ValueError):
        settle(source, partial)
    assert all(not tx.updates and not tx.sets for tx in source[1].transactions)


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
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, 'OMI_LOG_FORMAT': 'json', 'PUSHER_PROJECTION_DEBT_DURABLE_ENABLED': 'off'},
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


def test_discovery_pages_past_closed_rows_and_requests_newest_order():
    class Query:
        def __init__(self):
            self.page = 0
            self.orders = []
            self.directions = []

        def where(self, **kw):
            return self

        def order_by(self, field, direction=None):
            self.orders.append(field)
            self.directions.append(direction)
            return self

        def select(self, fields):
            assert fields == (
                'finished_at',
                'record_audio_closed',
                'record_audio_partial',
                'record_upload_revision',
                'deleted',
                'discarded',
                'private_cloud_sync_enabled',
            )
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
            return [
                SimpleNamespace(
                    reference=SimpleNamespace(path='oldest'),
                    to_dict=lambda: {'finished_at': finish, 'private_cloud_sync_enabled': True},
                )
            ]

    query = Query()
    rows, saturated, cursor = cluster.discover(
        SimpleNamespace(collection_group=lambda _: query, document=lambda path: path), budget=SweepBudget(60)
    )
    assert [path for path, _ in rows] == ['oldest'] and not saturated
    assert query.orders == ['finished_at', '__name__'] * 2
    assert query.directions == ['DESCENDING'] * 4
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

            def order_by(self, field, direction=None):
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
    monkeypatch.setattr(config, 'jobs_enabled', lambda: False)
    from database import _client, record_token_lease_metrics
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


@pytest.mark.parametrize('expiry_outcome', ['completed', 'error', 'budget_exhausted'])
def test_run_budget_deferral_cannot_reset_the_unattempted_tail(source, proof, monkeypatch, expiry_outcome):
    monkeypatch.setattr(config, 'jobs_enabled', lambda: False)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'off')
    from database import _client, record_token_lease_metrics
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
    attempted, events, promotions = [], [], []

    def promote(client, namespace, now, *, budget):
        assert namespace == 'batch_pipeline_prod'
        budget.check()
        promotions.append(now)
        return 1

    monkeypatch.setattr(cluster, 'promote_record_recoveries', promote)

    def expire(*args, **kwargs):
        if expiry_outcome == 'budget_exhausted':
            from utils.batch_pipeline.record_seal_budget import BudgetExhausted

            raise BudgetExhausted()
        if expiry_outcome == 'error':
            raise RuntimeError('synthetic unavailable cleanup')
        return 3

    monkeypatch.setattr(cluster.record_custody_receipts, 'prune', expire)

    def time_limited(rows, **kwargs):
        assert cluster.REPAIR_OLDEST._value.get() == max(age for _, age in rows)
        attempted.extend(path for path, _ in rows[:2])
        for path, _ in rows[:2]:
            kwargs['attempted'](path)
        return {'rows': len(rows), 'dispositions': {'budget_exhausted': len(rows[:2]), 'deferred': len(rows[2:])}}

    monkeypatch.setattr(cluster, 'coordinate', time_limited)
    for _ in range(5):
        cluster.run(progress=events.append)
    assert attempted == paths
    assert len(promotions) == 5
    assert sum(event.get('promoted', 0) for event in events) == 5
    assert [event['outcome'] for event in events if event['event'] == 'record_custody_receipts_expiry'] == [
        expiry_outcome
    ] * 5


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
    monkeypatch.setattr(config, 'jobs_enabled', lambda: False)
    from database import _client, record_token_lease_metrics
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
    assert reason == {'proof_reason': 'finish_missing', 'blocker': 'seal_eligible'}


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
    assert reason == {'proof_reason': 'tail_lagging', 'tail_gap_bucket': '30_to_120s', 'blocker': 'seal_eligible'}
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
        'elapsed_ms',
        'stage',
        'stage_ms',
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
    assert reason == {'blocker': 'upload_failed'}
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


def _partial_mark(revision, finish):
    return {
        'version': 1,
        'reason': sorted(cluster.partial_config.REASONS)[0],
        'upload_revision': revision,
        'finished_at': finish,
        'finished_partial_at': datetime.now(timezone.utc),
    }


@pytest.mark.parametrize(
    'extra,selected',
    [
        ({}, True),  # open, sync on: still a repair candidate
        ({'deleted': True}, False),
        ({'discarded': True}, False),
        ({'private_cloud_sync_enabled': False}, False),
        ({'record_audio_closed': True, 'record_audio_partial': 'MARK', 'record_upload_revision': 3}, False),
        # A new upload revision invalidates the barrier and must be revisited.
        ({'record_audio_closed': False, 'record_audio_partial': 'MARK', 'record_upload_revision': 4}, True),
    ],
)
def test_discovery_skips_rows_repair_can_only_refuse(extra, selected):
    finish = datetime.fromtimestamp(100, timezone.utc)
    data = {'finished_at': finish, 'private_cloud_sync_enabled': True, **extra}
    if data.get('record_audio_partial') == 'MARK':
        data['record_audio_partial'] = _partial_mark(3, finish)

    class Query:
        def where(self, **kw):
            return self

        def order_by(self, field, direction=None):
            return self

        def select(self, fields):
            return self

        def limit(self, _):
            return self

        def start_after(self, cursor):
            return self

        def stream(self, **kw):
            return [SimpleNamespace(reference=SimpleNamespace(path='row'), to_dict=lambda: dict(data))]

    rows, _, _ = cluster.discover(
        SimpleNamespace(collection_group=lambda _: Query(), document=lambda path: path), budget=SweepBudget(60)
    )
    assert bool(rows) is selected


@pytest.mark.parametrize('workers', ['1', '16', '48', '64'])
def test_repair_workers_accept_io_bound_range(monkeypatch, workers):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_WORKERS', workers)
    monkeypatch.setenv('RECORD_SEAL_REPAIR_ROW_SECONDS', '270')
    monkeypatch.setenv('RECORD_SEAL_REPAIR_RUN_SECONDS', '1500')
    monkeypatch.setenv('RECORD_SEAL_REPAIR_MODE', 'apply')
    assert config.settings() == (int(workers), 270, 1500, 'apply')


@pytest.mark.parametrize('workers', ['0', '65', '128'])
def test_repair_workers_outside_range_refuse(monkeypatch, workers):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_WORKERS', workers)
    with pytest.raises(ValueError, match='invalid repair limits'):
        config.settings()


def test_row_reuses_exactly_one_gcs_client_and_reports_stages(source, proof, monkeypatch):
    from contextlib import nullcontext
    from database import batch_pipeline_store
    from utils.batch_pipeline import artifact_policy, record_seal_repair, record_seal_sweeper
    from utils.other import local_storage, storage

    store, _, artifacts = source
    monkeypatch.setattr(config, 'enabled', lambda: True)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: SERVER)
    monkeypatch.setattr(cluster, 'silent_dependencies', nullcontext)
    monkeypatch.setattr(batch_pipeline_store, 'FirestoreStore', lambda _: store)
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', proof)
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.setattr(storage.audio_archive, 'admitted', lambda *a: False)
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic')
    blob = SimpleNamespace(name='chunks/synthetic/capture/100.bin', size=64000, generation=7, metadata={})
    bucket = SimpleNamespace(name=storage.private_cloud_sync_bucket, list_blobs=lambda **kw: iter([blob]))
    client = SimpleNamespace(bucket=lambda _: bucket)
    construct = Mock(return_value=client)
    monkeypatch.setattr(local_storage, 'create_storage_client', construct)
    # Any accidental default construction in either downstream module must count.
    monkeypatch.setattr(artifact_policy, 'create_storage_client', construct)
    monkeypatch.setattr(storage, 'create_storage_client', construct)
    monkeypatch.setattr(storage, 'storage_client', None)
    composed = Mock(return_value=artifacts)
    monkeypatch.setattr(artifact_policy, 'create_artifact_store', composed)
    monkeypatch.setattr(record_seal_repair, 'list_audio_chunks', storage.list_audio_chunks)
    checkpoints = []
    result = cluster.row_main(
        {'path': SCOPE[0], 'mode': 'apply', 'seconds': 240, 'started': time.monotonic() - 0.02},
        progress=checkpoints.append,
    )
    assert result['disposition'] == 'sealed_registered'
    assert construct.call_count == 1
    assert composed.call_args.args[1] is client
    assert list(result['stage_ms']) == list(cluster.record_seal_profile.STAGES)
    assert result['stage_ms']['startup'] >= 20
    assert {entry['stage'] for entry in checkpoints} == {'clients', 'proof', 'list', 'walk', 'apply'}
    assert all(0 <= value <= 3600000 for value in result['stage_ms'].values())
    assert result['chunks'] == result['bytes'] == 0  # This fixture stubs the decoder only.
    assert len(json.dumps(result).encode()) < 1024


def test_profile_measures_deltas_and_bounds_worst_case_ipc():
    now = [1.0]
    profile = cluster.record_seal_profile.RowProfile(0, clock=lambda: now[0])
    with profile.install():
        for stage in cluster.record_seal_profile.STAGES[1:]:
            profile.enter(stage)
            now[0] += 1
        cluster.record_seal_profile.received(123)
    result = profile.snapshot()
    assert result['stage_ms'] == dict.fromkeys(cluster.record_seal_profile.STAGES, 1000)
    assert result['chunks'] == 1 and result['bytes'] == 123
    result.update(
        disposition='budget_exhausted',
        blocker='already_closed_job_pending',
        partial_reason='tail_lost_or_unproven',
        proof_reason='tail_lagging',
        tail_gap_bucket='negative_or_unknown',
        trimmed_divergent_overlaps=4096,
    )
    result['stage_ms'] = dict.fromkeys(cluster.record_seal_profile.STAGES, 3600000)
    result['chunks'] = result['bytes'] = result['metadata_reloads'] = 2**53
    assert len(json.dumps(result).encode()) < 1024


@pytest.mark.parametrize('startup_delay', [0, 0.5])
@pytest.mark.parametrize('checkpoint,expected', [(True, 'walk'), (False, 'unknown')])
def test_killed_child_reports_last_received_stage(checkpoint, expected, startup_delay):
    children, events = [], []
    ready_read, ready_write = os.pipe()
    code = (
        'import os,time\n'
        + f'time.sleep({startup_delay})\n'
        + (
            'os.write(1, b\'{"stage":"walk","stage_ms":{"proof":12},"chunks":2,"bytes":99}\\n\')\n'
            if checkpoint
            else ''
        )
        + f'os.write({ready_write}, b"1"); os.close({ready_write})\n'
        + 'time.sleep(30)\n'
    )
    try:
        child = subprocess.Popen(
            [sys.executable, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, pass_fds=(ready_write,)
        )
        children.append(child)
        os.close(ready_write)
        ready_write = None
        # This is an IPC timeout test. Ensure the fixture emitted its profile
        # before advancing the coordinator's injected clock. Scheduler delays
        # cannot consume either the startup phase or the row budget.
        assert select.select([ready_read], [], [], 30)[0], 'fixture child did not become ready'
        assert os.read(ready_read, 1) == b'1'
        now = [0.0]

        def advance(seconds):
            now[0] += seconds

        report = cluster.coordinate(
            [('private', 100)],
            workers=1,
            row_seconds=0.3,
            run_seconds=5,
            mode='apply',
            launch=lambda *_: child,
            progress=events.append,
            clock=lambda: now[0],
            pause=advance,
        )
        assert report['dispositions'] == {'budget_exhausted': 1}
        assert events[0]['stage'] == expected
        assert report['disposition_elapsed_ms']['budget_exhausted'] == events[0]['elapsed_ms']
        assert child.returncode is not None and child.stdout.closed
        if checkpoint:
            assert events[0]['chunks'] == 2 and events[0]['bytes'] == 99
    finally:
        if ready_write is not None:
            os.close(ready_write)
        os.close(ready_read)
        for child in children:
            cluster.stop(child)


def test_ipc_tolerates_old_partial_oversized_and_untrusted_profiles():
    process = SimpleNamespace(stdout=io.BytesIO())
    output = cluster.RowOutput(process)
    output.accept(b'{"stage":"private@example.invalid","bytes":"private","stage_ms":{"walk":-1}}')
    assert output.profile == {'stage': 'unknown', 'stage_ms': {}}
    process.stdout = io.BytesIO(b'x' * 1025 + b'\n{"stage":"proof"}\n{"disposition":"sealed"}')
    output.drain(True)
    assert output.result == {'disposition': 'sealed'}
    assert output.profile['stage'] == 'proof'
    _, _, _, _, events = scheduling([('old-child', 100)])
    assert events[0]['stage'] == 'unknown' and events[0]['disposition'] == 'sealed'


@pytest.mark.parametrize('event', ['record_seal_repair', 'record_seal_repair_row'])
def test_parent_row_and_summary_are_warning(event, monkeypatch):
    import importlib.util
    import logging

    path = Path(__file__).resolve().parents[2] / 'scripts/record_seal_repair_job.py'
    spec = importlib.util.spec_from_file_location('seal_job_warning_test', path)
    module = importlib.util.module_from_spec(spec)
    # Loading this entrypoint must not replace pytest's logging handlers.
    import omi_logging

    monkeypatch.setattr(omi_logging, 'configure_logging', lambda *a, **kw: None)
    spec.loader.exec_module(module)
    records = []
    logger = logging.getLogger('record-seal-repair')
    monkeypatch.setattr(logger, 'handle', records.append)
    module.emit({'event': event, 'outcome': 'ok', 'stage_ms': {'walk': 12}})
    assert records[0].levelno == logging.WARNING
    assert json.loads(records[0].msg)['stage_ms']['walk'] == 12


@pytest.mark.parametrize('stage', ['run', 'rebuild'])
def test_job_failure_logs_exception_type_and_site_never_message(tmp_path, stage):
    entrypoint = Path(__file__).resolve().parents[2] / 'scripts/record_seal_repair_job.py'
    script = tmp_path / 'failure_boundary.py'
    private = 'users/private-uid/conversations/private-cid private@example.invalid'
    script.write_text(
        'import runpy, sys, types\n'
        f'entry = runpy.run_path({str(entrypoint)!r})\n'
        'def boom(**kwargs):\n'
        f'    raise RuntimeError({private!r})\n'
        'def ok(**kwargs):\n'
        '    return {"event": "record_seal_repair", "outcome": "ok", "rows": 0}\n'
        f'if {stage!r} == "run":\n'
        '    entry["repair"].run = boom\n'
        'else:\n'
        '    entry["repair"].run = ok\n'
        '    sys.modules["utils.record_projection_rebuild"] = types.SimpleNamespace(run_job=lambda: boom())\n'
        '    import utils\n'
        '    utils.record_projection_rebuild = sys.modules["utils.record_projection_rebuild"]\n'
        f'sys.argv = [{str(entrypoint)!r}]\n'
        'raise SystemExit(entry["main"]())\n'
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, 'OMI_LOG_FORMAT': 'json', 'RECORD_SEAL_REPAIR_ENABLED': 'true'},
    )
    assert private not in result.stdout and private not in result.stderr
    messages = [json.loads(json.loads(line)['message']) for line in result.stdout.splitlines() if line.strip()]
    event = 'record_seal_repair' if stage == 'run' else 'record_projection_rebuild'
    failure = next(m for m in messages if m.get('event') == event and m.get('outcome') == 'error')
    assert failure['exception_type'] == 'RuntimeError'
    assert re.fullmatch(r'[a-z0-9_]{1,64}\.py:\d+', failure['error_site'])
    assert set(failure) <= {'event', 'outcome', 'exception_type', 'error_site'}
    assert result.returncode == (1 if stage == 'run' else 0)


def _job_module(monkeypatch):
    import importlib.util

    import omi_logging

    path = Path(__file__).resolve().parents[2] / 'scripts/record_seal_repair_job.py'
    spec = importlib.util.spec_from_file_location('seal_job_failure_redaction', path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(omi_logging, 'configure_logging', lambda *a, **kw: None)
    spec.loader.exec_module(module)
    return module


def test_failure_redacts_dynamic_exception_class_name(monkeypatch):
    module = _job_module(monkeypatch)
    private = type('uid_9f8e7d6c5b4a_conversation', (RuntimeError,), {'__module__': 'private_payload'})
    try:
        raise private('users/private/conversations/private')
    except RuntimeError as error:
        payload = module.failure('record_seal_repair', error)
    assert payload['exception_type'] == 'other'
    assert 'uid_9f8e7d6c5b4a' not in json.dumps(payload)


def test_failure_drops_site_from_dynamically_compiled_frame(monkeypatch):
    module = _job_module(monkeypatch)
    code = compile('raise RuntimeError("x")', '/tmp/users/private-uid/conversation.py', 'exec')
    try:
        exec(code, {})
    except RuntimeError as error:
        payload = module.failure('record_seal_repair', error)
    assert payload['exception_type'] == 'RuntimeError'
    assert 'private-uid' not in json.dumps(payload)
    assert 'error_site' not in payload or 'conversation.py' not in payload['error_site']


def test_failure_falls_back_when_fields_cannot_be_built(monkeypatch):
    module = _job_module(monkeypatch)
    monkeypatch.setattr(module, '_error_site', lambda error: (_ for _ in ()).throw(ImportError('boom')))
    payload = module.failure('record_seal_repair', RuntimeError('users/private'))
    assert payload == {'event': 'record_seal_repair', 'outcome': 'error', 'exception_type': 'RuntimeError'}


class OrderedJobsClient:
    """Query fake enforcing numeric range, field existence and compound cursors."""

    def __init__(self, documents, error=None):
        self.documents, self.error, self.queries = documents, error, []

    def document(self, path):
        return SimpleNamespace(path=path)

    def collection(self, name):
        assert name == 'batch_pipeline_prod_jobs'
        client = self

        class Query:
            def __init__(self):
                self.filters, self.order, self.after, self.cap = [], [], None, None
                self.directions = []

            def where(self, *, filter):
                self.filters.append((filter.field_path, filter.op_string, filter.value))
                return self

            def order_by(self, field, direction=None):
                self.order.append(field)
                self.directions.append(direction or 'ASCENDING')
                return self

            def select(self, fields):
                assert fields in (
                    ('owner_id', 'conversation_id', 'enqueued_at', 'record_content_id'),
                    (
                        'owner_id',
                        'conversation_id',
                        'enqueued_at',
                        'record_content_id',
                        'record_dead_letter_deadline_at',
                    ),
                )
                return self

            def limit(self, cap):
                assert 0 < cap <= 128
                self.cap = cap
                return self

            def start_after(self, cursor):
                assert set(cursor) == set(self.order)
                self.after = cursor
                return self

            def stream(self, *, timeout, retry):
                assert 0 < timeout <= 10 and retry is None
                age_order = self.order in (['enqueued_at', '__name__'], ['record_dead_letter_deadline_at', '__name__'])
                assert age_order or self.order == ['__name__']
                if age_order and client.error:
                    raise client.error
                docs = client.documents[:]
                for field, op, value in self.filters:
                    if op == '==':
                        docs = [d for d in docs if d.to_dict().get(field) == value]
                    else:
                        assert field in ('enqueued_at', 'record_dead_letter_deadline_at') and op in ('<=', '>')
                        docs = [
                            d
                            for d in docs
                            if type(d.to_dict().get(field)) in (int, float)
                            and (
                                (d.to_dict()[field] <= value or math.isnan(d.to_dict()[field]))
                                if op == '<='
                                else d.to_dict()[field] > value
                            )
                        ]

                def key(value, path):
                    if not age_order:
                        return (path,)
                    # Firestore normalizes NaN below all other numbers.
                    numeric = (0, 0) if math.isnan(value) else (1, value)
                    return numeric, path

                field = self.order[0]
                descending = self.directions[0] == 'DESCENDING'
                docs.sort(key=lambda d: key(d.to_dict().get(field), d.reference.path), reverse=descending)
                if self.after:
                    point = key(self.after.get(field), self.after['__name__'].path)
                    docs = [
                        d
                        for d in docs
                        if (
                            key(d.to_dict().get(field), d.reference.path) < point
                            if descending
                            else key(d.to_dict().get(field), d.reference.path) > point
                        )
                    ]
                return docs[: self.cap]

        query = Query()
        self.queries.append(query)
        return query


def pending_job(index, enqueued=0, **extra):
    content, segment = cluster.record_identity('synthetic', f'capture-{index}')
    data = {
        'state': 'record_pending',
        'owner_id': 'synthetic',
        'conversation_id': f'capture-{index}',
        'record_content_id': content,
        'enqueued_at': enqueued,
        **extra,
    }
    return SimpleNamespace(
        id=segment, reference=SimpleNamespace(path=f'batch_pipeline_prod_jobs/{segment}'), to_dict=lambda: dict(data)
    )


@pytest.mark.parametrize('order', ['on', 'off'])
@pytest.mark.parametrize('page', ['mixed', 'all_zero', 'nonpositive', 'positive_sentinel'])
def test_run_gauge_excludes_invalid_enqueue_clocks_without_changing_discovery(source, proof, monkeypatch, order, page):
    horizon = datetime(2026, 11, 9, tzinfo=timezone.utc)
    stamp = horizon.timestamp()
    enqueued, expected = {
        'mixed': ([0, stamp - 7200, stamp - 3600], 7200),
        'all_zero': ([0, 0], 0),
        'nonpositive': ([-1, 0], 0),
        # Main's shared guard accepts every positive finite clock. Repair and
        # worker must agree, including a positive sentinel; no private floor.
        'positive_sentinel': ([1, stamp - 3600], stamp - 1),
    }[page]

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return horizon

    monkeypatch.setattr(cluster, 'datetime', FrozenDatetime)
    monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', order)
    jobs = OrderedJobsClient([pending_job(i, clock) for i, clock in enumerate(enqueued)])
    # The metric-free call remains the discovery/repair selection oracle.
    expected_rows, expected_saturated, expected_cursor = cluster.discover_jobs(jobs, budget=SweepBudget(60))
    samples = []
    assert cluster.discover_jobs(jobs, budget=SweepBudget(60), metric_ages=samples) == (
        expected_rows,
        expected_saturated,
        expected_cursor,
    )
    assert len(expected_rows) == len(enqueued)
    assert max(samples, default=0) == expected
    assert dict(expected_rows) == {
        f'users/synthetic/conversations/capture-{i}': None if clock <= 0 else max(0, int(stamp - clock))
        for i, clock in enumerate(enqueued)
    }  # Invalid rows are still repaired with upstream's metrics-only age representation.

    cursor_state = CursorClient()
    client = SimpleNamespace(
        collection=lambda name: (
            SimpleNamespace(document=lambda _: cursor_state)
            if name == 'batch_pipeline_prod_maintenance'
            else jobs.collection(name)
        ),
        document=jobs.document,
    )
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', proof)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: SERVER)
    monkeypatch.setattr(config, 'jobs_enabled', lambda: True)
    monkeypatch.setattr(config, 'settings', lambda: (16, 240, 1500, 'plan'))
    monkeypatch.setattr(cluster, 'discover', lambda *args, **kwargs: ([], False, None))

    def work(rows, **kwargs):
        assert rows == expected_rows
        assert cluster.REPAIR_OLDEST._value.get() == expected
        return {'rows': len(rows), 'dispositions': {}}

    monkeypatch.setattr(cluster, 'coordinate', work)
    previous = cluster.REPAIR_OLDEST._value.get()
    try:
        assert cluster.run()['outcome'] == 'ok'
    finally:
        cluster.REPAIR_OLDEST.set(previous)


@pytest.mark.parametrize('ages,expected', [([None, 1000], 1000), ([None], 0)])
def test_run_gauge_excludes_absent_conversation_ages(source, proof, monkeypatch, ages, expected):
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: CursorClient())
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', proof)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: SERVER)
    monkeypatch.setattr(config, 'jobs_enabled', lambda: False)
    monkeypatch.setattr(config, 'settings', lambda: (16, 240, 1500, 'plan'))
    rows = [(f'users/synthetic/conversations/capture-{i}', age) for i, age in enumerate(ages)]
    monkeypatch.setattr(cluster, 'discover', lambda *args, **kwargs: (rows, False, None))

    def work(selected, **kwargs):
        assert selected == rows
        assert cluster.REPAIR_OLDEST._value.get() == expected
        return {'rows': len(selected), 'dispositions': {}}

    monkeypatch.setattr(cluster, 'coordinate', work)
    previous = cluster.REPAIR_OLDEST._value.get()
    try:
        assert cluster.run()['outcome'] == 'ok'
    finally:
        cluster.REPAIR_OLDEST.set(previous)


@pytest.mark.parametrize('setting', [None, 'on', 'typo'])
def test_jobs_newest_first_ties_resume_encrypted_and_wrap(monkeypatch, setting):
    from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor

    monkeypatch.delenv('RECORD_SEAL_REPAIR_AGE_ORDER', raising=False)
    if setting:
        monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', setting)
    docs = [pending_job(0, 200), pending_job(1, 100), pending_job(2, 100)]
    expected = sorted(docs, key=lambda d: (d.to_dict()['enqueued_at'], d.id), reverse=True)
    client, budget, selected = OrderedJobsClient(docs), SweepBudget(60), {}
    state = CursorClient()
    frontier = RepairCursor(
        SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: state)), b'k' * 32, jobs=True
    )
    observed, after = [], None
    for doc in expected:
        rows, saturated, after = cluster.discover_jobs(
            client, budget=budget, after=after, max_rows=1, selected_cursors=selected
        )
        assert saturated and rows[0][0].endswith(doc.to_dict()['conversation_id'])
        assert selected[rows[0][0]] == after
        observed += rows
        frontier.write(after, budget)
        after = frontier.read(budget)
    assert len(observed) == 3
    assert cluster.discover_jobs(client, budget=budget, after=after) == ([], False, None)
    assert cluster.discover_jobs(client, budget=budget, max_rows=1)[0][0] == observed[0]
    assert b'synthetic' not in state.state['cursor']
    assert client.queries[0].filters[0] == ('state', '==', 'record_pending')
    assert client.queries[0].filters[1] == ('enqueued_at', '<=', after['horizon'].timestamp())


def test_jobs_frozen_horizon_wraps_despite_new_inflow(monkeypatch):
    monkeypatch.delenv('RECORD_SEAL_REPAIR_AGE_ORDER', raising=False)
    client = OrderedJobsClient([pending_job(0), pending_job(1, 100)])
    first, _, cursor = cluster.discover_jobs(client, budget=SweepBudget(60), max_rows=1)
    horizon = cursor['horizon']
    client.documents.extend(pending_job(i, horizon.timestamp() + i) for i in range(2, 42))
    second, _, cursor = cluster.discover_jobs(client, budget=SweepBudget(60), after=cursor, max_rows=1)
    assert len(second) == 1 and first != second and cursor['horizon'] == horizon
    assert cluster.discover_jobs(client, budget=SweepBudget(60), after=cursor) == ([], False, None)
    assert cluster.discover_jobs(client, budget=SweepBudget(60), max_rows=1)[0] == first


@pytest.mark.parametrize('enqueued', [None, 'old', True, float('nan'), float('inf'), -float('inf'), 'missing'])
def test_jobs_unknown_enqueue_clock_stays_ineligible_in_both_orders(monkeypatch, enqueued):
    doc = pending_job(0, enqueued)
    if enqueued == 'missing':
        data = doc.to_dict()
        data.pop('enqueued_at')
        doc.to_dict = lambda: data
    for mode in ('off', 'on'):
        monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', mode)
        rows, _, _ = cluster.discover_jobs(OrderedJobsClient([doc, pending_job(1)]), budget=SweepBudget(60))
        assert [path for path, _ in rows] == ['users/synthetic/conversations/capture-1']


def test_jobs_age_filter_and_page_bounds_remain_local(monkeypatch):
    monkeypatch.delenv('RECORD_SEAL_REPAIR_AGE_ORDER', raising=False)
    horizon = datetime.now(timezone.utc)
    stamp = horizon.timestamp() - config.JOBS_MIN_AGE_SECONDS
    client = OrderedJobsClient([pending_job(0, stamp), pending_job(1, stamp + 1), pending_job(2, stamp - 1)])
    cursor = {'path': 'batch_pipeline_prod_jobs/', 'enqueued_at': horizon.timestamp(), 'horizon': horizon}
    rows, saturated, cursor = cluster.discover_jobs(client, budget=SweepBudget(60), after=cursor, max_scan=1)
    assert rows == [] and saturated
    rows, _, cursor = cluster.discover_jobs(client, budget=SweepBudget(60), after=cursor)
    assert rows == [
        ('users/synthetic/conversations/capture-0', config.JOBS_MIN_AGE_SECONDS),
        ('users/synthetic/conversations/capture-2', config.JOBS_MIN_AGE_SECONDS + 1),
    ]
    assert cursor is None
    assert all(q.cap <= 128 for q in client.queries)


@pytest.mark.parametrize('setting', ['off', 'false', '0'])
def test_jobs_kill_switch_restores_exact_old_hash_scan(monkeypatch, setting):
    from tests.unit.test_record_pending_repair import JobsClient, job_doc

    monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', setting)
    # Ages deliberately oppose hash order. Compare the old adapter's result,
    # page limits and cursor exactly, including resumption from a legacy cursor.
    docs = sorted([job_doc(i, i * 100) for i in range(6)], key=lambda d: d.id)
    horizon = datetime.now(timezone.utc)
    after = {'path': docs[0].reference.path, 'finished_at': horizon}
    expected = cluster.discover_jobs(JobsClient(docs), budget=SweepBudget(60), after=after, max_rows=2)
    for doc in docs:
        original = doc.to_dict()
        doc.to_dict = lambda data=original: {**data, 'state': 'record_pending'}
    client = OrderedJobsClient(docs)
    actual = cluster.discover_jobs(client, budget=SweepBudget(60), after=after, max_rows=2)
    assert actual == expected
    assert client.queries[0].filters == [('state', '==', 'record_pending')]
    assert client.queries[0].order == ['__name__']


def test_jobs_switching_orders_restarts_at_newest_head(monkeypatch):
    client = OrderedJobsClient([pending_job(0), pending_job(1, 1)])
    monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', 'off')
    _, _, old = cluster.discover_jobs(client, budget=SweepBudget(60), max_rows=1)
    monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', 'on')
    rows, _, age = cluster.discover_jobs(client, budget=SweepBudget(60), after=old, max_rows=1)
    assert rows[0][0].endswith('capture-1') and client.queries[-1].after is None
    monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', 'off')
    cluster.discover_jobs(client, budget=SweepBudget(60), after=age, max_rows=1)
    assert client.queries[-1].after is None


def test_jobs_missing_index_falls_back_resumes_hash_and_logs_once(monkeypatch):
    monkeypatch.delenv('RECORD_SEAL_REPAIR_AGE_ORDER', raising=False)
    monkeypatch.setattr(cluster, '_age_order_index_warned', False)
    telemetry = Mock()
    monkeypatch.setattr(cluster, 'record_fallback', telemetry)
    client = OrderedJobsClient(
        [pending_job(i) for i in range(3)],
        cluster.FailedPrecondition('The query requires an index private@example.invalid'),
    )
    progress, seen, cursor = [], [], None
    for _ in range(4):
        rows, _, cursor = cluster.discover_jobs(
            client, budget=SweepBudget(60), after=cursor, max_rows=1, progress=progress.append
        )
        seen += [path for path, _ in rows]
    assert len(set(seen)) == len(seen) == 3 and cursor is None
    telemetry.assert_called_once_with(
        component='firestore_read',
        from_mode='record_seal_age_order',
        to_mode='record_seal_hash_order',
        reason='other',
        outcome='degraded',
    )
    assert progress == [{'event': 'record_seal_repair_age_order', 'outcome': 'missing_index_hash_order'}]
    assert 'private' not in json.dumps(progress)
    # A saved age cursor also falls back from the hash head, never a hash offset.
    age = {'path': client.documents[-1].reference.path, 'enqueued_at': 0, 'horizon': datetime.now(timezone.utc)}
    assert cluster.discover_jobs(client, budget=SweepBudget(60), after=age, max_rows=1)[0]
    assert client.queries[-1].after is None


@pytest.mark.parametrize('error', [cluster.FailedPrecondition('unrelated precondition'), RuntimeError('unavailable')])
def test_jobs_other_read_errors_are_not_hidden(monkeypatch, error):
    monkeypatch.delenv('RECORD_SEAL_REPAIR_AGE_ORDER', raising=False)
    client = OrderedJobsClient([], error)
    with pytest.raises(type(error)):
        cluster.discover_jobs(client, budget=SweepBudget(60))
    assert len(client.queries) == 1


@pytest.mark.parametrize('enqueued', [1.123456789012345, 2**53 + 1, -float('inf'), float('nan')])
def test_jobs_numeric_cursor_round_trips_without_datetime_rounding(enqueued):
    from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor

    state = CursorClient()
    frontier = RepairCursor(
        SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: state)), b'k' * 32, jobs=True
    )
    cursor = {
        'path': 'batch_pipeline_prod_jobs/synthetic',
        'enqueued_at': enqueued,
        'horizon': datetime.now(timezone.utc),
    }
    frontier.write(cursor, SweepBudget(60))
    actual = frontier.read(SweepBudget(60))
    if math.isnan(enqueued):
        assert math.isnan(actual.pop('enqueued_at'))
        cursor.pop('enqueued_at')
    assert actual == cursor


def test_jobs_age_indexes_are_owned_once_by_batch_registry_in_both_stages():
    from database.batch_pipeline_indexes import BATCH_PIPELINE_INDEX_REQUIREMENTS
    from database.firestore_index_registry import INDEX_REQUIREMENTS, firebase_index_manifest

    manifest = firebase_index_manifest()['indexes']
    for stage in ('prod', 'dev'):
        requirement = next(
            r for r in BATCH_PIPELINE_INDEX_REQUIREMENTS if r.identifier == f'batch_pipeline_{stage}_result_ready'
        )
        assert requirement.collection_group == f'batch_pipeline_{stage}_jobs'
        assert requirement.query_scope == 'COLLECTION'
        assert [(f.field_path, f.order) for f in requirement.fields] == [
            ('state', 'ASCENDING'),
            ('enqueued_at', 'ASCENDING'),
            ('__name__', 'ASCENDING'),
        ]
        assert sum(r.signature == requirement.signature for r in INDEX_REQUIREMENTS) == 1
        assert manifest.count(requirement.to_manifest()) == 1


@pytest.mark.parametrize('mode', ['off', 'on'])
@pytest.mark.parametrize('bad_clock', [0, -100])
def test_invalid_job_clock_is_repaired_but_excluded_from_age_metrics(monkeypatch, mode, bad_clock):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', mode)
    now = 1800000000
    monkeypatch.setattr(cluster, 'datetime', SimpleNamespace(now=lambda _: datetime.fromtimestamp(now, timezone.utc)))
    docs = [pending_job(0, bad_clock), pending_job(1, now - 10000)]
    rows, _, _ = cluster.discover_jobs(OrderedJobsClient(docs), budget=SweepBudget(60))
    assert dict(rows) == {
        'users/synthetic/conversations/capture-0': None,
        'users/synthetic/conversations/capture-1': 10000,
    }
    report, children, _, order, progress = scheduling(rows)
    assert order == [path for path, _ in rows]
    assert report['dispositions'] == {'sealed': 2}
    assert all(child.reaped for child in children)
    assert report['oldest_unsealed_seconds'] == report['oldest_seal_age_seconds'] == 10000
    assert report['invalid_clock_rows'] == 1
    assert ['seal_age_seconds' in row for row in progress] == [age is not None for _, age in rows]
    json.dumps(report, allow_nan=False)


def test_all_invalid_clocks_keep_summary_finite_and_count_attempts():
    report, _, _, order, progress = scheduling([('zero-clock', None)], outcomes={'zero-clock': (2, 'sealed', 0)})
    assert order == ['zero-clock']
    assert report['invalid_clock_rows'] == 1
    assert report['oldest_unsealed_seconds'] == report['oldest_seal_age_seconds'] == 0
    assert 'seal_age_seconds' not in progress[0]
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('clock', [0, -1, None, True, 'old', float('nan'), float('inf'), -float('inf')])
def test_metric_clock_rejects_nonpositive_nonfinite_or_nonnumeric(clock):
    assert not cluster.valid_metric_clock(clock)


@pytest.mark.parametrize('bad_stamp', [0, -100])
def test_invalid_conversation_finish_clock_preserves_selection(monkeypatch, bad_stamp):
    now = 1800000000
    monkeypatch.setattr(cluster.time, 'time', lambda: now)
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.select.return_value = query
    query.limit.return_value = query
    query.stream.return_value = [
        SimpleNamespace(
            reference=SimpleNamespace(path=path),
            to_dict=lambda stamp=stamp: {'finished_at': datetime.fromtimestamp(stamp, timezone.utc)},
        )
        for path, stamp in [('invalid', bad_stamp), ('normal', now - 1000)]
    ]
    rows, saturated, cursor = cluster.discover(
        SimpleNamespace(collection_group=lambda _: query), budget=SweepBudget(60)
    )
    assert rows == [('invalid', None), ('normal', 1000)]
    assert saturated is False and cursor is None


@pytest.mark.parametrize('diagnostics', [False, True])
@pytest.mark.parametrize('pending', [False, True])
def test_active_full_repair_counts_shadow_lease_would_expire(source, monkeypatch, diagnostics, pending):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'shadow')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', '1')
    monkeypatch.setattr(producer.time, 'time', lambda: 10000)
    store, client, artifacts = source
    client.rows[PATH]['record_upload_sessions'] = {
        'old': {
            'pod': 'live',
            'process_started_at': 1,
            'last_signal_at': 1,
            'lease_expires_at': 3601,
            'signal_source': 'frames',
        }
    }
    if pending:
        client.rows[JOB_PATH] = {
            'segment_id': JOB_PATH[1],
            'owner_id': 'synthetic',
            'conversation_id': 'capture',
            'record_content_id': 'record',
            'privacy_generation': 0,
            'state': 'record_pending',
        }
    proof = producer.parse_pusher_pod_proof(
        json.dumps(inventory([pod('live', 1)])).encode(), datetime.fromtimestamp(9999, timezone.utc).isoformat()
    )
    before = record_token_lease_metrics.EXPIRED_WOULD._value.get()
    observed = {} if diagnostics else None
    assert (
        cluster.repair_one(
            store,
            object(),
            artifacts,
            SCOPE[0],
            flags=SERVER,
            inventory=lambda: proof,
            budget=SweepBudget(30),
            reason_out=observed,
        )
        == 'upload_pending'
    )
    assert record_token_lease_metrics.EXPIRED_WOULD._value.get() == before + 1
    if observed is not None:
        assert observed['lease_reason'] == 'lease_would_expire'

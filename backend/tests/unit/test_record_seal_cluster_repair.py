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

    def tail(*_):
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
    rows, saturated = cluster.discover(SimpleNamespace(collection_group=lambda _: query), budget=SweepBudget(60))
    assert [path for path, _ in rows] == ['oldest'] and not saturated
    assert query.orders == ['finished_at', '__name__'] * 2


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

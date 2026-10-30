"""Operator pacing, receipt/restart and first-canary-error boundaries."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from testing.import_isolation import load_module_fresh


@pytest.fixture
def operator():
    return load_module_fresh(
        'stuck_backfill_operator', str(Path(__file__).resolve().parents[2] / 'scripts/stuck_backfill.py')
    )


@pytest.fixture
def runtime(operator, monkeypatch, tmp_path):
    monkeypatch.setattr(operator, 'check_enabled', lambda *_: None)
    monkeypatch.setattr(operator.db, 'revision', lambda _: 'closed')
    monkeypatch.setattr(operator.time, 'sleep', lambda _: None)
    reserve = Mock(return_value=0.0)
    monkeypatch.setattr(operator.db, 'reserve_admission', reserve)
    ref = Mock()
    client = SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: ref))
    # users/{owner}/conversations/{id} readback for noise close
    ref.collection.return_value.document.return_value.get.return_value = object()
    args = SimpleNamespace(receipts_dir=tmp_path / 'receipts', batch_size=1, job_timeout=5, spend_receipts=None)
    return client, args, ref, reserve


def plan(kind, n=2):
    return {
        'run_id': 'run',
        'max_modeled_usd': 100.0,
        'cutoff': '2026-10-22T02:17:14.930173Z',
        'rows': [
            {
                'uid': 'private-owner',
                'id': f'private-conversation-{i}',
                'kind': kind,
                'revision': '2026-10-22T00:00:00.123456789Z',
                'session_revision': None,
                'modeled_usd': 0.0033 if kind == 'substantive' else 0.0,
            }
            for i in range(n)
        ],
    }


def test_unknown_actual_spend_blocks_expansion_and_receipt_is_counts_only(operator, runtime, monkeypatch, capsys):
    client, args, ref, reserve = runtime
    request = Mock(return_value={'created': True, 'route': 'cloud_tasks', 'job_id': 'job'})
    monkeypatch.setattr(operator.lifecycle, 'request_finalization', request)
    monkeypatch.setattr(operator, 'wait_job', lambda *_: {'closed_revision': 'closed', 'job_id': 'job'})
    with pytest.raises(operator.db.BackfillConflict, match='actual_spend_reconciliation_required'):
        operator.apply(client, plan('substantive'), 'digest', args)
    assert request.call_count == reserve.call_count == 1
    receipt = json.loads((args.receipts_dir / 'batch-00001.private.json').read_text())
    assert receipt['complete'] is True and receipt['actual_spend_usd'] is None
    assert receipt['modeled_upper_usd'] == 0.0033
    assert receipt['entries'][0]['uid'] == 'private-owner'
    output = capsys.readouterr().out
    assert 'private-owner' not in output and 'private-conversation' not in output
    assert request.call_args.kwargs['trigger'] is operator.ProcessingTrigger.SILENT_BACKFILL
    assert request.call_args.kwargs['require_cloud_tasks'] is True


def test_noise_only_batches_have_proven_zero_provider_spend(operator, runtime, monkeypatch):
    client, args, ref, reserve = runtime
    close = Mock(return_value='closed')
    monkeypatch.setattr(operator.lifecycle, 'close_stuck_backfill_noise', close)
    operator.apply(client, plan('noise'), 'digest', args)
    assert close.call_count == reserve.call_count == 2
    for batch in [1, 2]:
        receipt = json.loads((args.receipts_dir / f'batch-{batch:05d}.private.json').read_text())
        assert receipt['complete'] and receipt['actual_spend_usd'] == 0.0
    # Safe resume skips known completed noise rather than closing twice.
    operator.apply(client, plan('noise'), 'digest', args)
    assert close.call_count == 2


def test_first_canary_refusal_disables_shared_run_and_preserves_incomplete_journal(operator, runtime, monkeypatch):
    client, args, ref, reserve = runtime
    request = Mock(return_value={'created': False, 'route': 'noop'})
    monkeypatch.setattr(operator.lifecycle, 'request_finalization', request)
    with pytest.raises(operator.db.BackfillConflict, match='admission_not_dispatched'):
        operator.apply(client, plan('substantive'), 'digest', args)
    assert request.call_count == reserve.call_count == 1
    ref.update.assert_called_once_with({'enabled': False})
    receipt = json.loads((args.receipts_dir / 'batch-00001.private.json').read_text())
    assert not receipt['complete']
    with pytest.raises(operator.db.BackfillConflict, match='incomplete_batch_requires_review'):
        operator.apply(client, plan('substantive'), 'digest', args)
    assert request.call_count == 1


def test_pacing_wait_rechecks_switch_before_admitting(operator, runtime, monkeypatch):
    client, args, ref, reserve = runtime
    reserve.side_effect = [1.0, 0.0]
    checks = Mock()
    monkeypatch.setattr(operator, 'check_enabled', checks)
    monkeypatch.setattr(operator.lifecycle, 'close_stuck_backfill_noise', Mock(return_value='closed'))
    operator.apply(client, plan('noise', 1), 'digest', args)
    assert reserve.call_count == 2 and checks.call_count == 2


def test_private_artifacts_refuse_symlinks_overwrite_and_world_readable_inputs(operator, tmp_path):
    path = tmp_path / 'plan.json'
    operator.private_write(path, {'rows': []})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        operator.private_write(path, {})
    link = tmp_path / 'link'
    link.symlink_to(path)
    with pytest.raises(operator.db.BackfillConflict, match='private_file_required'):
        operator.private_read(link)
    path.chmod(0o644)
    with pytest.raises(operator.db.BackfillConflict, match='0600'):
        operator.private_read(path)


def test_t2_preview_plan_pins_adjustable_100_dollar_default(operator):
    from datetime import datetime, timedelta, timezone

    query = Mock()
    query.where.return_value = query
    query.select.return_value = query
    query.limit.return_value = query
    query.stream.return_value = iter([])
    user = SimpleNamespace(collection=lambda _: query)
    client = SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: user))
    preview = operator.make_plan(
        client, {'synthetic-owner'}, datetime.now(timezone.utc) - timedelta(hours=2), 1000, 60, 100
    )
    assert preview['thresholds'] == {'seconds': 60, 'words': 100}
    assert preview['max_modeled_usd'] == 100.0
    assert operator.parse_time(preview['cutoff']).isoformat() == preview['cutoff']


def test_reconciled_actual_over_cap_disables_run(operator, runtime):
    client, args, ref, reserve = runtime
    with pytest.raises(operator.db.BackfillConflict, match='actual_budget_exceeded'):
        operator.enforce_actual_budget(client, plan('noise'), 100.01)
    ref.update.assert_called_once_with({'enabled': False})
    reserve.assert_not_called()


def test_resume_with_changed_batch_size_refuses_instead_of_skipping_items(operator, runtime, monkeypatch):
    client, args, ref, reserve = runtime
    close = Mock(return_value='closed')
    monkeypatch.setattr(operator.lifecycle, 'close_stuck_backfill_noise', close)
    operator.apply(client, plan('noise', 2), 'digest', args)
    args.batch_size = 2
    with pytest.raises(operator.db.BackfillConflict, match='incomplete_batch_requires_review'):
        operator.apply(client, plan('noise', 2), 'digest', args)
    assert close.call_count == 2


def test_completed_but_budget_deferred_row_is_not_operator_success(operator, runtime, monkeypatch):
    client, args, ref, reserve = runtime
    item = plan('substantive', 1)['rows'][0]
    job = {
        'uid': item['uid'],
        'conversation_id': item['id'],
        'processing_trigger': 'silent_backfill',
        'delivery_policy': operator.db.POLICY,
        'backfill_run_id': 'run',
        'dispatch_generation': 1,
        'status': 'completed',
        'fanout_status': 'completed',
        'terminal_outcome': 'success',
    }
    monkeypatch.setattr(operator.jobs, 'get_finalization_job', lambda *_args, **_kwargs: job)
    row = {
        'status': 'completed',
        'finalization_job_id': 'job',
        'terminal_no_derived_effects': True,
        'processing_deferred': True,
    }
    ref.collection.return_value.document.return_value.get.return_value = SimpleNamespace(to_dict=lambda: row)
    with pytest.raises(operator.db.BackfillConflict, match='canary_row_failed'):
        operator.wait_job(
            client, plan('substantive', 1), 'digest', item, {'job_id': 'job', 'dispatch_generation': 1}, 1
        )


@pytest.mark.parametrize('suffix', ['Z', '+00:00'])
def test_parse_time_accepts_plan_cutoff_without_losing_nanoseconds(operator, suffix):
    stamp = operator.parse_time('2026-10-22T02:17:14.123456789' + suffix)
    assert stamp.rfc3339() == '2026-10-22T02:17:14.123456789Z'


@pytest.mark.parametrize('failures', [1, 3, 4])
def test_noise_contention_backoff_and_journal(operator, runtime, monkeypatch, capsys, failures):
    from google.api_core.exceptions import Aborted

    client, args, ref, reserve = runtime
    sleep = Mock()
    monkeypatch.setattr(operator.time, 'sleep', sleep)

    # Exercise the actual lifecycle/database close and SDK transactional wrapper.
    # No writes are applied: this fake fails at the SDK commit boundary.
    class ContendedTransaction:
        _read_only = False
        _max_attempts = 5
        _id = None

        def _clean_up(self):
            self._id = None

        def _begin(self, retry_id=None):
            self._id = retry_id or b'fake-transaction'

        def _commit(self):
            raise Aborted('concurrent writer')

        def _rollback(self):
            pass

    client.transaction = Mock(side_effect=lambda: ContendedTransaction())
    monkeypatch.setattr(operator.db, '_close_txn', lambda *_: None)
    real_close = operator.lifecycle.close_stuck_backfill_noise
    attempts = 0

    def close(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts <= failures:
            return real_close(*args, **kwargs)
        return 'closed'

    monkeypatch.setattr(operator.lifecycle, 'close_stuck_backfill_noise', close)
    cohort = plan('noise', 2)
    operator.apply(client, cohort, 'digest', args)
    receipt = json.loads((args.receipts_dir / 'batch-00001.private.json').read_text())
    assert receipt['complete'] and receipt['actual_spend_usd'] == 0.0
    assert reserve.call_count == 2  # retries never reserve another admission
    assert [call.args[0] for call in sleep.call_args_list] == [5, 10, 15][: min(failures, 3)]
    entry = receipt['entries'][0]
    if failures == 4:
        assert receipt['counts'] == {'reserved': 1, 'skipped_close_contention': 1}
        assert entry['kind'] == 'skipped_close_contention'
        assert 'closed_revision' not in entry  # restore must ignore this entry
        assert entry['revision'] == cohort['rows'][0]['revision']
    else:
        assert receipt['counts'] == {'reserved': 1, 'noise': 1}
        assert entry['closed_revision'] == 'closed'
    ref.update.assert_not_called()  # contention does not disable the cohort
    assert attempts == min(failures + 1, 4) + 1  # next row still runs
    operator.apply(client, cohort, 'digest', args)
    assert attempts == min(failures + 1, 4) + 1  # completed journal is resumable
    output = capsys.readouterr().out
    assert 'private-owner' not in output and 'private-conversation' not in output


@pytest.mark.parametrize('error', [ValueError('bad cutoff'), RuntimeError('permission denied')])
def test_non_contention_errors_stop_without_retry(operator, runtime, monkeypatch, error):
    client, args, ref, _ = runtime
    close = Mock(side_effect=error)
    monkeypatch.setattr(operator.lifecycle, 'close_stuck_backfill_noise', close)
    with pytest.raises(type(error), match=str(error)):
        operator.apply(client, plan('noise', 1), 'digest', args)
    assert close.call_count == 1
    ref.update.assert_called_once_with({'enabled': False})
    receipt = json.loads((args.receipts_dir / 'batch-00001.private.json').read_text())
    assert not receipt['complete'] and receipt['entries'] == []


def test_stop_json_includes_error_and_cause(operator, monkeypatch, capsys):
    from google.api_core.exceptions import Aborted

    def fail():
        try:
            raise Aborted('concurrent writer')
        except Aborted as cause:
            raise ValueError('Failed to commit transaction in 5 attempts.') from cause

    monkeypatch.setattr(operator, 'main', fail)
    with pytest.raises(SystemExit) as stopped:
        operator.cli()
    assert stopped.value.code == 1
    details = json.loads(capsys.readouterr().err)
    assert details['error_type'] == 'ValueError'
    assert details['error_message'] == 'Failed to commit transaction in 5 attempts.'
    assert details['cause_type'] == 'Aborted'
    assert 'concurrent writer' in details['cause_message']


def test_skip_is_durable_before_later_row_stops(operator, runtime, monkeypatch):
    from google.api_core.exceptions import Aborted

    client, args, ref, _ = runtime
    args.batch_size = 2
    close = Mock(side_effect=[Aborted('hot row')] * 4 + [ValueError('invalid next row')])
    monkeypatch.setattr(operator.lifecycle, 'close_stuck_backfill_noise', close)
    with pytest.raises(ValueError, match='invalid next row'):
        operator.apply(client, plan('noise', 2), 'digest', args)
    receipt = json.loads((args.receipts_dir / 'batch-00001.private.json').read_text())
    assert not receipt['complete']
    assert len(receipt['entries']) == 1
    assert receipt['entries'][0]['kind'] == 'skipped_close_contention'
    assert 'closed_revision' not in receipt['entries'][0]

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

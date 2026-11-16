"""Dark, post-commit projection hold attribution through the production writers."""

from copy import deepcopy
import logging
from unittest.mock import Mock

import pytest

from config.policy import ProjectionPolicy
from config.policy.kill_switches import kill_switch
from database.batch_pipeline_projection_protocol import ProjectionGenerationAmbiguous, ProjectionReplay
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreTransaction
from tests.unit.test_batch_pipeline_hold_recovery import real_projection  # noqa: F401
from utils.batch_pipeline import projection_disposition
from utils.batch_pipeline.projection_hold_observability import log_projection_hold
from utils.sync.assignment_errors import SyncAssignmentConflict, SyncAssignmentConflictReason

FLAG = 'BATCH_PIPELINE_PROJECTION_HOLD_LOG_ENABLED'
REASONS = ['ambiguous_generation', 'conflict', 'poison_head', 'payload_contract', 'sibling']


def hold_lines(caplog):
    return [record for record in caplog.records if 'hold_reason=' in record.getMessage()]


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('reason', REASONS)
def test_each_writer_emits_once_only_after_success(real_projection, monkeypatch, caplog, reason, enabled):
    lane = real_projection
    monkeypatch.setenv(FLAG, str(enabled).lower())
    caplog.set_level(logging.INFO)
    store = lane.projector.store
    if reason == 'poison_head':
        assert lane.projector.resolve_failing_head('unit', lane.job, lane.entry, lane.binding, RuntimeError('private'))
    elif reason == 'sibling':
        lane.entry.update(
            projection={'state': 'quarantined'},
            projection_parts={'0': {'state': 'quarantined'}, '1': {'state': 'persisted'}},
            projection_part_count=2,
        )
        store.ready('unit', lane.binding, 30000, part_index=1, policy=ProjectionPolicy())
    else:
        if reason == 'ambiguous_generation':
            monkeypatch.setattr(store, 'check', Mock(side_effect=ProjectionGenerationAmbiguous('private')))
        elif reason == 'conflict':
            monkeypatch.setattr(
                store,
                'check',
                Mock(
                    side_effect=SyncAssignmentConflict(
                        'private', subtype=SyncAssignmentConflictReason.RECORD_TARGET_DISCARDED
                    )
                ),
            )
        else:
            lane.projector.load_result = Mock(return_value=[])
        lane.projector.assign_parts(
            lane.work, lane.entry, lane.binding, finish=False, policy=ProjectionPolicy(), job=lane.job
        )
    assert lane.entry['projection_state'] == 'quarantine_held'
    assert [record.getMessage() for record in hold_lines(caplog)] == (
        [f'event=batch_projection outcome=quarantine_persisted hold_reason={reason}'] if enabled else []
    )
    assert all(record.levelno == logging.INFO for record in hold_lines(caplog))
    assert not any(FLAG in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize('parts', [None, 'incomplete', 'complete'])
def test_single_and_multipart_persist_preserve_identical_off_writes(real_projection, monkeypatch, caplog, parts):
    lane = real_projection
    initial = deepcopy(lane.client.rows)
    if parts == 'complete':
        lane.entry['projection_parts'] = {'1': {'state': 'ready'}}
        initial = deepcopy(lane.client.rows)
    snapshots, logs = [], []
    for enabled in (False, True):
        lane.client.rows.clear()
        lane.client.rows.update(deepcopy(initial))
        monkeypatch.setenv(FLAG, str(enabled).lower())
        caplog.clear()
        caplog.set_level(logging.INFO)
        session = lane.projector.store.session(
            'unit',
            lane.binding,
            30000,
            policy=ProjectionPolicy(),
            **({'part_index': 0, 'part_count': 2} if parts else {}),
        )
        projection_disposition.persist_disposition(session, quarantined=True, hold_reason='ambiguous_generation')
        snapshots.append(deepcopy(lane.client.rows))
        logs.append([r.getMessage() for r in caplog.records if 'hold_reason=' not in r.getMessage()])
        assert len(hold_lines(caplog)) == int(enabled)
    assert snapshots[0] == snapshots[1]
    assert logs[0] == logs[1]


@pytest.mark.parametrize('error', [RuntimeError('private'), ProjectionReplay({'state': 'quarantined'})])
def test_failed_or_replayed_disposition_has_no_success_line(monkeypatch, caplog, error):
    monkeypatch.setenv(FLAG, 'true')
    caplog.set_level(logging.INFO)
    session = Mock()
    session.persist_empty.side_effect = error
    if isinstance(error, ProjectionReplay):
        assert projection_disposition.persist_disposition(session, quarantined=True) == error.receipt
    else:
        with pytest.raises(RuntimeError):
            projection_disposition.persist_disposition(session, quarantined=True)
    assert not hold_lines(caplog)


@pytest.mark.parametrize('enabled', [False, True])
def test_sibling_receipt_replay_logs_only_the_first_transition(real_projection, monkeypatch, caplog, enabled):
    lane = real_projection
    lane.entry.update(
        projection={'state': 'quarantined'},
        projection_state='persisted',
        projection_parts={'0': {'state': 'quarantined'}, '1': {'state': 'persisted'}},
        projection_part_count=2,
    )
    monkeypatch.setenv(FLAG, str(enabled).lower())
    caplog.set_level(logging.INFO)
    first = lane.projector.store.ready('unit', lane.binding, 30000, part_index=1, policy=ProjectionPolicy())
    committed = deepcopy(lane.client.rows)
    assert len(hold_lines(caplog)) == int(enabled)
    second = lane.projector.store.ready('unit', lane.binding, 30001, part_index=1, policy=ProjectionPolicy())
    assert first == second == {'state': 'ready'}
    assert lane.client.rows == committed
    assert [record.getMessage() for record in hold_lines(caplog)] == (
        ['event=batch_projection outcome=quarantine_persisted hold_reason=sibling'] if enabled else []
    )


@pytest.mark.parametrize(
    'summary_state,projection_state',
    [('persisted', 'persisted'), ('quarantined', 'persisted'), ('persisted', 'quarantine_held')],
)
def test_first_sibling_hold_transition_logs_once(real_projection, monkeypatch, caplog, summary_state, projection_state):
    lane = real_projection
    lane.entry.update(
        projection={'state': summary_state},
        projection_state=projection_state,
        projection_parts={'0': {'state': 'quarantined'}, '1': {'state': 'persisted'}},
        projection_part_count=2,
    )
    monkeypatch.setenv(FLAG, 'true')
    caplog.set_level(logging.INFO)
    lane.projector.store.ready('unit', lane.binding, 30000, part_index=1, policy=ProjectionPolicy())
    assert lane.entry['projection']['state'] == 'quarantined'
    assert lane.entry['projection_state'] == 'quarantine_held'
    assert [record.getMessage() for record in hold_lines(caplog)] == [
        'event=batch_projection outcome=quarantine_persisted hold_reason=sibling'
    ]


def test_sibling_commit_failure_has_no_success_line(real_projection, monkeypatch, caplog):
    lane = real_projection
    lane.entry.update(
        projection={'state': 'quarantined'},
        projection_parts={'0': {'state': 'quarantined'}, '1': {'state': 'persisted'}},
        projection_part_count=2,
    )
    monkeypatch.setenv(FLAG, 'true')
    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', Mock(side_effect=RuntimeError('commit failed')))
    caplog.set_level(logging.INFO)
    with pytest.raises(RuntimeError):
        lane.projector.store.ready('unit', lane.binding, 30000, part_index=1, policy=ProjectionPolicy())
    assert not hold_lines(caplog)


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
@pytest.mark.parametrize('flag', [FLAG, 'BATCH_TIMELINESS_ALL_TIME_COUNTS_ENABLED'])
@pytest.mark.parametrize('value,expected', [(None, False), ('false', False), ('off', False), ('true', True)])
def test_dark_flags_are_strict_opt_ins_in_every_parser_mode(monkeypatch, caplog, mode, flag, value, expected):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    monkeypatch.delenv(flag, raising=False)
    if value is not None:
        monkeypatch.setenv(flag, value)
    caplog.set_level(logging.INFO)
    assert kill_switch(flag, log=False) is expected
    assert not caplog.records


def test_unknown_reason_is_never_logged(monkeypatch, caplog):
    monkeypatch.setenv(FLAG, 'true')
    with pytest.raises(ValueError, match='unregistered'):
        log_projection_hold('private user text')
    assert not hold_lines(caplog)

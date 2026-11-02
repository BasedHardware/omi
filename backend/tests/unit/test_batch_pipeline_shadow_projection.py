"""Production assignment planning without any customer-data write capability."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline import projection
from utils.sync import assignment
from utils.batch_pipeline.shadow_projection import plan, run
from utils.batch_pipeline.shadow_transaction import ShadowBoundaryError, ShadowTransaction, Reference


def item():
    return WorkItem(
        'synthetic-shadow', 'synthetic-owner', 172800, 'encrypted:shadow', 10, 2, privacy_generation=0, shadow=True
    )


def payload():
    return {
        'audio_seconds': 10,
        'speech_seconds': 2,
        'speech_spans': [{'start': 1, 'end': 3}],
        'words': [{'word': 'A useful synthetic sentence.', 'timestamp': [1, 3], 'speaker': '0'}],
        'diarization': {'turns': [{'start': 1, 'end': 3, 'speaker': '0'}]},
    }


def test_real_builder_and_assignment_plan_without_a_writer(monkeypatch):
    # These flags use the same pure decision paths as serving, without requiring
    # a live config/client in the hermetic test harness.
    monkeypatch.setattr(projection, 'cap_dispatch_enabled', lambda *args: False)
    monkeypatch.setattr(assignment, 'smart_merge_flatten_enabled', lambda: False)
    monkeypatch.setattr(assignment, 'sync_lineage_resolve_enabled', lambda: False)
    reads = []

    def read(path, fields, timeout):
        reads.append(path)
        return None

    result = plan(item(), payload(), {}, read, decode=deepcopy)
    assert result['status'] == 'planned'
    assert result['parts'] == 1 and result['planned_writes'] >= 2
    assert 0 < result['reads'] <= 16
    assert all(path[:2] == ('users', 'synthetic-owner') for path in reads)


def test_rejected_plan_has_no_customer_writer_and_does_not_retain_payload():
    tx = ShadowTransaction('owner', lambda *args: {'secret': 'synthetic'})
    ref = tx.user().collection('conversations').document('one')
    assert ref.get().to_dict() == {'secret': 'synthetic'}
    tx.set(ref, {'transcript_segments': ['private synthetic text']})
    assert tx.writes == 1 and not hasattr(tx, 'client')
    assert 'private synthetic text' not in repr(tx.__dict__)
    for call in (tx.commit, tx.delete):
        with pytest.raises(ShadowBoundaryError):
            call()
    with pytest.raises(ShadowBoundaryError, match='read_after_write'):
        ref.get()
    tx.close()
    assert not tx._cache


def test_capabilities_refuse_foreign_owner_real_references_and_excess_reads():
    reader = Mock(return_value=None)
    tx = ShadowTransaction('owner', reader, max_reads=1)
    with pytest.raises(ShadowBoundaryError, match='foreign_owner'):
        Reference(tx, ('users', 'another', 'conversations', 'one')).get()
    with pytest.raises(ShadowBoundaryError, match='foreign_write_reference'):
        tx.set(Mock(), {'x': 1})
    tx.user().collection('conversations').document('one').get()
    with pytest.raises(ShadowBoundaryError, match='read_budget'):
        tx.user().collection('conversations').document('two').get()
    assert reader.call_count == 1


@pytest.mark.parametrize('change', ['serving', 'geometry', 'commit'])
def test_invalid_or_writing_planner_never_returns_success(change):
    work, data = item(), payload()
    if change == 'serving':
        work = replace(work, shadow=False)
    elif change == 'geometry':
        data['speech_seconds'] = 9

    def assign(tx, *args, **kwargs):
        tx.commit()

    with pytest.raises((ShadowBoundaryError, ValueError)):
        plan(work, data, {}, lambda *args: None, decode=deepcopy, assign=assign if change == 'commit' else None)


def test_empty_speech_never_invokes_assignment():
    assign = Mock(side_effect=AssertionError('assignment forbidden'))
    assert (
        plan(item(), {'words': [], 'speech_seconds': 0}, {}, Mock(), decode=deepcopy, assign=assign)['status']
        == 'empty'
    )
    assign.assert_not_called()


def test_exception_boundary_returns_only_status_and_never_payload(monkeypatch, caplog):
    from database.batch_pipeline_shadow import ShadowStore

    monkeypatch.setattr(
        ShadowStore, 'projection_input', lambda *args: (_ for _ in ()).throw(RuntimeError('private synthetic text'))
    )
    assert run(Mock(), 'synthetic-shadow', payload()) == {'status': 'error'}
    assert 'private synthetic text' not in caplog.text

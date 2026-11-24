"""Typed boundaries preserve error ownership, snapshot cleanup and empty projections."""

from dataclasses import replace

import pytest

from database.batch_final_pass import ReferenceUnavailable
from tests.unit.test_batch_final_pass import (
    lane as lane,
    prod_shaped as prod_shaped,
    reference_store as reference_store,
    run_prod,
)
from tests.unit.test_batch_final_pass_resources import sdk_reference as sdk_reference
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget
from utils.conversations import final_pass_batch as batch


@pytest.mark.parametrize(
    'shared_units,expected_unit,expected_outcome',
    [
        (set(), 'unit-a', 'failed_incomplete_coverage'),
        ({'unit-a', 'unit-b'}, 'unit-a', 'skipped_shared_unit'),
        ({'unit-b'}, 'unit-b', 'skipped_shared_unit'),
    ],
)
def test_selected_reference_failure_keeps_its_own_unit(
    prod_shaped, monkeypatch, shared_units, expected_unit, expected_outcome
):
    segment = prod_shaped.conversation.transcript_segments[0].model_copy(deep=True)
    segment.id, segment.speaker_id_scope = 'second-segment', 'final:batch:unit-b'
    prod_shaped.conversation.transcript_segments.append(segment)
    errors = {}

    def refuse(store, uid, unit, cid, **kwargs):
        error = ReferenceUnavailable('skipped_shared_unit') if unit in shared_units else ValueError('unit_duration')
        errors[unit] = error
        raise error

    monkeypatch.setattr(batch, 'load_reference', refuse)
    result = run_prod(prod_shaped)
    assert result['outcome'] == expected_outcome
    assert result['failing_unit'] == expected_unit
    assert result['reason'] == ('skipped_shared_unit' if shared_units else 'unit_duration')
    assert not prod_shaped.gpu
    assert all(not hasattr(error, 'failing_unit') for error in errors.values())


def test_empty_part_list_preserves_coverage_failure_instead_of_unbound_cleanup(prod_shaped, monkeypatch):
    prod_shaped.binding = replace(prod_shaped.binding, record_origin=False)
    monkeypatch.setattr(batch, 'split_result', lambda *args: [])
    result = run_prod(prod_shaped)
    assert result['outcome'] == 'failed_incomplete_coverage'
    assert result['reason'] == 'projection_segment_missing'
    assert not prod_shaped.gpu


@pytest.mark.parametrize('raise_in_body', [False, True])
def test_real_sdk_snapshot_is_cleared_after_success_or_refusal(sdk_reference, raise_in_body):
    from database.batch_pipeline_reads import read_snapshot

    snapshots = []

    def read(tx):
        snapshots.append(tx.transaction)
        assert tx.transaction.id == b'bounded-read-only-snapshot'
        if raise_in_body:
            raise ValueError('unit_duration')
        return 'read-only-result'

    if raise_in_body:
        with pytest.raises(ValueError, match='unit_duration'):
            read_snapshot(sdk_reference.store, read, ArtifactReadBudget(101, 0, 0))
    else:
        assert read_snapshot(sdk_reference.store, read, ArtifactReadBudget(101, 0, 0)) == 'read-only-result'
    assert snapshots[0].id is None and not snapshots[0].in_progress
    assert [kind for kind, _ in sdk_reference.calls] == ['begin', 'rollback']

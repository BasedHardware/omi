"""Reader-first WorkItem rollout: stored item envelopes may carry fields this build does not know.

A later deploy may add an optional WorkItem field. Pods still running this
build, or a rollback to it, must keep reading those envelopes, so every reader
of a stored item envelope builds it through ``WorkItem.from_dict``, which
ignores unknown fields. No new field is written by this change.
"""

import ast
from pathlib import Path

import pytest

from utils.batch_pipeline.contracts import Priority, WorkItem

BACKEND = Path(__file__).resolve().parents[2]
READERS = (
    'database/batch_pipeline_shadow.py',
    'utils/batch_pipeline/shadow_projection.py',
    'utils/batch_pipeline/shadow_recovery.py',
    'utils/batch_pipeline/upload_coalescing.py',
)


def _item(**fields):
    return WorkItem('segment', 'synthetic-owner', 100.0, 'gs://synthetic/audio', 1.0, Priority.DEEP, **fields)


def test_an_unknown_field_from_a_newer_writer_is_ignored():
    item = _item(conversation_id='target', capture_time_trust='untrusted')
    envelope = {**item.to_dict(), 'capture_clock_estimated': True, 'some_future_field': {'nested': 1}}
    assert WorkItem.from_dict(envelope) == item


@pytest.mark.parametrize('include_nulls', [False, True])
def test_from_dict_round_trips_every_envelope_this_build_writes(include_nulls):
    item = _item(source_conversation_ids=('one', 'two'))
    assert WorkItem.from_dict(item.to_dict(include_nulls=include_nulls)) == item


def test_from_dict_keeps_validation_and_required_fields():
    with pytest.raises(TypeError):
        WorkItem.from_dict({'segment_id': 'segment', 'unknown': 1})
    with pytest.raises(ValueError):
        WorkItem.from_dict({**_item().to_dict(), 'source_conversation_ids': ['a/b']})


@pytest.mark.parametrize('relative', READERS)
def test_stored_envelope_readers_never_construct_work_item_from_a_raw_mapping(relative):
    tree = ast.parse((BACKEND / relative).read_text())
    raw = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'WorkItem'
        and any(keyword.arg is None for keyword in node.keywords)
    ]
    assert raw == [], f'{relative}: use WorkItem.from_dict for stored envelopes (lines {raw})'

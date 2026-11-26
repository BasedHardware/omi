"""A protocol-2 source-reuse row committed by a pre-reuse ordered merger still projects.

Production shape (2026-11-16): intake stamped ``protocol_version=2`` and
``source_reuse_version=1`` on the job; the GPU pump's older merger copied only
``protocol_version`` onto the result row. The projector refused the row as an
immutable binding mismatch and the owner's chain stopped behind it.
"""

import pytest

from config.policy import ProjectionPolicy
from database.batch_pipeline_projection_protocol import ProjectionBlocked, source_reader_marked
from database.batch_pipeline_source_projection import project_alias
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.scheduler import owner_key
from tests.unit.test_batch_pipeline_source_reuse import (  # noqa: F401
    COPY,
    NOW,
    SOURCE,
    UID,
    local,
    prepare_copy,
    setup_store,
)

KEY = 'a' * 64


@pytest.mark.parametrize(
    'entry,job,expected',
    [
        ({'source_reuse_version': 1}, {'source_reuse_key': KEY}, True),
        ({'source_alias_version': 1}, {'source_reuse_key': KEY}, True),
        # Pre-reuse merger: no marker field on the row, marker on the immutable job.
        ({}, {'source_reuse_key': KEY, 'source_reuse_version': 1}, True),
        ({}, {'source_reuse_key': KEY, 'source_alias_version': 1}, True),
        # Never a source row without the job's source key.
        ({'source_reuse_version': 1}, {}, False),
        ({}, {'source_reuse_version': 1}, False),
        # No marker anywhere: an unknown protocol-2 row stays refused.
        ({}, {'source_reuse_key': KEY}, False),
        # A marker that is present but not this reader's version is refused, not inherited.
        ({'source_reuse_version': 2}, {'source_reuse_key': KEY, 'source_reuse_version': 1}, False),
        ({'source_alias_version': None}, {'source_reuse_key': KEY, 'source_alias_version': 1}, False),
        ({}, {'source_reuse_key': KEY, 'source_reuse_version': 2}, False),
        # Mixed markers: one valid marker never launders an unsupported one.
        ({'source_reuse_version': 1, 'source_alias_version': 2}, {'source_reuse_key': KEY}, False),
        ({'source_reuse_version': 2, 'source_alias_version': 1}, {'source_reuse_key': KEY}, False),
        ({'source_reuse_version': 1, 'source_alias_version': None}, {'source_reuse_key': KEY}, True),
        ({'source_reuse_version': 1, 'source_alias_version': 1}, {'source_reuse_key': KEY}, True),
    ],
)
def test_source_reader_marker_admission(entry, job, expected):
    assert source_reader_marked({'protocol_version': 2, **entry}, job) is expected


def _strip_row_markers(store):
    path = store.ref('results', COPY).path
    for field in ('source_reuse_version', 'source_alias_version'):
        store.client.rows[path].pop(field, None)


def test_row_committed_by_pre_reuse_merger_projects_on_the_job_marker():
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    store.client.rows[store.ref('jobs', COPY).path].update(protocol_version=2, source_alias_version=1)
    _strip_row_markers(store)

    assert project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())

    row = store.ref('results', COPY).get().to_dict()
    assert row['projection_state'] != 'pending'
    assert 'source_alias_version' not in row and 'source_reuse_version' not in row


def test_unmarked_protocol_two_row_without_a_job_marker_stays_refused():
    # The realistic residual: a job with a source key but no marker at all
    # (pre-marker intake). Its unmarked row must stay refused.
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    job = store.client.rows[store.ref('jobs', COPY).path]
    for field in ('source_reuse_version', 'source_alias_version'):
        job.pop(field, None)
    assert job.get('source_reuse_key') == KEY
    _strip_row_markers(store)

    with pytest.raises(ProjectionBlocked, match='immutable result binding mismatch'):
        project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    assert store.ref('results', COPY).get().to_dict()['projection_state'] == 'pending'


def test_inherited_marker_is_counted_and_marked_rows_are_not(monkeypatch):
    calls = []
    from database import batch_pipeline_projection_protocol as protocol

    monkeypatch.setattr(protocol, 'record_fallback', lambda **kwargs: calls.append(kwargs))
    assert source_reader_marked({'protocol_version': 2, 'source_reuse_version': 1}, {'source_reuse_key': KEY})
    assert calls == []
    assert source_reader_marked({'protocol_version': 2}, {'source_reuse_key': KEY, 'source_reuse_version': 1})
    assert calls == [
        {
            'component': 'sync_dispatch',
            'from_mode': 'row_source_marker',
            'to_mode': 'job_source_marker',
            'reason': 'capability_mismatch',
            'outcome': 'recovered',
        }
    ]
    assert not source_reader_marked({'protocol_version': 2}, {'source_reuse_key': KEY})
    assert len(calls) == 1


def test_canonical_sync_row_committed_unmarked_passes_the_binding_gate():
    # The incident's ordinary flavor: an intake-stamped canonical sync job
    # (source_reuse_version=1, no source_alias) whose row the old merger
    # committed unmarked. The gate must admit it on the job's marker.
    store, original = setup_store()
    job_path = store.ref('jobs', SOURCE).path
    row_path = store.ref('results', SOURCE).path
    store.client.rows[job_path].update(protocol_version=2, source_reuse_version=1)
    assert 'source_alias' not in store.client.rows[job_path]
    row = store.client.rows[row_path]
    for field in ('source_reuse_version', 'source_alias_version', 'projection'):
        row.pop(field, None)
    row['projection_state'] = 'pending'
    store.client.rows[store.ref('owners', owner_key(UID)).path].pop('projection_watermark', None)
    binding = ProjectionBinding(UID, 'source-job', 'source-content', (SOURCE,), privacy_generation=0)
    session = store.session(SOURCE, binding, NOW, policy=ProjectionPolicy())
    try:
        session.prepare(store.client.transaction())
    except ProjectionBlocked as error:
        assert 'immutable result binding mismatch' not in str(error)
    # Same row with a wrong marker is refused at the gate.
    store.client.rows[row_path]['source_reuse_version'] = 2
    session = store.session(SOURCE, binding, NOW, policy=ProjectionPolicy())
    with pytest.raises(ProjectionBlocked, match='immutable result binding mismatch'):
        session.prepare(store.client.transaction())

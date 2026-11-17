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
from tests.unit.test_batch_pipeline_source_reuse import COPY, NOW, local, prepare_copy, setup_store  # noqa: F401

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
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    _strip_row_markers(store)

    with pytest.raises(ProjectionBlocked, match='immutable result binding mismatch'):
        project_alias(store, copy, binding, NOW, policy=ProjectionPolicy())
    assert store.ref('results', COPY).get().to_dict()['projection_state'] == 'pending'

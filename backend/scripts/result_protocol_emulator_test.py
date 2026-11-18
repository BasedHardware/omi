# LIFECYCLE: permanent
"""PL-631/632/633: mixed-version result contracts over the shared Store interface.

Require OMI_REQUIRE_STORE_BACKENDS=all for old Firestore, replacement Postgres
and simulator qualification. Customer privacy/content authority uses the existing
harness seam; this does not qualify full alias enrollment, Projector or billing.
Only the historical copier and hypothetical capable successor are substituted.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import sys

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

pytest_plugins = ['tests.conftest']

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked, source_reader_marked
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline import merge as merger
from utils.batch_pipeline.contracts import Priority, WorkItem, WorkResult
from utils.batch_pipeline.scheduler import Scheduler, owner_key

pytestmark = pytest.mark.integration
NOW = 1_000_000.0
REQUIRED = 'required_result_markers'


@pytest.fixture
def h(store_backend, monkeypatch):  # noqa: F811
    store_backend.seed_user('owner')
    monkeypatch.setenv('BATCH_RESULT_PROTOCOL_GUARD_ENABLED', 'true')
    return store_backend


def read(h, table, key):
    return h.store.run(lambda tx: tx.get(table, key))


def update(h, table, key, fields):
    def body(tx):
        doc = tx.get(table, key)
        doc.update(deepcopy(fields))
        tx.put(table, key, doc)

    h.store.run(body)


def ready(h):
    """Real enqueue/pull/settle; no vendor or synthetic query selection."""
    queue = Scheduler(h.store)
    queue.enqueue(
        WorkItem('unit', h.uid('owner'), NOW, 'gs://synthetic/audio', 5.0, Priority.FRESH, privacy_generation=0),
        NOW,
    )
    lease = queue.pull(NOW + 1, 1)[0]
    assert queue.complete(WorkResult('unit', 'gs://synthetic/own-result#2'), lease.token, NOW + 2)
    return read(h, 'jobs', 'unit')


def snapshot(h):
    return {
        'job': read(h, 'jobs', 'unit'),
        'result': read(h, 'results', 'unit'),
        'owner': read(h, 'owners', owner_key(h.uid('owner'))),
    }


@pytest.mark.parametrize('marker', ['source_reuse_version', 'source_alias_version'])
@pytest.mark.parametrize('copy', ['missing', 'null'])
def test_pl631_stale_copier_keeps_supported_job_readable(h, monkeypatch, marker, copy):
    ready(h)
    update(
        h, 'jobs', 'unit', {'protocol_version': 2, 'source_reuse_key': 'synthetic', marker: 1, REQUIRED: {marker: 1}}
    )
    # The independently deployed historical copier emitted protocol but no markers.
    with monkeypatch.context() as old_copier:
        old_copier.setattr(merger, 'merge_markers', lambda job: {})
        entry = merger.OrderedMerge(h.store).commit_next(h.uid('owner'), NOW + 3)
    assert entry['protocol_version'] == 2 and marker not in entry
    if copy == 'null':
        update(h, 'results', 'unit', {marker: None})
    before = snapshot(h)
    assert source_reader_marked(before['result'], before['job'])
    assert snapshot(h) == before, 'compatibility reading must not rewrite durable authority'


@pytest.mark.parametrize('defect', ['conflicting_copy', 'boolean_copy', 'unknown_requirement', 'no_source_key'])
def test_pl631_reader_does_not_launder_conflicting_authority(h, defect):
    ready(h)
    update(
        h,
        'jobs',
        'unit',
        {
            'protocol_version': 2,
            'source_reuse_key': 'synthetic',
            'source_reuse_version': 1,
            REQUIRED: {'source_reuse_version': 1},
        },
    )
    entry = merger.OrderedMerge(h.store).commit_next(h.uid('owner'), NOW + 3)
    assert source_reader_marked(entry, read(h, 'jobs', 'unit'))
    if defect in ('conflicting_copy', 'boolean_copy'):
        update(h, 'results', 'unit', {'source_reuse_version': 2 if defect == 'conflicting_copy' else True})
    else:
        update(
            h,
            'jobs',
            'unit',
            {REQUIRED: {'future_version': 1}} if defect == 'unknown_requirement' else {'source_reuse_key': ''},
        )
    before = snapshot(h)
    assert not source_reader_marked(before['result'], before['job'])
    assert snapshot(h) == before


@pytest.mark.parametrize('defect', ['protocol', 'unknown', 'version', 'missing', 'boolean', 'float'])
def test_pl632_refusal_preserves_job_and_log_until_a_capable_successor(h, monkeypatch, defect):
    ready(h)
    update(
        h,
        'owners',
        owner_key(h.uid('owner')),
        {
            'log_tail': 'already-committed',
            'log_sequence': 5,
            'watermark': {'capture_at': NOW - 10, 'segment_id': 'already-committed'},
        },
    )
    fields = {
        'protocol_version': 2,
        'source_reuse_key': 'synthetic',
        'source_reuse_version': 1,
        REQUIRED: {'source_reuse_version': 1},
    }
    if defect == 'protocol':
        fields['protocol_version'] = 999
    elif defect == 'unknown':
        fields[REQUIRED]['future_version'] = 1
    elif defect == 'missing':
        fields.pop('source_reuse_version')
    else:
        fields['source_reuse_version'] = fields[REQUIRED]['source_reuse_version'] = {
            'version': 2,
            'boolean': True,
            'float': 1.0,
        }[defect]
    update(h, 'jobs', 'unit', fields)
    before = snapshot(h)
    assert before['job']['state'] == 'result_ready' and before['result'] == {}
    # Restarted incapable mergers must not consume a sequence or require requeue.
    for offset in (3, 4):
        assert merger.OrderedMerge(h.store).commit_next(h.uid('owner'), NOW + offset) is None
        assert snapshot(h) == before
    if defect != 'unknown':
        return  # A future binary is not permission to accept malformed metadata.

    # Model one exact future requirement's capability decision, not future semantics.
    current_markers = merger.merge_markers

    def future_capability(job):
        if job == before['job'] and job[REQUIRED] == {'source_reuse_version': 1, 'future_version': 1}:
            return dict(job[REQUIRED])
        return current_markers(job)

    monkeypatch.setattr(merger, 'merge_markers', future_capability)
    entry = merger.OrderedMerge(h.store).commit_next(h.uid('owner'), NOW + 5)
    assert entry['log_sequence'] == before['owner'].get('log_sequence', 0) + 1
    assert entry['previous_segment_id'] == before['owner'].get('log_tail')
    assert entry['result'] == before['job']['result']
    after = read(h, 'jobs', 'unit')
    assert after['state'] == 'committed' and after['merge_pending'] is False
    assert after['audio_uri'] == before['job']['audio_uri']


def fallback(h, envelope='canonical', slot_state='pending'):
    job = ready(h)
    key = owner_key(h.uid('owner'))
    slot = {
        'segment_id': 'unit',
        'owner_id': job['owner_id'],
        'owner_key': key,
        'capture_at': NOW,
        'privacy_generation': 0,
        'protocol_version': 2,
        'previous_segment_id': 'predecessor',
        'log_sequence': 3,
        'committed_at': NOW - 20,
        'projection_state': slot_state,
        'result': {'segment_id': 'unit', 'result_uri': 'gs://synthetic/alias-result#1'},
        'projection_blocked_since': NOW - 10,
        'projection_block_type': 'SyncAssignmentConflict',
    }
    required = {'source_reuse_version': 1}
    if envelope == 'historical_dual':
        required['source_alias_version'] = 1
    elif envelope == 'legacy_alias':
        required = {'source_alias_version': 1}
    update(
        h,
        'jobs',
        'unit',
        {
            'protocol_version': 2,
            'source_reuse_version': 1,
            'source_reuse_key': 'synthetic',
            REQUIRED: required,
            'stt_route': {'stt_route': 'provider'},
            'source_alias_fallback': {'source_segment_id': 'canonical-source', 'log_slot': slot},
            'projection_binding': {
                'job_id': 'binding-job',
                'content_id': 'content',
                'run_token': 'binding-token',
                'run_epoch': 2,
            },
        },
    )
    update(
        h,
        'owners',
        key,
        {'log_tail': 'successor', 'log_sequence': 7, 'watermark': {'capture_at': NOW + 20, 'segment_id': 'successor'}},
    )
    h.store.run(
        lambda tx: tx.put(
            'content',
            f"{h.uid('owner')}/content",
            {
                'status': 'processing',
                'dispatch_protocol': 'batch_v1',
                'job_id': 'binding-job',
                'ledger_run_token': 'binding-token',
                'ledger_run_epoch': 2,
            },
        )
    )
    return slot


@pytest.mark.parametrize('envelope', ['canonical', 'legacy_alias', 'historical_dual'])
@pytest.mark.parametrize('slot_state', ['pending', 'ready'])
def test_pl633_fallback_restores_exact_slot_once(h, envelope, slot_state):
    slot = fallback(h, envelope, slot_state)
    before = snapshot(h)
    ledger = read(h, 'content', f"{h.uid('owner')}/content")
    entry = merger.OrderedMerge(h.store).commit_next(h.uid('owner'), NOW + 3)
    assert entry is not None
    for field in (
        'segment_id',
        'owner_id',
        'owner_key',
        'capture_at',
        'privacy_generation',
        'previous_segment_id',
        'log_sequence',
        'committed_at',
    ):
        assert entry[field] == slot[field]
    assert entry['result'] == before['job']['result']
    assert entry['source_reuse_version'] == 1 and 'source_alias_version' not in entry
    assert entry['projection_state'] == 'pending' and entry['projection_redriven_at'] == NOW + 3
    assert entry['projection_blocked_since'] is None and entry['projection_block_type'] is None
    assert read(h, 'owners', owner_key(h.uid('owner'))) == {
        **before['owner'],
        'revision': before['owner']['revision'] + 1,
    }
    assert read(h, 'content', f"{h.uid('owner')}/content") == ledger
    after = snapshot(h)
    assert after['job']['audio_uri'] == before['job']['audio_uri']
    assert after['job']['state'] == 'committed' and after['job']['merge_pending'] is False
    assert merger.OrderedMerge(h.store).commit_next(h.uid('owner'), NOW + 4) is None
    assert snapshot(h) == after


@pytest.mark.parametrize(
    'defect', ['unknown', 'slot_generation', 'slot_result', 'slot_owner', 'ledger_owner', 'privacy']
)
def test_pl633_unproven_fallback_cannot_change_custody_or_log(h, defect):
    fallback(h, 'historical_dual')
    job = read(h, 'jobs', 'unit')
    if defect == 'unknown':
        job[REQUIRED]['future_version'] = 1
    elif defect == 'slot_generation':
        job['source_alias_fallback']['log_slot']['privacy_generation'] = 1
    elif defect == 'slot_result':
        job['source_alias_fallback']['log_slot']['result'] = job['result']
    elif defect == 'slot_owner':
        job['source_alias_fallback']['log_slot']['owner_id'] = 'foreign-synthetic-owner'
    elif defect == 'ledger_owner':
        update(h, 'content', f"{h.uid('owner')}/content", {'ledger_run_token': 'new-owner-token'})
    else:
        h.customer.block_privacy(h.uid('owner'))
    if defect not in ('ledger_owner', 'privacy'):
        h.store.run(lambda tx: tx.put('jobs', 'unit', job))
    before = snapshot(h)
    ledger = read(h, 'content', f"{h.uid('owner')}/content")
    try:
        assert merger.OrderedMerge(h.store).commit_next(h.uid('owner'), NOW + 3) is None
    except (ProjectionBlocked, BatchPrivacyBlocked):
        assert defect in ('ledger_owner', 'privacy')
    assert snapshot(h) == before
    assert read(h, 'content', f"{h.uid('owner')}/content") == ledger

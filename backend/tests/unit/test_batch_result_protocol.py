"""Mixed deploy-unit result metadata and pre-append protocol refusal."""

import ast
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from config.policy import BatchUnitPolicy, ProjectionPolicy
from database.batch_pipeline_intake import admit
from database.batch_pipeline_projection_protocol import source_reader_marked
from database.batch_pipeline_source_fallback import merge_ready
from database.batch_pipeline_source_projection import project_alias
from database.batch_pipeline_store import FirestoreTransaction
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from tests.unit.test_batch_pipeline_source_reuse import COPY, NOW, NS, SOURCE, UID, local, prepare_copy, setup_store
from utils.batch_pipeline import merge as merger
from utils.batch_pipeline.contracts import WorkResult
from utils.batch_pipeline.result_protocol import REQUIRED, REFUSED, SOURCE_MARKERS, merge_markers, stamp
from utils.batch_pipeline.scheduler import Scheduler, owner_key


@pytest.mark.parametrize('marker', SOURCE_MARKERS)
def test_every_intake_requirement_has_a_merge_and_legacy_copy_reader(marker):
    job = {'source_reuse_key': 'synthetic'}
    stamp(job, marker)
    assert merge_markers(job) == {marker: SOURCE_MARKERS[marker]}
    assert source_reader_marked({'protocol_version': 2}, job)


@pytest.mark.parametrize(
    'defect', ['protocol', 'unknown', 'version', 'missing', 'boolean', 'boolean_job_only', 'float_job_only']
)
def test_unsupported_requirement_never_consumes_an_ordered_log_slot(defect, monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('head'), 0)
    lease = queue.pull(0, 1)[0]
    assert queue.complete(WorkResult('head', 'gs://synthetic/result'), lease.token, 1)
    job = store.rows['jobs', 'head']
    job['source_reuse_key'] = 'synthetic'
    stamp(job, 'source_reuse_version')
    if defect == 'protocol':
        job['protocol_version'] = 999
    elif defect == 'unknown':
        job[REQUIRED]['future_version'] = 1
    elif defect == 'version':
        job['source_reuse_version'] = job[REQUIRED]['source_reuse_version'] = 2
    elif defect == 'missing':
        job.pop('source_reuse_version')
    elif defect == 'boolean_job_only':
        job['source_reuse_version'] = True
    elif defect == 'float_job_only':
        job['source_reuse_version'] = 1.0
    else:
        job['source_reuse_version'] = job[REQUIRED]['source_reuse_version'] = True
    before, refused = deepcopy(store.rows), REFUSED._value.get()
    assert merger.OrderedMerge(store).commit_next('heavy', 2) is None
    assert store.rows == before
    assert ('results', 'head') not in store.rows
    assert REFUSED._value.get() > refused
    # A capable merger can still claim exactly the same ready job; no repair/requeue.
    monkeypatch.setattr(merger, 'merge_markers', lambda job: dict(job[REQUIRED]))
    assert merger.OrderedMerge(store).commit_next('heavy', 3)['log_sequence'] == 1


def test_guard_kill_switch_restores_copying_without_disabling_reader_recovery(monkeypatch):
    job = {'protocol_version': 999}
    assert merge_markers(job) is None
    monkeypatch.setenv('BATCH_RESULT_PROTOCOL_GUARD_ENABLED', 'false')
    assert merge_markers(job) == {}
    stamp(job, 'source_reuse_version')
    job['source_reuse_key'] = 'synthetic'
    assert source_reader_marked({'protocol_version': 2}, job)


def test_new_intake_old_worker_projects_alias_and_releases_its_head(monkeypatch):
    store, original = setup_store()
    copy, binding = prepare_copy(store, original)
    # Keep synthetic canonical/artifact fixtures, but admit the copy on the real path.
    store.client.rows.pop(store.ref('jobs', COPY).path)
    store.client.rows.pop(store.ref('results', COPY).path)
    from database.sync_ledger import sync_content_ledger_ref

    store.client.rows.pop(sync_content_ledger_ref(store.client, UID, binding.content_id).path)

    def run(body):
        tx = FirestoreTransaction(store.client, NS, store.client.transaction())
        result = body(tx)
        tx.flush()
        return result

    answer = admit(
        SimpleNamespace(run=run),
        [copy],
        binding,
        NOW,
        namespace=NS,
        policy=replace(BatchUnitPolicy(), batch_enabled=True),
        source_aliases={COPY: {'segment_id': SOURCE, 'result_uri': 'gs://synthetic/copy-result#1'}},
    )
    assert answer['outcome'] == 'batch'
    job = store.ref('jobs', COPY).get().to_dict()
    assert job[REQUIRED] == {'source_alias_version': 1}
    # Exercise the actual merger with the historical metadata-copy behavior.
    memory = MemoryStore()
    memory.rows['jobs', COPY] = job
    memory.rows['owners', owner_key(UID)] = {'log_tail': SOURCE, 'log_sequence': 1}
    monkeypatch.setattr(merger, 'merge_markers', lambda _: {})
    row = merger.OrderedMerge(memory).commit_next(UID, NOW)
    assert row['protocol_version'] == 2 and not any(key in row for key in SOURCE_MARKERS)
    store.client.rows[store.ref('jobs', COPY).path] = memory.rows['jobs', COPY]
    store.ref('results', COPY).create(row)
    assert project_alias(store, copy, binding, NOW + 1, policy=ProjectionPolicy())
    assert store.ref('results', COPY).get().to_dict()['projection_state'] != 'pending'
    assert store.ref('owners', owner_key(UID)).get().to_dict()['projection_watermark'] == COPY


def test_fallback_merger_refuses_unknown_requirements_before_reading_or_writing():
    job = {'protocol_version': 2, REQUIRED: {'future_version': 1}}
    # Refusal must precede even access to the suspended log slot.
    assert merge_ready(SimpleNamespace(), job, NOW) is None


def test_no_intake_marker_declaration_bypasses_the_registry():
    backend = Path(__file__).resolve().parents[2]
    # These are the protocol-2 job producers, including the accepted-alias restart.
    for name in ('batch_pipeline_intake.py', 'batch_pipeline_source_reuse.py', 'batch_pipeline_source_fallback.py'):
        tree = ast.parse((backend / 'database' / name).read_text())
        declarations = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword):
                declarations.add(node.arg)
            if isinstance(node, ast.Dict):
                declarations.update(
                    key.value for key in node.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)
                )
        assert {name for name in declarations if name and name.endswith('_version')} <= {
            'protocol_version',
            *SOURCE_MARKERS,
        }


def test_new_canonical_intake_survives_scheduler_and_copies_registered_requirements():
    store = MemoryStore()
    work = replace(item('canonical'), source_reuse_key='a' * 64, privacy_generation=0)
    from utils.batch_pipeline.contracts import ProjectionBinding

    binding = ProjectionBinding('heavy', 'job', 'content', ('canonical',), privacy_generation=0)
    assert (
        admit(store, [work], binding, 0, namespace=NS, policy=replace(BatchUnitPolicy(), batch_enabled=True))['outcome']
        == 'batch'
    )
    queue = Scheduler(store)
    lease = queue.pull(0, 1)[0]
    assert queue.complete(WorkResult('canonical', 'gs://synthetic/result'), lease.token, 1)
    entry = merger.OrderedMerge(store).commit_next('heavy', 2)
    assert entry['source_reuse_version'] == 1
    assert source_reader_marked(entry, store.rows['jobs', 'canonical'])


@pytest.mark.parametrize('bad', [None, True, 2])
def test_explicit_copy_conflict_is_not_recovered_from_job(bad):
    job = {'source_reuse_key': 'synthetic'}
    stamp(job, 'source_reuse_version')
    assert not source_reader_marked({'source_reuse_version': bad}, job)


@pytest.mark.parametrize('defect', ['no_witness', 'wrong_slot', 'unknown', 'wrong_version'])
def test_stale_alias_envelope_requires_the_exact_legacy_fallback_witness(defect):
    job = {
        'protocol_version': 2,
        'segment_id': 'unit',
        'source_reuse_key': 'synthetic',
        'source_reuse_version': 1,
        REQUIRED: {'source_alias_version': 1},
        'source_alias_fallback': {'source_segment_id': 'canonical', 'log_slot': {'segment_id': 'unit'}},
    }
    assert merge_markers(job) == {'source_reuse_version': 1}
    assert source_reader_marked({'source_reuse_version': 1}, job)
    if defect == 'no_witness':
        job.pop('source_alias_fallback')
    elif defect == 'wrong_slot':
        job['source_alias_fallback']['log_slot']['segment_id'] = 'other'
    elif defect == 'unknown':
        job[REQUIRED]['future_version'] = 1
    else:
        job[REQUIRED]['source_alias_version'] = 2
    assert merge_markers(job) is None
    assert not source_reader_marked({'source_reuse_version': 1}, job)

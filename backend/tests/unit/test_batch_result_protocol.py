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
    job = {'source_reuse_key': 'synthetic'}
    stamp(job, 'source_reuse_version')
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


# These versions are owned downstream or by provider routing, never intake
# requirements. Restrict exclusions to their current owners so a new producer
# cannot borrow a projector-only name to evade the registry.
NON_INTAKE_VERSION_FIELDS = {
    'database/batch_pipeline_projection_session.py': {'lineage_quarantine_version', 'quarantine_version'},
    'database/batch_pipeline_projection_release.py': {'lineage_quarantine_version', 'projection_release_version'},
    'database/batch_pipeline_projection_privacy.py': {'privacy_quarantine_version'},
    'utils/batch_pipeline/merge.py': {'recovery_version'},
    'utils/batch_pipeline/provider_stt.py': {'recovery_version', 'table_version'},
}


def _stamp_calls(tree):
    names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or '').endswith('result_protocol')
        for alias in node.names
        if alias.name == 'stamp'
    }
    if not names:
        return []
    calls = []

    class Calls(ast.NodeVisitor):
        def __init__(self):
            self.functions = []

        def visit_FunctionDef(self, node):
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id in names:
                marker = (
                    node.args[1]
                    if len(node.args) > 1
                    else next((keyword.value for keyword in node.keywords if keyword.arg == 'marker'), None)
                )
                value = (
                    marker.value if isinstance(marker, ast.Constant) and isinstance(marker.value, str) else '<computed>'
                )
                calls.append(('.'.join(self.functions), value))
            self.generic_visit(node)

    Calls().visit(tree)
    return calls


def _version_declarations(tree):
    declarations = set()
    for node in ast.walk(tree):
        keys = []
        if isinstance(node, ast.keyword):
            if node.arg:
                declarations.add(node.arg)
        elif isinstance(node, ast.Dict):
            keys = node.keys
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            keys = [node.slice]
        for key in keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                declarations.add(key.value)
            elif isinstance(key, ast.JoinedStr) and any(
                isinstance(part, ast.Constant) and str(part.value).endswith('_version') for part in key.values
            ):
                declarations.add('<computed>_version')
    return {name for name in declarations if name.endswith('_version')}


def test_no_intake_marker_declaration_bypasses_the_registry():
    backend = Path(__file__).resolve().parents[2]
    expected = {
        ('database/batch_pipeline_intake.py', 'admit.commit', 'source_reuse_version'),
        ('database/batch_pipeline_source_reuse.py', 'enqueue_alias', 'source_alias_version'),
        ('database/batch_pipeline_source_fallback.py', 'enqueue', 'source_reuse_version'),
    }
    observed = set()
    # Discover protocol/job writers across both layers, including future modules.
    # The cheap text prefilter avoids parsing unrelated account-domain sources.
    for directory in ('database', 'utils/batch_pipeline'):
        for path in (backend / directory).rglob('*.py'):
            source = path.read_text()
            if not any(
                token in source
                for token in ('protocol_version', "'jobs'", '"jobs"', 'required_result_markers', 'result_protocol')
            ):
                continue
            relative = path.relative_to(backend).as_posix()
            allowed = {'protocol_version', *SOURCE_MARKERS, *NON_INTAKE_VERSION_FIELDS.get(relative, set())}
            tree = ast.parse(source)
            assert _version_declarations(tree) <= allowed, relative
            if 'result_protocol' not in source:
                continue
            for function, marker in _stamp_calls(tree):
                assert marker in SOURCE_MARKERS, (relative, function, marker)
                observed.add((relative, function, marker))
    assert expected <= observed
    assert {call for call in observed if call[:2] in {entry[:2] for entry in expected}} == expected


@pytest.mark.parametrize(
    'source',
    [
        "job = {'protocol_version': 2, 'future_version': 1}",
        "job.update(protocol_version=2, future_version=1)",
        "job['protocol_version'] = 2; job['future_version'] = 1",
        "job['protocol_version'] = 2; job[f'{feature}_version'] = 1",
    ],
)
def test_new_or_computed_producer_marker_cannot_escape_completeness_guard(source):
    assert not _version_declarations(ast.parse(source)) <= {'protocol_version', *SOURCE_MARKERS}


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


@pytest.mark.parametrize('bad', [True, 2, '1'])
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


@pytest.mark.parametrize(
    ('section', 'defect'),
    [
        ('job', {'source_alias_of': 'canonical'}),
        ('job', {'source_alias': {'segment_id': 'canonical'}}),
        ('job', {'protocol_version': 3}),
        ('job', {'requires_compute_admission': True}),
        ('job', {'result': {'segment_id': 'different'}}),
        ('job', {REQUIRED: {'source_alias_version': 1, 'source_reuse_version': 1, 'future_version': 1}}),
        ('job', {REQUIRED: {'source_alias_version': 2, 'source_reuse_version': 1}}),
        ('job', {REQUIRED: {'source_alias_version': True, 'source_reuse_version': 1}}),
        ('fallback', {'source_segment_id': 'unit'}),
        ('slot', {'owner_key': 'other'}),
        ('slot', {'owner_id': 'other'}),
        ('slot', {'capture_at': 20}),
        ('slot', {'privacy_generation': 1}),
        ('slot', {'privacy_generation': False}),
        ('position', {}),
        ('slot', {'projection_state': 'erased'}),
        ('slot', {'projection': {'disposition': 'visible'}}),
        ('slot', {'result': {'segment_id': 'unit', 'result_uri': 'gs://synthetic/fresh'}}),
    ],
)
def test_historical_dual_alias_envelope_requires_bound_dormant_slot(section, defect):
    position = {
        'segment_id': 'unit',
        'owner_id': 'synthetic-owner',
        'owner_key': 'synthetic-owner-key',
        'capture_at': 10,
        'privacy_generation': 0,
    }
    slot = {
        **position,
        'projection_state': 'pending',
        'previous_segment_id': None,
        'result': {'segment_id': 'unit', 'result_uri': 'gs://synthetic/old'},
    }
    fallback = {'source_segment_id': 'canonical', 'log_slot': slot}
    job = {
        **position,
        'protocol_version': 2,
        'source_reuse_key': 'synthetic',
        'source_reuse_version': 1,
        'requires_compute_admission': False,
        'stt_route': {'stt_route': 'provider'},
        'result': {'segment_id': 'unit', 'result_uri': 'gs://synthetic/fresh'},
        REQUIRED: {'source_alias_version': 1, 'source_reuse_version': 1},
        'source_alias_fallback': fallback,
    }
    repaired_markers = {'source_reuse_version': 1}
    assert merge_markers(job) == repaired_markers
    assert source_reader_marked(repaired_markers, job)
    if section == 'position':
        # Missing on both sides does not witness a privacy fence.
        job.pop('privacy_generation')
        slot.pop('privacy_generation')
    else:
        {'job': job, 'fallback': fallback, 'slot': slot}[section].update(defect)
    assert merge_markers(job) is None
    assert not source_reader_marked(repaired_markers, job)


@pytest.mark.parametrize('marker', ["'wrong_marker'", "'future_version'", 'computed_marker'])
def test_stamp_positional_marker_arguments_are_checked(marker):
    source = "from utils.batch_pipeline.result_protocol import stamp as mark\n" + f"mark(job, {marker})"
    assert any(name not in SOURCE_MARKERS for _, name in _stamp_calls(ast.parse(source)))


def test_stamping_a_legacy_second_marker_retains_all_known_and_unknown_requirements():
    job = {'protocol_version': 2, 'source_reuse_key': 'synthetic', 'source_alias_version': 1}
    stamp(job, 'source_reuse_version')
    assert merge_markers(job) == {'source_reuse_version': 1, 'source_alias_version': 1}
    assert source_reader_marked({}, job)
    job[REQUIRED]['future_version'] = 1
    stamp(job, 'source_reuse_version')
    assert job[REQUIRED]['future_version'] == 1
    assert merge_markers(job) is None
    assert not source_reader_marked({}, job)


@pytest.mark.parametrize('unknown', ['protocol', 'requirement'])
def test_stamping_cannot_downgrade_an_existing_unsupported_protocol_or_requirement(unknown):
    job = {'protocol_version': 2, 'source_reuse_key': 'synthetic'}
    if unknown == 'protocol':
        job['protocol_version'] = 3
    else:
        job[REQUIRED] = {'source_reuse_version': 2}
    before = deepcopy(job)
    with pytest.raises(ValueError, match='unsupported result'):
        stamp(job, 'source_reuse_version')
    assert job == before


def test_null_copies_are_counted_as_missing_only_with_an_explicit_supported_job(monkeypatch):
    from database import batch_pipeline_projection_protocol as protocol

    observed = []
    monkeypatch.setattr(protocol, 'record_fallback', lambda **kwargs: observed.append(kwargs))
    job = {'source_reuse_key': 'synthetic'}
    stamp(job, 'source_reuse_version')
    assert source_reader_marked({'source_reuse_version': None, 'source_alias_version': None}, job)
    assert len(observed) == 1
    assert source_reader_marked({'source_reuse_version': 1, 'source_alias_version': None}, job)
    assert len(observed) == 1


def test_old_intake_can_add_a_registered_marker_without_rewriting_the_envelope():
    job = {'source_reuse_key': 'synthetic'}
    stamp(job, 'source_alias_version')
    job.update(protocol_version=2, source_reuse_version=1)  # Pre-registry intake retry.
    before = deepcopy(job)
    assert merge_markers(job) == {'source_reuse_version': 1, 'source_alias_version': 1}
    assert source_reader_marked({'source_alias_version': 1}, job)
    assert job == before

"""Completeness guard for the batch pipeline census registry (W3 / SCA-1921).

The registry is only useful if an unregistered state cannot ship. These tests
combine the reviewed lifecycle table with collection-scoped payload AST
discovery, so a new job/projection state at a registered writer site fails CI
while request-lane coalescing vocabularies stay out of scope.
"""

from __future__ import annotations

import ast
import json
import runpy
from functools import lru_cache
from pathlib import Path

import pytest

from config import batch_census
from config.batch_census import (
    COLLECTION,
    COLLECTION_GROUP,
    ENTRIES,
    JOB_STATE_MODULES,
    JOB_STATES,
    NON_JOB_STATE_MODULES,
    PROJECTION_STATE_MODULES,
    states_for,
)
from tests.support.lifecycle_ast import constant_names, literal_key
from tests.support.lifecycle_state_table import STATES
from tests.support.lifecycle_writer_inventory import FIELD_SITES

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
STATE_FIELDS = frozenset({'state', 'projection_state', 'recovery_state', 'status'})
BATCH_SCOPE = ('database/batch_pipeline', 'utils/batch_pipeline/', 'database/record_partial.py')


def _in_batch_scope(module: str) -> bool:
    return module.startswith(BATCH_SCOPE)


@lru_cache(maxsize=None)
def _defined_constants(module: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    tree = ast.parse((BACKEND / module).read_text())
    return tuple((name, tuple(sorted(values))) for name, values in constant_names(tree).items())


@lru_cache(maxsize=None)
def _imports(module: str) -> tuple[tuple[str, str, str], ...]:
    """(local name, defining module, defining name) for absolute ``from`` imports."""
    tree = ast.parse((BACKEND / module).read_text())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        target = node.module.replace('.', '/') + '.py'
        if not (BACKEND / target).exists():
            continue
        found.extend((alias.asname or alias.name, target, alias.name) for alias in node.names)
    return tuple(found)


@lru_cache(maxsize=None)
def _resolve_constant(module: str, name: str, stack: frozenset[tuple[str, str]] = frozenset()) -> frozenset[str]:
    local = dict(_defined_constants(module))
    if name in local:
        return frozenset(local[name])
    if (module, name) in stack:
        return frozenset()
    for local_name, target, target_name in _imports(module):
        if local_name == name:
            return _resolve_constant(target, target_name, stack | {(module, name)})
    return frozenset()


def state_sites(source: str, field: str, module: str | None = None) -> set[tuple[str, str]]:
    """(qualified owner, literal value) for each write to ``field`` in ``source``."""
    tree = ast.parse(source)
    constants = constant_names(tree)
    found: set[tuple[str, str]] = set()

    def literals(value):
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return {value.value}
        if isinstance(value, ast.Name):
            if value.id in constants:
                return set(constants[value.id])
            return set(_resolve_constant(module, value.id)) if module else set()
        if isinstance(value, ast.IfExp):
            return literals(value.body) | literals(value.orelse)
        return set()

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack: list[str] = []

        def visit_ClassDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_FunctionDef = visit_ClassDef
        visit_AsyncFunctionDef = visit_ClassDef

        def _record(self, key, value):
            if field not in literal_key(key, constants):
                return
            owner = '.'.join(self.stack) or '<module>'
            found.update((owner, literal) for literal in literals(value))

        def visit_Dict(self, node):
            for key, value in zip(node.keys, node.values):
                self._record(key, value)
            self.generic_visit(node)

        def visit_Assign(self, node):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    self._record(target.slice, node.value)
            self.generic_visit(node)

        def visit_Call(self, node):
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            )
            if name in {'dict', 'update', 'set', 'setdefault'}:
                for keyword in node.keywords:
                    if keyword.arg == field:
                        self._record(ast.Constant(field), keyword.value)
                if name == 'setdefault' and len(node.args) >= 2:
                    self._record(node.args[0], node.args[1])
            self.generic_visit(node)

    Visitor().visit(tree)
    return found


def literal_states(source: str, field: str, module: str | None = None) -> set[str]:
    """Literal values written to ``field`` anywhere in ``source``."""
    return {value for _owner, value in state_sites(source, field, module)}


def is_excluded_site(module: str, field: str, owner: str, value: str) -> bool:
    """True when a reviewed mixed-purpose site writes a non-job document."""
    return field == 'state' and (owner, value) in batch_census.NON_JOB_STATE_SITES.get(module, ())


def discovered_states(modules, field: str, sources: dict[str, str] | None = None) -> set[str]:
    found: set[str] = set()
    for module in modules:
        source = (sources or {}).get(module) or (BACKEND / module).read_text()
        for owner, value in state_sites(source, field, module):
            if not is_excluded_site(module, field, owner, value):
                found.add(value)
    return found


def unregistered_states(source: str, registered, field: str = 'state', module: str | None = None) -> set[str]:
    return literal_states(source, field, module) - set(registered)


# --- lifecycle table coverage ----------------------------------------------


def test_every_lifecycle_table_batch_state_is_registered():
    table = {row.state for row in STATES if row.machine == 'batch'}
    assert table <= set(JOB_STATES)


def test_every_lifecycle_table_projection_state_is_registered():
    table = {row.state for row in STATES if row.machine == 'batch_projection'}
    assert table <= states_for('batch_projection')


# --- AST discovery ----------------------------------------------------------


def test_registered_job_states_match_ast_discovery():
    assert discovered_states(JOB_STATE_MODULES, 'state') == set(JOB_STATES)


def test_registered_projection_states_match_ast_discovery():
    discovered = discovered_states(PROJECTION_STATE_MODULES, 'projection_state')
    legacy = {entry.state for entry in batch_census.entries_for('batch_projection') if entry.legacy}
    assert discovered == states_for('batch_projection') - legacy
    assert legacy == {'claimed'}


def test_non_job_state_site_exclusions_name_live_sites():
    for module, exclusions in batch_census.NON_JOB_STATE_SITES.items():
        assert module in JOB_STATE_MODULES, f'{module} must stay in the job discovery set'
        sites = state_sites((BACKEND / module).read_text(), 'state', module)
        for exclusion in exclusions:
            assert exclusion in sites, f'{module} exclusion {exclusion} no longer names a state write'


@pytest.mark.parametrize('module', sorted(batch_census.NON_JOB_STATE_SITES))
def test_mixed_purpose_module_keeps_its_job_states_in_scope(module):
    excluded = {value for _owner, value in batch_census.NON_JOB_STATE_SITES[module]}
    discovered = discovered_states([module], 'state')
    assert not discovered & excluded, f'{module} leaked a non-job marker into the job census'
    assert discovered <= set(JOB_STATES), f'{module} writes an unregistered job state'


def test_mixed_purpose_module_job_write_mutation_is_rejected():
    module = 'database/batch_pipeline_speech_redrive.py'
    source = (BACKEND / module).read_text()
    assert "state='result_ready'" in source
    mutated = source.replace("state='result_ready'", "state='brand_new_state'", 1)
    assert mutated != source
    assert discovered_states([module], 'state', sources={module: mutated}) - set(JOB_STATES) == {'brand_new_state'}


def test_synthetic_new_state_at_a_registered_site_is_rejected():
    source = "def commit(tx):\n    tx.update(ref, {'state': 'brand_new_state'})\n"
    assert unregistered_states(source, JOB_STATES) == {'brand_new_state'}


def test_synthetic_new_projection_state_is_rejected():
    source = "def commit(tx):\n    tx.update(ref, {'projection_state': 'brand_new_state'})\n"
    assert unregistered_states(source, states_for('batch_projection'), 'projection_state') == {'brand_new_state'}


def test_unrelated_coalescing_state_does_not_create_a_false_failure():
    coalescing = 'database/batch_pipeline_coalescing.py'
    assert coalescing in NON_JOB_STATE_MODULES
    assert coalescing not in JOB_STATE_MODULES
    # The vocabulary exists, but it is request-lane state, not a pipeline stock.
    assert {'holding', 'sealed', 'done'} <= literal_states((BACKEND / coalescing).read_text(), 'state')
    assert not {'holding', 'sealed', 'done'} & discovered_states(JOB_STATE_MODULES, 'state')


def test_every_batch_state_writer_module_is_classified():
    assert not set(JOB_STATE_MODULES) & set(NON_JOB_STATE_MODULES)
    for module in (*JOB_STATE_MODULES, *NON_JOB_STATE_MODULES, *PROJECTION_STATE_MODULES):
        assert module in FIELD_SITES, f'{module} no longer writes a reviewed payload site'
    for module, sites in FIELD_SITES.items():
        if not _in_batch_scope(module):
            continue
        fields = {field for _owner, field, _value, _siblings in sites}
        if 'state' in fields:
            assert (
                module in JOB_STATE_MODULES or module in NON_JOB_STATE_MODULES
            ), f'Classify {module}: it writes a batch-scope state field'
        if 'projection_state' in fields:
            assert module in PROJECTION_STATE_MODULES, f'Classify {module}: it writes projection_state'


# --- bounded reasons --------------------------------------------------------


def test_unknown_legacy_reason_has_bounded_representation():
    for entry in ENTRIES:
        if entry.reason_field is None:
            continue
        assert entry.reasons, f'{entry.key} declares a reason field without a vocabulary'
        assert 'legacy' in entry.reasons, f'{entry.key} needs a bounded legacy bucket'
        assert all(label == label.lower() and ' ' not in label for label in entry.reasons)


def test_reason_vocabularies_match_code_enums():
    from database.batch_pipeline_privacy import BatchPrivacyReason
    from utils.observability.reasons import VendorHoldReason

    assert set(batch_census.VENDOR_HOLD_REASONS) == {reason.value for reason in VendorHoldReason} | {'legacy'}
    assert set(batch_census.PRIVACY_REASONS) == {reason.value for reason in BatchPrivacyReason} | {'legacy'}


def test_dead_and_quarantine_reasons_are_bounded():
    assert set(batch_census.DEAD_REASONS) == {'held_expired', 'input_expiring', 'record_barrier_aged', 'legacy'}
    assert set(batch_census.QUARANTINE_REASONS) == {'worker_failed', 'legacy'}


# --- neighbour vocabularies -------------------------------------------------


def test_memory_outbox_states_match_the_model():
    from models.memory_apply import MemoryOutboxStatus

    assert states_for('memory_outbox') == {status.value for status in MemoryOutboxStatus}


def test_collection_names_match_code():
    from database.outbox_provider_stt import collection_name as provider_outbox_name

    assert batch_census.COLLECTIONS['provider_outbox'] == (
        provider_outbox_name('prod'),
        provider_outbox_name('dev'),
    )
    assert batch_census.COLLECTIONS['jobs'] == ('batch_pipeline_prod_jobs', 'batch_pipeline_dev_jobs')
    assert batch_census.COLLECTIONS['results'] == ('batch_pipeline_prod_results', 'batch_pipeline_dev_results')


# --- registry shape ---------------------------------------------------------


def test_registry_keys_are_unique_and_scoped():
    keys = [entry.key for entry in ENTRIES]
    assert len(keys) == len(set(keys))
    for entry in ENTRIES:
        assert entry.scope in {COLLECTION, COLLECTION_GROUP}
        assert entry.collection in batch_census.COLLECTIONS
        assert entry.field in STATE_FIELDS
        assert entry.filters and entry.filters[0][0] == entry.field


def test_custody_assumptions_are_marked():
    for entry in ENTRIES:
        if entry.custody is None:
            continue
        assert entry.custody.provenance in {'declared', 'unverified', 'none'}
        if entry.custody.provenance == 'unverified':
            assert entry.custody.note, f'{entry.key} must state why its custody clock is unverified'


def test_projection_custody_uses_a_field_results_documents_carry():
    # provider_intent is written on job documents only; results carry committed_at
    # or a stamped held_deadline_at.
    for entry in batch_census.entries_for('batch_projection'):
        if entry.custody is not None:
            assert entry.custody.clock in {'committed_at', 'held_deadline_at'}, entry.key
    assert batch_census.BY_KEY['batch_projection:ready'].custody.clock == 'committed_at'
    assert batch_census.BY_KEY['batch:result_ready'].custody.clock == 'provider_intent.settled_at'


def test_unverified_clocks_are_marked():
    for entry in ENTRIES:
        if entry.clock is None:
            assert not entry.clock_verified
        if not entry.clock_verified:
            assert entry.clock is None or entry.custody is not None or entry.legacy


def test_recovery_entries_state_that_the_vocabulary_is_not_yet_guarded():
    for entry in batch_census.entries_for('batch_recovery'):
        assert 'not AST-guarded' in entry.note, entry.key


# --- changed-file CI selection ---------------------------------------------


@pytest.mark.parametrize(
    'path',
    [
        'backend/utils/batch_pipeline/provider_stt.py',
        'backend/database/batch_pipeline_speech_redrive.py',
        'backend/utils/observability/reasons.py',
        'backend/config/batch_census.py',
        'backend/scripts/batch_pipeline_poll_state_census.py',
    ],
)
def test_census_guard_runs_for_writer_and_vocabulary_changes(path):
    selector = runpy.run_path(str(BACKEND / 'scripts/select_backend_unit_tests.py'))
    guard = set(selector['CENSUS_GUARD_TESTS'])
    assert guard == {'tests/unit/test_batch_census_registry.py'}
    all_tests = selector['discover_all_tests']()
    selected, reason = selector['tests_for_changed_paths']([path], all_tests)
    assert guard <= set(selected), reason


def test_unmapped_census_neighbours_keep_their_full_fallback():
    selector = runpy.run_path(str(BACKEND / 'scripts/select_backend_unit_tests.py'))
    all_tests = selector['discover_all_tests']()
    # The registry is not otherwise mapped to a narrow area, so its edit must
    # still select the full suite while the guard runs.
    selected, _reason = selector['tests_for_changed_paths'](['backend/config/batch_census.py'], all_tests)
    assert set(selected) == set(all_tests)


# --- poll-state census ------------------------------------------------------


def test_known_states_matches_registry_job_vocabulary():
    from scripts.batch_pipeline_poll_state_census import KNOWN_STATES

    assert list(KNOWN_STATES) == list(JOB_STATES)


def test_known_states_merge_pending_scope_stays_explicit():
    from scripts import batch_pipeline_poll_state_census as tool

    source = Path(tool.__file__).read_text()
    assert "FieldFilter('merge_pending', '==', True)" in source
    waiting = batch_census.BY_KEY['batch:record_recovery_waiting']
    assert 'merge_pending=False' in waiting.note
    assert 'record_recovery_waiting' in JOB_STATES


# --- generated manifest -----------------------------------------------------


def test_generator_produces_exact_checked_in_manifest():
    from scripts import generate_firestore_indexes

    manifest = (ROOT / 'firestore.indexes.json').read_text(encoding='utf-8')
    assert manifest == generate_firestore_indexes.render_manifest()


def _signatures():
    data = json.loads((ROOT / 'firestore.indexes.json').read_text(encoding='utf-8'))
    return {
        (
            index['collectionGroup'],
            index['queryScope'],
            tuple((field['fieldPath'], field.get('order') or field.get('arrayConfig')) for field in index['fields']),
        )
        for index in data['indexes']
    }


@pytest.mark.parametrize(
    'collection,scope,fields',
    [
        ('batch_pipeline_prod_jobs', COLLECTION, ('state', 'provider_intent.settled_at', '__name__')),
        ('batch_pipeline_dev_jobs', COLLECTION, ('state', 'provider_intent.settled_at', '__name__')),
        ('batch_pipeline_prod_jobs', COLLECTION, ('state', 'fresh_capture', 'enqueued_at', '__name__')),
        ('batch_pipeline_dev_jobs', COLLECTION, ('state', 'fresh_capture', 'enqueued_at', '__name__')),
        ('batch_pipeline_prod_provider_stt_outbox', COLLECTION, ('state', 'created_at', '__name__')),
        ('batch_pipeline_dev_provider_stt_outbox', COLLECTION, ('state', 'created_at', '__name__')),
        ('batch_pipeline_prod_provider_stt_outbox', COLLECTION, ('state', 'due_at', '__name__')),
        ('batch_pipeline_dev_provider_stt_outbox', COLLECTION, ('state', 'due_at', '__name__')),
        ('batch_pipeline_prod_results', COLLECTION, ('projection_state', 'held_deadline_at', '__name__')),
        ('batch_pipeline_dev_results', COLLECTION, ('projection_state', 'held_deadline_at', '__name__')),
        ('memory_outbox', COLLECTION_GROUP, ('status', 'available_at', '__name__')),
    ],
)
def test_census_indexes_are_declared_with_expected_scope(collection, scope, fields):
    signature = (collection, scope, tuple((field, 'ASCENDING') for field in fields))
    assert signature in _signatures()


def test_memory_outbox_keeps_both_scopes():
    signatures = _signatures()
    fields = (('status', 'ASCENDING'), ('available_at', 'ASCENDING'), ('__name__', 'ASCENDING'))
    assert ('memory_outbox', COLLECTION, fields) in signatures
    assert ('memory_outbox', COLLECTION_GROUP, fields) in signatures


def test_conversations_and_cap_hold_indexes_stay_collection_scoped():
    from database.batch_pipeline_indexes import BATCH_PIPELINE_INDEX_REQUIREMENTS

    signatures = _signatures()
    assert (
        'conversations',
        COLLECTION,
        (('status', 'ASCENDING'), ('finished_at', 'ASCENDING'), ('__name__', 'ASCENDING')),
    ) in signatures
    assert (
        'stt_cap_holds',
        COLLECTION,
        (('state', 'ASCENDING'), ('listed_at', 'DESCENDING'), ('__name__', 'DESCENDING')),
    ) in signatures
    # This PR's census declarations add no conversations or cap-hold index; their
    # existing scoped twins predate this change and are not duplicated here.
    census = [
        requirement
        for requirement in BATCH_PIPELINE_INDEX_REQUIREMENTS
        if '_batch_census_' in requirement.identifier
        or requirement.identifier == 'memory_outbox_group_status_available_at'
    ]
    assert len(census) == 11
    assert not {requirement.collection_group for requirement in census} & {'conversations', 'stt_cap_holds'}

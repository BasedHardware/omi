import ast
import importlib
from dataclasses import replace
from pathlib import Path

import pytest

from database.firestore_index_registry import FIELD_INDEX_REQUIREMENTS
from scripts import firestore_index_oracle as oracle
from scripts import firestore_query_shapes as exporter
from tests.support import firestore_outside_query_drivers as outside
from tests.support.firestore_caller_witnesses import (
    install_capture,
    matching_profile_names,
    witness_completeness_errors,
)
from tests.support.firestore_conversation_profiles import discover_callers
from tests.support.firestore_index_rules import is_served
from tests.support.firestore_outside_caller_witnesses import (
    TARGETS as OUTSIDE_WITNESS_TARGETS,
    WITNESSES as OUTSIDE_WITNESSES,
    _run_scheduled_health_check,
)
from tests.support.firestore_query_driver_registry import DRIVERS
from tests.support.firestore_query_drivers import run_all_drivers
from tests.support.firestore_serving_query_inventory import (
    discover_serving_query_functions,
    serving_function_body_digest,
)
from tests.support.firestore_shape_recorder import RecordingFirestore
from tests.unit.fixtures.offline_firestore_sdk import OfflineFirestoreClient

ROOT = Path(__file__).resolve().parents[2]

OUTSIDE_FIELD_REQUIREMENT_PAIRS = (
    ('chat_first_dead_letters', 'created_at'),
    ('chat_first_proactive_intents', 'created_at'),
    ('fair_use_events', 'case_ref'),
    ('llm_usage', 'date'),
)


@pytest.fixture(scope='module')
def outside_results():
    return run_all_drivers(outside.DRIVERS)


@pytest.fixture(scope='module')
def outside_caller_inventory():
    return discover_callers(ROOT, OUTSIDE_WITNESS_TARGETS)


@pytest.fixture(scope='module')
def outside_contract_artifacts(outside_results):
    manifest = exporter.load_manifest()
    client = OfflineFirestoreClient(project='shape-contract')
    queries = {
        key: [
            oracle.build_query(oracle.hydrate_shape(shape.to_dict(), client, 'outside-contract'), client)
            for shape in result.shapes
        ]
        for key, result in outside_results.items()
    }
    payload = exporter.build_export(outside_results, manifest)
    return {'manifest': manifest, 'queries': queries, 'payload': payload}


def test_outside_registry_is_part_of_the_export_registry():
    assert outside.DRIVERS
    assert all(DRIVERS[key] is entry for key, entry in outside.DRIVERS.items())


def test_every_outside_shape_is_manifest_served_and_oracle_serializable(outside_results, outside_contract_artifacts):
    manifest = outside_contract_artifacts['manifest']
    for key, result in outside_results.items():
        assert not result.errors, (key, result.errors)
        assert result.shapes, key
        queries = outside_contract_artifacts['queries'][key]
        assert len(queries) == len(result.shapes)
        for shape, query in zip(result.shapes, queries):
            assert is_served(shape, manifest), (key, shape.to_dict())
            assert query is not None
    payload = outside_contract_artifacts['payload']
    assert {row['function'] for row in payload['drivers']} == set(outside.DRIVERS)
    assert payload['counts']['unserved_certain'] == payload['counts']['unserved_uncertain'] == 0
    for row in payload['shapes']:
        assert row['served'] and not row['uncertain'], (row['id'], row['driver_function'])
    assert oracle.deduplicate(payload['shapes'])


def test_operational_profiles_are_explicit_and_exported(outside_results):
    for key, entry in outside.DRIVERS.items():
        assert entry.profiles, key
        assert {shape.parameter_combo['caller_profile'] for shape in outside_results[key].shapes} == {
            profile.name for profile in entry.profiles
        }, key
        for profile in entry.profiles:
            want = not profile.name.startswith(('operational-', 'maintenance-'))
            assert profile.serving is want, (key, profile.name)
    assert (
        outside.DRIVERS['utils.memory.belief_backfill._default_item_reader'].profiles[0].name.startswith('operational-')
    )
    assert (
        outside.DRIVERS['services.users.data_export_iterators.iter_user_subcollection']
        .profiles[0]
        .name.startswith('export-')
    )
    assert (
        outside.DRIVERS['utils.memory.daily_memory_sweep_inventory._seed_registry']
        .profiles[0]
        .name.startswith('maintenance-')
    )


def test_nested_export_records_the_child_query(outside_results):
    shapes = outside_results['services.users.data_export_iterators.iter_user_nested_subcollection'].shapes
    assert {shape.collection_group for shape in shapes} >= {
        'goals',
        'workstreams',
        'events',
        'goal_history',
        'artifact_refs',
        'continuation_checkpoints',
    }
    assert any(shape.collection_path.endswith('/parent-1/events') for shape in shapes)


def test_state_fixtures_reach_fenced_claims_feedback_and_keyframes(outside_results):
    claim = outside_results['utils.memory.daily_memory_sweep._invoke_model_once_claimed'].shapes
    assert any(
        {predicate.field for predicate in shape.filters}
        == {'uid', 'account_generation', 'source_generation', 'sweep_generation', 'window_id'}
        for shape in claim
    )
    feedback = outside_results['utils.feedback_context.resolve_chat_context'].shapes
    assert any(
        {'chat_session_id', 'created_at'} == {predicate.field for predicate in shape.filters} for shape in feedback
    )
    keyframes = outside_results['services.conversation_keyframes.reconcile_conversation_keyframe_jobs'].shapes
    assert {shape.collection_group for shape in keyframes} >= {'conversation_keyframe_jobs', 'screen_activity'}
    assert any(shape.cursors for result in outside_results.values() for shape in result.shapes)


def test_outside_pins_are_literal_reviewed_function_fingerprints():
    tree = ast.parse((ROOT / 'tests/support/firestore_outside_query_drivers.py').read_text())
    node = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'BODY_DIGEST' for target in node.targets)
    )
    assert isinstance(node, ast.Dict)
    assert ast.literal_eval(node) == outside.BODY_DIGEST
    assert outside.BODY_DIGEST == {
        key: entry.body_digest for key, entry in {**outside.COVERED_BY, **outside.SKIPS}.items() if entry.body_digest
    }
    assert all(serving_function_body_digest(key) == digest for key, digest in outside.BODY_DIGEST.items())


@pytest.mark.parametrize('directory', ['routers', 'utils', 'services', 'jobs', 'new_serving_package'])
def test_serving_sentinel_covers_every_backend_directory(tmp_path, directory):
    folder = tmp_path / directory
    folder.mkdir()
    (folder / 'reader.py').write_text(
        "def read(db, flag):\n    query = db.collection('c')\n    if flag:\n        query = query.where('f', '==', 1)\n    return query.count().get()\n"
    )
    assert [row['key'] for row in discover_serving_query_functions(tmp_path)] == [f'{directory}.reader.read']


@pytest.mark.parametrize('directory', ['tests', 'scripts', 'migrations', 'testing', '.venv'])
def test_serving_sentinel_excludes_non_serving_roots(tmp_path, directory):
    folder = tmp_path / directory
    folder.mkdir()
    (folder / 'reader.py').write_text("def read(db):\n    return db.collection('c').stream()\n")
    assert discover_serving_query_functions(tmp_path) == []


def test_sentinel_finds_nested_builders_and_collection_gets_not_document_gets(tmp_path):
    (tmp_path / 'reader.py').write_text(
        "def nested(db):\n    def inner():\n        return db.collection('c').where('f', '==', 1).get()\n    return inner()\ndef collection(db):\n    ref = db.collection('c')\n    return ref.get()\ndef document(db):\n    ref = db.collection('c').document('d')\n    return ref.get()\ndef point(db):\n    return db.collection('c').document('d').get()\n"
    )
    assert {row['key'] for row in discover_serving_query_functions(tmp_path)} == {'reader.nested', 'reader.collection'}


def test_relocated_queries_keep_their_exact_shapes():
    module = importlib.import_module('database.serving_query_reads')
    client = RecordingFirestore()
    module.list_active_desktop_prompt_snapshots(firestore_client=client)
    module.list_desktop_release_snapshots(firestore_client=client)
    module.find_fair_use_case_snapshots('case-1', firestore_client=client)
    prompts, releases, case = client.shapes
    assert prompts.collection_group == 'desktop_prompts'
    assert [(p.field, p.operator, p.value) for p in prompts.filters] == [('active', '==', True)]
    assert prompts.limit == 50
    assert releases.orders == (('build_number', 'DESCENDING'),)
    assert case.scope == 'COLLECTION_GROUP' and case.collection_group == 'fair_use_events'
    assert [(p.field, p.operator, p.value) for p in case.filters] == [('case_ref', '==', 'case-1')]
    assert case.limit == 1


def test_outside_field_requirements_generate_their_manifest_overrides():
    manifest = exporter.load_manifest()
    for pair in OUTSIDE_FIELD_REQUIREMENT_PAIRS:
        collection, field = pair
        requirements = [
            requirement
            for requirement in FIELD_INDEX_REQUIREMENTS
            if (requirement.collection_group, requirement.field_path) == pair
        ]
        assert requirements, pair
        overrides = [
            entry for entry in manifest['fieldOverrides'] if (entry['collectionGroup'], entry['fieldPath']) == pair
        ]
        assert len(overrides) == 1, pair
        assert overrides[0] in [requirement.to_manifest() for requirement in requirements], pair
        assert not any(
            entry['collectionGroup'] == collection
            and entry['queryScope'] == 'COLLECTION_GROUP'
            and [part['fieldPath'] for part in entry['fields']] == [field, '__name__']
            for entry in manifest['indexes']
        )
    fair_use = next(
        requirement
        for requirement in FIELD_INDEX_REQUIREMENTS
        if (requirement.collection_group, requirement.field_path) == ('fair_use_events', 'case_ref')
    )
    assert set(fair_use.collection_group_modes) == {'ASCENDING', 'DESCENDING'}


def test_nonserving_outside_row_flipped_to_serving_fails_the_guard(outside_contract_artifacts):
    nonserving = [row for row in outside_contract_artifacts['payload']['shapes'] if not row['serving']]
    assert nonserving
    unserved = dict(nonserving[0], served=False)
    assert not exporter.format_guard_failure(exporter.evaluate_shapes([unserved]))
    flipped = dict(unserved, serving=True)
    assert exporter.format_guard_failure(exporter.evaluate_shapes([flipped]))


def test_outside_caller_witnesses_match_the_discovered_bindings(outside_caller_inventory):
    errors = witness_completeness_errors(outside_caller_inventory, OUTSIDE_WITNESSES)
    assert not errors, '; '.join(errors)
    for witness in OUTSIDE_WITNESSES.values():
        names = {profile.name for profile in outside.DRIVERS[witness.target].profiles}
        assert witness.profiles and set(witness.profiles) <= names, witness.key


def test_outside_caller_completeness_flags_a_new_discovered_binding(outside_caller_inventory):
    discovered = dict(outside_caller_inventory)
    injected = 'routers/fair_use_admin.py:new_case_route:database.serving_query_reads.find_fair_use_case_snapshots'
    discovered[injected] = {
        'target': 'database.serving_query_reads.find_fair_use_case_snapshots',
        'references': 1,
    }
    errors = witness_completeness_errors(discovered, OUTSIDE_WITNESSES)
    assert any(injected in error for error in errors)


@pytest.mark.parametrize('witness_key', sorted(OUTSIDE_WITNESSES))
def test_outside_caller_witness_executes_the_real_caller(monkeypatch, witness_key):
    witness = OUTSIDE_WITNESSES[witness_key]
    capture = install_capture(monkeypatch, witness)
    witness.run(monkeypatch, capture)
    assert capture.calls, witness_key
    profiles = outside.DRIVERS[witness.target].profiles
    for call in capture.calls:
        assert matching_profile_names(profiles, call) == set(witness.profiles), (witness_key, call)


def test_scheduled_health_check_windows_the_real_collector(monkeypatch):
    witness = OUTSIDE_WITNESSES[
        'utils/task_intelligence/chat_first_materialization_health.py:collect:'
        'utils.task_intelligence.chat_first_materialization_health._documents'
    ]
    capture = install_capture(monkeypatch, replace(witness, abort=False))
    status, captured = _run_scheduled_health_check(monkeypatch, capture)
    assert status == 'healthy'
    entry = outside.DRIVERS[witness.target]
    scheduled = next(profile for profile in entry.profiles if profile.name == 'scheduled-materialization-health')
    assert scheduled.serving is True
    assert matching_profile_names((scheduled,), captured) == {'scheduled-materialization-health'}
    for mutation in ({'uid': 'shape-user'}, {'min_created_at': None}, {'limit': 25}):
        assert not matching_profile_names((scheduled,), {**captured, **mutation})

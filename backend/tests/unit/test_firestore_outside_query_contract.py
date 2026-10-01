import ast
import importlib
from pathlib import Path

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore_v1 import Client

from scripts import firestore_index_oracle as oracle
from scripts import firestore_query_shapes as exporter
from tests.support import firestore_outside_query_drivers as outside
from tests.support.firestore_index_rules import is_served
from tests.support.firestore_query_driver_registry import DRIVERS
from tests.support.firestore_query_drivers import run_all_drivers
from database.firestore_outside_index_requirements import OUTSIDE_SERVING_FIELD_INDEX_CALLERS
from tests.support.firestore_serving_query_inventory import (
    discover_serving_query_functions,
    serving_function_body_digest,
)
from tests.support.firestore_shape_recorder import RecordingFirestore

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def outside_results():
    return run_all_drivers(outside.DRIVERS)


def test_outside_registry_is_part_of_the_export_registry():
    assert outside.DRIVERS
    assert all(DRIVERS[key] is entry for key, entry in outside.DRIVERS.items())


def test_every_outside_shape_is_manifest_served_and_oracle_serializable(outside_results):
    manifest = exporter.load_manifest()
    client = Client(project='shape-contract', credentials=AnonymousCredentials())
    for key, result in outside_results.items():
        assert not result.errors, (key, result.errors)
        assert result.shapes, key
        for shape in result.shapes:
            assert is_served(shape, manifest), (key, shape.to_dict())
            encoded = shape.to_dict()
            hydrated = oracle.hydrate_shape(encoded, client, 'outside-contract')
            query = oracle.build_query(hydrated, client)
            assert query is not None
    payload = exporter.build_export(outside_results, manifest)
    assert {row['function'] for row in payload['drivers']} == set(outside.DRIVERS)
    assert payload['counts']['unserved_certain'] == payload['counts']['unserved_uncertain'] == 0
    assert oracle.deduplicate(payload['shapes'])


def test_operational_profiles_are_explicit_and_exported(outside_results):
    for key, entry in outside.DRIVERS.items():
        assert entry.profiles, key
        assert {shape.parameter_combo['caller_profile'] for shape in outside_results[key].shapes} == {
            profile.name for profile in entry.profiles
        }, key
    assert (
        outside.DRIVERS['utils.memory.belief_backfill._default_item_reader'].profiles[0].name.startswith('operational-')
    )
    assert outside.DRIVERS['services.users.data_export._iter_user_subcollection'].profiles[0].name.startswith('export-')
    assert (
        outside.DRIVERS['utils.memory.daily_memory_sweep_inventory._seed_registry']
        .profiles[0]
        .name.startswith('maintenance-')
    )


def test_nested_export_records_the_child_query(outside_results):
    shapes = outside_results['services.users.data_export._iter_user_nested_subcollection'].shapes
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


def test_group_single_field_requirements_preserve_collection_defaults_and_cite_callers():
    manifest = exporter.load_manifest()
    for pair, callers in OUTSIDE_SERVING_FIELD_INDEX_CALLERS.items():
        collection, field = pair
        overrides = [
            entry for entry in manifest['fieldOverrides'] if (entry['collectionGroup'], entry['fieldPath']) == pair
        ]
        assert len(overrides) == 1, pair
        assert overrides[0]['indexes'] == [
            {'order': 'ASCENDING', 'queryScope': 'COLLECTION'},
            {'order': 'DESCENDING', 'queryScope': 'COLLECTION'},
            {'arrayConfig': 'CONTAINS', 'queryScope': 'COLLECTION'},
            {'order': 'ASCENDING', 'queryScope': 'COLLECTION_GROUP'},
        ]
        assert callers
        for caller in callers:
            path = caller.split(':')[0]
            assert (ROOT.parent / path if path.startswith('web/') else ROOT / path).is_file(), caller
        assert not any(
            entry['collectionGroup'] == collection
            and entry['queryScope'] == 'COLLECTION_GROUP'
            and [part['fieldPath'] for part in entry['fields']] == [field, '__name__']
            for entry in manifest['indexes']
        )

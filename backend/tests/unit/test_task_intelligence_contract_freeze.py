from copy import deepcopy
import json

import pytest

from utils.task_intelligence.contracts import (
    REQUIRED_CONTRACT_DOMAINS,
    REQUIRED_SOURCE_IDS,
    discover_backend_writer_anchors,
    load_contract_manifest,
    load_fixture,
    load_source_manifest,
    validate_contract_manifest,
    validate_source_manifest,
)
from utils.task_intelligence.fixture_runner import (
    TEST_ADAPTERS,
    run_capture_case,
    run_fixture_suite,
    run_recorded_association_case,
    run_recorded_ranking_case,
)


@pytest.fixture(scope='module')
def discovered_writer_anchors():
    return discover_backend_writer_anchors()


def test_v1_contract_manifest_has_every_cross_lane_domain():
    manifest = load_contract_manifest()

    validate_contract_manifest(manifest)

    assert set(manifest['$defs']).issuperset(REQUIRED_CONTRACT_DOMAINS)
    assert manifest['domain_owners']['candidate'] == 'backend product domain'
    assert manifest['domain_owners']['kernel_workstream_bridge'] == 'TypeScript runtime kernel'


def test_contract_manifest_rejects_missing_domain():
    manifest = deepcopy(load_contract_manifest())
    del manifest['$defs']['evidence_ref']

    with pytest.raises(ValueError, match='missing contract domains'):
        validate_contract_manifest(manifest)


def test_capture_fixture_freezes_cross_modality_semantics():
    fixture = load_fixture('capture_v2.json')

    assert fixture['schema_version'] == 1
    assert fixture['policy_version'] == 'capture.v2'
    for case in fixture['cases']:
        assert set(case['inputs']) == {'transcript', 'screen'}
        assert callable(TEST_ADAPTERS['transcript_capture_v2'])
        assert callable(TEST_ADAPTERS['screen_capture_v2'])
        transcript = run_capture_case(case, 'transcript')
        screen = run_capture_case(case, 'screen')
        assert transcript == screen
        assert transcript.__dict__ == case['expected']
        assert case['expected']['interruption'] != 'new_task_notification'

    by_id = {case['id']: case['expected'] for case in fixture['cases']}
    assert by_id['clear_commitment'] == {'outcome': 'auto_accept_silent', 'interruption': 'none'}
    assert by_id['unaccepted_request']['outcome'] == 'pending_candidate'
    assert by_id['owned_direct_request_at_confidence_floors']['outcome'] == 'pending_candidate'
    assert by_id['owned_direct_request_below_ownership_floor']['outcome'] == 'ignore'
    assert by_id['public_channel_not_owned']['outcome'] == 'ignore'


def test_association_and_ranking_fixtures_include_negative_and_empty_cases():
    association = load_fixture('association_v1.json')
    ranking = load_fixture('ranking_v2.json')

    association_by_id = {case['id']: run_recorded_association_case(case) for case in association['cases']}
    assert association_by_id['entity_only']['workstream_id'] is None
    assert association_by_id['immaterial_repeat']['material'] is False
    assert ranking['schema_version'] == 2
    assert ranking['policy_version'] == 'ranking.v2'

    for case in ranking['cases']:
        selected = run_recorded_ranking_case(case)
        assert set(selected).isdisjoint(case['must_not_select'])
    assert (
        next(case for case in ranking['cases'] if case['id'] == 'recent_only_correctly_returns_empty')[
            'recorded_judgment'
        ]
        == []
    )
    missing_evidence = next(case for case in ranking['cases'] if case['id'] == 'missing_evidence_fails_closed')
    assert run_recorded_ranking_case(missing_evidence) == ['grounded_due_task']


def test_fixture_runner_is_byte_stable():
    kwargs = {
        'capture': load_fixture('capture_v2.json'),
        'association': load_fixture('association_v1.json'),
        'ranking': load_fixture('ranking_v2.json'),
    }
    first = json.dumps(run_fixture_suite(**kwargs), sort_keys=True, separators=(',', ':'))
    second = json.dumps(run_fixture_suite(**kwargs), sort_keys=True, separators=(',', ':'))

    assert first == second


def test_source_manifest_registers_every_known_writer_class(discovered_writer_anchors):
    manifest = load_source_manifest()

    validate_source_manifest(manifest, discovered_anchors=discovered_writer_anchors)

    assert {source['id'] for source in manifest['sources']} == REQUIRED_SOURCE_IDS
    assert discovered_writer_anchors


def test_source_manifest_negative_check_rejects_scanner_discovered_unregistered_writer(
    tmp_path, discovered_writer_anchors
):
    manifest = load_source_manifest()
    discovered = set(discovered_writer_anchors)
    python_writer = tmp_path / 'backend' / 'services' / 'new_writer.py'
    swift_writer = tmp_path / 'desktop' / 'macos' / 'Desktop' / 'Sources' / 'NewWriter.swift'
    dart_writer = tmp_path / 'app' / 'lib' / 'new_writer.dart'
    for path in (python_writer, swift_writer, dart_writer):
        path.parent.mkdir(parents=True, exist_ok=True)
    python_writer.write_text(
        'from database import action_items as differently_named\n'
        'def write(uid, data):\n'
        '    return differently_named.create_action_item(uid, data)\n',
        encoding='utf-8',
    )
    swift_writer.write_text('func write() async { try await APIClient.shared.createActionItem() }\n', encoding='utf-8')
    dart_writer.write_text('Future<void> write() async { await api.updateActionItem("id"); }\n', encoding='utf-8')
    synthetic = discover_backend_writer_anchors(repository_root=tmp_path)
    assert synthetic == {
        ('backend/services/new_writer.py', 'action_items_db.create_action_item'),
        ('desktop/macos/Desktop/Sources/NewWriter.swift', 'client.createActionItem'),
        ('app/lib/new_writer.dart', 'client.updateActionItem'),
    }
    discovered.update(synthetic)

    with pytest.raises(ValueError, match='unregistered writer anchors'):
        validate_source_manifest(manifest, discovered_anchors=discovered)


def test_source_manifest_rejects_stale_writer_anchor(discovered_writer_anchors):
    manifest = deepcopy(load_source_manifest())
    manifest['sources'][0]['writer_anchors'].append(
        {'path': 'backend/routers/removed_writer.py', 'symbol': 'action_items_db.create_action_item', 'discover': True}
    )

    with pytest.raises(ValueError, match='stale writer anchors'):
        validate_source_manifest(manifest, discovered_anchors=discovered_writer_anchors)


def test_source_manifest_rejects_missing_owner_path(tmp_path):
    manifest = deepcopy(load_source_manifest())
    manifest['sources'][0]['owner_paths'] = ['missing/writer.py']

    with pytest.raises(ValueError, match='missing owner path'):
        validate_source_manifest(manifest, repository_root=tmp_path)


def test_fixture_loader_rejects_path_traversal():
    with pytest.raises(ValueError, match='simple filename'):
        load_fixture('../capture_v2.json')


def test_contract_rejects_candidate_payload_ambiguity_and_invalid_local_evidence():
    manifest = deepcopy(load_contract_manifest())
    candidate = deepcopy(
        next(candidate for candidate in manifest['examples']['candidate'] if candidate['subject_kind'] == 'workstream')
    )
    candidate['task_change'] = {'description': 'Conflicting task payload'}
    manifest['examples']['candidate'].append(candidate)

    with pytest.raises(ValueError, match='invalid candidate example'):
        validate_contract_manifest(manifest)

    manifest = deepcopy(load_contract_manifest())
    manifest['examples']['evidence_ref'][0].pop('device_id')
    with pytest.raises(ValueError, match='invalid evidence_ref example'):
        validate_contract_manifest(manifest)


def test_contract_accepts_task_create_and_update_candidates_but_rejects_missing_update_target():
    manifest = deepcopy(load_contract_manifest())
    validate_contract_manifest(manifest)
    candidates = manifest['examples']['candidate']
    assert {candidate['candidate_id'] for candidate in candidates}.issuperset({'cand-task-create', 'cand-task-update'})

    invalid = deepcopy(next(candidate for candidate in candidates if candidate['candidate_id'] == 'cand-task-update'))
    invalid.pop('task_id')
    manifest['examples']['candidate'].append(invalid)
    with pytest.raises(ValueError, match='invalid candidate example'):
        validate_contract_manifest(manifest)


def test_goal_metric_facts_and_task_priority_match_the_master_plan_contract():
    manifest = load_contract_manifest()
    definitions = manifest['$defs']

    assert set(definitions['goalMetric']['properties']) == {'type', 'current', 'target', 'min', 'max', 'unit'}
    assert definitions['goalMetric']['required'] == ['type', 'current', 'target']
    assert set(definitions['deterministicFacts']['properties']) == {
        'days_to_due',
        'someone_blocked',
        'has_concrete_next_action',
        'focused_goal_linked',
        'context_match_signals',
        'capture_confidence',
    }
    assert definitions['task']['properties']['priority']['enum'] == ['high', 'medium', 'low', None]
    assert manifest['examples']['task'][0]['priority'] == 'high'
    assert manifest['examples']['goal'][0]['metric']['unit'] == 'users'


@pytest.mark.parametrize(
    ('example_index', 'field'),
    [
        (0, 'candidate_id'),
        (1, 'task_id'),
        (2, 'resolution_code'),
        (3, 'candidate_id'),
        (4, 'intervention_id'),
        (5, 'feedback_action'),
        (6, 'attribution_chain_id'),
    ],
)
def test_attribution_json_schema_rejects_each_event_variant_without_required_linkage(example_index, field):
    manifest = deepcopy(load_contract_manifest())
    manifest['examples']['attribution_event'][example_index].pop(field)

    with pytest.raises(ValueError, match='invalid attribution_event example'):
        validate_contract_manifest(manifest)


@pytest.mark.parametrize(
    ('domain', 'container_field'),
    [('goal', 'metric'), ('decision_record', 'facts_snapshot'), ('kernel_workstream_bridge', 'open_loop_snapshot')],
)
def test_cross_lane_structured_snapshots_reject_private_blob_escape_hatches(domain, container_field):
    manifest = deepcopy(load_contract_manifest())
    example = manifest['examples'][domain][0]
    if domain == 'goal':
        example[container_field] = {'raw_prompt': 'private'}
    elif domain == 'kernel_workstream_bridge':
        example[container_field][0]['raw_prompt'] = 'private'
    else:
        example[container_field]['raw_prompt'] = 'private'

    with pytest.raises(ValueError, match=f'invalid {domain} example'):
        validate_contract_manifest(manifest)

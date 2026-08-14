import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from v3_dev_cloud_proof import (
    GATE_STATUS_BLOCKED,
    GATE_STATUS_READY_TO_EXECUTE,
    REQUIRED_ARTIFACTS,
    build_dev_cloud_fixture_bundle,
    build_proof_matrix,
    build_target_preflight_report,
    write_prepared_bundle,
)


def _complete_env():
    return {
        'MEMORY_DEV_CLOUD_PROJECT_ID': 'omi-memory-dev',
        'MEMORY_DEV_CLOUD_PROJECT_NUMBER': '1234567890',
        'MEMORY_DEV_CLOUD_DATABASE_ID': '(default)',
        'MEMORY_DEV_CLOUD_REGION': 'us-central1',
        'MEMORY_DEV_CLOUD_BACKEND_URL': 'https://memory-dev.example.test',
        'MEMORY_DEV_CLOUD_DEPLOYED_REVISION': 'memory-dev-rev-1',
        'MEMORY_DEV_CLOUD_IMAGE_DIGEST': 'sha256:' + 'a' * 64,
        'MEMORY_DEV_CLOUD_RUNTIME_SERVICE_ACCOUNT': 'runtime@omi-memory-dev.iam.gserviceaccount.com',
        'MEMORY_DEV_CLOUD_FIXTURE_WRITER_PRINCIPAL': 'fixture-writer@omi-memory-dev.iam.gserviceaccount.com',
        'GOOGLE_CLOUD_PROJECT': 'omi-memory-dev',
        'GOOGLE_CLOUD_PROJECT_NUMBER': '1234567890',
        'MEMORY_PRODUCTION_PROJECT_IDS': 'omi-prod,basedhardware-prod',
        'MEMORY_PRODUCTION_PROJECT_NUMBERS': '999,888',
        'MEMORY_V3_GET_ENABLED': 'true',
        'MEMORY_MODE': 'read',
        'MEMORY_ENABLED_USERS': 'memory-dev-synthetic-user-a,memory-dev-synthetic-user-b',
        'MEMORY_V3_CURSOR_SECRET': 'do-not-emit-this-secret',
        'MEMORY_V3_CURSOR_SECRET_VERSION': 'dev-v1',
    }


def test_default_preflight_is_blocked_and_non_mutating():
    report = build_target_preflight_report({})

    assert report['status'] == GATE_STATUS_BLOCKED
    assert report['mutation_allowed'] is False
    assert any(blocker['blocker_id'] == 'missing_required_env' for blocker in report['blockers'])
    assert 'READY_TO_EXECUTE_DEV_CLOUD_PROOF is not Gate 2 GO.' in report['non_claims']


def test_complete_non_prod_preflight_is_ready_to_execute_but_not_gate_go():
    report = build_target_preflight_report(_complete_env())

    assert report['status'] == GATE_STATUS_READY_TO_EXECUTE
    assert report['blockers'] == []
    assert report['target']['actual_project_id'] == 'omi-memory-dev'
    assert report['target']['runtime_service_account'] != report['target']['fixture_writer_principal']
    assert 'READY_TO_EXECUTE_DEV_CLOUD_PROOF is not Gate 2 GO.' in report['non_claims']


def test_preflight_hard_stops_on_production_project_id_and_number():
    env = _complete_env()
    env['MEMORY_DEV_CLOUD_PROJECT_ID'] = 'omi-prod'
    env['GOOGLE_CLOUD_PROJECT'] = 'omi-prod'
    env['MEMORY_DEV_CLOUD_PROJECT_NUMBER'] = '999'
    env['GOOGLE_CLOUD_PROJECT_NUMBER'] = '999'

    report = build_target_preflight_report(env)
    blocker_ids = {blocker['blocker_id'] for blocker in report['blockers']}

    assert report['status'] == GATE_STATUS_BLOCKED
    assert 'expected_project_id_is_production' in blocker_ids
    assert 'actual_project_id_is_production' in blocker_ids
    assert 'expected_project_number_is_production' in blocker_ids
    assert 'actual_project_number_is_production' in blocker_ids


def test_preflight_rejects_runtime_identity_as_fixture_writer():
    env = _complete_env()
    env['MEMORY_DEV_CLOUD_FIXTURE_WRITER_PRINCIPAL'] = env['MEMORY_DEV_CLOUD_RUNTIME_SERVICE_ACCOUNT']

    report = build_target_preflight_report(env)

    assert report['status'] == GATE_STATUS_BLOCKED
    assert any(blocker['blocker_id'] == 'runtime_identity_matches_fixture_writer' for blocker in report['blockers'])


def test_fixture_bundle_uses_two_synthetic_users_and_no_firestore_writes():
    bundle = build_dev_cloud_fixture_bundle(uid_a='dev-a', uid_b='dev-b', run_id='run-1', account_generation=3)

    assert bundle['status'] == 'NOT_RUN'
    assert bundle['synthetic_uids'] == ['dev-a', 'dev-b']
    assert bundle['document_count'] == len(bundle['documents'])
    assert 'memory_control/global_read_gate' in bundle['documents']
    assert 'memory_control/write_convergence_gate' in bundle['documents']
    assert 'users/dev-a/memory_state/head' in bundle['documents']
    assert 'users/dev-b/memory_state/head' in bundle['documents']
    assert bundle['documents']['users/dev-a/memory_control/state']['mode'] == 'read'
    assert bundle['documents']['users/dev-a/memory_control/state']['grants']['omi_chat']['default_memory'] is True
    assert bundle['documents']['users/dev-a/memory_state/head']['source'] == 'memory_state_head'
    assert any('does not write Firestore' in claim for claim in bundle['non_claims'])


def test_proof_matrix_contains_required_security_and_rollback_cases():
    matrix = build_proof_matrix()
    case_ids = {case['id'] for case in matrix['cases']}

    assert matrix['status'] == 'NOT_RUN'
    assert matrix['required_case_count'] >= 20
    assert 'user_a_references_user_b' in case_ids
    assert 'runtime_firestore_read_permission_denied' in case_ids
    assert 'every_get_case_zero_memory_writes' in case_ids
    assert 'kill_switch_rollback' in case_ids


def test_write_prepared_bundle_creates_full_artifact_contract(tmp_path):
    repo_root = Path(__file__).resolve().parents[3]
    output_dir = tmp_path / 'bundle'

    result = write_prepared_bundle(
        repo_root=repo_root,
        output_dir=output_dir,
        uid_a='dev-a',
        uid_b='dev-b',
        run_id='run-1',
        env=_complete_env(),
    )

    assert result['status'] == GATE_STATUS_READY_TO_EXECUTE
    assert result['artifact_count'] == len(REQUIRED_ARTIFACTS)
    for artifact in REQUIRED_ARTIFACTS:
        assert (output_dir / artifact).exists(), artifact
    manifest = json.loads((output_dir / 'candidate-manifest.json').read_text())
    assert manifest['redacted_env']['MEMORY_V3_CURSOR_SECRET'] == '<redacted>'
    assert manifest['redacted_env']['MEMORY_ENABLED_USERS'] == '<set:redacted-user-list>'
    checksums = (output_dir / 'checksums.sha256').read_text()
    assert 'candidate-manifest.json' in checksums
    assert 'fixtures.redacted.json' in checksums

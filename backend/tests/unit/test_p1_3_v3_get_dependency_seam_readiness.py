import importlib.util
import json
from pathlib import Path


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location('v17_p1_3_v3_get_dependency_seam_readiness', script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(execute=False):
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / 'scripts' / 'p1_3_v3_get_dependency_seam_readiness.py')
    return module.build_report(execute=execute)


def test_get_dependency_seam_readiness_is_blocked_read_only_and_safe():
    report = _report(execute=False)

    assert report['artifact'] == 'v17_p1_3_v3_get_dependency_seam_readiness'
    assert report['status'] == 'BLOCKED'
    assert report['proof_status'] == 'NOT_RUN'
    assert report['read_only'] is True
    assert report['runtime_wiring_changed'] is False
    assert report['routers_memories_modified'] is False
    assert report['production_app_imported'] is False
    assert report['network_or_provider_calls_executed'] is False
    assert report['firestore_reads_executed'] is False
    assert report['firestore_writes_executed'] is False
    assert report['telemetry_sink_calls_executed'] is False
    assert report['approval_claimed'] is False


def test_get_dependency_seam_readiness_pins_deterministic_dependency_order():
    report = _report(execute=True)

    assert report['proof_status'] == 'BLOCKED'
    assert report['dependency_order'] == [
        'authenticate_subject',
        'reject_client_uid_override',
        'load_enrollment_control',
        'validate_runtime_config',
        'validate_cursor',
        'select_projection_source',
        'check_rate_limit_backpressure',
        'projection_read_allowed_after_rate_limit_backpressure',
    ]
    assert report['rate_limit_before_projection_read'] is True
    assert report['auth_subject_first'] is True
    assert report['client_uid_override_rejected_before_control'] is True


def test_get_dependency_seam_readiness_cases_are_fail_closed_without_route_claims():
    report = json.loads(json.dumps(_report(execute=True), sort_keys=True))
    cases = {case['case_id']: case for case in report['seam_cases']}

    assert cases['happy_enrolled_ready']['status'] == 'READY'
    assert cases['client_uid_override']['decision_code'] == 'client_uid_override_rejected'
    assert cases['non_enrolled']['status'] == 'LEGACY_PRIMARY_ONLY'
    assert cases['non_enrolled']['v17_legacy_merge_allowed'] is False
    for case_id in [
        'control_missing',
        'config_missing',
        'cursor_invalid',
        'projection_source_missing',
        'backpressure_denied',
    ]:
        assert cases[case_id]['status'] == 'BLOCKED'
        assert cases[case_id]['should_fetch_v17_projection'] is False
        assert cases[case_id]['should_fetch_legacy'] is False
    assert report['summary']['blocked_case_count'] == 6
    assert report['summary']['legacy_primary_only_case_count'] == 1


def test_get_dependency_seam_readiness_is_registered_and_does_not_import_routes():
    root = Path(__file__).resolve().parents[2]
    script_path = root / 'scripts' / 'p1_3_v3_get_dependency_seam_readiness.py'
    source = script_path.read_text(encoding='utf-8')
    test_sh = (root / 'test.sh').read_text(encoding='utf-8')
    external_script = (root / 'scripts' / 'p1_3_v3_external_compatibility_readiness.py').read_text(encoding='utf-8')
    runtime_script = (root / 'scripts' / 'p1_3_v3_get_runtime_wiring_readiness.py').read_text(encoding='utf-8')
    ticket_doc = (root.parent / 'docs' / 'epics' / 'v17_memory_implementation_tickets.md').read_text(encoding='utf-8')
    oracle_doc = (root.parent / 'docs' / 'epics' / 'v17_t20_oracle_milestone_review.md').read_text(encoding='utf-8')

    assert 'backend.routers.memories' not in source
    assert 'routers.memories' not in source
    assert 'TestClient(' not in source
    assert 'requests.' not in source
    assert 'test_v3_get_dependency_seam.py' in test_sh
    assert 'test_p1_3_v3_get_dependency_seam_readiness.py' in test_sh
    assert 'get_dependency_seam_readiness_proof' in external_script
    assert 'get_dependency_seam_readiness_proof' in runtime_script
    assert 'p1_3_v3_get_dependency_seam_readiness.py' in ticket_doc
    assert 'pre-wiring GET dependency seam/adapter readiness' in ticket_doc
    assert 'p1_3_v3_get_dependency_seam_readiness.py' in oracle_doc
    assert 'pre-wiring GET dependency seam/adapter readiness' in oracle_doc

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / 'backend' / 'scripts' / 'p1_3_v3_fastapi_route_contract.py'
TEST_SH = REPO_ROOT / 'backend' / 'test.sh'
TICKET_DOC = REPO_ROOT / 'docs' / 'epics' / 'memory_implementation_tickets.md'
ORACLE_DOC = REPO_ROOT / 'docs' / 'epics' / 'memory_t20_oracle_milestone_review.md'
VENV_PYTHON = REPO_ROOT / 'backend' / 'venv' / 'bin' / 'python'


def _proof_python() -> Path | str:
    """Run the FastAPI proof in the repo venv when present.

    The normal Hermes/backend pytest environment intentionally may not include
    FastAPI. The route contract proof is still valid and local, but it must not
    make the full memory unit glob uncollectable outside the venv.
    """
    return VENV_PYTHON if VENV_PYTHON.exists() else sys.executable


def _run_script(*args):
    completed = subprocess.run(
        [str(_proof_python()), str(SCRIPT), *args],
        cwd=REPO_ROOT / 'backend',
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return json.loads(completed.stdout)


def test_v3_fastapi_route_contract_runner_exists_and_is_local_only():
    assert SCRIPT.exists(), 'missing controlled FastAPI/TestClient /v3 route contract runner'
    report = _run_script()

    assert report['status'] == 'BLOCKED'
    assert report['proof_status'] == 'PASSED'
    assert report['runtime_wired'] is False
    assert report['read_only'] is True
    assert report['mutation_allowed'] is False
    assert report['network_or_provider_calls_executed'] is False
    assert report['provider_calls_executed'] is False
    assert report['cloud_calls_executed'] is False
    assert report['firestore_reads_executed'] is False
    assert report['firestore_writes_executed'] is False
    assert report['production_rollout_approved'] is False


def test_v3_fastapi_route_contract_executes_response_model_and_header_cases():
    report = _run_script('--execute')

    assert report['fastapi_testclient_importable'] is True
    assert report['route_under_test'] == 'GET /v3/memories'
    assert report['response_model'] == 'List[MemoryDB]'
    assert report['app_type'] == 'controlled_isolated_fastapi_app'
    assert report['imports_real_router_or_app'] is False

    cases = {case['case_id']: case for case in report['cases']}
    assert cases['legacy_compatible_item']['status_code'] == 200
    assert cases['legacy_compatible_item']['body'][0]['id'] == 'mem-legacy-1'
    assert cases['legacy_compatible_item']['body'][0]['content'] == 'User likes tea'
    assert cases['legacy_compatible_item']['body'][0]['category'] == 'system'
    assert cases['legacy_compatible_item']['body'][0]['reviewed'] is True
    assert cases['legacy_compatible_item']['body'][0]['manually_added'] is False

    header_case = cases['additive_headers_no_body_mutation']
    assert header_case['status_code'] == 200
    assert header_case['headers']['x-omi-memory-source'] == 'memory-default-projection'
    assert header_case['headers']['x-omi-memory-policy'] == 'default_memory'
    assert 'x-omi-memory-source' not in json.dumps(header_case['body'])
    assert header_case['body'][0]['id'] == 'mem-header-1'


def test_v3_fastapi_route_contract_pins_enabled_empty_denied_and_no_leakage_behavior():
    report = _run_script('--execute')
    cases = {case['case_id']: case for case in report['cases']}

    assert cases['enabled_empty']['status_code'] == 200
    assert cases['enabled_empty']['body'] == []
    assert cases['enabled_empty']['legacy_fallback_marker_present'] is False

    denied = cases['fail_closed_denied_no_body_data']
    assert denied['status_code'] == 403
    assert denied['body_text'] == ''
    assert denied['json_body'] is None
    assert denied['legacy_fallback_marker_present'] is False
    assert denied['memory_body_data_present'] is False

    no_leak = cases['memory_only_fields_filtered_from_memorydb_body']
    assert no_leak['status_code'] == 200
    body_text = json.dumps(no_leak['body'], sort_keys=True)
    assert 'memory_source' not in body_text
    assert 'account_generation' not in body_text
    assert 'projection_generation' not in body_text
    assert 'archive_default_visible' not in body_text
    assert no_leak['body'][0]['id'] == 'mem-filter-1'


def test_v3_fastapi_route_contract_registered_documented_and_linked_from_readiness():
    test_sh = TEST_SH.read_text()
    ticket_doc = TICKET_DOC.read_text()
    oracle_doc = ORACLE_DOC.read_text()

    assert 'test_p1_3_v3_fastapi_route_contract.py' in test_sh
    assert 'p1_3_v3_fastapi_route_contract.py' in ticket_doc
    assert 'p1_3_v3_fastapi_route_contract.py' in oracle_doc

    readiness_script = REPO_ROOT / 'backend' / 'scripts' / 'p1_3_v3_external_compatibility_readiness.py'
    readiness_text = readiness_script.read_text()
    assert 'fastapi_route_contract_proof' in readiness_text
    assert 'backend/scripts/p1_3_v3_fastapi_route_contract.py' in readiness_text

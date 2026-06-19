import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / 'backend' / 'scripts' / 'v17_p1_5_tools_fastapi_testclient_readiness.py'
TICKET_DOC = REPO_ROOT / 'docs' / 'epics' / 'v17_memory_implementation_tickets.md'
ORACLE_DOC = REPO_ROOT / 'docs' / 'epics' / 'v17_t20_oracle_milestone_review.md'
TEST_SH = REPO_ROOT / 'backend' / 'test.sh'


def _run_readiness(*args):
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return json.loads(completed.stdout)


def _local_fastapi_importable():
    try:
        return importlib.util.find_spec('fastapi') is not None
    except ValueError:
        return False


def test_tools_fastapi_testclient_readiness_is_safe_blocked_by_default():
    report = _run_readiness()

    assert report['status'] == 'BLOCKED'
    assert report['proof_status'] == 'NOT_RUN'
    assert report['read_only'] is True
    assert report['mutation_allowed'] is False
    assert report['network_or_provider_calls_executed'] is False
    assert report['provider_calls_executed'] is False
    assert report['cloud_calls_executed'] is False
    assert report['firestore_reads_executed'] is False
    assert report['firestore_writes_executed'] is False
    assert report['benchmark_evidence_collected'] is False
    assert report['approval_claimed'] is False
    assert report['production_rollout_approved'] is False
    assert report['fastapi_testclient_importable'] == _local_fastapi_importable()
    assert report['route_surfaces_count'] == 3
    assert report['behavior_cases_count'] == 6


def test_tools_fastapi_testclient_readiness_pins_exact_routes_and_gap_cases():
    report = _run_readiness('--execute')
    route_keys = {surface['key'] for surface in report['route_surfaces']}
    case_keys = {case['key'] for case in report['behavior_cases']}

    assert route_keys == {
        'tools_rest_get_memories',
        'tools_rest_search_memories',
        'agent_execute_tool_memory_tools',
    }
    assert case_keys == {
        'response_model_serialization',
        'quoted_evidence_boundary_preservation',
        'fail_closed_denied_and_no_grant_states',
        'enabled_empty_state_stability',
        'prompt_injection_payload_as_quoted_data',
        'archive_and_stale_short_term_default_unavailable',
    }
    assert all(surface['status'] == 'NOT_RUN' for surface in report['route_surfaces'])
    assert all(surface['evidence'] == [] for surface in report['route_surfaces'])
    assert all(case['status'] == 'NOT_RUN' for case in report['behavior_cases'])
    assert all(case['evidence'] == [] for case in report['behavior_cases'])


def test_tools_fastapi_testclient_readiness_links_existing_local_proof_and_non_claims():
    report = _run_readiness('--execute')
    text = json.dumps(report, sort_keys=True)

    assert 'backend/routers/tools.py GET /v1/tools/memories' in text
    assert 'backend/routers/tools.py POST /v1/tools/memories/search' in text
    assert 'backend/routers/agent_tools.py POST /v1/agent/execute-tool' in text
    assert 'backend/tests/unit/test_v17_tools_agent_route_response_shape.py' in text
    assert 'backend/tests/unit/test_v17_tools_rest_memory_runtime_adapter.py' in text
    assert 'FastAPI TestClient production-dependency proof was not run' in text
    assert 'No production traffic' in text
    assert 'No Firestore/Pinecone/cloud/provider calls' in text


def test_tools_fastapi_testclient_readiness_pins_exact_dependency_and_install_blocker():
    report = _run_readiness('--execute')
    text = json.dumps(report, sort_keys=True)

    assert report['dependency_evidence']['required_dependency_file'] == 'backend/requirements.txt'
    assert report['dependency_evidence']['required_fastapi_pin'] == 'fastapi==0.121.0'
    assert report['dependency_evidence']['required_httpx_pin'] == 'httpx==0.28.0'
    assert report['dependency_evidence']['verification_python_major_minor']
    assert report['dependency_evidence']['local_fastapi_import_error'] in ('ModuleNotFoundError', None)
    assert report['dependency_evidence']['bounded_install_attempted'] is True
    assert (
        report['dependency_evidence']['bounded_install_command'] == "python3 -m pip install --user 'fastapi==0.121.0'"
    )
    assert report['dependency_evidence']['bounded_install_exit_code'] == 1
    assert 'externally-managed-environment' in report['dependency_evidence']['bounded_install_stderr_excerpt']
    assert 'PEP 668' in report['dependency_evidence']['bounded_install_stderr_excerpt']
    assert 'fastapi==0.121.0' in text
    assert 'httpx==0.28.0' in text
    assert 'externally-managed-environment' in text


def test_tools_fastapi_testclient_readiness_registered_and_documented():
    test_sh = TEST_SH.read_text()
    ticket_doc = TICKET_DOC.read_text()
    oracle_doc = ORACLE_DOC.read_text()

    assert 'test_v17_p1_5_tools_fastapi_testclient_readiness.py' in test_sh
    assert 'v17_p1_5_tools_fastapi_testclient_readiness.py' in ticket_doc
    assert 'v17_p1_5_tools_fastapi_testclient_readiness.py' in oracle_doc
    assert 'FastAPI `TestClient` production-dependency proof remains BLOCKED/NOT_RUN' in ticket_doc
    assert 'FastAPI `TestClient` production-dependency proof remains BLOCKED/NOT_RUN' in oracle_doc

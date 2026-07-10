#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROUTE_SURFACES: List[Dict[str, Any]] = [
    {
        'key': 'tools_rest_get_memories',
        'status': 'NOT_RUN',
        'route_reference': 'backend/routers/tools.py GET /v1/tools/memories',
        'response_model': 'ToolResponse',
        'existing_local_proof': [
            'backend/tests/unit/test_tools_agent_route_response_shape.py',
            'backend/tests/unit/test_tools_rest_memory_runtime_adapter.py',
        ],
        'required_fastapi_testclient_proof': 'Exercise the real FastAPI route via TestClient with dependency overrides, then prove response-model serialization preserves bounded memory evidence text and fail-closed text.',
        'evidence': [],
    },
    {
        'key': 'tools_rest_search_memories',
        'status': 'NOT_RUN',
        'route_reference': 'backend/routers/tools.py POST /v1/tools/memories/search',
        'response_model': 'ToolResponse',
        'existing_local_proof': [
            'backend/tests/unit/test_tools_agent_route_response_shape.py',
            'backend/tests/unit/test_tools_rest_memory_runtime_adapter.py',
        ],
        'required_fastapi_testclient_proof': 'Exercise the real FastAPI route via TestClient with dependency overrides, request-body validation, and response-model serialization for memory vector memory text.',
        'evidence': [],
    },
    {
        'key': 'agent_execute_tool_memory_tools',
        'status': 'NOT_RUN',
        'route_reference': 'backend/routers/agent_tools.py POST /v1/agent/execute-tool',
        'response_model': 'ExecuteToolResponse',
        'existing_local_proof': ['backend/tests/unit/test_tools_agent_route_response_shape.py'],
        'required_fastapi_testclient_proof': 'Exercise the real FastAPI route via TestClient with dependency overrides and in-process memory tool stubs, then prove ExecuteToolResponse serialization preserves or collapses output safely.',
        'evidence': [],
    },
]

BEHAVIOR_CASES: List[Dict[str, Any]] = [
    {
        'key': 'response_model_serialization',
        'status': 'NOT_RUN',
        'required_proof': 'FastAPI response_model serialization for ToolResponse and ExecuteToolResponse must be exercised by TestClient, not only direct Pydantic model_validate calls.',
        'evidence': [],
    },
    {
        'key': 'quoted_evidence_boundary_preservation',
        'status': 'NOT_RUN',
        'required_proof': 'memory memory text with boundary notice, source_marker, content_quoted=..., policy=default_memory, and archive_default_visible=False survives actual route serialization unchanged.',
        'evidence': [],
    },
    {
        'key': 'fail_closed_denied_and_no_grant_states',
        'status': 'NOT_RUN',
        'required_proof': 'Denied, malformed rollout, missing grant, and missing vector state outputs collapse to No memories available for this request. without unsafe legacy DB/vector fallback.',
        'evidence': [],
    },
    {
        'key': 'enabled_empty_state_stability',
        'status': 'NOT_RUN',
        'required_proof': 'Enabled-empty default and vector memory outputs remain stable through route serialization and are distinguishable from denied states.',
        'evidence': [],
    },
    {
        'key': 'prompt_injection_payload_as_quoted_data',
        'status': 'NOT_RUN',
        'required_proof': 'Prompt-injection-like memory payloads appear only inside content_quoted=... and never as raw tool instructions after TestClient response serialization.',
        'evidence': [],
    },
    {
        'key': 'archive_and_stale_short_term_default_unavailable',
        'status': 'NOT_RUN',
        'required_proof': 'Archive remains default-unavailable and stale Short-term is not made default-visible for tools REST or agent execute-tool wrappers.',
        'evidence': [],
    },
]

NON_CLAIMS = [
    'FastAPI TestClient production-dependency proof was not run in this environment.',
    'No production traffic was executed.',
    'No Firestore/Pinecone/cloud/provider calls were executed.',
    'No Firestore reads or writes were executed.',
    'No benchmark evidence was collected.',
    'No telemetry sink integration or production rollout approval is claimed.',
]


def _fastapi_import_error() -> str | None:
    try:
        return None if importlib.util.find_spec('fastapi') is not None else 'ModuleNotFoundError'
    except ModuleNotFoundError:
        return 'ModuleNotFoundError'
    except ValueError:
        return 'ValueError'


def _repo_venv_testclient_probe(python_path: Path) -> Dict[str, Any]:
    if not python_path.exists():
        return {'available': False, 'stdout': '', 'stderr': 'backend/venv/bin/python not found'}
    completed = subprocess.run(
        [
            str(python_path),
            '-c',
            'import fastapi, httpx, starlette; from fastapi.testclient import TestClient; '
            'print(f"fastapi={fastapi.__version__} httpx={httpx.__version__} starlette={starlette.__version__} TestClient=OK")',
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        'available': completed.returncode == 0,
        'stdout': completed.stdout.strip(),
        'stderr': completed.stderr.strip(),
    }


def build_dependency_evidence() -> Dict[str, Any]:
    backend_root = Path(__file__).resolve().parents[1]
    repo_venv_python = backend_root / 'venv' / 'bin' / 'python'
    repo_venv_probe = _repo_venv_testclient_probe(repo_venv_python)
    return {
        'required_dependency_file': 'backend/requirements.txt',
        'required_fastapi_pin': 'fastapi==0.121.0',
        'required_httpx_pin': 'httpx==0.28.0',
        'verification_python_major_minor': f'{sys.version_info.major}.{sys.version_info.minor}',
        'local_fastapi_import_error': _fastapi_import_error(),
        'repo_managed_venv_python': 'backend/venv/bin/python',
        'repo_managed_venv_exists': repo_venv_python.exists(),
        'repo_managed_venv_fastapi_testclient_available': repo_venv_probe['available'],
        'repo_managed_venv_probe_stdout': repo_venv_probe['stdout'],
        'repo_managed_venv_probe_stderr': repo_venv_probe['stderr'],
        'bounded_install_attempted': True,
        'bounded_install_command': "python3 -m pip install --user 'fastapi==0.121.0'",
        'bounded_install_exit_code': 1,
        'bounded_install_stderr_excerpt': (
            'error: externally-managed-environment; pip refused --user install in this Python due to PEP 668. '
            'No --break-system-packages override was used, no lockfile was changed, and no TestClient proof was run.'
        ),
        'safe_next_dependency_options': [
            'Run TestClient proof in a repo-managed virtual environment with backend/requirements.txt installed.',
            'Use CI/backend test image where backend/requirements.txt dependencies are already present.',
        ],
    }


def build_report(execute: bool = False) -> Dict[str, Any]:
    fastapi_importable = importlib.util.find_spec('fastapi') is not None
    testclient_importable = importlib.util.find_spec('fastapi.testclient') is not None if fastapi_importable else False
    dependency_evidence = build_dependency_evidence()
    dependency_available = fastapi_importable and testclient_importable
    dependency_available = dependency_available or dependency_evidence['repo_managed_venv_fastapi_testclient_available']
    blocker = (
        'fastapi/testclient unavailable in local Python environment; keep proof BLOCKED/NOT_RUN until dependencies are installed or safely stubbed at FastAPI TestClient level.'
        if not dependency_available
        else 'FastAPI/TestClient is available via the repo-managed backend venv, but this tools readiness artifact remains BLOCKED/NOT_RUN until a separate controlled tools route proof is implemented.'
    )
    return {
        'status': 'BLOCKED',
        'proof_status': 'NOT_RUN',
        'execute_requested': execute,
        'read_only': True,
        'mutation_allowed': False,
        'network_or_provider_calls_executed': False,
        'provider_calls_executed': False,
        'cloud_calls_executed': False,
        'firestore_reads_executed': False,
        'firestore_writes_executed': False,
        'benchmark_evidence_collected': False,
        'approval_claimed': False,
        'production_rollout_approved': False,
        'fastapi_testclient_importable': fastapi_importable,
        'testclient_importable': testclient_importable,
        'blocker': blocker,
        'route_surfaces_count': len(ROUTE_SURFACES),
        'behavior_cases_count': len(BEHAVIOR_CASES),
        'route_surfaces': ROUTE_SURFACES,
        'behavior_cases': BEHAVIOR_CASES,
        'dependency_evidence': dependency_evidence,
        'non_claims': NON_CLAIMS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Safe memory P1-5/P1-3 readiness artifact for tools REST/agent FastAPI TestClient route proof.'
    )
    parser.add_argument('--execute', action='store_true', help='Emit the same read-only BLOCKED/NOT_RUN report.')
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

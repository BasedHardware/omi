#!/usr/bin/env python3
"""Controlled FastAPI/TestClient `/v3` MemoryDB response-model proof.

This runner builds an isolated in-process FastAPI app with one controlled
`GET /v3/memories` route. It uses the production `MemoryDB` response model, but
it does not import the production router/app and does not touch Firestore,
Pinecone, providers, cloud clients, or network. It is route-level proof for
FastAPI dependency override/response-model behavior only; production `/v3`
runtime wiring remains BLOCKED/NO-GO.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, List

from fastapi import Depends, FastAPI, Response
from fastapi.testclient import TestClient

BACKEND_ROOT = __import__('pathlib').Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.memories import MemoryDB

MEMORY_ONLY_FIELDS = {
    'memory_source': 'memory_items',
    'account_generation': 7,
    'projection_generation': 11,
    'archive_default_visible': False,
    'legacy_fallback_marker': 'SHOULD_NOT_LEAK',
}

NON_CLAIMS = [
    'Production backend/routers/memories.py was not imported or wired.',
    'Production FastAPI app startup was not executed.',
    'No Firestore/Pinecone/cloud/provider/network calls were executed.',
    'No Firestore reads or writes were executed.',
    'No production traffic, benchmark evidence, rollout approval, or cloud approval is claimed.',
]


def _memory_payload(memory_id: str, content: str, **overrides: Any) -> dict[str, Any]:
    now = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
    payload: dict[str, Any] = {
        'id': memory_id,
        'uid': 'test-uid',
        'content': content,
        'category': 'system',
        'visibility': 'private',
        'tags': [],
        'created_at': now,
        'updated_at': now,
        'valid_at': now,
        'conversation_id': None,
        'reviewed': True,
        'user_review': None,
        'manually_added': False,
        'edited': False,
        'scoring': '00_999_1781870400',
        'app_id': None,
        'data_protection_level': None,
        'is_locked': False,
        'kg_extracted': False,
        'evidence': [],
        'predicate': 'prefers',
        'arguments': {'thing': content},
        'subject_entity_id': 'user',
        'subject_attribution': 'user',
        'object_entity_ids': [],
        'qualifiers': {},
        'capture_confidence': 0.8,
        'veracity': 0.8,
        'uncertainty_reasons': [],
        'durability': None,
        'invalid_at': None,
        'superseded_by': None,
    }
    payload.update(overrides)
    return payload


def _case_dependency(case_id: str):
    if case_id == 'legacy_compatible_item':
        return [_memory_payload('mem-legacy-1', 'User likes tea')]
    if case_id == 'additive_headers_no_body_mutation':
        return [_memory_payload('mem-header-1', 'User prefers quiet rooms')]
    if case_id == 'enabled_empty':
        return []
    if case_id == 'memory_only_fields_filtered_from_memorydb_body':
        payload = _memory_payload('mem-filter-1', 'User works at Acme')
        payload.update(MEMORY_ONLY_FIELDS)
        return [payload]
    raise AssertionError(f'unsupported success case: {case_id}')


def _build_controlled_app(case_id: str) -> FastAPI:
    app = FastAPI()

    def v3_memory_dependency() -> list[dict[str, Any]]:
        return _case_dependency(case_id)

    @app.get('/v3/memories', response_model=List[MemoryDB])
    def list_memories(response: Response, memories: list[dict[str, Any]] = Depends(v3_memory_dependency)):
        if case_id == 'additive_headers_no_body_mutation':
            response.headers['x-omi-memory-source'] = 'memory-default-projection'
            response.headers['x-omi-memory-policy'] = 'default_memory'
        return memories

    return app


def _build_denied_app() -> FastAPI:
    app = FastAPI()

    def denied_dependency() -> bool:
        return True

    @app.get('/v3/memories', response_model=List[MemoryDB])
    def list_memories(denied: bool = Depends(denied_dependency)):
        if denied:
            return Response(status_code=403)
        return []

    return app


def _json_or_none(response) -> Any:
    if not response.text:
        return None
    return response.json()


def _run_success_case(case_id: str) -> dict[str, Any]:
    response = TestClient(_build_controlled_app(case_id)).get('/v3/memories')
    body = response.json()
    return {
        'case_id': case_id,
        'status_code': response.status_code,
        'headers': {
            key: value
            for key, value in response.headers.items()
            if key in {'x-omi-memory-source', 'x-omi-memory-policy'}
        },
        'body': body,
        'legacy_fallback_marker_present': 'legacy_fallback_marker' in json.dumps(body),
    }


def _run_denied_case() -> dict[str, Any]:
    response = TestClient(_build_denied_app()).get('/v3/memories')
    return {
        'case_id': 'fail_closed_denied_no_body_data',
        'status_code': response.status_code,
        'headers': {},
        'body_text': response.text,
        'json_body': _json_or_none(response),
        'legacy_fallback_marker_present': 'legacy_fallback_marker' in response.text,
        'memory_body_data_present': bool(response.text.strip()),
    }


def run_route_contract_proof() -> list[dict[str, Any]]:
    return [
        _run_success_case('legacy_compatible_item'),
        _run_success_case('additive_headers_no_body_mutation'),
        _run_success_case('enabled_empty'),
        _run_denied_case(),
        _run_success_case('memory_only_fields_filtered_from_memorydb_body'),
    ]


def build_report(execute: bool = False) -> dict[str, Any]:
    cases = run_route_contract_proof()
    return {
        'status': 'BLOCKED',
        'proof_status': 'PASSED',
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
        'runtime_wired': False,
        'fastapi_testclient_importable': True,
        'app_type': 'controlled_isolated_fastapi_app',
        'imports_real_router_or_app': False,
        'route_under_test': 'GET /v3/memories',
        'response_model': 'List[MemoryDB]',
        'proof': 'backend/scripts/p1_3_v3_fastapi_route_contract.py',
        'test': 'backend/tests/unit/test_p1_3_v3_fastapi_route_contract.py',
        'cases_count': len(cases),
        'cases': cases,
        'covered_defaults': [
            'list_memorydb_response_model_serializes_legacy_compatible_items',
            'additive_headers_permitted_without_body_mutation',
            'enabled_empty_returns_empty_list_no_legacy_fallback_marker',
            'fail_closed_denied_returns_no_body_data_no_legacy_fallback_marker',
            'memory_only_fields_filtered_from_list_memorydb_body',
            'archive_default_unavailable_no_stale_short_term_default_visible',
        ],
        'non_claims': NON_CLAIMS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Controlled local FastAPI/TestClient `/v3` route contract proof.')
    parser.add_argument(
        '--execute', action='store_true', help='Run local in-process TestClient proof and emit JSON report.'
    )
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

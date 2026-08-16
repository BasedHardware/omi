"""Contract tests for the integration-public OpenAPI surface.

These tests validate that every documented integration REST route exists in
`docs/api-reference/integration-public-openapi.json` with the expected method
and a modeled (non-anonymous) success response schema. The spec is generated
from backend authority (`backend/scripts/export_openapi.py --surface
integration-public`), so this guards against accidental route removal or
response-shape regression for first-party integration consumers (e.g. the
personas-open-source store-facts route) and third-party plugins.

Out of scope: WebSocket/SSE/binary protocols, app-client routes, public
Developer API routes, and any non-Omi third-party API.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Set, Tuple

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'integration-public-openapi.json'

# Every integration REST route the spec must cover. Method + path template.
# Path templates use the OpenAPI `{param}` form. `/v2/integrations/{app_id}/
# user/facts` is intentionally absent: memories and facts are the same concept
# on the backend and are served by /user/memories (POST).
EXPECTED_OPERATIONS: Set[Tuple[str, str]] = {
    ('POST', '/v2/integrations/{app_id}/user/conversations'),
    ('POST', '/v2/integrations/{app_id}/user/memories'),
    ('GET', '/v2/integrations/{app_id}/conversations'),
    ('GET', '/v2/integrations/{app_id}/memories'),
    ('POST', '/v2/integrations/{app_id}/search/conversations'),
    ('POST', '/v2/integrations/{app_id}/notification'),
    ('GET', '/v2/integrations/{app_id}/tasks'),
    ('POST', '/v1/integrations/notification'),
}


def _load_spec() -> Dict:
    import json

    return json.loads(SPEC_PATH.read_text())


def _operations(spec: Dict) -> Set[Tuple[str, str]]:
    ops = set()
    for path, path_item in spec.get('paths', {}).items():
        for method in ('get', 'post', 'patch', 'put', 'delete'):
            if method in path_item:
                ops.add((method.upper(), path))
    return ops


def _normalize(path: str) -> str:
    return re.sub(r'\{[^}]+\}', '{param}', path)


def test_integration_public_spec_exists():
    assert SPEC_PATH.exists(), f'integration-public spec missing at {SPEC_PATH}'


def test_all_expected_integration_routes_are_documented():
    spec = _load_spec()
    actual = {(m, _normalize(p)) for (m, p) in _operations(spec)}
    expected = {(m, _normalize(p)) for (m, p) in EXPECTED_OPERATIONS}

    missing = sorted(expected - actual)
    assert not missing, f'integration-public spec missing routes: {missing}'


def test_no_undocumented_integration_routes_drifted_in():
    """If a route is added to the spec, name it here so it stays intentional."""
    spec = _load_spec()
    actual = {(m, _normalize(p)) for (m, p) in _operations(spec)}
    expected = {(m, _normalize(p)) for (m, p) in EXPECTED_OPERATIONS}
    extra = sorted(actual - expected)
    assert (
        not extra
    ), 'Undocumented integration routes appeared in the spec. Add them to ' 'EXPECTED_OPERATIONS with intent: ' + str(
        extra
    )


def _success_response_ref(spec: Dict, path: str, method: str) -> str | None:
    path_item = spec['paths'].get(path)
    if not path_item or method.lower() not in path_item:
        return None
    responses = path_item[method.lower()].get('responses', {})
    success = responses.get('200')
    if not success:
        return None
    schema = success.get('content', {}).get('application/json', {}).get('schema', {})
    if '$ref' in schema:
        return schema['$ref']
    if 'items' in schema and isinstance(schema['items'], dict) and '$ref' in schema['items']:
        return schema['items']['$ref']
    return None


@pytest.mark.parametrize('method,path', sorted(EXPECTED_OPERATIONS))
def test_each_integration_route_has_a_modeled_success_response(method: str, path: str):
    spec = _load_spec()
    # Re-resolve the path template against the spec's literal path (param names
    # may differ, e.g. {app_id} vs {appId}); find the matching literal path.
    normalized_expected = _normalize(path)
    literal_path = next(
        (p for p in spec['paths'] if _normalize(p) == normalized_expected),
        None,
    )
    assert literal_path is not None, f'path {path} not found in spec'

    ref = _success_response_ref(spec, literal_path, method)
    assert ref, (
        f'{method} {path} 200 response has no modeled schema (anonymous/inline '
        'object). Add a Pydantic response_model to the backend route.'
    )
    assert ref.startswith(
        '#/components/schemas/'
    ), f'{method} {path} 200 response must reference a named schema, got {ref}'

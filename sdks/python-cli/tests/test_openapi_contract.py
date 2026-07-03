from __future__ import annotations

import json
import re
from pathlib import Path

from omi_cli.models import MemoryCategory

ROOT_DIR = Path(__file__).resolve().parents[3]
PUBLIC_OPENAPI_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'openapi.json'


CLI_ROUTES = {
    ('GET', '/v1/dev/user/action-items'),
    ('POST', '/v1/dev/user/action-items'),
    ('PATCH', '/v1/dev/user/action-items/{action_item_id}'),
    ('DELETE', '/v1/dev/user/action-items/{action_item_id}'),
    ('GET', '/v1/dev/user/conversations'),
    ('POST', '/v1/dev/user/conversations'),
    ('POST', '/v1/dev/user/conversations/from-segments'),
    ('GET', '/v1/dev/user/conversations/{conversation_id}'),
    ('PATCH', '/v1/dev/user/conversations/{conversation_id}'),
    ('DELETE', '/v1/dev/user/conversations/{conversation_id}'),
    ('GET', '/v1/dev/user/goals'),
    ('POST', '/v1/dev/user/goals'),
    ('GET', '/v1/dev/user/goals/{goal_id}'),
    ('PATCH', '/v1/dev/user/goals/{goal_id}'),
    ('DELETE', '/v1/dev/user/goals/{goal_id}'),
    ('PATCH', '/v1/dev/user/goals/{goal_id}/progress'),
    ('GET', '/v1/dev/user/goals/{goal_id}/history'),
    ('GET', '/v1/dev/user/memories'),
    ('POST', '/v1/dev/user/memories'),
    ('PATCH', '/v1/dev/user/memories/{memory_id}'),
    ('DELETE', '/v1/dev/user/memories/{memory_id}'),
}


def load_public_openapi() -> dict:
    return json.loads(PUBLIC_OPENAPI_PATH.read_text())


def normalize_route_template(path: str) -> str:
    return re.sub(r'\{[^}]+\}', '{}', path)


def test_cli_hardcoded_routes_exist_in_public_openapi():
    spec = load_public_openapi()
    operations = {
        (method.upper(), normalize_route_template(path)): (path, method)
        for path, path_item in spec['paths'].items()
        for method in path_item
        if method.upper() in {'GET', 'POST', 'PATCH', 'DELETE'}
    }

    missing = []
    for method, path in sorted(CLI_ROUTES):
        normalized = normalize_route_template(path)
        if (method, normalized) not in operations:
            missing.append(f'{method} {path}')

    assert missing == []


def test_cli_memory_category_enum_matches_public_openapi():
    spec = load_public_openapi()
    expected = set(spec['components']['schemas']['MemoryCategory']['enum'])
    actual = {item.value for item in MemoryCategory}

    assert actual == expected

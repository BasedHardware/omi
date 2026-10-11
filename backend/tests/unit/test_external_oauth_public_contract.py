"""Structural containment checks avoid importing the routers' cloud graph."""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def _class_fields(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    return {
        statement.target.id
        for statement in node.body
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
    }


def test_generic_integration_oauth_write_is_provider_restricted():
    fields = _class_fields(BACKEND / 'routers' / 'integrations.py', 'IntegrationData')
    assert {'connected', 'access_token', 'refresh_token'} <= fields
    source = (BACKEND / 'routers' / 'integrations.py').read_text(encoding='utf-8')
    save_route = source[source.index('def save_integration') : source.index('def delete_integration')]
    assert "resolved[1]['kind'] == 'oauth'" in save_route
    assert 'oauth_integration_requires_authorization_flow' in save_route


def test_task_integration_listing_uses_typed_nonsecret_projection():
    fields = _class_fields(BACKEND / 'routers' / 'task_integrations.py', 'TaskIntegrationStatus')
    assert fields == {'app_key', 'connected'}
    source = (BACKEND / 'routers' / 'task_integrations.py').read_text(encoding='utf-8')
    response_class = source[
        source.index('class TaskIntegrationsResponse') : source.index('class DefaultTaskIntegrationRequest')
    ]
    assert 'access_token' not in response_class
    assert 'refresh_token' not in response_class
    assert 'Dict[str, Any]' not in response_class


def test_checked_in_production_admission_is_closed():
    import json

    manifest = json.loads((BACKEND / 'config' / 'external_oauth_admission.json').read_text(encoding='utf-8'))
    assert manifest['connectors']
    assert all(entry['enabled'] is False for entry in manifest['connectors'].values())

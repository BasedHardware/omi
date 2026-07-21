import re
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, Security
from fastapi.security import APIKeyHeader
from starlette.responses import PlainTextResponse

from scripts import route_policy_inventory as inventory


def _policy(**overrides):
    policy = {
        'review_status': 'reviewed',
        'auth': {'mechanisms': ['unknown'], 'scopes': [], 'placement': 'unknown'},
        'byok': 'unknown',
        'rate_limit': {
            'policy_name': 'unknown',
            'key_subject': 'unknown',
            'enforcement': 'unknown',
            'placement': 'unknown',
        },
        'timeout_class': 'default_method',
        'surface': 'unknown',
        'visibility': 'unknown',
        'data_domain': 'unknown',
        'deprecation': {'state': 'active'},
        'owner': 'backend',
    }
    policy.update(overrides)
    return policy


def _manifest(routes):
    return {'schema_version': 1, 'service': inventory.SERVICE, 'routes': routes}


def _route(method, path, *, route_type='http', policy=None):
    route = {'route_type': route_type, 'path': path, 'policy': policy or _policy()}
    if route_type == 'http':
        route['method'] = method
    return route


def _write_manifest(tmp_path: Path, routes) -> Path:
    path = tmp_path / 'route_policy_manifest.yaml'
    rendered_routes = []
    for route in routes:
        lines = [f"  - route_type: {route['route_type']}"]
        if route.get('method'):
            lines.append(f"    method: {route['method']}")
        lines.append(f"    path: {route['path']}")
        lines.append('    policy:')
        lines.append(f"      review_status: {route['policy']['review_status']}")
        if route['policy'].get('exempt_reason'):
            lines.append(f"      exempt_reason: {route['policy']['exempt_reason']}")
        lines.extend(
            [
                '      auth:',
                '        mechanisms:',
                *[f'          - {mechanism}' for mechanism in route['policy']['auth']['mechanisms']],
                '        scopes: []',
                f"        placement: {route['policy']['auth']['placement']}",
                f"      byok: {route['policy']['byok']}",
                '      rate_limit:',
                f"        policy_name: {route['policy']['rate_limit']['policy_name']}",
                f"        key_subject: {route['policy']['rate_limit']['key_subject']}",
                f"        enforcement: {route['policy']['rate_limit']['enforcement']}",
                f"        placement: {route['policy']['rate_limit']['placement']}",
                f"      timeout_class: {route['policy']['timeout_class']}",
                f"      surface: {route['policy']['surface']}",
                f"      visibility: {route['policy']['visibility']}",
                f"      data_domain: {route['policy']['data_domain']}",
                '      deprecation:',
                f"        state: {route['policy']['deprecation']['state']}",
                f"      owner: {route['policy']['owner']}",
            ]
        )
        rendered_routes.append('\n'.join(lines))
    path.write_text(
        'schema_version: 1\nservice: backend-main\nroutes:\n'
        + ('\n'.join(rendered_routes) if rendered_routes else '[]\n')
    )
    return path


def test_inventory_expands_multi_method_and_websocket_routes():
    app = FastAPI()

    @app.api_route('/items/{item_id}', methods=['GET', 'POST'], include_in_schema=False)
    def item(item_id: str):
        return {'item_id': item_id}

    @app.websocket('/ws')
    async def ws():
        return None

    entries = inventory.iter_inventory_entries(app)

    assert [entry['route_key'] for entry in entries] == [
        'backend-main:http:GET:/items/{item_id}',
        'backend-main:http:POST:/items/{item_id}',
        'backend-main:websocket:WEBSOCKET:/ws',
    ]
    assert entries[0]['include_in_schema'] is False
    assert entries[2]['observed']['timeout_class_hint'] == 'websocket'


def test_beta_promotion_token_is_registered_for_only_the_two_beta_admission_routes():
    manifest = inventory.load_manifest(inventory.DEFAULT_MANIFEST_PATH)
    assert 'beta_promotion_token' in inventory.AUTH_MECHANISMS
    routes = [
        route
        for route in manifest['routes']
        if 'beta_promotion_token' in route.get('policy', {}).get('auth', {}).get('mechanisms', [])
    ]
    assert [(route.get('method'), route.get('path')) for route in routes] == [
        ('POST', '/v2/desktop/beta/promote-qualified'),
        ('POST', '/v2/desktop/beta/candidates/reserve'),
    ]


def test_dependency_evidence_captures_nested_depends_and_security():
    app = FastAPI()
    api_key_header = APIKeyHeader(name='Authorization')

    def inner_dependency():
        return 'inner'

    def outer_dependency(value: str = Depends(inner_dependency)):
        return value

    def security_dependency(api_key: str = Security(api_key_header)):
        return api_key

    @app.get('/secure')
    def secure_route(_outer: str = Depends(outer_dependency), _security: str = Depends(security_dependency)):
        return {'ok': True}

    [entry] = inventory.iter_inventory_entries(app)

    assert any(name.endswith('.inner_dependency') for name in entry['dependencies'])
    assert any(name.endswith('.outer_dependency') for name in entry['dependencies'])
    assert any(name.endswith('.security_dependency') for name in entry['dependencies'])


def test_inventory_json_does_not_include_memory_addresses_for_defaults_or_security_dependencies():
    app = FastAPI()
    api_key_header = APIKeyHeader(name='Authorization')

    def security_dependency(api_key: str = Security(api_key_header)):
        return api_key

    @app.get('/secure')
    def secure_route(_security: str = Depends(security_dependency)):
        return {'ok': True}

    rendered = inventory.stable_json({'routes': inventory.iter_inventory_entries(app)})

    assert not re.search(r'0x[0-9a-fA-F]+', rendered)
    assert 'fastapi.security.api_key.APIKeyHeader' in rendered


def test_inventory_includes_options_routes():
    app = FastAPI()

    @app.options('/items')
    def options_items():
        return {'ok': True}

    @app.api_route('/combined', methods=['GET', 'OPTIONS'])
    def combined():
        return {'ok': True}

    keys = [entry['route_key'] for entry in inventory.iter_inventory_entries(app)]

    assert 'backend-main:http:OPTIONS:/items' in keys
    assert 'backend-main:http:GET:/combined' in keys
    assert 'backend-main:http:OPTIONS:/combined' in keys


def test_inventory_includes_starlette_routes_and_mounted_sub_apps():
    app = FastAPI()

    async def starlette_home(request):
        return PlainTextResponse('ok')

    app.add_route('/starlette', starlette_home, methods=['GET'])

    sub_app = FastAPI()

    @sub_app.get('/child')
    def child():
        return {'ok': True}

    app.mount('/sub', sub_app)

    keys = [entry['route_key'] for entry in inventory.iter_inventory_entries(app)]

    assert 'backend-main:http:GET:/starlette' in keys
    assert 'backend-main:http:GET:/sub/child' in keys


def test_manifest_validation_rejects_duplicate_entries(tmp_path):
    path = _write_manifest(
        tmp_path,
        [
            _route('GET', '/items'),
            _route('GET', '/items'),
        ],
    )

    with pytest.raises(inventory.RoutePolicyError, match='duplicate manifest route key'):
        inventory.load_manifest(path)


def test_exempt_manifest_entry_requires_reason(tmp_path):
    path = _write_manifest(tmp_path, [_route('GET', '/items', policy=_policy(review_status='exempt'))])

    with pytest.raises(inventory.RoutePolicyError, match='exempt routes must include policy.exempt_reason'):
        inventory.load_manifest(path)


def test_manifest_validation_rejects_system_route_type(tmp_path):
    path = _write_manifest(tmp_path, [_route(None, '/docs', route_type='system')])

    with pytest.raises(inventory.RoutePolicyError, match='route_type must be one of'):
        inventory.load_manifest(path)


def test_check_reports_missing_stale_and_duplicate_registered_routes():
    app = FastAPI()

    @app.get('/items')
    def first():
        return {'ok': True}

    @app.get('/items')
    def second():
        return {'ok': True}

    entries = inventory.iter_inventory_entries(app)
    manifest = _manifest([_route('GET', '/old')])

    problems, summary = inventory.validate_inventory(entries=entries, manifest=manifest)

    joined = '\n'.join(problems)
    assert 'missing manifest entries' in joined
    assert 'backend-main:http:GET:/items' in joined
    assert 'stale manifest entries' in joined
    assert 'backend-main:http:GET:/old' in joined
    assert 'duplicate registered routes' in joined
    assert summary['duplicate_registered_routes'] == 1


def test_missing_manifest_route_keys_returns_live_keys_not_in_manifest():
    app = FastAPI()

    @app.get('/items')
    def items():
        return {'ok': True}

    @app.post('/items')
    def create_item():
        return {'ok': True}

    entries = inventory.iter_inventory_entries(app)
    manifest = _manifest([_route('GET', '/items')])

    assert inventory.missing_manifest_route_keys(entries, manifest) == ['backend-main:http:POST:/items']


def test_missing_baseline_allows_legacy_missing_routes_and_rejects_new_routes():
    missing = ['backend-main:http:GET:/legacy', 'backend-main:http:POST:/new']

    problems, summary = inventory.validate_missing_baseline(
        missing=missing,
        baseline_keys={'backend-main:http:GET:/legacy'},
    )

    assert 'new routes missing manifest entries' in '\n'.join(problems)
    assert 'backend-main:http:POST:/new' in '\n'.join(problems)
    assert summary['new_missing_manifest_entries'] == 1
    assert summary['stale_missing_baseline_entries'] == 0


def test_missing_baseline_passes_when_current_missing_matches_baseline():
    problems, summary = inventory.validate_missing_baseline(
        missing=['backend-main:http:GET:/legacy'],
        baseline_keys={'backend-main:http:GET:/legacy'},
        base_baseline_keys={'backend-main:http:GET:/legacy'},
    )

    assert problems == []
    assert summary['baseline_additions'] == 0
    assert summary['new_missing_manifest_entries'] == 0
    assert summary['stale_missing_baseline_entries'] == 0


def test_missing_baseline_reports_stale_entries_when_routes_are_manifested_or_removed():
    problems, summary = inventory.validate_missing_baseline(
        missing=['backend-main:http:GET:/legacy'],
        baseline_keys={'backend-main:http:GET:/legacy', 'backend-main:http:DELETE:/removed'},
    )

    assert 'stale legacy missing-route baseline entries' in '\n'.join(problems)
    assert 'backend-main:http:DELETE:/removed' in '\n'.join(problems)
    assert summary['new_missing_manifest_entries'] == 0
    assert summary['stale_missing_baseline_entries'] == 1


def test_missing_baseline_rejects_additions_relative_to_base_branch():
    problems, summary = inventory.validate_missing_baseline(
        missing=['backend-main:http:GET:/legacy', 'backend-main:http:POST:/new'],
        baseline_keys={'backend-main:http:GET:/legacy', 'backend-main:http:POST:/new'},
        base_baseline_keys={'backend-main:http:GET:/legacy'},
    )

    assert 'legacy missing-route baseline grew relative to the base branch' in '\n'.join(problems)
    assert 'backend-main:http:POST:/new' in '\n'.join(problems)
    assert summary['baseline_additions'] == 1
    assert summary['new_missing_manifest_entries'] == 0


def test_route_key_baseline_loader_ignores_comments_and_rejects_invalid_entries(tmp_path):
    path = tmp_path / 'baseline.txt'
    path.write_text(
        '\n'.join(
            [
                '# comment',
                '',
                'backend-main:http:GET:/items',
                'other:http:GET:/items',
                'backend-main:system:GET:/docs',
                'backend-main:http:GET:/items',
            ]
        )
    )

    with pytest.raises(inventory.RoutePolicyError) as exc_info:
        inventory.load_route_key_baseline(path)

    message = str(exc_info.value)
    assert 'invalid route policy baseline entries' in message
    assert 'duplicate route policy baseline entries' in message


def test_missing_baseline_writer_outputs_sorted_route_keys(tmp_path):
    path = tmp_path / 'baseline.txt'

    inventory.write_missing_baseline(path, ['backend-main:http:POST:/b', 'backend-main:http:GET:/a'])

    lines = [line for line in path.read_text().splitlines() if line and not line.startswith('#')]
    assert lines == ['backend-main:http:GET:/a', 'backend-main:http:POST:/b']


def test_check_reports_equivalent_path_template_duplicates():
    app = FastAPI()

    @app.get('/users/{id}')
    def first(id: str):
        return {'id': id}

    @app.get('/users/{user_id}')
    def second(user_id: str):
        return {'id': user_id}

    entries = inventory.iter_inventory_entries(app)
    manifest = _manifest(
        [
            _route('GET', '/users/{id}'),
            _route('GET', '/users/{user_id}'),
        ]
    )

    problems, summary = inventory.validate_inventory(entries=entries, manifest=manifest)

    joined = '\n'.join(problems)
    assert 'equivalent path templates' in joined
    assert summary['duplicate_registered_routes'] == 1


def test_timeout_override_validation_runs_both_directions():
    app = FastAPI()

    @app.post('/v2/sync-jobs/run')
    def sync_job():
        return {'ok': True}

    @app.post('/v2/no-override')
    def no_override():
        return {'ok': True}

    entries = inventory.iter_inventory_entries(app, paths_timeout={'/v2/sync-jobs/run': 1500, '/missing': 10})
    manifest = _manifest(
        [
            _route('POST', '/v2/sync-jobs/run', policy=_policy(timeout_class='sync_job')),
            _route('POST', '/v2/no-override', policy=_policy(timeout_class='audio_merge')),
        ]
    )

    problems, summary = inventory.validate_inventory(
        entries=entries,
        manifest=manifest,
        paths_timeout={'/v2/sync-jobs/run': 1500, '/missing': 10},
    )

    joined = '\n'.join(problems)
    assert 'stale timeout override paths' in joined
    assert '/missing' in joined
    assert 'declares audio_merge without a path override' in joined
    assert summary['stale_timeout_overrides'] == 1
    assert summary['missing_timeout_overrides'] == 1


def test_timeout_override_conflicts_with_default_manifest_class():
    app = FastAPI()

    @app.post('/v2/sync-jobs/run')
    def sync_job():
        return {'ok': True}

    entries = inventory.iter_inventory_entries(app, paths_timeout={'/v2/sync-jobs/run': 1500})
    manifest = _manifest([_route('POST', '/v2/sync-jobs/run', policy=_policy(timeout_class='default_method'))])

    problems, summary = inventory.validate_inventory(
        entries=entries,
        manifest=manifest,
        paths_timeout={'/v2/sync-jobs/run': 1500},
    )

    assert 'has sync_job timeout override but manifest says default_method' in '\n'.join(problems)
    assert summary['missing_timeout_overrides'] == 1


def test_deprecated_fastapi_route_conflicts_with_active_manifest_state():
    app = FastAPI()

    @app.get('/old', deprecated=True)
    def old():
        return {'ok': True}

    entries = inventory.iter_inventory_entries(app)
    manifest = _manifest([_route('GET', '/old', policy=_policy(deprecation={'state': 'active'}))])

    problems, summary = inventory.validate_inventory(entries=entries, manifest=manifest)

    assert 'FastAPI-deprecated but manifest says active' in '\n'.join(problems)
    assert summary['deprecation_conflicts'] == 1


def test_live_route_cannot_be_marked_removed():
    app = FastAPI()

    @app.get('/old')
    def old():
        return {'ok': True}

    entries = inventory.iter_inventory_entries(app)
    manifest = _manifest([_route('GET', '/old', policy=_policy(deprecation={'state': 'removed'}))])

    problems, summary = inventory.validate_inventory(entries=entries, manifest=manifest)

    assert 'is registered but manifest says removed' in '\n'.join(problems)
    assert summary['deprecation_conflicts'] == 1


def test_system_routes_are_reported_as_excluded_not_application_routes():
    app = FastAPI()

    app_entries = inventory.iter_inventory_entries(app)
    system_entries = inventory.iter_system_route_entries(app)

    assert app_entries == []
    assert {entry['path'] for entry in system_entries} >= {'/openapi.json', '/docs', '/redoc'}

    sub_app = FastAPI()
    app.mount('/sub', sub_app)

    mounted_system_entries = inventory.iter_system_route_entries(app)

    assert '/sub/docs' in {entry['path'] for entry in mounted_system_entries}


def test_problem_detail_limiter_keeps_header_and_reports_hidden_count():
    problem = textwrap.dedent("""\
        missing manifest entries:
          - one
          - two
          - three
        """).strip()

    assert inventory.limit_problem_details(problem, max_lines=3).endswith('  ... 1 more not shown')


def test_main_reports_malformed_yaml_without_traceback(tmp_path, monkeypatch, capsys):
    manifest_path = tmp_path / 'route_policy_manifest.yaml'
    manifest_path.write_text('routes:\n  - [unterminated\n')
    monkeypatch.setattr(
        inventory,
        'generate_backend_route_inventory',
        lambda: {'service': inventory.SERVICE, 'schema_version': inventory.SCHEMA_VERSION, 'routes': []},
    )
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'route_policy_inventory.py',
            '--manifest',
            str(manifest_path),
            '--check',
        ],
    )

    assert inventory.main() == 1
    captured = capsys.readouterr()
    assert 'Route policy inventory check failed:' in captured.err
    assert 'Traceback' not in captured.err

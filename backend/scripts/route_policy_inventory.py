#!/usr/bin/env python3
"""Inventory backend routes and check route-policy manifest coverage.

This tool is intentionally metadata-only. It imports the real backend FastAPI
app through the same hermetic fake-service bootstrap used by export_openapi.py,
then emits registered route evidence and compares it with the declared
route-policy manifest. It must never be imported by runtime request handling.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import re
import socket
import sys
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml
from fastapi.datastructures import DefaultPlaceholder
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.routing import Mount, Route, WebSocketRoute

try:
    from scripts import export_openapi
except ModuleNotFoundError:  # Direct CLI execution via scripts/openapi_runner.sh.
    import export_openapi

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / 'backend'
DEFAULT_MANIFEST_PATH = BACKEND_DIR / 'route_policy_manifest.yaml'
DEFAULT_MISSING_BASELINE_PATH = BACKEND_DIR / 'route_policy_legacy_missing_routes.txt'

SERVICE = 'backend-main'
SCHEMA_VERSION = 1
HTTP_METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'TRACE'}
SYSTEM_ROUTE_PATHS = {'/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc'}

REVIEW_STATUS = {'reviewed', 'legacy_unreviewed', 'exempt'}
ROUTE_TYPES = {'http', 'websocket'}
AUTH_MECHANISMS = {
    'public',
    'firebase_id_token',
    'admin_key_uid_prefix',
    'developer_api_key',
    'mcp_api_key',
    'mcp_oauth',
    'service_oidc',
    'webhook_signature',
    'websocket_first_message',
    'unknown',
}
AUTH_PLACEMENTS = {'dependency', 'inline', 'middleware', 'external_gateway', 'first_message', 'unknown', 'none'}
BYOK_POLICIES = {
    'not_applicable',
    'validated_when_headers_present',
    'skipped_for_key_rotation',
    'websocket_manual',
    'unknown',
}
RATE_LIMIT_KEY_SUBJECTS = {'uid', 'api_key', 'app_key', 'ip', 'custom', 'none', 'unknown'}
RATE_LIMIT_ENFORCEMENTS = {'fail_open', 'fail_closed', 'shadow', 'none', 'unknown'}
RATE_LIMIT_PLACEMENTS = {'dependency', 'inline', 'wrapper', 'websocket_lock', 'none', 'unknown'}
TIMEOUT_CLASSES = {
    'default_method',
    'sync_job',
    'audio_merge',
    'account_deletion_wipe',
    'streaming',
    'websocket',
    'unknown',
}
SURFACES = {
    'first_party_app',
    'developer_api',
    'mcp',
    'oauth',
    'admin',
    'internal_task',
    'desktop_update',
    'monitoring',
    'shared_public',
    'webhook',
    'well_known',
    'unknown',
}
VISIBILITIES = {'public_documented', 'public_undocumented', 'first_party', 'internal', 'admin', 'well_known', 'unknown'}
DATA_DOMAINS = {
    'conversations',
    'memories',
    'action_items',
    'user_profile',
    'auth',
    'billing',
    'sync_audio',
    'chat',
    'apps',
    'credentials',
    'metrics',
    'firmware',
    'desktop_updates',
    'unknown',
}
DEPRECATION_STATES = {'active', 'deprecated', 'sunset', 'removed'}


class RoutePolicyError(RuntimeError):
    """Raised when route inventory or manifest validation fails."""


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n'


def route_key(service: str, route_type: str, method: str | None, path: str) -> str:
    normalized_method = (method or 'WEBSOCKET').upper()
    return f'{service}:{route_type}:{normalized_method}:{path}'


def _qualified_name(call: Any) -> str:
    if call is None:
        return '<none>'
    module = getattr(call, '__module__', None)
    qualname = getattr(call, '__qualname__', None) or getattr(call, '__name__', None)
    if module and qualname:
        return f'{module}.{qualname}'
    call_type = type(call)
    type_module = getattr(call_type, '__module__', None)
    type_qualname = getattr(call_type, '__qualname__', None) or getattr(call_type, '__name__', None)
    if type_module and type_qualname:
        return f'{type_module}.{type_qualname}'
    return '<unknown>'


def _collect_dependency_names(dependant: Any) -> list[str]:
    names: list[str] = []

    def visit(node: Any) -> None:
        for dependency in getattr(node, 'dependencies', []) or []:
            names.append(_qualified_name(getattr(dependency, 'call', None)))
            visit(dependency)

    visit(dependant)
    return sorted(set(names))


def _route_endpoint(route: Any) -> str:
    return _qualified_name(getattr(route, 'endpoint', None))


def _response_class_name(route: APIRoute) -> str | None:
    response_class = getattr(route, 'response_class', None)
    if response_class is None:
        return None
    if isinstance(response_class, DefaultPlaceholder):
        return _qualified_name(response_class.value)
    return getattr(response_class, '__name__', repr(response_class))


def _prefixed_path(prefix: str, path: str) -> str:
    if not prefix:
        return path
    if path == '/':
        return prefix
    return prefix.rstrip('/') + path


def _normalized_path_shape(path: str) -> str:
    return re.sub(r'\{[^}/]+\}', '{}', path)


def _timeout_class_for_path(path: str, paths_timeout: dict[str, Any]) -> str:
    if path == '/v2/sync-jobs/run':
        return 'sync_job'
    if path == '/v2/audio-merge-jobs/run':
        return 'audio_merge'
    if path == '/v1/users/account-deletion-wipes/run':
        return 'account_deletion_wipe'
    if path in paths_timeout:
        return 'unknown'
    return 'default_method'


def iter_inventory_entries(
    app: Any, *, service: str = SERVICE, paths_timeout: dict[str, Any] | None = None, path_prefix: str = ''
) -> list[dict]:
    paths_timeout = paths_timeout or {}
    entries: list[dict] = []

    for route_order, route in enumerate(app.routes):
        if isinstance(route, APIRoute):
            methods = sorted((route.methods or set()) & HTTP_METHODS)
            for method in methods:
                path = _prefixed_path(path_prefix, route.path)
                timeout_override = paths_timeout.get(path)
                entries.append(
                    {
                        'service': service,
                        'route_type': 'http',
                        'method': method,
                        'path': path,
                        'route_key': route_key(service, 'http', method, path),
                        'path_shape': _normalized_path_shape(path),
                        'route_order': route_order,
                        'name': route.name,
                        'operation_id': route.operation_id,
                        'unique_id': route.unique_id,
                        'tags': sorted(route.tags or []),
                        'include_in_schema': route.include_in_schema,
                        'deprecated': bool(route.deprecated),
                        'endpoint': _route_endpoint(route),
                        'status_code': route.status_code,
                        'response_class': _response_class_name(route),
                        'dependencies': _collect_dependency_names(route.dependant),
                        'observed': {
                            'timeout_override': timeout_override is not None,
                            'timeout_override_seconds': timeout_override,
                            'timeout_class_hint': _timeout_class_for_path(path, paths_timeout),
                        },
                    }
                )
        elif isinstance(route, (APIWebSocketRoute, WebSocketRoute)):
            path = _prefixed_path(path_prefix, route.path)
            entries.append(
                {
                    'service': service,
                    'route_type': 'websocket',
                    'method': 'WEBSOCKET',
                    'path': path,
                    'route_key': route_key(service, 'websocket', 'WEBSOCKET', path),
                    'path_shape': _normalized_path_shape(path),
                    'route_order': route_order,
                    'name': route.name,
                    'operation_id': None,
                    'unique_id': None,
                    'tags': [],
                    'include_in_schema': False,
                    'deprecated': False,
                    'endpoint': _route_endpoint(route),
                    'status_code': None,
                    'response_class': None,
                    'dependencies': _collect_dependency_names(getattr(route, 'dependant', None)),
                    'observed': {
                        'timeout_override': False,
                        'timeout_override_seconds': None,
                        'timeout_class_hint': 'websocket',
                    },
                }
            )
        elif isinstance(route, Route) and route.path not in SYSTEM_ROUTE_PATHS:
            path = _prefixed_path(path_prefix, route.path)
            methods = sorted((route.methods or set()) & HTTP_METHODS)
            for method in methods:
                timeout_override = paths_timeout.get(path)
                entries.append(
                    {
                        'service': service,
                        'route_type': 'http',
                        'method': method,
                        'path': path,
                        'route_key': route_key(service, 'http', method, path),
                        'path_shape': _normalized_path_shape(path),
                        'route_order': route_order,
                        'name': route.name,
                        'operation_id': None,
                        'unique_id': None,
                        'tags': [],
                        'include_in_schema': False,
                        'deprecated': False,
                        'endpoint': _route_endpoint(route),
                        'status_code': None,
                        'response_class': None,
                        'dependencies': [],
                        'observed': {
                            'timeout_override': timeout_override is not None,
                            'timeout_override_seconds': timeout_override,
                            'timeout_class_hint': _timeout_class_for_path(path, paths_timeout),
                            'route_class': type(route).__name__,
                        },
                    }
                )
        elif isinstance(route, Mount) and hasattr(route.app, 'routes'):
            entries.extend(
                iter_inventory_entries(
                    route.app,
                    service=service,
                    paths_timeout=paths_timeout,
                    path_prefix=_prefixed_path(path_prefix, route.path),
                )
            )

    return sorted(
        entries, key=lambda entry: (entry['route_type'], entry['path'], entry['method'], entry['route_order'])
    )


def iter_system_route_entries(app: Any, *, service: str = SERVICE, path_prefix: str = '') -> list[dict]:
    entries: list[dict] = []
    for route_order, route in enumerate(app.routes):
        if isinstance(route, (APIRoute, APIWebSocketRoute, WebSocketRoute)):
            continue
        if isinstance(route, Mount) and hasattr(route.app, 'routes'):
            entries.extend(
                iter_system_route_entries(
                    route.app,
                    service=service,
                    path_prefix=_prefixed_path(path_prefix, route.path),
                )
            )
            continue
        if not isinstance(route, Route):
            continue
        if route.path not in SYSTEM_ROUTE_PATHS:
            continue
        path = _prefixed_path(path_prefix, route.path)
        methods = sorted((route.methods or {'GET'}) & HTTP_METHODS)
        for method in methods:
            entries.append(
                {
                    'service': service,
                    'route_type': 'system',
                    'method': method,
                    'path': path,
                    'route_key': route_key(service, 'system', method, path),
                    'route_order': route_order,
                    'name': route.name,
                    'endpoint': _route_endpoint(route),
                    'exclusion_reason': 'fastapi_generated_system_route',
                }
            )
    return sorted(entries, key=lambda entry: (entry['path'], entry['method']))


def _require_enum(value: Any, allowed: set[str], field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or value not in allowed:
        errors.append(f'{field} must be one of {sorted(allowed)}, got {value!r}')


def _optional_enum(value: Any, allowed: set[str], field: str, errors: list[str]) -> None:
    if value is not None:
        _require_enum(value, allowed, field, errors)


def _validate_policy(route_key_value: str, policy: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(policy, dict):
        return [f'{route_key_value}: policy must be an object']

    review_status = policy.get('review_status')
    _require_enum(review_status, REVIEW_STATUS, f'{route_key_value}.policy.review_status', errors)
    if review_status == 'exempt' and not policy.get('exempt_reason'):
        errors.append(f'{route_key_value}: exempt routes must include policy.exempt_reason')

    auth = policy.get('auth', {})
    if not isinstance(auth, dict):
        errors.append(f'{route_key_value}.policy.auth must be an object')
    else:
        mechanisms = auth.get('mechanisms', [])
        if not isinstance(mechanisms, list) or not mechanisms:
            errors.append(f'{route_key_value}.policy.auth.mechanisms must be a non-empty list')
        else:
            for mechanism in mechanisms:
                _require_enum(mechanism, AUTH_MECHANISMS, f'{route_key_value}.policy.auth.mechanisms[]', errors)
        scopes = auth.get('scopes', [])
        if not isinstance(scopes, list):
            errors.append(f'{route_key_value}.policy.auth.scopes must be a list')
        _optional_enum(auth.get('placement'), AUTH_PLACEMENTS, f'{route_key_value}.policy.auth.placement', errors)

    _optional_enum(policy.get('byok'), BYOK_POLICIES, f'{route_key_value}.policy.byok', errors)

    rate_limit = policy.get('rate_limit', {})
    if not isinstance(rate_limit, dict):
        errors.append(f'{route_key_value}.policy.rate_limit must be an object')
    else:
        if not isinstance(rate_limit.get('policy_name', 'unknown'), str):
            errors.append(f'{route_key_value}.policy.rate_limit.policy_name must be a string')
        _optional_enum(
            rate_limit.get('key_subject'),
            RATE_LIMIT_KEY_SUBJECTS,
            f'{route_key_value}.policy.rate_limit.key_subject',
            errors,
        )
        _optional_enum(
            rate_limit.get('enforcement'),
            RATE_LIMIT_ENFORCEMENTS,
            f'{route_key_value}.policy.rate_limit.enforcement',
            errors,
        )
        _optional_enum(
            rate_limit.get('placement'),
            RATE_LIMIT_PLACEMENTS,
            f'{route_key_value}.policy.rate_limit.placement',
            errors,
        )

    _optional_enum(policy.get('timeout_class'), TIMEOUT_CLASSES, f'{route_key_value}.policy.timeout_class', errors)
    _optional_enum(policy.get('surface'), SURFACES, f'{route_key_value}.policy.surface', errors)
    _optional_enum(policy.get('visibility'), VISIBILITIES, f'{route_key_value}.policy.visibility', errors)
    _optional_enum(policy.get('data_domain'), DATA_DOMAINS, f'{route_key_value}.policy.data_domain', errors)

    deprecation = policy.get('deprecation', {})
    if not isinstance(deprecation, dict):
        errors.append(f'{route_key_value}.policy.deprecation must be an object')
    else:
        _optional_enum(
            deprecation.get('state', 'active'),
            DEPRECATION_STATES,
            f'{route_key_value}.policy.deprecation.state',
            errors,
        )

    return errors


def load_manifest(path: Path) -> dict:
    if not path.exists():
        raise RoutePolicyError(f'missing route policy manifest: {path}')
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise RoutePolicyError(f'{path} must contain a YAML object')

    errors: list[str] = []
    if raw.get('schema_version') != SCHEMA_VERSION:
        errors.append(f'schema_version must be {SCHEMA_VERSION}')
    service = raw.get('service')
    if not isinstance(service, str) or not service:
        errors.append('service must be a non-empty string')
    routes = raw.get('routes')
    if not isinstance(routes, list):
        errors.append('routes must be a list')
        routes = []

    seen: dict[str, int] = {}
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            errors.append(f'routes[{index}] must be an object')
            continue
        route_type = route.get('route_type')
        _require_enum(route_type, ROUTE_TYPES, f'routes[{index}].route_type', errors)
        path_value = route.get('path')
        if not isinstance(path_value, str) or not path_value.startswith('/'):
            errors.append(f'routes[{index}].path must be an absolute path string')
            continue
        method = route.get('method')
        if route_type == 'http':
            if not isinstance(method, str) or method.upper() not in HTTP_METHODS:
                errors.append(f'routes[{index}].method must be an HTTP method')
                continue
            method = method.upper()
        elif route_type == 'websocket':
            method = 'WEBSOCKET'

        key = route_key(service, route_type, method, path_value)
        if key in seen:
            errors.append(f'duplicate manifest route key {key} at routes[{seen[key]}] and routes[{index}]')
        seen[key] = index
        errors.extend(_validate_policy(key, route.get('policy')))

    if errors:
        raise RoutePolicyError('\n'.join(errors))
    return raw


def manifest_policy_by_key(manifest: dict) -> dict[str, dict]:
    service = manifest['service']
    policies: dict[str, dict] = {}
    for route in manifest.get('routes', []):
        route_type = route['route_type']
        method = route.get('method')
        if route_type == 'websocket':
            method = 'WEBSOCKET'
        policies[route_key(service, route_type, method, route['path'])] = route['policy']
    return policies


def missing_manifest_route_keys(entries: Iterable[dict], manifest: dict) -> list[str]:
    policies = manifest_policy_by_key(manifest)
    live_keys = {entry['route_key'] for entry in entries}
    return sorted(live_keys - set(policies))


def load_route_key_baseline(path: Path) -> set[str]:
    if not path.exists():
        raise RoutePolicyError(f'missing route policy baseline: {path}')
    route_keys: set[str] = set()
    duplicates: list[str] = []
    invalid: list[str] = []
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(':', 3)
        if len(parts) != 4 or parts[0] != SERVICE or parts[1] not in ROUTE_TYPES:
            invalid.append(f'line {line_number}: {line}')
            continue
        if line in route_keys:
            duplicates.append(f'line {line_number}: {line}')
            continue
        route_keys.add(line)
    if invalid or duplicates:
        problems = []
        if invalid:
            problems.append('invalid route policy baseline entries:\n' + '\n'.join(f'  - {item}' for item in invalid))
        if duplicates:
            problems.append(
                'duplicate route policy baseline entries:\n' + '\n'.join(f'  - {item}' for item in duplicates)
            )
        raise RoutePolicyError('\n'.join(problems))
    return route_keys


def render_route_key_baseline(route_keys: Iterable[str]) -> str:
    return (
        '# Legacy backend routes missing route-policy manifest entries.\n'
        '#\n'
        '# This file is a ratchet for issue #8959. CI allows these pre-existing\n'
        '# missing entries while failing when a new registered backend route is\n'
        '# added without a matching backend/route_policy_manifest.yaml entry.\n'
        '# Remove keys from this file as routes get reviewed and added to the manifest.\n'
        + '\n'.join(sorted(route_keys))
        + '\n'
    )


def validate_missing_baseline(
    *, missing: list[str], baseline_keys: set[str], base_baseline_keys: set[str] | None = None
) -> tuple[list[str], dict]:
    missing_keys = set(missing)
    new_missing = sorted(missing_keys - baseline_keys)
    stale_baseline = sorted(baseline_keys - missing_keys)
    baseline_additions = sorted(baseline_keys - base_baseline_keys) if base_baseline_keys is not None else []

    problems = []
    if new_missing:
        problems.append(
            'new routes missing manifest entries:\n'
            + '\n'.join(f'  - {key}' for key in new_missing)
            + '\n\nAdd policy for these routes to backend/route_policy_manifest.yaml, or regenerate the legacy '
            + 'baseline only for pre-existing routes.'
        )
    if stale_baseline:
        problems.append(
            'stale legacy missing-route baseline entries:\n'
            + '\n'.join(f'  - {key}' for key in stale_baseline)
            + '\n\nRemove these keys from the baseline; they are no longer missing from the live route inventory.'
        )
    if baseline_additions:
        problems.append(
            'legacy missing-route baseline grew relative to the base branch:\n'
            + '\n'.join(f'  - {key}' for key in baseline_additions)
            + '\n\nNew routes require backend/route_policy_manifest.yaml policy entries; do not add them to the '
            + 'legacy baseline.'
        )

    return problems, {
        'baseline_missing_entries': len(baseline_keys),
        'base_baseline_missing_entries': len(base_baseline_keys) if base_baseline_keys is not None else None,
        'current_missing_manifest_entries': len(missing),
        'baseline_additions': len(baseline_additions),
        'new_missing_manifest_entries': len(new_missing),
        'stale_missing_baseline_entries': len(stale_baseline),
    }


def find_duplicate_registered_routes(entries: Iterable[dict]) -> list[str]:
    by_key: dict[str, list[dict]] = defaultdict(list)
    by_shape_key: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        by_key[entry['route_key']].append(entry)
        shape_key = route_key(
            entry['service'], entry['route_type'], entry['method'], entry.get('path_shape', entry['path'])
        )
        by_shape_key[shape_key].append(entry)
    duplicates = []
    for key, matches in sorted(by_key.items()):
        if len(matches) <= 1:
            continue
        endpoints = ', '.join(f"{match['route_order']}:{match['endpoint']}" for match in matches)
        duplicates.append(f'{key} registered {len(matches)} times ({endpoints})')
    for key, matches in sorted(by_shape_key.items()):
        if len(matches) <= 1:
            continue
        raw_paths = sorted({match['path'] for match in matches})
        if len(raw_paths) <= 1:
            continue
        endpoints = ', '.join(f"{match['route_order']}:{match['path']}:{match['endpoint']}" for match in matches)
        duplicates.append(f'{key} registered with equivalent path templates {raw_paths} ({endpoints})')
    return duplicates


def validate_inventory(
    *,
    entries: list[dict],
    manifest: dict,
    paths_timeout: dict[str, Any] | None = None,
) -> tuple[list[str], dict]:
    paths_timeout = paths_timeout or {}
    policies = manifest_policy_by_key(manifest)
    live_keys = {entry['route_key'] for entry in entries}
    manifest_keys = set(policies)

    missing = sorted(live_keys - manifest_keys)
    stale = sorted(manifest_keys - live_keys)
    duplicate_registered = find_duplicate_registered_routes(entries)

    http_paths = {entry['path'] for entry in entries if entry['route_type'] == 'http'}
    stale_timeout_overrides = sorted(path for path in paths_timeout if path not in http_paths)
    missing_timeout_overrides = []
    deprecation_conflicts = []
    for entry in entries:
        policy = policies.get(entry['route_key'])
        if not policy:
            continue
        timeout_class = policy.get('timeout_class')
        if timeout_class in {'sync_job', 'audio_merge', 'account_deletion_wipe'} and entry['path'] not in paths_timeout:
            missing_timeout_overrides.append(f"{entry['route_key']} declares {timeout_class} without a path override")
        if entry['observed']['timeout_override']:
            expected_timeout_class = entry['observed']['timeout_class_hint']
            if expected_timeout_class != 'unknown' and timeout_class != expected_timeout_class:
                missing_timeout_overrides.append(
                    f"{entry['route_key']} has {expected_timeout_class} timeout override but manifest says {timeout_class}"
                )
            elif expected_timeout_class == 'unknown' and timeout_class == 'default_method':
                missing_timeout_overrides.append(
                    f"{entry['route_key']} has a timeout override but manifest says default_method"
                )
        deprecation_state = (policy.get('deprecation') or {}).get('state', 'active')
        if entry['deprecated'] and deprecation_state == 'active':
            deprecation_conflicts.append(f"{entry['route_key']} is FastAPI-deprecated but manifest says active")
        if deprecation_state == 'removed':
            deprecation_conflicts.append(f"{entry['route_key']} is registered but manifest says removed")

    problems = []
    if missing:
        problems.append('missing manifest entries:\n' + '\n'.join(f'  - {key}' for key in missing))
    if stale:
        problems.append('stale manifest entries:\n' + '\n'.join(f'  - {key}' for key in stale))
    if duplicate_registered:
        problems.append('duplicate registered routes:\n' + '\n'.join(f'  - {item}' for item in duplicate_registered))
    if stale_timeout_overrides:
        problems.append(
            'stale timeout override paths:\n' + '\n'.join(f'  - {path}' for path in stale_timeout_overrides)
        )
    if missing_timeout_overrides:
        problems.append('missing timeout overrides:\n' + '\n'.join(f'  - {item}' for item in missing_timeout_overrides))
    if deprecation_conflicts:
        problems.append('deprecation conflicts:\n' + '\n'.join(f'  - {item}' for item in deprecation_conflicts))

    summary = build_summary(entries, manifest, missing=missing, stale=stale, duplicate_registered=duplicate_registered)
    summary['stale_timeout_overrides'] = len(stale_timeout_overrides)
    summary['missing_timeout_overrides'] = len(missing_timeout_overrides)
    summary['deprecation_conflicts'] = len(deprecation_conflicts)
    return problems, summary


def limit_problem_details(problem: str, *, max_lines: int) -> str:
    if max_lines <= 0:
        return problem
    lines = problem.splitlines()
    if len(lines) <= max_lines:
        return problem
    hidden = len(lines) - max_lines
    return '\n'.join(lines[:max_lines] + [f'  ... {hidden} more not shown'])


def _count_policy_values(policies: Iterable[dict], path: tuple[str, ...]) -> Counter:
    values = Counter()
    for policy in policies:
        current: Any = policy
        for part in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if isinstance(current, list):
            values.update(current)
        else:
            values.update([current if current is not None else '<missing>'])
    return values


def build_summary(
    entries: list[dict],
    manifest: dict,
    *,
    missing: list[str] | None = None,
    stale: list[str] | None = None,
    duplicate_registered: list[str] | None = None,
) -> dict:
    policies = manifest_policy_by_key(manifest)
    review_status = Counter((policy or {}).get('review_status', '<missing>') for policy in policies.values())
    route_types = Counter(entry['route_type'] for entry in entries)
    unknown_fields = {}
    for name, path in {
        'auth_mechanisms': ('auth', 'mechanisms'),
        'auth_placement': ('auth', 'placement'),
        'byok': ('byok',),
        'rate_limit_policy_name': ('rate_limit', 'policy_name'),
        'rate_limit_key_subject': ('rate_limit', 'key_subject'),
        'timeout_class': ('timeout_class',),
        'surface': ('surface',),
        'visibility': ('visibility',),
        'data_domain': ('data_domain',),
    }.items():
        counts = _count_policy_values(policies.values(), path)
        unknown_fields[name] = counts.get('unknown', 0) + counts.get('<missing>', 0)

    return {
        'service': manifest.get('service', SERVICE),
        'total_application_routes': len(entries),
        'route_types': dict(sorted(route_types.items())),
        'manifest_entries': len(policies),
        'review_status': dict(sorted(review_status.items())),
        'missing_manifest_entries': len(missing or []),
        'stale_manifest_entries': len(stale or []),
        'duplicate_registered_routes': len(duplicate_registered or []),
        'include_in_schema_false': sum(
            1 for entry in entries if entry['route_type'] == 'http' and not entry['include_in_schema']
        ),
        'deprecated_routes': sum(1 for entry in entries if entry.get('deprecated')),
        'special_timeout_routes': sum(1 for entry in entries if entry['observed']['timeout_override']),
        'unknown_or_missing_policy_fields': unknown_fields,
    }


@contextmanager
def record_and_block_all_network() -> Iterator[list[str]]:
    attempts: list[str] = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    original_gethostbyname = socket.gethostbyname
    original_gethostbyname_ex = socket.gethostbyname_ex

    def record(kind: str, target: object) -> None:
        attempts.append(f'{kind}: {target!r}')

    def guarded_connect(sock: socket.socket, address: object):
        if sock.family != socket.AF_UNIX:
            record('connect', address)
            raise RoutePolicyError(f'blocked network connection to {address!r}')
        return original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: object):
        if sock.family != socket.AF_UNIX:
            record('connect_ex', address)
            raise RoutePolicyError(f'blocked network connection to {address!r}')
        return original_connect_ex(sock, address)

    def guarded_create_connection(address: object, *args, **kwargs):
        record('create_connection', address)
        raise RoutePolicyError(f'blocked network connection to {address!r}')

    def guarded_getaddrinfo(host: object, *args, **kwargs):
        record('getaddrinfo', host)
        raise RoutePolicyError(f'blocked DNS resolution for {host!r}')

    def guarded_gethostbyname(host: object):
        record('gethostbyname', host)
        raise RoutePolicyError(f'blocked DNS resolution for {host!r}')

    def guarded_gethostbyname_ex(host: object):
        record('gethostbyname_ex', host)
        raise RoutePolicyError(f'blocked DNS resolution for {host!r}')

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    socket.getaddrinfo = guarded_getaddrinfo
    socket.gethostbyname = guarded_gethostbyname
    socket.gethostbyname_ex = guarded_gethostbyname_ex
    try:
        yield attempts
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.create_connection = original_create_connection
        socket.getaddrinfo = original_getaddrinfo
        socket.gethostbyname = original_gethostbyname
        socket.gethostbyname_ex = original_gethostbyname_ex


def generate_backend_route_inventory() -> dict:
    original_env = dict(os.environ)
    original_cwd = Path.cwd()
    side_effect_snapshot = export_openapi.snapshot_side_effect_paths()
    export_openapi.configure_hermetic_environment()
    expected_fake_env = dict(os.environ)
    export_openapi._install_import_paths()

    logging.disable(logging.CRITICAL)
    try:
        os.chdir(BACKEND_DIR)
        fake_firestore, fake_redis, get_mock_firestore, get_fake_redis = (
            export_openapi.install_hermetic_dependency_patches()
        )
        with record_and_block_all_network() as network_attempts:
            backend_main = importlib.import_module('main')

            export_openapi.relink_imported_service_singletons(
                fake_firestore,
                fake_redis,
                get_mock_firestore,
                get_fake_redis,
            )
            paths_timeout = dict(getattr(backend_main, 'paths_timeout', {}) or {})
            entries = iter_inventory_entries(backend_main.app, paths_timeout=paths_timeout)
            system_routes = iter_system_route_entries(backend_main.app)

            if network_attempts:
                raise RoutePolicyError(
                    'route inventory attempted network during import/generation: ' + '; '.join(network_attempts)
                )

            export_openapi.assert_env_unchanged(expected_fake_env)
            return {
                'service': SERVICE,
                'schema_version': SCHEMA_VERSION,
                'routes': entries,
                'system_routes_excluded': system_routes,
                'paths_timeout': paths_timeout,
            }
    finally:
        logging.disable(logging.NOTSET)
        os.chdir(original_cwd)
        export_openapi.restore_restorable_side_effect_paths(side_effect_snapshot)
        os.environ.clear()
        os.environ.update(original_env)
        export_openapi.assert_no_side_effect_path_mutations(side_effect_snapshot)


def attach_manifest_policy(inventory: dict, manifest: dict) -> dict:
    policies = manifest_policy_by_key(manifest)
    routes = []
    for entry in inventory['routes']:
        enriched = dict(entry)
        enriched['manifest_policy'] = policies.get(entry['route_key'])
        enriched['manifest_status'] = 'covered' if entry['route_key'] in policies else 'missing'
        routes.append(enriched)
    return {
        **inventory,
        'routes': routes,
        'summary': build_summary(
            routes, manifest, missing=[entry['route_key'] for entry in routes if not entry['manifest_policy']]
        ),
    }


def write_inventory(path: Path, inventory: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json(inventory))


def write_missing_baseline(path: Path, route_keys: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_route_key_baseline(route_keys))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Inventory backend routes and check route-policy manifest coverage.')
    parser.add_argument('--manifest', default=str(DEFAULT_MANIFEST_PATH), help='route policy manifest path')
    parser.add_argument(
        '--missing-baseline',
        default=str(DEFAULT_MISSING_BASELINE_PATH),
        help='legacy missing-route baseline used by --enforce-missing-baseline',
    )
    parser.add_argument(
        '--base-missing-baseline',
        help='optional base-branch baseline; rejects additions to the legacy missing-route baseline',
    )
    parser.add_argument('--print', action='store_true', help='print deterministic JSON inventory')
    parser.add_argument('--write-inventory', metavar='PATH', help='write deterministic JSON inventory to PATH')
    parser.add_argument('--write-missing-baseline', metavar='PATH', help='write current missing route keys to PATH')
    parser.add_argument('--check', action='store_true', help='validate manifest coverage against registered routes')
    parser.add_argument(
        '--enforce-missing-baseline',
        action='store_true',
        help='fail if missing manifest entries are not in the legacy baseline, or baseline keys are stale',
    )
    parser.add_argument('--report-only', action='store_true', help='print check problems but exit zero')
    parser.add_argument('--max-problem-lines', type=int, default=80, help='maximum lines to print per problem group')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        inventory = generate_backend_route_inventory()
        manifest = load_manifest(Path(args.manifest))
        enriched_inventory = attach_manifest_policy(inventory, manifest)

        if args.print:
            sys.stdout.write(stable_json(enriched_inventory))
        if args.write_inventory:
            write_inventory(Path(args.write_inventory), enriched_inventory)
            print(f'wrote {args.write_inventory}')
        missing_keys = missing_manifest_route_keys(inventory['routes'], manifest)
        if args.write_missing_baseline:
            write_missing_baseline(Path(args.write_missing_baseline), missing_keys)
            print(f'wrote {args.write_missing_baseline}')
        if args.check:
            problems, summary = validate_inventory(
                entries=inventory['routes'],
                manifest=manifest,
                paths_timeout=inventory.get('paths_timeout') or {},
            )
            print('Backend route policy inventory summary:')
            print(stable_json(summary).rstrip())
            if problems:
                print('Route policy inventory check found issues:', file=sys.stderr)
                print(
                    '\n\n'.join(
                        limit_problem_details(problem, max_lines=args.max_problem_lines) for problem in problems
                    ),
                    file=sys.stderr,
                )
                return 0 if args.report_only else 1
            print('route policy manifest covers registered backend routes')
        if args.enforce_missing_baseline:
            baseline_keys = load_route_key_baseline(Path(args.missing_baseline))
            base_baseline_keys = (
                load_route_key_baseline(Path(args.base_missing_baseline)) if args.base_missing_baseline else None
            )
            problems, summary = validate_missing_baseline(
                missing=missing_keys,
                baseline_keys=baseline_keys,
                base_baseline_keys=base_baseline_keys,
            )
            print('Backend route policy missing-baseline summary:')
            print(stable_json(summary).rstrip())
            if problems:
                print('Route policy missing-baseline check found issues:', file=sys.stderr)
                print(
                    '\n\n'.join(
                        limit_problem_details(problem, max_lines=args.max_problem_lines) for problem in problems
                    ),
                    file=sys.stderr,
                )
                return 0 if args.report_only else 1
            print('route policy missing-route baseline is current')
        if not (
            args.print
            or args.write_inventory
            or args.write_missing_baseline
            or args.check
            or args.enforce_missing_baseline
        ):
            print('No action requested; use --print, --write-inventory, or --check.', file=sys.stderr)
            return 2
        return 0
    except (RoutePolicyError, export_openapi.OpenAPIContractError, yaml.YAMLError) as e:
        print(f'Route policy inventory check failed: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

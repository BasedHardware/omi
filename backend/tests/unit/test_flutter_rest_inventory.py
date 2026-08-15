"""Inventory + contract test for the Flutter app's Python-backend REST surface.

The Flutter app (`app/lib/backend/http/`) is the primary first-party REST
consumer of the Python backend; its routes are built as
`'${Env.apiBaseUrl}vN/...'` string literals. This is the Flutter sibling of
`test_desktop_rest_inventory.py` (macOS) and `test_windows_rest_inventory.py`,
added after #11613 shipped a desktop route with no spec entry and broke that
guard for every open PR: each first-party client needs the same inventory so a
new client call site cannot drift from backend-owned OpenAPI authority silently.

- Extracts every `${Env.apiBaseUrl}vN/...` route literal under app/lib/backend/http.
- Normalizes Dart string interpolation (`$id` / `${expr}`) to param placeholders
  and strips query strings.
- Excludes out-of-scope protocols (streaming/SSE/multipart/WebSocket) and
  asserts each in-scope route exists in the app-client OpenAPI spec.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Set

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
FLUTTER_HTTP_ROOT = ROOT_DIR / 'app' / 'lib' / 'backend' / 'http'

# Unlike the desktop inventories, every route this extractor finds is in scope:
# the Flutter client reaches its streaming/WebSocket surfaces through other
# bases than Env.apiBaseUrl, and the REST routes that DO appear (including
# /v2/messages/{id}/report and /v2/files) are all modeled in the spec. Add a
# prefix here only with a live extracted route it excludes; a prefix excluding
# nothing is a blind spot waiting for a call site.
OUT_OF_SCOPE_PREFIXES: tuple = ()

# Client base-url roots: `dev_api.dart` / `mcp_api.dart` declare
# `'${Env.apiBaseUrl}v1/dev'`-style prefixes and append subpaths at call sites,
# so the extracted string is a prefix root, not a callable route. Covering the
# appended subpaths needs call-site-aware extraction and is a tracked extension
# of this inventory, not silently in scope.
BASE_URL_ROOTS = {'/v1/dev', '/v1/mcp'}

# Known gaps already tracked with a follow-up owner. Add here ONLY with a note
# naming the tracking PR/issue, exactly like the desktop inventories.
KNOWN_MISSING_ROUTES: Set[str] = set()

# Dart route literals: capture from `${Env.apiBaseUrl}` to the closing quote,
# then cut at the first `?` (query strings and optional-query ternaries).
_ROUTE_RE = re.compile(r'\$\{Env\.apiBaseUrl\}(v[0-9]/[^\'"]*)')
_BRACED_INTERPOLATION_RE = re.compile(r'\$\{[^}]*\}')
_SIMPLE_INTERPOLATION_RE = re.compile(r'\$[A-Za-z_][A-Za-z0-9_]*')
_QUERY_RE = re.compile(r'\?.*$')


def _extract_routes_from_dart(source: str) -> Set[str]:
    routes: Set[str] = set()
    for match in _ROUTE_RE.finditer(source):
        route = _QUERY_RE.sub('', match.group(1))
        route = _BRACED_INTERPOLATION_RE.sub('{param}', route)
        # Drop any trailing unterminated interpolation the quote/query cut left.
        route = re.sub(r'\$\{.*$', '', route)
        route = _SIMPLE_INTERPOLATION_RE.sub('{param}', route)
        route = re.sub(r'//+', '/', route)
        route = '/' + route
        if len(route) > 1 and route.endswith('/'):
            route = route.rstrip('/')
        routes.add(route)
    return routes


def _load_flutter_sources() -> str:
    return '\n'.join(path.read_text(encoding='utf-8') for path in sorted(FLUTTER_HTTP_ROOT.rglob('*.dart')))


def _in_scope(routes: Set[str]) -> Set[str]:
    return {r for r in routes if not r.startswith(OUT_OF_SCOPE_PREFIXES) and r not in BASE_URL_ROOTS}


def _load_spec_paths() -> Set[str]:
    spec = json.loads(SPEC_PATH.read_text(encoding='utf-8'))
    return set(spec.get('paths', {}).keys())


def _covered_by_spec(route: str, spec_paths: Set[str]) -> bool:
    """Segment-wise match where a spec `{param}` segment matches ANY client
    segment, including a hardcoded literal (`/v1/wrapped/2025` is covered by
    `/v1/wrapped/{year}` exactly as the HTTP router resolves it). A client
    `{param}` segment still requires a spec param at that position."""
    segments = route.split('/')
    for spec_path in spec_paths:
        spec_segments = spec_path.split('/')
        if len(spec_segments) != len(segments):
            continue
        if all(s.startswith('{') or s == c for s, c in zip(spec_segments, segments)):
            return True
    return False


def test_flutter_sources_exist_and_declare_backend_routes():
    assert FLUTTER_HTTP_ROOT.is_dir(), 'Flutter backend http tree moved; update FLUTTER_HTTP_ROOT'
    routes = _extract_routes_from_dart(_load_flutter_sources())
    assert len(routes) > 20, (
        f'route extraction found only {len(routes)} routes; the `Env.apiBaseUrl` '
        'convention or client layout changed and the extraction regex needs updating'
    )


def test_every_in_scope_flutter_rest_route_exists_in_app_client_openapi():
    routes = _in_scope(_extract_routes_from_dart(_load_flutter_sources()))
    spec_paths = _load_spec_paths()
    missing = sorted(r for r in routes if not _covered_by_spec(r, spec_paths) and r not in KNOWN_MISSING_ROUTES)
    assert not missing, (
        'Flutter REST routes hardcoded under app/lib/backend/http are missing from the '
        'app-client OpenAPI spec. Either add the backend route + response_model, document '
        'the route as out of scope in OUT_OF_SCOPE_PREFIXES, or, if it is a known gap '
        f'already tracked, add it to KNOWN_MISSING_ROUTES with a follow-up owner: {missing}'
    )


def test_known_missing_routes_do_not_rot():
    """A KNOWN_MISSING entry whose route gained a spec entry (or left the code)
    must be removed so the allowlist only ever shrinks toward zero."""
    routes = _in_scope(_extract_routes_from_dart(_load_flutter_sources()))
    spec_paths = _load_spec_paths()
    stale = sorted(r for r in KNOWN_MISSING_ROUTES if r not in routes or _covered_by_spec(r, spec_paths))
    assert not stale, f'KNOWN_MISSING_ROUTES entries no longer needed, remove them: {stale}'

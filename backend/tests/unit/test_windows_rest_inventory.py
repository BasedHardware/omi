"""Inventory + contract test for the Windows desktop app's Python-backend REST surface.

The Windows app (`desktop/windows/src/`) is a first-party REST consumer of the
Python backend: the renderer calls it through the `omiApi` client and the main
process through `apiFetch`/`net.fetch` (task sync, assistants). Its routes map to
the same Firebase-auth app-client OpenAPI surface the Flutter and macOS apps use
(`docs/api-reference/app-client-openapi.json`).

This is the Windows sibling of `test_desktop_rest_inventory.py` (macOS), added
after #11613 shipped a desktop route with no spec entry and broke that guard for
every open PR: each first-party client needs the same inventory so a new client
call site cannot drift from backend-owned OpenAPI authority silently.

- Extracts every `/vN/...` route literal hardcoded under `desktop/windows/src`.
- Excludes out-of-scope protocols (Rust desktop backend, streaming/SSE,
  multipart, WebSocket) via the same prefix list the macOS inventory uses.
- Asserts each in-scope route exists in the app-client OpenAPI spec.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Set

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
WINDOWS_SOURCE_ROOT = ROOT_DIR / 'desktop' / 'windows' / 'src'

# Route prefixes that belong to other service boundaries / protocols, mirrored
# from test_desktop_rest_inventory.py (macOS): the Windows app talks to the same
# Rust desktop backend + streaming surfaces that are out of scope for the
# Python-backend REST SSoT.
OUT_OF_SCOPE_PREFIXES = (
    '/v2/realtime',  # Rust desktop backend
    '/v1/x/',  # integration OAuth (desktop-mediated)
    '/v1/tts/synthesize',  # Rust desktop backend
    '/v2/chat/',  # streaming chat / Rust
    '/v2/chat-sessions',  # Rust desktop backend
    '/v2/desktop/',  # Rust desktop backend
    '/v2/files',  # multipart upload
    '/v2/apps',  # Rust-proxied app routes
    '/v2/voice-message/transcribe-stream',  # streaming upload; spec models only the non-streaming sibling
    '/v4/listen',  # WebSocket transcription socket
)

# Known gaps already tracked with a follow-up owner. Add here ONLY with a note
# naming the tracking PR/issue, exactly like the macOS inventory's list. These
# entries mirror test_desktop_rest_inventory.py: the same backend surfaces are
# consumed by both desktop clients and carry the same follow-up.
KNOWN_MISSING_ROUTES: Set[str] = {
    # Backend router exists (routers/auto_model.py) but the route is not
    # exported to the app-client spec yet; same export-scope gap class as
    # #11613's search-chunks incident.
    '/v1/auto/model-pick',
    # These backend routes exist but return unmodeled (loose) responses, so
    # adding them to the app-client surface would regress the strict
    # `unmodeled_success_response_count == 0` gate (see the macOS inventory's
    # identical entries). Tracked for the response_model-first follow-up.
    '/v1/personas',
    '/v1/staged-tasks',
    '/v1/staged-tasks/promote',
    '/v1/tools/conversations',
    '/v1/tools/conversations/search',
    '/v1/tools/memories',
    '/v1/tools/memories/search',
}

# TS/TSX route literals: '/v1/...' in any quote style including template
# literals; `${expr}` interpolation becomes an OpenAPI-style param placeholder.
_ROUTE_RE = re.compile(r'[\'"`](/v[0-9]/[^\'"`\s]*)')
_TEMPLATE_INTERPOLATION_RE = re.compile(r'\$\{[^}]*\}')
_QUERY_RE = re.compile(r'\?.*$')


def _extract_routes_from_typescript(source: str) -> Set[str]:
    routes: Set[str] = set()
    for match in _ROUTE_RE.finditer(source):
        route = match.group(1)
        if '*' in route:
            # Wildcard PATTERNS (route-policy comments/docs), not callable paths.
            continue
        route = _TEMPLATE_INTERPOLATION_RE.sub('{param}', route)
        route = _QUERY_RE.sub('', route)
        # Drop any trailing unterminated interpolation fragment the quote scan
        # cut through (e.g. a ternary building an optional query suffix).
        route = re.sub(r'\$\{.*$', '', route)
        route = re.sub(r'//+', '/', route)
        if len(route) > 1 and route.endswith('/'):
            route = route.rstrip('/')
        routes.add(route)
    return routes


def _load_windows_sources() -> str:
    chunks = []
    for pattern in ('**/*.ts', '**/*.tsx'):
        for path in sorted(WINDOWS_SOURCE_ROOT.glob(pattern)):
            if path.name.endswith(('.test.ts', '.test.tsx', '.generated.ts')):
                # Generated clients mirror the spec by construction; tests may
                # exercise fixture routes that are not product surface.
                continue
            chunks.append(path.read_text(encoding='utf-8'))
    return '\n'.join(chunks)


def _in_scope(routes: Set[str]) -> Set[str]:
    return {r for r in routes if not r.startswith(OUT_OF_SCOPE_PREFIXES)}


def _load_spec_paths() -> Set[str]:
    spec = json.loads(SPEC_PATH.read_text(encoding='utf-8'))
    return set(spec.get('paths', {}).keys())


def _covered_by_spec(route: str, spec_paths: Set[str]) -> bool:
    """Segment-wise match where a spec `{param}` segment matches ANY client
    segment, including a hardcoded literal, exactly as the HTTP router resolves
    the path. A client `{param}` segment still requires a spec param there."""
    segments = route.split('/')
    for spec_path in spec_paths:
        spec_segments = spec_path.split('/')
        if len(spec_segments) != len(segments):
            continue
        if all(s.startswith('{') or s == c for s, c in zip(spec_segments, segments)):
            return True
    return False


def test_windows_sources_exist_and_declare_backend_routes():
    assert WINDOWS_SOURCE_ROOT.is_dir(), 'Windows desktop source tree moved; update WINDOWS_SOURCE_ROOT'
    routes = _in_scope(_extract_routes_from_typescript(_load_windows_sources()))
    # A bare non-empty assertion lets the extractor silently regress to a single
    # route; the floor keeps the extraction honest (currently ~60 in scope).
    assert len(routes) >= 20, (
        f'route extraction found only {len(routes)} in-scope routes; the extraction '
        'regex or client layout changed and the extractor needs updating'
    )


def test_every_in_scope_windows_rest_route_exists_in_app_client_openapi():
    routes = _in_scope(_extract_routes_from_typescript(_load_windows_sources()))
    spec_paths = _load_spec_paths()
    missing = sorted(r for r in routes if not _covered_by_spec(r, spec_paths) and r not in KNOWN_MISSING_ROUTES)
    assert not missing, (
        'Windows REST routes hardcoded under desktop/windows/src are missing from the '
        'app-client OpenAPI spec. Either add the backend route + response_model, document '
        'the route as out of scope in OUT_OF_SCOPE_PREFIXES, or, if it is a known gap '
        f'already tracked, add it to KNOWN_MISSING_ROUTES with a follow-up owner: {missing}'
    )


def test_known_missing_routes_do_not_rot():
    """A KNOWN_MISSING entry whose route gained a spec entry (or left the code)
    must be removed so the allowlist only ever shrinks toward zero."""
    routes = _in_scope(_extract_routes_from_typescript(_load_windows_sources()))
    spec_paths = _load_spec_paths()
    stale = sorted(r for r in KNOWN_MISSING_ROUTES if r not in routes or _covered_by_spec(r, spec_paths))
    assert not stale, f'KNOWN_MISSING_ROUTES entries no longer needed, remove them: {stale}'


def test_out_of_scope_prefixes_match_at_least_one_route():
    """Mirrors the macOS inventory's rot guard: a prefix excluding nothing is a
    dead entry that silently widens the blind spot if that surface ever gains a
    Windows call site."""
    routes = _extract_routes_from_typescript(_load_windows_sources())
    dead = sorted(p for p in OUT_OF_SCOPE_PREFIXES if not any(r.startswith(p) for r in routes))
    assert not dead, f'OUT_OF_SCOPE_PREFIXES entries match no extracted route, remove them: {dead}'

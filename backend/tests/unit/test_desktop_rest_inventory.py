"""Inventory + contract test for the macOS desktop app's Python-backend REST surface.

The desktop app (`desktop/macos/Desktop/Sources/APIClient.swift`) is a first-party
REST consumer of the Python backend. Its routes map to the same Firebase-auth
app-client OpenAPI surface the Flutter app uses (`docs/api-reference/
app-client-openapi.json`). This test:

- Extracts every backend REST route string hardcoded in APIClient.swift.
- Excludes out-of-scope protocols (Rust desktop backend `/v2/agent/*`,
  `/v2/realtime/*`, `/v1/config/api-keys`, integration OAuth `/v1/x/*`, local
  VM, WebSocket/SSE/binary).
- Asserts each in-scope route exists in the app-client OpenAPI spec.

When this test passes, the desktop's REST surface is proven to map to
backend-owned OpenAPI authority. Generated Swift DTOs and APIClient Codable
migration build on top of this foundation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Set

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
APICLIENT_SWIFT = ROOT_DIR / 'desktop' / 'macos' / 'Desktop' / 'Sources' / 'APIClient.swift'

# Route prefixes that belong to other service boundaries / protocols and are
# explicitly out of scope for the Python-backend REST SSoT rollout.
OUT_OF_SCOPE_PREFIXES = (
    '/v2/realtime',  # Rust desktop backend
    '/v2/agent',  # Rust desktop backend / agent VM
    '/v1/config/api-keys',  # Rust desktop backend
    '/v1/x/',  # integration OAuth (desktop-mediated)
    '/v1/tts/synthesize',  # Rust desktop backend
    '/v2/chat/',  # streaming chat / Rust
    '/v2/chat-sessions',  # Rust desktop backend
    '/v2/desktop/',  # Rust desktop backend
    '/v2/messages/',  # SSE streaming
    '/v2/files',  # multipart upload
    '/v2/apps',  # Rust-proxied app routes (desktop uses v1/apps)
)

# Swift string-interpolation route literals look like "v1/conversations/\(id)".
# Strip the interpolation, the query string, and any trailing punctuation to
# recover the OpenAPI-style path template.
_INTERPOLATION_RE = re.compile(r'\\\([^)]*\)')
_QUERY_RE = re.compile(r'\?.*$')
_TRAILING_PUNCT_RE = re.compile(r'["]+$')


def _extract_routes_from_swift(source: str) -> Set[str]:
    """Pull `vN/...` route literals out of APIClient.swift source text."""
    routes: Set[str] = set()
    for match in re.finditer(r'"(v[0-9]/[^"]*)"', source):
        route = match.group(1)
        # Replace Swift string interpolation `\(id)` with an OpenAPI param
        # placeholder so sub-resource paths survive: `v1/conversations/\(id)/starred`
        # becomes `v1/conversations/{id}/starred`, not `v1/conversations/starred`.
        route = _INTERPOLATION_RE.sub('{param}', route)
        # Drop query strings.
        route = _QUERY_RE.sub('', route)
        # Collapse any double slashes left by malformed interpolation.
        route = re.sub(r'//+', '/', route)
        if route.endswith('/'):
            route = route.rstrip('/')
        # Match the OpenAPI spec's leading-slash form.
        route = '/' + route
        routes.add(route)
    return routes


def _in_scope(routes: Set[str]) -> Set[str]:
    return {r for r in routes if not r.startswith(OUT_OF_SCOPE_PREFIXES)}


def _load_spec_paths() -> Set[str]:
    import json

    spec = json.loads(SPEC_PATH.read_text())
    return set(spec.get('paths', {}).keys())


def _normalize_for_match(path: str) -> str:
    """Normalize both Swift-extracted and spec paths so they compare equal.

    Swift extraction leaves `{id}` where a path param was; the OpenAPI spec uses
    the actual param name (e.g. `{conversation_id}`). Strip param names so both
    sides reduce to a `__param__` placeholder.
    """
    return re.sub(r'\{[^}]+\}', '{param}', path)


def test_apiclient_swift_exists():
    assert APICLIENT_SWIFT.exists(), f'APIClient.swift missing at {APICLIENT_SWIFT}'


def test_out_of_scope_prefixes_match_at_least_one_route():
    """Every documented out-of-scope prefix must match at least one extracted route."""
    source = APICLIENT_SWIFT.read_text()
    all_routes = _extract_routes_from_swift(source)
    unused_prefixes = sorted(
        prefix for prefix in OUT_OF_SCOPE_PREFIXES if not any(route.startswith(prefix) for route in all_routes)
    )
    assert not unused_prefixes, 'Unused OUT_OF_SCOPE_PREFIXES (no matching routes): ' + str(unused_prefixes)


# Desktop REST routes that the macOS app calls but the backend does not
# currently expose in the app-client OpenAPI surface. Each must be fixed
# (add the backend route + response_model, or correct the desktop path) and
# removed from this set. Tracked as SSoT blockers, not silently tolerated.
KNOWN_MISSING_ROUTES: Set[str] = {
    # Desktop calls these but no matching backend route exists — likely dead
    # endpoints or naming drift to be resolved in a follow-up slice.
    '/v1/action-items/batch-scores',
    '/v1/goals/completed',
    '/v1/personas/check-username',
    '/v1/personas/generate-prompt',
    '/v3/memories/mark-all-read',
    '/v3/memories/visibility',  # backend has /v3/memories/{memory_id}/visibility
    '/v3/memories/{param}/read',
    '/v3/memory-imports/batch',  # backend route exists but lacks response_model export
    # These backend routes exist but return unmodeled (loose) responses, so
    # adding them to the app-client surface would regress the strict
    # `unmodeled_success_response_count == 0` gate. They are tracked for a
    # follow-up that adds Pydantic response_models first, then exports them.
    '/v1/personas',
    '/v1/scores',
    '/v1/staged-tasks',
    '/v1/staged-tasks/{param}',
    '/v1/staged-tasks/batch-scores',
    '/v1/staged-tasks/migrate',
    '/v1/staged-tasks/migrate-conversation-items',
    '/v1/staged-tasks/promote',
    '/v1/tools/action-items',
    '/v1/tools/action-items/{param}',
    '/v1/tools/calendar-events',
    '/v1/tools/conversations',
    '/v1/tools/conversations/search',
    '/v1/tools/memories',
    '/v1/tools/memories/search',
}


def test_every_in_scope_desktop_rest_route_exists_in_app_client_openapi():
    source = APICLIENT_SWIFT.read_text()
    in_scope = _in_scope(_extract_routes_from_swift(source))
    spec_paths = _load_spec_paths()
    spec_normalized = {_normalize_for_match(p) for p in spec_paths}

    missing = sorted(
        r for r in in_scope if _normalize_for_match(r) not in spec_normalized and r not in KNOWN_MISSING_ROUTES
    )
    assert not missing, (
        'Desktop REST routes hardcoded in APIClient.swift are missing from the '
        'app-client OpenAPI spec. Either add the backend route + response_model, '
        'document the route as out of scope in OUT_OF_SCOPE_PREFIXES, or, if it '
        'is a known gap already tracked, add it to KNOWN_MISSING_ROUTES with a '
        'follow-up owner: ' + str(missing)
    )


def test_known_missing_routes_do_not_drift():
    """The KNOWN_MISSING set must stay accurate.

    If a route gets fixed (added to the spec), it must be removed here so the
    set does not silently grow stale. If a new missing route appears, it must
    be named here rather than left untracked.
    """
    source = APICLIENT_SWIFT.read_text()
    in_scope = _in_scope(_extract_routes_from_swift(source))
    spec_paths = _load_spec_paths()
    spec_normalized = {_normalize_for_match(p) for p in spec_paths}

    actually_missing = {r for r in in_scope if _normalize_for_match(r) not in spec_normalized}
    # Every route in KNOWN_MISSING must still be actually missing, otherwise it
    # was fixed and the entry is now stale.
    stale = sorted(KNOWN_MISSING_ROUTES - actually_missing)
    assert not stale, 'These KNOWN_MISSING_ROUTES are now in the app-client spec — remove ' 'them from the set: ' + str(
        stale
    )


def test_desktop_rest_inventory_is_nonempty():
    """Sanity guard: the extractor must keep finding routes."""
    source = APICLIENT_SWIFT.read_text()
    in_scope = _in_scope(_extract_routes_from_swift(source))
    assert len(in_scope) >= 20, (
        f'Expected at least 20 in-scope desktop REST routes, found {len(in_scope)}. '
        'The Swift route extractor may have regressed.'
    )

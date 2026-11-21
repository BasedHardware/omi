"""Single source of truth for the legacy-sync import ratchet's selection scope.

The ratchet (``tests/unit/test_sync_legacy_import_ratchet.py``) scans every
backend Python source outside ``tests/``, ``routers/sync.py`` and the retiring
legacy sync modules themselves for imports of the retiring legacy sync
modules. Surviving modules inside ``utils/sync/`` (the cap-hold core,
assignment, ledger, ...) ARE scanned: they stay after C10/C11, so their
legacy edges are exactly the ones the deletion PRs must cut. CI path
selection (``scripts/select_backend_unit_tests.py``) uses the cheap predicate
below over the same exclusions, so a new importer in any area — including
areas whose ``AREA_TESTS`` mapping does not name a ``test_sync_*`` glob —
still runs the ratchet on changed-file CI instead of only the post-merge
``--all`` run. Modeled on ``tests/support/background_task_ratchet_scope.py``,
which keeps the drain ratchet on its scanner's walk scope for the same
reason; the ratchet's own test asserts the scope constants cannot drift.
"""

from __future__ import annotations

EXCLUDED_TOP_DIRS = frozenset({'tests'})
EXCLUDED_PREFIXES = ()
EXCLUDED_FILES = frozenset({'routers/sync.py'})
EXCLUDED_PARTS = frozenset({'venv', 'node_modules', '__pycache__', 'site-packages'})


def is_sync_legacy_ratchet_path(path: str) -> bool:
    """Cheap CI-selection predicate: a guaranteed superset of the ratchet's
    importer scope (every ``*.py`` the ratchet walk can scan selects it).

    Accepts repo-relative (``backend/...``) or backend-relative paths. The
    ratchet's exclusions are mirrored so ``tests/`` edits and
    environment/cache trees do not widen a narrow selection; the ratchet test
    pins these constants against its own so the two scopes cannot drift
    apart. Retiring modules and ``routers/sync.py`` are excluded for edge
    purposes, but they still select the ratchet through the ``utils/sync`` /
    ``routers/sync`` AREA_TESTS mapping (``test_sync_*``).
    """
    normalized = path.strip().replace('\\', '/')
    while normalized.startswith('./'):
        normalized = normalized[2:]
    normalized = normalized.removeprefix('backend/')
    if not normalized.endswith('.py'):
        return False
    parts = normalized.split('/')
    if parts[0] in EXCLUDED_TOP_DIRS or normalized.startswith(EXCLUDED_PREFIXES) or normalized in EXCLUDED_FILES:
        return False
    return not any(part.startswith('.') or part in EXCLUDED_PARTS for part in parts)

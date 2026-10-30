"""Single source of truth for the background-task ratchet's module scope.

The ratchet (``tests/unit/test_background_task_ratchet.py``) scans every
module reachable from the Cloud Tasks / sync handler routers through
first-party ``utils.*`` / ``routers.*`` / ``services.*`` top-level imports,
plus the whole ``utils/batch_pipeline`` and ``utils/sync`` packages. CI path
selection (``scripts/select_backend_unit_tests.py``) uses the cheap prefix
superset derived here over the same scope constants, so a change to any
module the scanner can reach always selects the ratchet: the scanner's scope
and the selector's scope cannot drift apart. Modeled on
``tests/support/firestore_serving_query_inventory.py``, which keeps the
Firestore query guard on its inventory's walk scope for the same reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

ROOT_MODULES = (
    'routers/sync.py',
    'routers/batch_pipeline.py',
    'routers/users.py',
    'routers/conversation_finalization.py',
)
EXTRA_MODULES = ('utils/stt/soniox_usage.py',)
WHOLE_PACKAGES = ('utils/batch_pipeline', 'utils/sync')
FOLLOWED_PREFIXES = ('utils.', 'routers.', 'services.')

_scope_cache: frozenset[str] | None = None


def _module_path(name: str) -> Path | None:
    relative = name.replace('.', '/')
    for candidate in (BACKEND_DIR / f'{relative}.py', BACKEND_DIR / relative / '__init__.py'):
        if candidate.is_file():
            return candidate
    return None


def _imported_names(node: ast.AST) -> set[str]:
    """Import-time imports: everything outside function bodies (incl. guarded/try blocks)."""
    names: set[str] = set()
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Import):
            names.update(alias.name for alias in child.names)
        elif isinstance(child, ast.ImportFrom) and child.module and child.level == 0:
            names.add(child.module)
            names.update(f'{child.module}.{alias.name}' for alias in child.names)
        else:
            names.update(_imported_names(child))
    return names


def scoped_modules() -> list[Path]:
    """Modules the background-task ratchet scans (see module docstring)."""
    seen: set[Path] = set()
    stack = [BACKEND_DIR / root for root in (*ROOT_MODULES, *EXTRA_MODULES)]
    for package in WHOLE_PACKAGES:
        stack.extend(sorted((BACKEND_DIR / package).glob('*.py')))
    while stack:
        path = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        for name in _imported_names(ast.parse(path.read_text(encoding='utf-8'))):
            if not name.startswith(FOLLOWED_PREFIXES):
                continue
            target = _module_path(name)
            if target is not None and target not in seen:
                stack.append(target)
    return sorted(seen)


def ratchet_scope() -> frozenset[str]:
    """Backend-relative scope paths; the walk is only paid once per process."""
    global _scope_cache
    if _scope_cache is None:
        _scope_cache = frozenset(path.relative_to(BACKEND_DIR).as_posix() for path in scoped_modules())
    return _scope_cache


def ratchet_selection_prefixes() -> tuple[str, ...]:
    """Top-level directories that can contain scanned modules, derived from the
    scope constants (root modules, whole packages, followed import prefixes).

    Selection uses this cheap superset instead of the AST walk so the selector
    stays fast; ``backend/tests/unit/test_background_task_ratchet.py`` asserts
    the walk's closure never escapes it.
    """
    prefixes = {root.split('/', 1)[0] + '/' for root in ROOT_MODULES}
    prefixes.update(f'{package.split("/", 1)[0]}/' for package in WHOLE_PACKAGES)
    prefixes.update(f'{prefix.split(".", 1)[0]}/' for prefix in FOLLOWED_PREFIXES)
    return tuple(sorted(prefixes))


def is_background_task_ratchet_path(path: str) -> bool:
    """Cheap CI-selection predicate: a guaranteed superset of ``ratchet_scope()``.

    Accepts repo-relative (``backend/...``) or backend-relative paths; the
    prefixes are backend-relative top-level directories.
    """
    normalized = path.strip().replace('\\', '/')
    while normalized.startswith('./'):
        normalized = normalized[2:]
    normalized = normalized.removeprefix('backend/')
    return normalized.startswith(ratchet_selection_prefixes())

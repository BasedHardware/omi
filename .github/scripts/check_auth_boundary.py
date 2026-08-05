#!/usr/bin/env python3
"""Keep the auth boundary sealed: utils/auth/ is the only door to Firebase Auth (WP3).

Outside ``backend/utils/auth/`` (and the documented exceptions below) no module may touch the Firebase
**auth** surface — ``import firebase_admin.auth`` / ``from firebase_admin.auth import ...`` /
``from firebase_admin import auth`` / a ``<firebase_admin-alias>.auth`` attribute access (e.g.
``firebase_admin.auth.verify_id_token(...)`` after a plain ``import firebase_admin``, or
``fb.auth.verify_id_token(...)`` after ``import firebase_admin as fb``). Callers reach
authentication through the neutral port (``utils.auth.get_auth_provider()`` → verify_token /
get_user_profile / …), so the backend stays swappable (Firebase | OIDC/Keycloak).

Deliberately NOT forbidden: ``firebase_admin.initialize_app`` (process bootstrap), ``firebase_admin.
messaging`` (push, ADR-0011), ``firebase_admin.firestore`` (that's the Firestore guard's job). This is
the auth analogue of the Firestore/object-store/vector boundary guards; without it an upstream merge
could silently reintroduce a raw Firebase-auth call (ADR-0029/0030). Ratchets against a baseline (WP3
target: empty). Companion of ADR-0034/0004.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_ROOT = Path('backend')
DEFAULT_BASELINE = Path('.github/scripts/auth_boundary_baseline.json')

# Paths (relative to the scan root, i.e. backend/) exempt from the boundary:
#  - utils/auth/ : the boundary itself (the port + its firebase/oidc adapters).
#  - tests/, testing/ : the test suites (they inject the in-memory FakeAuthProvider / stub firebase).
#  - scripts/    : one-off operational tooling (ADR-0023).
#  - agent-proxy/, pusher/ : separately deployed services with their own firebase app (ADR-0023).
#  - migrations/ : removed in WP1; kept so a re-added dir cannot silently slip in.
EXCLUDED_PREFIXES = ('utils/auth/', 'tests/', 'testing/', 'scripts/', 'agent-proxy/', 'pusher/', 'migrations/')


def _is_forbidden_import_module(module: str | None) -> bool:
    if not module:
        return False
    return module == 'firebase_admin.auth' or module.startswith('firebase_admin.auth.')


def _forbidden_dynamic_import(node: ast.Call, is_forbidden) -> bool:
    """A literal dynamic import of a forbidden module: ``importlib.import_module('X')``,
    ``import_module('X')`` (bare, from ``from importlib import import_module``) or ``__import__('X')``.

    The attribute form is restricted to ``importlib.import_module`` so an unrelated helper method named
    ``import_module`` is not a false positive. The module name is taken from the first positional
    argument or, if absent, the ``name=`` keyword — so a keyword-form call cannot dodge the check."""
    func = node.func
    if isinstance(func, ast.Attribute):
        if not (func.attr == 'import_module' and isinstance(func.value, ast.Name) and func.value.id == 'importlib'):
            return False
    elif isinstance(func, ast.Name):
        if func.id not in ('import_module', '__import__'):
            return False
    else:
        return False
    arg = node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == 'name'), None)
    return isinstance(arg, ast.Constant) and isinstance(arg.value, str) and is_forbidden(arg.value)


def _firebase_admin_aliases(tree: ast.AST) -> set[str]:
    """Local names bound to the ``firebase_admin`` package by ``import`` statements.

    ``import firebase_admin`` / ``import firebase_admin as fb`` / ``import firebase_admin.auth``
    all bind a name that can then reach the auth surface via ``<name>.auth`` — an alias must not
    let ``fb.auth.verify_id_token(...)`` slip past the boundary. ``firebase_admin`` is always
    recognised so a raw ``firebase_admin.auth`` attribute access is caught even in a snippet that
    imports the submodule directly.
    """
    aliases = {'firebase_admin'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'firebase_admin' or alias.name.startswith('firebase_admin.'):
                    aliases.add(alias.asname or alias.name.split('.', 1)[0])
    # Propagated aliases: ``fb2 = fb`` (or ``x = firebase_admin``) rebinds the package to another
    # name that can still reach ``.auth``. Iterate to a fixpoint so chains (a = fb; b = a) are covered.
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id not in aliases:
                        aliases.add(target.id)
                        changed = True
    return aliases


class _BoundaryVisitor(ast.NodeVisitor):
    def __init__(self, aliases: set[str]) -> None:
        self.count = 0
        self._aliases = aliases

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - AST visitor name
        for alias in node.names:
            if _is_forbidden_import_module(alias.name):
                self.count += 1
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - AST visitor name
        # ``from firebase_admin.auth import X``.
        if _is_forbidden_import_module(node.module):
            self.count += 1
        # ``from firebase_admin import auth``.
        elif node.module == 'firebase_admin' and any(alias.name == 'auth' for alias in node.names):
            self.count += 1
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802 - AST visitor name
        # ``<firebase_admin-alias>.auth`` attribute access (catches fb.auth.verify_id_token(...) after
        # ``import firebase_admin as fb`` as well as the plain ``import firebase_admin`` form).
        # initialize_app / messaging / firestore are allowed.
        if node.attr == 'auth' and isinstance(node.value, ast.Name) and node.value.id in self._aliases:
            self.count += 1
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - AST visitor name
        # Literal ``importlib.import_module('firebase_admin.auth')`` / ``__import__(...)`` that dodges
        # the static ``import`` (mirrors the vector/object guards).
        if _forbidden_dynamic_import(node, _is_forbidden_import_module):
            self.count += 1
        self.generic_visit(node)


def count_boundary_violations(source: str, filename: str = '<unknown>') -> int:
    tree = ast.parse(source, filename=filename)
    visitor = _BoundaryVisitor(_firebase_admin_aliases(tree))
    visitor.visit(tree)
    return visitor.count


def collect_counts(repository_root: Path, scan_root: Path) -> dict[str, int]:
    root = repository_root / scan_root
    counts: dict[str, int] = {}
    for path in sorted(root.rglob('*.py')):
        rel_to_scan = path.relative_to(root).as_posix()
        if any(rel_to_scan.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        count = count_boundary_violations(path.read_text(encoding='utf-8'), str(path))
        if count:
            counts[path.relative_to(repository_root).as_posix()] = count
    return counts


def load_baseline(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for key, value in payload.items()
    ):
        raise ValueError(f'baseline must be a JSON object of path-to-nonnegative-count entries: {path}')
    return payload


def violations(counts: dict[str, int], baseline: dict[str, int]) -> list[str]:
    return [
        f'{path}: found {count}, baseline allows {baseline.get(path, 0)}'
        for path, count in sorted(counts.items())
        if count > baseline.get(path, 0)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPOSITORY_ROOT)
    parser.add_argument('--scan-root', type=Path, default=DEFAULT_SCAN_ROOT)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    parser.add_argument('--print-counts', action='store_true')
    args = parser.parse_args()

    repository_root = args.root.resolve()
    counts = collect_counts(repository_root, args.scan_root)
    if args.print_counts:
        print(json.dumps(counts, indent=2, sort_keys=True))
        return 0

    baseline_path = args.baseline if args.baseline.is_absolute() else repository_root / args.baseline
    errors = violations(counts, load_baseline(baseline_path))
    if not errors:
        return 0
    print('FAIL: auth boundary breached — go through the utils.auth port')
    print('(get_auth_provider().verify_token / get_user_profile), not firebase_admin.auth.')
    print(*errors, sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Keep the Firestore persistence boundary sealed: database/ is the only door (WP1).

Outside ``backend/database/`` (and the documented exceptions below) no module may:
  * import the client / SDK — ``database._client``, ``google.cloud.firestore*``,
    ``firebase_admin.firestore`` (or ``from firebase_admin import firestore``); or
  * run a raw persistence op — a ``.document(...)`` / ``.collection(...)`` /
    ``.collection_group(...)`` / ``.transaction(...)`` method call.

Blessed database/ ports (``database.document_store``, ``database.sentinels``,
``database.firestore_errors``, ``database.document_ids`` and every other
``database.*`` module) are allowed everywhere — that is how callers reach persistence now.

Ratchets against a baseline (WP1 target: empty). Companion of ADR-0001/0002/0004: this is the
seal that makes the storage layer swappable (Firestore | Mongo | ArcadeDB) in WP2.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_ROOT = Path('backend')
DEFAULT_BASELINE = Path('.github/scripts/firestore_persistence_boundary_baseline.json')

# Paths (relative to the scan root, i.e. backend/) exempt from the boundary:
#  - database/   : the boundary itself.
#  - tests/, testing/ : the test suites (they inject fakes and drive fixtures).
#  - scripts/    : one-off operational tooling, not deployed runtime (intentional, permanent — ADR-0023).
#  - agent-proxy/: a separately deployed service with its own firebase_admin app (intentional — ADR-0023).
#  - migrations/ : removed in WP1; kept here so a re-added dir does not silently slip in.
EXCLUDED_PREFIXES = ('database/', 'tests/', 'testing/', 'scripts/', 'agent-proxy/', 'migrations/')

_FORBIDDEN_OP_METHODS = frozenset({'document', 'collection', 'collection_group', 'transaction'})


def _is_forbidden_import_module(module: str | None) -> bool:
    if not module:
        return False
    return (
        module == 'database._client'
        or module.startswith('database._client.')
        or module == 'google.cloud.firestore'
        or module.startswith('google.cloud.firestore')
        or module == 'firebase_admin.firestore'
        or module.startswith('firebase_admin.firestore')
    )


def _is_forbidden_firestore_member(name: str) -> bool:
    # A ``from google.cloud import <name>`` / ``from firebase_admin import <name>`` member that reaches
    # the Firestore SDK: ``firestore`` and the versioned client packages ``firestore_v1``,
    # ``firestore_admin_v1``, … (``from google.cloud import firestore_v1`` bypasses the plain-import seal).
    return name == 'firestore' or name.startswith('firestore_') or name.startswith('firestore.')


def _is_forbidden_database_member(name: str) -> bool:
    # ``from database import _client`` (parent-package form) reaches the raw client; the blessed
    # ``database.*`` ports (document_store, sentinels, firestore_errors, document_ids, …) stay allowed.
    return name == '_client' or name.startswith('_client.')


class _BoundaryVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.count = 0

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - AST visitor name
        for alias in node.names:
            if _is_forbidden_import_module(alias.name):
                self.count += 1
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - AST visitor name
        # ``from google.cloud.firestore import X`` / ``from database._client import X``.
        if _is_forbidden_import_module(node.module):
            self.count += 1
        # ``from google.cloud import firestore`` / ``firestore_v1`` / ``from firebase_admin import firestore``.
        elif node.module in ('google.cloud', 'firebase_admin'):
            if any(_is_forbidden_firestore_member(alias.name) for alias in node.names):
                self.count += 1
        # ``from database import _client`` (parent-package import of the raw client).
        elif node.module == 'database':
            if any(_is_forbidden_database_member(alias.name) for alias in node.names):
                self.count += 1
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - AST visitor name
        if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_OP_METHODS:
            self.count += 1
        self.generic_visit(node)


def count_boundary_violations(source: str, filename: str = '<unknown>') -> int:
    visitor = _BoundaryVisitor()
    visitor.visit(ast.parse(source, filename=filename))
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
        isinstance(key, str) and isinstance(value, int) and value >= 0 for key, value in payload.items()
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
    print('FAIL: Firestore persistence boundary breached — go through database/ ports')
    print('(database.document_store / sentinels / firestore_errors), not the client/SDK.')
    print(*errors, sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

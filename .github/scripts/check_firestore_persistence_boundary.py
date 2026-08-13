#!/usr/bin/env python3
"""Keep the Firestore persistence boundary sealed: database/ is the only door (WP1; ADR-0044).

Outside ``backend/database/`` (and the documented exceptions below) no module may:
  * construct a RAW SDK client — ``firestore.Client()`` / ``firestore.AsyncClient()`` /
    ``firestore_v1.Client()`` / ``firebase_admin.firestore.client()``; or
  * import ``database._client`` — the raw client builder (callers receive an injected ``db_client``
    facade, ADR-0044, or go through ``database.store``); or
  * import ``database.sentinels`` — it re-exports Firestore SDK sentinels (``DELETE_FIELD``, …)
    that do not translate on the Mongo adapter; neutral ``database.store.sentinels`` is the port.

ADR-0044: importing the Firestore SDK for constants/decorators/``FieldFilter`` (``from google.cloud
import firestore``) and running ``.document()``/``.collection()``/``.transaction()`` on the injected
``db_client`` facade ARE allowed — upstream threads that facade through the domain, and it is itself a
database/ port. The only remaining leak is building your own SDK client, caught above.

Blessed database/ ports (``database.document_store``, ``database.store`` and its
``database.store.sentinels``, ``database.firestore_errors``, ``database.document_ids`` and every
other ``database.*`` module except ``database._client`` / ``database.sentinels``) are allowed
everywhere — that is how callers reach persistence now.

Ratchets against a baseline (WP1 target: empty). Companion of ADR-0001/0002/0004/0044: this is the
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
# NOTE: migrations/ is intentionally NOT excluded — a re-added migration that touches Firestore
# directly must fail this boundary too (the upstream migrations are on the neutral port; verified 0).
EXCLUDED_PREFIXES = ('database/', 'tests/', 'testing/', 'scripts/', 'agent-proxy/')


def _is_forbidden_import_module(module: str | None) -> bool:
    if not module:
        return False
    return (
        # ``database.sentinels`` re-exports Firestore SDK sentinels (DELETE_FIELD, ArrayUnion, …).
        # Domain code writing through the neutral store must use ``database.store.sentinels`` instead —
        # a Firestore sentinel does not translate on the Mongo adapter (it is stored as a literal).
        module == 'database.sentinels'
        or module.startswith('database.sentinels.')
    )
    # NOTE (ADR-0044): ``from database._client import db / get_firestore_client`` is allowed — ``db``
    # is the neutral facade proxy (Mongo) / the real SDK client (Firestore backend), i.e. the
    # sanctioned way to obtain a ``db_client``. The raw leak — building an SDK client directly — is
    # caught by ``_is_client_construction``.
    # NOTE (ADR-0044): importing the Firestore SDK itself is NO LONGER forbidden. Upstream threads a
    # ``db_client`` (the neutral facade on Mongo) and passes Firestore constants/decorators
    # (``firestore.Query.DESCENDING``, ``SERVER_TIMESTAMP``, ``FieldFilter``, ``transactional``) into
    # it; the facade translates them. The leak that still matters — constructing a RAW client — is
    # caught by ``_is_client_construction`` below, not by banning the import.


def _is_forbidden_firestore_member(name: str) -> bool:
    # ADR-0044: ``from google.cloud import firestore`` (and the versioned packages) is allowed —
    # domain code uses the SDK only for constants/decorators/FieldFilter passed to the injected
    # ``db_client`` facade. Constructing a raw client is what stays forbidden (see below).
    del name
    return False


# firestore.Client() / firestore.AsyncClient() / firestore_v1.Client() / firebase_admin.firestore.client()
_CLIENT_CTOR_ATTRS = frozenset({'Client', 'AsyncClient'})


def _is_client_construction(node: ast.Call) -> bool:
    """A raw Firestore/Firebase client construction — the one persistence leak still forbidden outside
    ``database/`` (ADR-0044). Domain code must receive an injected ``db_client`` (the neutral facade),
    never build its own SDK client."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    receiver = func.value
    base = receiver.id if isinstance(receiver, ast.Name) else (receiver.attr if isinstance(receiver, ast.Attribute) else '')
    if func.attr in _CLIENT_CTOR_ATTRS:  # firestore.Client(...) / firestore_v1.AsyncClient(...)
        return base == 'firestore' or base.startswith('firestore_')
    if func.attr == 'client':  # firebase_admin.firestore.client(...)
        return base == 'firestore'
    return False


def _is_forbidden_database_member(name: str) -> bool:
    # ``from database import sentinels`` reaches the Firestore SDK sentinels (use
    # ``database.store.sentinels`` instead). ``from database import _client`` is allowed (ADR-0044:
    # it yields the facade accessors ``db`` / ``get_firestore_client``). The remaining blessed
    # ``database.*`` ports (document_store, firestore_errors, document_ids, store, …) stay allowed.
    return name == 'sentinels' or name.startswith('sentinels.')


def _forbidden_dynamic_import(node: ast.Call) -> bool:
    """A literal dynamic import of a forbidden module: ``importlib.import_module('X')``,
    ``import_module('X')`` (bare, from ``from importlib import import_module``) or ``__import__('X')``.

    The attribute form is restricted to ``importlib.import_module`` so an unrelated helper method named
    ``import_module`` is not a false positive. The module name is taken from the first positional
    argument or, if absent, the ``name=`` keyword — so a keyword-form call cannot dodge the check.
    Mirrors the object-store boundary guard so a runtime caller cannot load ``database._client`` /
    the Firestore SDK dynamically and bypass the persistence-boundary gate.
    """
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
    return isinstance(arg, ast.Constant) and isinstance(arg.value, str) and _is_forbidden_import_module(arg.value)


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
        # ADR-0044: ``.document()/.collection()/.transaction()`` are no longer flagged — they run on
        # the injected ``db_client`` facade (a database/ port). The forbidden leak is constructing a
        # raw SDK client, or dynamically importing the raw client module.
        if _is_client_construction(node):
            self.count += 1
        elif _forbidden_dynamic_import(node):
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
    print('FAIL: Firestore persistence boundary breached — go through database/ ports')
    print('(database.document_store / database.store.sentinels / database.firestore_errors), not the')
    print('client/SDK. The forbidden re-export is database.sentinels — use database.store.sentinels.')
    print(*errors, sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

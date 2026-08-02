#!/usr/bin/env python3
"""Keep the vector-store boundary sealed: utils/vector/ is the only door (WP4).

Outside ``backend/utils/vector/`` (and the documented exceptions below) no module may import the raw
vector client — ``pinecone`` (``import pinecone`` / ``from pinecone[...] import ...`` / a literal
``importlib.import_module('pinecone')`` / ``__import__('pinecone')``) or ``langchain_pinecone``.
Callers reach vector search through the neutral port
(``utils.vector.get_vector_store()`` → ``upsert`` / ``query`` / ``delete_by_ids`` / …), so the backend
stays swappable (Pinecone | Qdrant). This is the vector-store analogue of the Firestore and
object-store boundary guards; without it an upstream merge could silently reintroduce a raw Pinecone
client in an auto-merged region or a new file (ADR-0029/0030).

Import-based (a raw client cannot be built without importing the SDK); the ``.upsert``/``.query``
method names are intentionally NOT forbidden because the neutral port uses them too. Ratchets against
a baseline (WP4 target: empty). Companion of ADR-0033/0004.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_ROOT = Path('backend')
DEFAULT_BASELINE = Path('.github/scripts/vector_store_boundary_baseline.json')

# Paths (relative to the scan root, i.e. backend/) exempt from the boundary:
#  - utils/vector/ : the boundary itself (the port + its pinecone/qdrant adapters).
#  - tests/, testing/ : the test suites (they inject the in-memory FakeVectorStore).
#  - scripts/      : one-off operational tooling (incl. scripts/rag dev helpers) — ADR-0023.
#  - agent-proxy/  : a separately deployed service — ADR-0023.
#  - migrations/   : removed in WP1; kept here so a re-added dir does not silently slip in.
EXCLUDED_PREFIXES = ('utils/vector/', 'tests/', 'testing/', 'scripts/', 'agent-proxy/', 'migrations/')


def _is_forbidden_import_module(module: str | None) -> bool:
    if not module:
        return False
    return (
        module == 'pinecone'
        or module.startswith('pinecone.')
        or module == 'langchain_pinecone'
        or module.startswith('langchain_pinecone.')
    )


class _BoundaryVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.count = 0

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - AST visitor name
        for alias in node.names:
            if _is_forbidden_import_module(alias.name):
                self.count += 1
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - AST visitor name
        if _is_forbidden_import_module(node.module):
            self.count += 1
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - AST visitor name
        # Literal dynamic-import forms that dodge the static ``import``: ``importlib.import_module('pinecone')``,
        # ``import_module('pinecone')`` and ``__import__('pinecone')`` with a forbidden string literal.
        func = node.func
        func_name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        if func_name in ('import_module', '__import__') and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and _is_forbidden_import_module(first.value):
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
    print('FAIL: vector-store boundary breached — go through the utils.vector port')
    print('(get_vector_store().upsert / query / delete_by_ids), not a raw pinecone/langchain_pinecone client.')
    print(*errors, sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

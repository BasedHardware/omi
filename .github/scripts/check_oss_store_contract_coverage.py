#!/usr/bin/env python3
"""Inventory the document-store query shapes whose Mongo translation is NOT covered by a contract test.

This is a **static inventory with a ratchet**, not behavioral coverage: it cannot tell whether a
contract test asserts the right thing, only whether some contract test drives the module at all. It
exists because of a real, shipped defect: `database/apps.py` expressed 19 marketplace reads as
``where(filter=BaseCompositeFilter('AND', [...]))``, the facade (ADR-0044) never translated that
shape, and so **every** marketplace query returned 500 under our own default (``STORAGE_BACKEND=mongo``)
from the day the facade landed until 2026-08-21 — while the whole suite stayed green. Nothing was
watching, because the unit suites stub the filter object and the live E2E never calls ``/v1/apps``.

The lesson is not "apps.py needed a test": it is that the *set of modules using a shape the facade has
to translate* was invisible. This guard makes it visible and keeps it from growing.

A module counts as **at risk** when it uses one of the shapes below — the ones the facade has to
re-express rather than pass through, which is where a Mongo/Firestore divergence can hide:

  composite_filter   BaseCompositeFilter(...)                  -> Mongo $and/$or, flattened
  cursor             start_at/start_after/end_at/end_before    -> range predicates on the sort key
  projection         .select(...)                              -> Mongo projection document
  aggregation        .count(...)                               -> count_documents / aggregate
  transaction        @firestore.transactional, transaction=    -> Mongo session (see also: stream())
  batch              .batch()                                  -> grouped bulk_write, per collection
  atomic_field_ops   ArrayUnion / ArrayRemove / Increment      -> $addToSet / $pull / $inc
  collection_group   .collection_group(...)                    -> a collection-name convention

It counts as **covered** when some file in ``backend/tests/contract/`` imports it (any of
``import database.x``, ``from database import x``, ``from database.x import y``) — the dual-backend
contract suites are the only ones that run the real chain (module -> facade -> adapter -> live
Firestore emulator AND live Mongo replica set) and assert the two agree.

The count that ratchets is *at-risk-and-uncovered shapes per module*. It may only go down: covering a
module drops its entry, and a new module (or an upstream merge that adds one of these shapes to an
uncovered module) fails until it is either covered or consciously added to the baseline.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_ROOT = Path('backend')
DEFAULT_BASELINE = Path('.github/scripts/store_contract_coverage_baseline.json')

DOMAIN_DIR = 'database'
CONTRACT_DIR = 'tests/contract'

# Modules under database/ that are not domain accessors over the document store: the store port and
# its adapters, the facade, the raw-client accessor, and the other datastores (redis, vectors). They
# have their own guards and suites; counting their shapes here would only add noise.
EXCLUDED_MODULES = frozenset(
    {
        '__init__',
        '_client',
        'document_store',
        'firestore_cache',
        'firestore_cache_metrics',
        'firestore_errors',
        'firestore_index_registry',
        'firestore_read_metrics',
        'firestore_transaction_retry',
        'helpers',
        'mem_db',
        'redis_db',
        'redis_pubsub',
        'sentinels',
        'vector_db',
    }
)

CURSOR_METHODS = frozenset({'start_at', 'start_after', 'end_at', 'end_before'})
ATOMIC_FIELD_OPS = frozenset({'ArrayUnion', 'ArrayRemove', 'Increment'})


class _ShapeVisitor(ast.NodeVisitor):
    """Collect the at-risk shapes a module uses, by name."""

    def __init__(self) -> None:
        self.shapes: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - AST visitor name
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        if name == 'BaseCompositeFilter':
            self.shapes.add('composite_filter')
        elif name in CURSOR_METHODS:
            self.shapes.add('cursor')
        elif name == 'select':
            self.shapes.add('projection')
        elif name == 'count':
            self.shapes.add('aggregation')
        elif name == 'batch':
            self.shapes.add('batch')
        elif name in ATOMIC_FIELD_OPS:
            self.shapes.add('atomic_field_ops')
        elif name == 'collection_group':
            self.shapes.add('collection_group')
        if any(kw.arg == 'transaction' for kw in node.keywords):
            self.shapes.add('transaction')
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - AST visitor name
        self._decorators(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802 - AST visitor name
        self._decorators(node)
        self.generic_visit(node)

    def _decorators(self, node) -> None:
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Attribute) and target.attr == 'transactional':
                self.shapes.add('transaction')
            elif isinstance(target, ast.Name) and target.id == 'transactional':
                self.shapes.add('transaction')

    # A shape reached through an argument named ``transaction`` is the same risk as the kwarg form.
    def visit_arg(self, node: ast.arg) -> None:  # noqa: N802 - AST visitor name
        if node.arg == 'transaction':
            self.shapes.add('transaction')
        self.generic_visit(node)


def module_shapes(source: str) -> set[str]:
    """The at-risk shapes used by one module's source. Syntax errors surface as an empty set."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    visitor = _ShapeVisitor()
    visitor.visit(tree)
    return visitor.shapes


class _ContractImportVisitor(ast.NodeVisitor):
    """Collect the ``database.<module>`` names a contract test imports."""

    def __init__(self) -> None:
        self.modules: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - AST visitor name
        for alias in node.names:
            parts = alias.name.split('.')
            if len(parts) >= 2 and parts[0] == DOMAIN_DIR:
                self.modules.add(parts[1])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - AST visitor name
        module = node.module or ''
        parts = module.split('.')
        if parts[0] == DOMAIN_DIR:
            if len(parts) >= 2:
                self.modules.add(parts[1])
            else:
                # ``from database import apps, users`` — each name is a module.
                self.modules.update(alias.name for alias in node.names)
        self.generic_visit(node)


def contract_covered_modules(sources: dict[str, str]) -> set[str]:
    """Module names driven by at least one contract test, given {path: source}."""
    covered: set[str] = set()
    for source in sources.values():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        visitor = _ContractImportVisitor()
        visitor.visit(tree)
        covered |= visitor.modules
    return covered


def check(domain_sources: dict[str, str], contract_sources: dict[str, str]) -> dict[str, int]:
    """{module: number of at-risk shapes with no contract coverage}, given sources keyed by name/path.

    Pure over strings so the unit test can drive it without a repository on disk.
    """
    covered = contract_covered_modules(contract_sources)
    counts: dict[str, int] = {}
    for name, source in domain_sources.items():
        if name in EXCLUDED_MODULES or name in covered:
            continue
        shapes = module_shapes(source)
        if shapes:
            counts[name] = len(shapes)
    return counts


def detail(domain_sources: dict[str, str], contract_sources: dict[str, str]) -> dict[str, list[str]]:
    """Same as :func:`check` but naming the shapes — the report a human ranks work from."""
    covered = contract_covered_modules(contract_sources)
    out: dict[str, list[str]] = {}
    for name, source in domain_sources.items():
        if name in EXCLUDED_MODULES or name in covered:
            continue
        shapes = module_shapes(source)
        if shapes:
            out[name] = sorted(shapes)
    return out


def _read_sources(repository_root: Path, scan_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    base = scan_root if scan_root.is_absolute() else repository_root / scan_root
    domain = {path.stem: path.read_text(encoding='utf-8') for path in sorted((base / DOMAIN_DIR).glob('*.py'))}
    contract = {
        str(path): path.read_text(encoding='utf-8') for path in sorted((base / CONTRACT_DIR).glob('test_*.py'))
    }
    return domain, contract


def load_baseline(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, int) and value >= 0 for key, value in payload.items()
    ):
        raise ValueError(f'baseline must be a JSON object of module-to-nonnegative-count entries: {path}')
    return payload


def violations(counts: dict[str, int], baseline: dict[str, int]) -> list[str]:
    return [
        f'{DOMAIN_DIR}/{module}.py: {count} at-risk shape(s) with no contract test, baseline allows '
        f'{baseline.get(module, 0)}'
        for module, count in sorted(counts.items())
        if count > baseline.get(module, 0)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPOSITORY_ROOT)
    parser.add_argument('--scan-root', type=Path, default=DEFAULT_SCAN_ROOT)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    parser.add_argument('--print-counts', action='store_true')
    parser.add_argument('--report', action='store_true', help='name the uncovered shapes per module')
    args = parser.parse_args()

    repository_root = args.root.resolve()
    domain_sources, contract_sources = _read_sources(repository_root, args.scan_root)
    if args.report:
        print(json.dumps(detail(domain_sources, contract_sources), indent=2, sort_keys=True))
        return 0
    counts = check(domain_sources, contract_sources)
    if args.print_counts:
        print(json.dumps(counts, indent=2, sort_keys=True))
        return 0

    baseline_path = args.baseline if args.baseline.is_absolute() else repository_root / args.baseline
    errors = violations(counts, load_baseline(baseline_path))
    if not errors:
        return 0
    print('FAIL: a document-store query shape the facade has to translate gained no dual-backend cover.')
    print('Add a contract test under backend/tests/contract/ that drives the module through the facade')
    print('against BOTH a live Firestore emulator and a live Mongo replica set (recipe:')
    print('deploy/onprem/SELFHOST_NOTES.md, "Dual-backend contract test"), or raise the baseline knowingly.')
    print(*errors, sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

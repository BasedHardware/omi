#!/usr/bin/env python3
"""Prevent new direct Pydantic model construction in Firestore readers.

Firestore documents must cross ``database.read_boundary`` so malformed or
legacy data receives one safe logging, telemetry, and fail-open/fail-closed
policy. This ratchet would have caught the repeated #9494 -> #9696 class of
retail malformed-document fixes.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_ROOT = Path('backend/database')
DEFAULT_BASELINE = Path('.github/scripts/firestore_model_read_boundary_baseline.json')
EXCLUDED_FILES = frozenset({'read_boundary.py'})


def _is_models_import(module: str | None) -> bool:
    return module == 'models' or (module is not None and module.startswith('models.'))


class _ModelConstructionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.model_names: set[str] = set()
        self.model_module_names: set[str] = set()
        self.count = 0

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - AST visitor name
        for alias in node.names:
            if _is_models_import(alias.name):
                # ``import models.other`` binds ``models``; an alias binds itself.
                self.model_module_names.add(alias.asname or alias.name.split('.', 1)[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - AST visitor name
        if _is_models_import(node.module):
            self.model_names.update(alias.asname or alias.name for alias in node.names)
            if node.module == 'models':
                self.model_module_names.update(alias.asname or alias.name for alias in node.names)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - AST visitor name
        if self._is_model_validate(node) or self._is_model_kwargs_constructor(node):
            self.count += 1
        self.generic_visit(node)

    def _is_model_validate(self, node: ast.Call) -> bool:
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == 'model_validate'
            and bool(node.args or node.keywords)
            and self._is_model_reference(node.func.value)
        )

    def _is_model_kwargs_constructor(self, node: ast.Call) -> bool:
        return (
            self._is_model_reference(node.func)
            and any(keyword.arg is None for keyword in node.keywords)
        )

    def _is_model_reference(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.model_names
        dotted = self._dotted_name(node)
        return dotted is not None and len(dotted) > 1 and dotted[0] in self.model_module_names

    @staticmethod
    def _dotted_name(node: ast.expr) -> tuple[str, ...] | None:
        if isinstance(node, ast.Name):
            return (node.id,)
        if isinstance(node, ast.Attribute):
            parent = _ModelConstructionVisitor._dotted_name(node.value)
            return (*parent, node.attr) if parent is not None else None
        return None


def count_model_constructions(source: str, filename: str = '<unknown>') -> int:
    visitor = _ModelConstructionVisitor()
    visitor.visit(ast.parse(source, filename=filename))
    return visitor.count


def collect_counts(repository_root: Path, scan_root: Path) -> dict[str, int]:
    root = repository_root / scan_root
    counts: dict[str, int] = {}
    for path in sorted(root.rglob('*.py')):
        if path.name in EXCLUDED_FILES:
            continue
        count = count_model_constructions(path.read_text(encoding='utf-8'), str(path))
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
    print('FAIL: direct Firestore model construction increased; use database.read_boundary instead.')
    print('This guard closes the #9494 -> #9696 malformed-document failure class.')
    print(*errors, sep='\n')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

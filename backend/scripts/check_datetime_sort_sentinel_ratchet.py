#!/usr/bin/env python3
"""Reject naive ``datetime.min`` / ``datetime.max`` sentinels in backend sort keys.

The #9571 review-queue 500 and the #9600 follow-up both came from ordering
timezone-aware stored dates against a naive ``datetime.min`` fallback. This is
a narrow static tripwire, not behavioral proof: it catches direct sentinels in
``sorted(..., key=...)`` and ``values.sort(key=...)``. Production behavior still
needs its normal regression coverage.

Use an explicit timezone-aware fallback instead:

    datetime.min.replace(tzinfo=timezone.utc)
    datetime.max.replace(tzinfo=timezone.utc)

The scan intentionally excludes tests and only rejects a direct naive sentinel
inside an inline sort key. It does not infer the timezone behavior of helper
functions or classify arbitrary datetime expressions.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = Path("backend")
# Virtual environments are local tooling, not backend sources. In particular,
# the OpenAPI checker creates ``.openapi-venv`` under backend/; scanning a
# vendored Python-2 compatibility module there would make this source ratchet
# fail independently of a production change. Dot-prefixed directories are
# excluded below, but developers also keep plain ``venv``/``env`` checkouts
# under backend/ (test.sh supports them), so exclude those by name too.
EXCLUDED_DIRECTORY_NAMES = {"__pycache__", "tests", "venv", "env", "node_modules"}
BASELINE = 0

SORT_SENTINEL_GUIDANCE = (
    "Use datetime.min.replace(tzinfo=timezone.utc) or "
    "datetime.max.replace(tzinfo=timezone.utc) for timezone-aware sort fallbacks. "
    "#9571 and #9600 were the real 500 incidents; this static tripwire supplements behavioral coverage."
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    sentinel: str


@dataclass(frozen=True)
class DateTimeBindings:
    class_names: frozenset[str]
    module_names: frozenset[str]


def _datetime_bindings(tree: ast.Module) -> DateTimeBindings:
    """Resolve the common stdlib datetime import spellings used by backend code."""

    class_names: set[str] = set()
    module_names: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom) and statement.module == "datetime":
            for imported in statement.names:
                if imported.name == "datetime":
                    class_names.add(imported.asname or imported.name)
        elif isinstance(statement, ast.Import):
            for imported in statement.names:
                if imported.name == "datetime":
                    module_names.add(imported.asname or imported.name)
    return DateTimeBindings(frozenset(class_names), frozenset(module_names))


def _sentinel_name(node: ast.AST, bindings: DateTimeBindings) -> str | None:
    """Return ``min``/``max`` when *node* is a stdlib datetime bound."""

    if not isinstance(node, ast.Attribute) or node.attr not in {"min", "max"}:
        return None
    if isinstance(node.value, ast.Name) and node.value.id in bindings.class_names:
        return node.attr
    if (
        isinstance(node.value, ast.Attribute)
        and node.value.attr == "datetime"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id in bindings.module_names
    ):
        return node.attr
    return None


def _is_timezone_aware_replacement(node: ast.AST) -> bool:
    """Recognize the established ``datetime.min/max.replace(tzinfo=...)`` pattern."""

    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "replace":
        return False
    return any(
        keyword.arg == "tzinfo" and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
        for keyword in node.keywords
    )


class _NaiveSortSentinelVisitor(ast.NodeVisitor):
    def __init__(self, bindings: DateTimeBindings) -> None:
        self.bindings = bindings
        self.sentinels: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - AST visitor name
        key = self._sort_key(node)
        if key is not None:
            self._inspect_key(key)
        self.generic_visit(node)

    @staticmethod
    def _sort_key(node: ast.Call) -> ast.AST | None:
        if isinstance(node.func, ast.Name) and node.func.id == "sorted":
            return next((keyword.value for keyword in node.keywords if keyword.arg == "key"), None)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "sort":
            return next((keyword.value for keyword in node.keywords if keyword.arg == "key"), None)
        return None

    def _inspect_key(self, key: ast.AST) -> None:
        for candidate in ast.walk(key):
            sentinel = _sentinel_name(candidate, self.bindings)
            if sentinel is None:
                continue
            if self._is_inside_timezone_aware_replacement(candidate, key):
                continue
            self.sentinels.append((candidate.lineno, sentinel))

    @staticmethod
    def _is_inside_timezone_aware_replacement(sentinel: ast.AST, key: ast.AST) -> bool:
        for candidate in ast.walk(key):
            if not _is_timezone_aware_replacement(candidate):
                continue
            assert isinstance(candidate, ast.Call)
            assert isinstance(candidate.func, ast.Attribute)
            if candidate.func.value is sentinel:
                return True
        return False


def findings(source: str, relative_path: str = "<unknown>") -> list[Finding]:
    """Return direct naive datetime bounds used in an inline sort key."""

    tree = ast.parse(source, filename=relative_path)
    visitor = _NaiveSortSentinelVisitor(_datetime_bindings(tree))
    visitor.visit(tree)
    return [Finding(relative_path, line, sentinel) for line, sentinel in visitor.sentinels]


def source_files(repository_root: Path) -> list[Path]:
    source_root = repository_root / SOURCE_ROOT
    if not source_root.is_dir():
        raise RuntimeError(f"scan root not found: {source_root}")
    return sorted(
        path
        for path in source_root.rglob("*.py")
        if not any(
            directory in EXCLUDED_DIRECTORY_NAMES or directory.startswith(".")
            for directory in path.relative_to(source_root).parts
        )
    )


def collect_findings(repository_root: Path) -> list[Finding]:
    result: list[Finding] = []
    for path in source_files(repository_root):
        relative_path = path.relative_to(repository_root).as_posix()
        result.extend(findings(path.read_text(encoding="utf-8"), relative_path))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT, help="Repository root to scan.")
    parser.add_argument(
        "--print", dest="print_findings", action="store_true", help="Print findings without enforcing the baseline."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = collect_findings(args.root.resolve())
    except (OSError, SyntaxError, UnicodeDecodeError, RuntimeError) as exc:
        print(f"FAIL: datetime sort-sentinel ratchet could not run: {exc}", file=sys.stderr)
        return 2

    if args.print_findings:
        for finding in result:
            print(f"{finding.path}:{finding.line}: naive datetime.{finding.sentinel} sort sentinel")
        print(f"\nnaive datetime sort sentinels: {len(result)} (baseline {BASELINE})")
        return 0

    if len(result) > BASELINE:
        print(
            f"FAIL: naive datetime.min/max sort sentinels rose to {len(result)} (baseline {BASELINE}):",
            file=sys.stderr,
        )
        for finding in result:
            print(f"{finding.path}:{finding.line}: datetime.{finding.sentinel}", file=sys.stderr)
        print(SORT_SENTINEL_GUIDANCE, file=sys.stderr)
        return 1

    print(f"OK: naive datetime.min/max sort sentinels at baseline ({len(result)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

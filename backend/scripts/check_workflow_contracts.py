#!/usr/bin/env python3
"""Static checks for high-risk workflow contracts."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path, PurePosixPath
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
CONTRACTS_PATH = BACKEND_DIR / "testing" / "workflow_contracts.json"
CONTRACTS_REL_PATH = "backend/testing/workflow_contracts.json"


def load_contracts() -> dict[str, Any]:
    return json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))


def normalize_path(path: str) -> str:
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def path_matches(path: str, pattern: str) -> bool:
    return PurePosixPath(path).match(pattern)


def workflow_sources(
    contracts: dict[str, Any],
    changed_paths: list[str] | None = None,
    *,
    check_name: str | None = None,
) -> set[str]:
    changed = [normalize_path(path) for path in changed_paths or [] if normalize_path(path)]
    if changed and any(path_matches(path, CONTRACTS_REL_PATH) for path in changed):
        changed = []
    sources: set[str] = set()
    for workflow in contracts.get("workflows", []):
        if workflow.get("risk") != "high":
            continue
        if check_name and check_name not in (workflow.get("checks") or []):
            continue
        patterns = workflow.get("sources", [])
        if changed and not any(any(path_matches(path, pattern) for pattern in patterns) for path in changed):
            continue
        for pattern in patterns:
            if "*" in pattern:
                sources.update(
                    path.relative_to(REPO_DIR).as_posix()
                    for path in REPO_DIR.glob(pattern)
                    if path.is_file() and path.suffix == ".py"
                )
            else:
                source = REPO_DIR / pattern
                if source.is_file():
                    sources.add(pattern)
    return sources


def _tuple_arity(node: ast.AST) -> int | None:
    if not isinstance(node, ast.Subscript):
        return None
    root = ast.unparse(node.value)
    if root not in {"tuple", "Tuple"}:
        return None
    if isinstance(node.slice, ast.Tuple):
        return len(node.slice.elts)
    return 1


def check_no_large_tuple_results(contracts: dict[str, Any], changed_paths: list[str] | None = None) -> list[str]:
    allowlist = {
        (entry["path"], entry["function"])
        for entry in contracts.get("checks", {}).get("no_large_tuple_results", {}).get("allowlist", [])
    }
    errors: list[str] = []
    for rel_path in sorted(workflow_sources(contracts, changed_paths, check_name="no_large_tuple_results")):
        source_path = REPO_DIR / rel_path
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            errors.append(f"{rel_path}:{exc.lineno}: cannot parse source: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.returns is None:
                continue
            arity = _tuple_arity(node.returns)
            if arity is None or arity <= 2 or node.name.endswith("_key") or (rel_path, node.name) in allowlist:
                continue
            errors.append(
                f"{rel_path}:{node.lineno}: {node.name} returns a positional tuple with {arity} fields; "
                "use a named dataclass/model result or add a temporary allowlist entry with a migration reason"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-files", help="Only check workflow sources touched by this file list.")
    args = parser.parse_args()

    changed_paths = None
    if args.changed_files:
        changed_paths = Path(args.changed_files).read_text(encoding="utf-8").splitlines()

    contracts = load_contracts()
    errors = check_no_large_tuple_results(contracts, changed_paths)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("Workflow contract checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

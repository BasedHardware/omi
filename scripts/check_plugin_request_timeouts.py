#!/usr/bin/env python3
"""Fail plugin requests calls that carry no timeout; stdlib only."""

import argparse
import ast
import pathlib
import sys

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "request", "head"}


def session_names(tree: ast.Module) -> set:
    names = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "Session"
            and isinstance(func.value, ast.Name)
            and func.value.id == "requests"
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def unbounded_calls(path: pathlib.Path):
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []

    sessions = session_names(tree)
    async_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    async_lines.add(inner.lineno)

    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in HTTP_METHODS:
            continue
        base = node.func.value
        is_requests = (
            (isinstance(base, ast.Name) and base.id == "requests")
            or (isinstance(base, ast.Attribute) and base.attr == "requests")
            or (isinstance(base, ast.Name) and base.id in sessions)
        )
        if not is_requests:
            continue
        if any(keyword.arg == "timeout" for keyword in node.keywords):
            continue
        found.append((node.lineno, node.func.attr, node.lineno in async_lines))
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="plugins")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    if args.files:
        paths = [pathlib.Path(f) for f in args.files if f.endswith(".py")]
    else:
        paths = sorted(pathlib.Path(args.root).rglob("*.py"))

    failures = []
    for path in paths:
        if not path.exists() or not str(path).startswith("plugins/"):
            continue
        name = path.name
        if name.startswith("test_") or name.endswith("_test.py") or "/tests/" in str(path):
            continue
        for lineno, method, on_loop in unbounded_calls(path):
            failures.append((path, lineno, method, on_loop))

    if failures:
        print(f"{len(failures)} requests call(s) without a timeout:", file=sys.stderr)
        for path, lineno, method, on_loop in failures:
            where = " (inside async def, blocks the event loop)" if on_loop else ""
            print(f"  {path}:{lineno} requests.{method}(){where}", file=sys.stderr)
        print("Pass timeout=<seconds> or timeout=(connect, read) to every call.", file=sys.stderr)
        return 1

    print(f"plugin request timeouts: {len(paths)} file(s) checked, no unbounded calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

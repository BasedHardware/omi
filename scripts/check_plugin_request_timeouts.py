#!/usr/bin/env python3
"""Fail when a ``requests`` call under plugins/ has no explicit ``timeout``.

``requests`` applies no default timeout, so an upstream that accepts a TCP
connection and then stops answering keeps the caller blocked forever — and a
blocking call made inside an ``async def`` handler stalls the whole event loop
for every route on that worker.

This guard is the reusable version of three earlier one-off fixes (#14278,
#14255, #14257). It scans every ``*.py`` file under ``plugins/`` with the
stdlib ``ast`` module and fails the build if any ``requests.<verb>()`` or
``requests.Session().<verb>()`` call omits the ``timeout`` keyword.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

METHODS = {"get", "post", "put", "delete", "patch", "request", "head", "options"}


def _method_of(func: ast.expr):
    """Return the HTTP verb if ``func`` is a requests call, else ``None``."""
    if not isinstance(func, ast.Attribute):
        return None
    # requests.get(...) / requests.post(...) / ...
    if isinstance(func.value, ast.Name) and func.value.id == "requests":
        return func.attr
    # requests.Session().get(...) / requests.session().post(...) / ...
    if func.attr in METHODS and isinstance(func.value, ast.Call):
        inner = func.value.func
        if (
            isinstance(inner, ast.Attribute)
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "requests"
            and inner.attr in ("Session", "session")
        ):
            return func.attr
    return None


def scan_source(source: str):
    """Yield ``(lineno, method)`` for every requests call lacking a timeout."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        method = _method_of(node.func)
        if method not in METHODS:
            continue
        has_timeout = any(
            isinstance(kw.arg, str) and kw.arg == "timeout" for kw in node.keywords
        )
        if not has_timeout:
            yield node.lineno, method


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(pathlib.Path(__file__).resolve().parents[1]),
        help="repository root (defaults to the parent of scripts/)",
    )
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root)
    plugins = root / "plugins"
    if not plugins.is_dir():
        print(f"check_plugin_request_timeouts: {plugins} not found", file=sys.stderr)
        return 1

    violations = []
    for path in sorted(plugins.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for lineno, method in scan_source(source):
            rel = path.relative_to(root)
            violations.append(f"{rel}:{lineno}: requests.{method}(...) missing timeout")

    if violations:
        for line in violations:
            print(line)
        print(
            f"check_plugin_request_timeouts: {len(violations)} requests call(s) "
            "under plugins/ missing an explicit timeout",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

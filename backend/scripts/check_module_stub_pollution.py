#!/usr/bin/env python3
"""Tier-2 hard gate: ban module-scope ``sys.modules`` mutation in backend tests.

WHY: a single pytest process across all backend unit files fails during collection
because ~100 test files mutate ``sys.modules`` at module scope to paper over
import-time side effects in production code. That mutation is a *symptom*; the
*disease* is production import-time side effects (see
``backend/docs/test_isolation.md``). This checker enforces the test-side discipline
while the production-side cause is fixed incrementally.

WHAT IT DETECTS (at module scope only — fixtures/functions are untouched):
  - ``sys.modules[x] = ...``        (Assign, Subscript target on sys.modules)
  - ``del sys.modules[x]``          (Delete, Subscript target on sys.modules)
  - ``sys.modules.pop(...)``        (Expr/Assign wrapping such a call)
  - ``sys.modules.update(...)``
  - ``sys.modules.setdefault(...)``
  - ``sys.modules.clear()``
  - ``sys.modules.__setitem__(...)``
  - ``sys.modules.popitem(...)``

ALLOWLIST:
  - ``conftest.py`` is always exempt (it is the sanctioned home for session-level
    optional-dependency stubs).
  - The sanctioned reserve helper(s) under ``backend/testing/`` are exempt.
  - A deprecated legacy allowlist (``backend/tests/.module_stub_legacy_allowlist``)
    carries existing offenders during the migration. Its only permitted change is
    to *shrink*; ``--check-allowlist-monotonic <base>`` fails if it grew.

USAGE:
  # full tree (CI authoritative):
  python backend/scripts/check_module_stub_pollution.py
  # changed-files scope (pre-push fast path):
  python backend/scripts/check_module_stub_pollution.py --files <file-list>
  # enforce monotone-shrinking allowlist:
  python backend/scripts/check_module_stub_pollution.py --check-allowlist-monotonic main

Exit 1 on any unallowlisted offender or any allowlist growth. See
``.coordination/test-isolation/PLAN.md`` for the spirit and ``DECISIONS.md`` (D4/D7)
for rationale.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterator
from typing import Any, List, cast
from pathlib import Path

MUTATING_ATTRS = frozenset({"pop", "update", "setdefault", "clear", "__setitem__", "popitem"})

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_ALLOWLIST = BACKEND_DIR / "tests" / ".module_stub_legacy_allowlist"
SANCTIONED_HELPERS = {
    "backend/testing/import_isolation.py",
}


def _is_sys_modules(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "modules"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    )


def _iter_module_level_stmts(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield every statement that executes at module (import) scope.

    Descends into module-level compound statements (``if``/``for``/``while``/
    ``try``/``with``/``match``) including their ``orelse``/``handlers``/``finalbody``
    bodies, because those branches run during import. Class bodies also execute at
    import time, so they are descended into. Stops at function definitions — their
    bodies are not module scope.
    """
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        yield node
        for field in ("body", "orelse", "finalbody"):
            inner = getattr(node, field, None)
            if isinstance(inner, list):
                yield from _iter_module_level_stmts(cast(List[ast.stmt], inner))
        handlers = getattr(node, "handlers", None)
        if isinstance(handlers, list):
            for handler in cast(List[Any], handlers):
                hbody = getattr(handler, "body", None)
                if isinstance(hbody, list):
                    yield from _iter_module_level_stmts(cast(List[ast.stmt], hbody))
        cases = getattr(node, "cases", None)  # ast.Match (3.10+)
        if isinstance(cases, list):
            for case in cast(List[Any], cases):
                cbody = getattr(case, "body", None)
                if isinstance(cbody, list):
                    yield from _iter_module_level_stmts(cast(List[ast.stmt], cbody))


def _check_sys_modules_write(node: ast.stmt) -> int | None:
    """Return lineno if ``node`` performs a module-scope ``sys.modules`` write, else None.

    Handles Assign / AnnAssign / Delete with ``sys.modules[...]`` targets, and bare
    or assigned calls to ``sys.modules.pop/update/setdefault/clear/__setitem__/popitem``.
    """
    # sys.modules[x] = ...  (plain and annotated assignments)
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Subscript) and _is_sys_modules(target.value):
                return node.lineno
        if isinstance(node, ast.Assign):
            # x = sys.modules.setdefault(...) / .pop(...) etc.
            if isinstance(node.value, ast.Call) and _is_call_on_sys_modules(node.value):
                return node.lineno
        return None
    # del sys.modules[x]
    if isinstance(node, ast.Delete):
        for target in node.targets:
            if isinstance(target, ast.Subscript) and _is_sys_modules(target.value):
                return node.lineno
        return None
    # bare call statement: sys.modules.pop(...) / .update(...) etc.
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        if _is_call_on_sys_modules(node.value):
            return node.lineno
    return None


def _module_level_offenders(tree: ast.Module) -> list[int]:
    """Return line numbers of module-scope ``sys.modules`` mutations.

    Walks all module-scope statements (including those nested inside top-level
    ``if``/``for``/``try``/``with`` blocks, which also run at import time) while
    skipping function/class bodies.
    """
    lines: list[int] = []
    for node in _iter_module_level_stmts(tree.body):
        lineno = _check_sys_modules_write(node)
        if lineno is not None:
            lines.append(lineno)
    return lines


def _is_call_on_sys_modules(call: ast.Call) -> bool:
    f = call.func
    return isinstance(f, ast.Attribute) and f.attr in MUTATING_ATTRS and _is_sys_modules(f.value)


def _load_allowlist(path: Path) -> set[str]:
    if not path.exists():
        return set()
    entries: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line)
    return entries


def _is_exempt(rel_path: str) -> bool:
    if rel_path.endswith("conftest.py"):
        return True
    if rel_path in SANCTIONED_HELPERS:
        return True
    return False


def _candidate_files(root: Path) -> list[Path]:
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return []
    return sorted(tests_dir.rglob("*.py"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(BACKEND_DIR), help="backend root (default: backend/)")
    parser.add_argument("--files", help="path to a file listing repo-relative paths to check (changed-files mode)")
    parser.add_argument("--allowlist", default=str(DEFAULT_ALLOWLIST), help="legacy allowlist file")
    parser.add_argument(
        "--check-allowlist-monotonic",
        metavar="BASE_REF",
        help="fail if the allowlist grew relative to BASE_REF (monotone-shrinking ratchet)",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    allowlist_path = Path(args.allowlist).resolve()
    allowlist = _load_allowlist(allowlist_path)

    # Monotone-allowlist check (independent of file scan).
    if args.check_allowlist_monotonic:
        base = args.check_allowlist_monotonic
        rc = _check_monotonic(allowlist_path, base)
        if rc != 0:
            return rc

    # Determine files to scan.
    if args.files:
        listed = Path(args.files).read_text(encoding="utf-8").splitlines()
        files: list[Path] = []
        for raw in listed:
            raw = raw.strip()
            if not raw:
                continue
            # repo-relative -> absolute
            p = REPO_ROOT / raw
            if p.suffix == ".py" and p.exists():
                files.append(p)
    else:
        files = _candidate_files(root)

    violations: list[str] = []
    checked = 0
    for path in files:
        try:
            rel = path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            continue
        # Only police files under backend/tests.
        if not rel.startswith("backend/tests/"):
            continue
        if _is_exempt(rel):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{rel}: SYNTAX ERROR {exc}")
            continue
        offending_lines = _module_level_offenders(tree)
        if offending_lines and rel not in allowlist:
            joined = ", ".join(f"L{n}" for n in offending_lines)
            violations.append(f"{rel}: module-scope sys.modules mutation at {joined}")

        checked += 1

    if not args.quiet:
        print(f"Checked {checked} backend test file(s); {len(violations)} violation(s).")

    if violations:
        print("\nModule-scope sys.modules mutation is banned in backend tests.", file=sys.stderr)
        print("Fix the production import-time side effect (Tier 1) or use", file=sys.stderr)
        print("monkeypatch.setattr / FastAPI dependency_overrides (Tier 2).", file=sys.stderr)
        print("See backend/docs/test_isolation.md.\n", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    return 0


def _check_monotonic(allowlist_path: Path, base_ref: str) -> int:
    """Fail if the allowlist has entries not present at BASE_REF (i.e. it grew).

    Creating the file fresh (it did not exist at BASE_REF) is allowed — that is
    seeding, not growth.
    """
    import subprocess

    rel = allowlist_path.relative_to(REPO_ROOT).as_posix()
    exists_at_base = (
        subprocess.run(
            ["git", "cat-file", "-e", f"{base_ref}:{rel}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    if not exists_at_base:
        return 0  # creation, not growth

    out = subprocess.run(
        ["git", "show", f"{base_ref}:{rel}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    base_entries = {
        line.strip() for line in out.stdout.splitlines() if line.strip() and not line.strip().startswith("#")
    }
    current = _load_allowlist(allowlist_path)
    added = current - base_entries
    if added:
        print(
            f"FAIL: module-stub legacy allowlist grew relative to {base_ref} ({len(added)} new entry/entries):",
            file=sys.stderr,
        )
        for e in sorted(added):
            print(f"  + {e}", file=sys.stderr)
        print("The allowlist may only shrink. See .coordination/test-isolation/PLAN.md (P4).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

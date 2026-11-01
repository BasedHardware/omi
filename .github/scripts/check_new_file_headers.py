#!/usr/bin/env python3
"""Require a purpose header on NEW first-party source files.

A new file is one that does not exist at the base ref. Scopes: ``backend/``
(``.py``), ``app/lib/`` (``.dart``), ``desktop/macos/Desktop/Sources/``
(``.swift``) and ``desktop/macos/agent/src/`` (``.ts``; the only non-.ts file
there is a patched vendored ACP entry, not first-party source).

Thresholds, and why they hold:

- Python: the first statement must be a module docstring -- that is the only
  position a reader (and tooling) treats as the file's purpose.
- Dart/Swift/TS: at least MIN_HEADER_COMMENT_LINES comment lines before the
  first non-import code line. One line is a marker (``// MARK:``, ``// TODO:``,
  a stray ``///``), not an ownership statement; both repo conventions --
  a leading ``//`` block above the imports and a ``///``/``/* */`` block right
  after them -- satisfy this.
- Files under MIN_FILE_LINES are exempt: they are single small extensions or
  constant sets whose name states their purpose. The headerless hot files this
  check guards against run hundreds of lines.

Excluded: tests (executable specs describe their subject), generated files
(never hand-edited), ``__init__.py`` (package markers own nothing).

Instance: #14527 merged the 231-line headerless
``app/lib/backend/http/api_result.dart`` -- the C3 typed-result contract at
the heart of the app's HTTP layer -- with no statement of what it owns; every
substantial new file should say what it owns where the next reader looks first.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

MIN_HEADER_COMMENT_LINES = 2
MIN_FILE_LINES = 40

SCOPES = (
    ("backend/", (".py",)),
    ("app/lib/", (".dart",)),
    ("desktop/macos/Desktop/Sources/", (".swift",)),
    ("desktop/macos/agent/src/", (".ts",)),
)

GENERATED_SUFFIXES = (".g.dart", ".gen.dart", ".freezed.dart", ".g.swift", ".generated.swift")
GENERATED_PARTS = ("/gen/", "/l10n/", "/Generated/")
TEST_DIR_NAMES = {"test", "tests", "testing", "__tests__"}
TEST_BASENAMES = re.compile(r"^(test_.*|.*_test)\.(py|dart|ts)$|^.*Tests?\.swift$")

# Structural lines a purpose header may sit above or between. Dart string-literal
# exports (`export 'x';`) are library plumbing; TS `export const/function/...`
# stays real code and stops the scan.
IMPORT_LIKE = re.compile(
    r"^(?:@[A-Za-z]+\s+)?import\b|^export\s+['\"]|^part(?:\s+of)?\b|^#(?:if|else|elif|endif)\b|^#!"
)


def clean_git_env() -> dict[str, str]:
    # Drop the entire Git namespace: a check invoked from a hook must operate on
    # the explicit --root repo, never on inherited GIT_DIR/GIT_INDEX_FILE state.
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def is_test_path(relative: str) -> bool:
    parts = relative.replace("\\", "/").split("/")
    if any(part in TEST_DIR_NAMES for part in parts[:-1]):
        return True
    return bool(TEST_BASENAMES.match(parts[-1]))


def is_generated_path(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    return normalized.endswith(GENERATED_SUFFIXES) or any(part in normalized for part in GENERATED_PARTS)


def scope_for(relative: str) -> str | None:
    normalized = relative.replace("\\", "/")
    for prefix, extensions in SCOPES:
        if normalized.startswith(prefix) and normalized.endswith(extensions):
            return prefix
    return None


def python_has_header(text: str) -> tuple[bool, str | None]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return False, f"cannot parse new Python file: {exc}"
    first = tree.body[0] if tree.body else None
    documented = (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )
    return documented, None


def comment_lang_has_header(text: str) -> bool:
    run = 0
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#!"):
            continue
        if stripped.startswith(("//", "/*", "*", "*/")):
            run += 1
            if run >= MIN_HEADER_COMMENT_LINES:
                return True
            continue
        if IMPORT_LIKE.match(stripped):
            run = 0
            continue
        return False
    return False


def has_header(path: Path) -> tuple[bool, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False, "must be UTF-8 text to carry a header"
    lines = text.splitlines()
    if len(lines) < MIN_FILE_LINES:
        return True, None
    if path.suffix == ".py":
        return python_has_header(text)
    return comment_lang_has_header(text), None


def file_exists_at_base(root: Path, base: str, relative: str) -> bool:
    result = subprocess.run(
        ["git", "show", f"{base}:{relative}"],
        cwd=root,
        capture_output=True,
        text=True,
        env=clean_git_env(),
    )
    return result.returncode == 0


def validate(root: Path, changed_paths: list[str], base: str) -> list[str]:
    failures: list[str] = []
    for relative in changed_paths:
        normalized = relative.replace("\\", "/").strip()
        if not normalized or scope_for(normalized) is None:
            continue
        if normalized.endswith("/__init__.py") or normalized == "__init__.py":
            continue
        if is_test_path(normalized) or is_generated_path(normalized):
            continue
        path = root / normalized
        if not path.is_file():
            continue
        if file_exists_at_base(root, base, normalized):
            continue
        documented, error = has_header(path)
        if error:
            failures.append(f"{normalized}: {error}")
        elif not documented:
            failures.append(
                f"{normalized}: new first-party source file lacks a purpose header "
                "(Python: module docstring as the first statement; Dart/Swift/TS: "
                f">={MIN_HEADER_COMMENT_LINES} comment lines before the first non-import code)"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-files", required=True, help="File listing changed repository-relative paths.")
    parser.add_argument("--base", required=True, help="Base ref the diff is taken against.")
    parser.add_argument("--root", default=".", help="Repository root.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    changed_file = Path(args.changed_files)
    if not changed_file.is_absolute():
        changed_file = root / changed_file
    try:
        changed_paths = [line for line in changed_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        print(f"FAIL: could not read changed-files input: {exc}")
        return 1

    failures = validate(root, changed_paths, args.base)
    if failures:
        print("FAIL: new first-party source files must carry a purpose header")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("OK: every new first-party source file carries a purpose header")
    return 0


if __name__ == "__main__":
    sys.exit(main())

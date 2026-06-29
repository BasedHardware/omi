#!/usr/bin/env python3
"""Advisory architecture guardrails for changed files.

Warns on large changed files and long functions, then exits 0. This script is
intentionally stdlib-only so it can run early in CI without setup steps.
"""

import argparse
import ast
import os
import re
from pathlib import Path


SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".dart",
    ".h",
    ".hpp",
    ".js",
    ".jsx",
    ".kt",
    ".m",
    ".mm",
    ".py",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
SKIP_SUFFIXES = (
    ".gen.dart",
    ".g.dart",
    ".lock",
    ".min.js",
)
SKIP_PARTS = {
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
}
BRACE_FUNCTION_RE = re.compile(
    r"""
    ^\s*
    (?:
      (?:public|private|internal|fileprivate|open|static|async|export|default|mutating|override|final|inline)\s+
    )*
    (?:
      func\s+\w+|
      function\s+\w+|
      async\s+function\s+\w+|
      fn\s+\w+|
      [A-Za-z_][\w:<>\[\]\?&\*\s]+\s+[A-Za-z_]\w*\s*\([^;]*\)
    )
    [^{;]*\{
    """,
    re.VERBOSE,
)


def source_file(path):
    if path.suffix not in SOURCE_EXTENSIONS:
        return False
    if path.name.endswith(SKIP_SUFFIXES):
        return False
    return not any(part in SKIP_PARTS for part in path.parts)


def annotation_escape(value):
    return str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def emit_warning(path, line, title, message):
    print(
        f"::warning file={annotation_escape(path)},line={line},title={annotation_escape(title)}::"
        f"{annotation_escape(message)}"
    )


def read_changed_files(path):
    changed = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            raw_path = raw_line.strip()
            if raw_path:
                changed.append(Path(raw_path))
    return changed


def python_functions(path, source):
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    functions = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end_line = getattr(node, "end_lineno", node.lineno)
        functions.append((node.name, node.lineno, end_line, end_line - node.lineno + 1))
    return functions


def brace_functions(path, lines):
    functions = []
    in_function = None
    brace_depth = 0

    for index, line in enumerate(lines, start=1):
        if in_function is None:
            if not BRACE_FUNCTION_RE.search(line):
                continue
            in_function = {
                "name": line.strip().split("{", 1)[0].strip()[:80] or path.name,
                "line": index,
            }
            brace_depth = line.count("{") - line.count("}")
            if brace_depth <= 0:
                functions.append((in_function["name"], index, index, 1))
                in_function = None
            continue

        brace_depth += line.count("{") - line.count("}")
        if brace_depth <= 0:
            start = in_function["line"]
            functions.append((in_function["name"], start, index, index - start + 1))
            in_function = None

    return functions


def long_functions(path, source, line_threshold):
    if path.suffix == ".py":
        functions = python_functions(path, source)
    else:
        functions = brace_functions(path, source.splitlines())
    return [item for item in functions if item[3] > line_threshold]


def write_summary(warnings, file_threshold, function_threshold):
    lines = [
        "## Architecture guardrails",
        "",
        f"Advisory thresholds: files over {file_threshold} lines, functions over {function_threshold} lines.",
        "",
    ]
    if not warnings:
        lines.append("No advisory architecture warnings for changed files.")
    else:
        lines.append("| Type | Location | Detail |")
        lines.append("| --- | --- | --- |")
        for warning in warnings:
            lines.append(f"| {warning['type']} | {warning['location']} | {warning['detail']} |")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
            handle.write("\n")
    else:
        print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Warn on large changed files and long functions")
    parser.add_argument("--changed-files", default="/tmp/changed-files.txt", type=Path)
    parser.add_argument("--file-lines", default=800, type=int)
    parser.add_argument("--function-lines", default=150, type=int)
    args = parser.parse_args()

    warnings = []
    if not args.changed_files.exists():
        write_summary(warnings, args.file_lines, args.function_lines)
        return 0

    for path in read_changed_files(args.changed_files):
        if not path.exists() or not path.is_file() or not source_file(path):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        line_count = source.count("\n") + (0 if source.endswith("\n") or not source else 1)
        if line_count > args.file_lines:
            message = f"{path} is {line_count} lines; consider splitting files over {args.file_lines} lines."
            emit_warning(path, 1, "Large changed file", message)
            warnings.append({"type": "File size", "location": f"{path}:1", "detail": f"{line_count} lines"})

        for name, start, _end, length in long_functions(path, source, args.function_lines):
            message = (
                f"{name} is {length} lines; consider extracting focused helpers over " f"{args.function_lines} lines."
            )
            emit_warning(path, start, "Long function", message)
            warnings.append({"type": "Function length", "location": f"{path}:{start}", "detail": message})

    write_summary(warnings, args.file_lines, args.function_lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

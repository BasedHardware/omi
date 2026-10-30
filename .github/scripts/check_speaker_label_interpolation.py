#!/usr/bin/env python3
"""Ratchet raw speaker interpolation after #23379 and the Speaker 379 live-notes incident.

Existing storage/routing expressions are compared by AST fingerprint, not a count:
removing one old expression never buys permission to introduce a different leak.
Display text must use utils.speakers.display / SpeakerNames. Wire fields remain IDs.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from pathlib import Path
import re
import subprocess
import sys

AUTHORITY = {
    'backend/utils/speaker_display.py',
    'backend/utils/speakers/display.py',
    'app/lib/ui/format/speaker_names.dart',
    'app/lib/ui/format/diarization_label.dart',
}
RAW = re.compile(r'(?i)(?:\b(?:raw_)?speaker_?id\b|\bdiarization_?label\b|raw_for_transport|rawForTransport)')


def findings(path: str, source: str) -> list[tuple[str, int]]:
    if path in AUTHORITY or '/tests/' in path or '/test/' in path:
        return []
    if path.startswith('backend/') and path.endswith('.py'):
        tree = ast.parse(source)
        hits = []
        tainted = set()

        def is_raw(expression):
            return bool(RAW.search(ast.unparse(expression))) or any(
                isinstance(part, ast.Name)
                and part.id in tainted
                or isinstance(part, ast.Attribute)
                and part.attr in ('speaker', 'speaker_id', 'speakerId')
                for part in ast.walk(expression)
            )

        # Local aliases do not turn storage identity into safe display text.
        for _ in range(3):
            for assignment in ast.walk(tree):
                if (
                    isinstance(assignment, (ast.Assign, ast.AnnAssign))
                    and assignment.value is not None
                    and is_raw(assignment.value)
                ):
                    targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
                    for target in targets:
                        tainted.update(part.id for part in ast.walk(target) if isinstance(part, ast.Name))
        for node in ast.walk(tree):
            if (isinstance(node, ast.ImportFrom) and node.module == 'utils.speaker_display') or (
                isinstance(node, ast.Import) and any(alias.name == 'utils.speaker_display' for alias in node.names)
            ):
                hits.append((ast.dump(node, include_attributes=False), node.lineno))
            expressions = []
            speaker_template = False
            if isinstance(node, ast.JoinedStr):
                expressions = [v.value for v in node.values if isinstance(v, ast.FormattedValue)]
                speaker_template = any(
                    isinstance(left, ast.Constant)
                    and isinstance(left.value, str)
                    and re.search(r'(?<![_A-Za-z])Speaker[ \t]*$', left.value)
                    and isinstance(right, ast.FormattedValue)
                    for left, right in zip(node.values, node.values[1:])
                )
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'format':
                expressions = list(node.args) + [kw.value for kw in node.keywords]
                speaker_template = (
                    isinstance(node.func.value, ast.Constant)
                    and isinstance(node.func.value.value, str)
                    and bool(re.search(r'(?<![_A-Za-z])Speaker[ \t]*\{', node.func.value.value))
                )
            elif (
                isinstance(node, ast.BinOp)
                and isinstance(node.op, ast.Mod)
                and isinstance(node.left, ast.Constant)
                and isinstance(node.left.value, str)
            ):
                expressions = [node.right]
                speaker_template = bool(re.search(r'(?<![_A-Za-z])Speaker[ \t]*%', node.left.value))
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                for literal, dynamic in ((node.left, node.right), (node.right, node.left)):
                    if (
                        isinstance(literal, ast.Constant)
                        and isinstance(literal.value, str)
                        and re.search(r'(?<![_A-Za-z])Speaker[ \t]*$', literal.value)
                    ):
                        expressions = [dynamic]
                        speaker_template = True
            if not expressions:
                continue
            rendered = ast.unparse(node)
            # Generic aliases are caught when the template itself says Speaker/SPEAKER.
            raw = any(is_raw(expr) for expr in expressions)
            template = (
                node.func.value if isinstance(node, ast.Call) else node.left if isinstance(node, ast.BinOp) else None
            )
            if isinstance(template, ast.Constant) and isinstance(template.value, str):
                raw = raw or bool(re.search(r'(?:\{|%\()(?:raw_)?speaker_?id\b', template.value, re.I))
            alias = re.search(r'[Ss][Pp][Ee][Aa][Kk][Ee][Rr][ _]', rendered) and any(
                re.search(r'\b(?:sid|speaker|speaker_key|speaker_idx)\b', ast.unparse(expr)) for expr in expressions
            )
            if raw or alias or speaker_template:
                hits.append((ast.dump(node, include_attributes=False), node.lineno))
        return hits
    if path.startswith('app/lib/') and path.endswith('.dart') and '/gen/' not in path and '/l10n/' not in path:
        return [
            (match.group(), source.count('\n', 0, match.start()) + 1)
            for match in re.finditer(
                r'''(?:['"][^'"\n]*\$(?:\{[^}\n]*(?:speakerId|rawForTransport)[^}\n]*\}|speakerId\b)[^'"\n]*['"])''',
                source,
            )
        ]
    return []


def regressions(path: str, before: str, after: str) -> list[int]:
    old = Counter(fingerprint for fingerprint, _ in findings(path, before))
    lines = []
    for fingerprint, line in findings(path, after):
        if old[fingerprint]:
            old[fingerprint] -= 1
        else:
            lines.append(line)
    return lines


def _main_ratchet(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--changed-files', required=True)
    parser.add_argument('--base', required=True)
    args = parser.parse_args(argv)
    failures = []
    for path in Path(args.changed_files).read_text().splitlines():
        file = Path(path)
        if not file.is_file() or not (path.endswith('.py') or path.endswith('.dart')):
            continue
        result = subprocess.run(['git', 'show', f'{args.base}:{path}'], text=True, capture_output=True)
        failures.extend(
            f'{path}:{line}: raw speaker interpolation; use display_participants / SpeakerNames'
            for line in regressions(path, result.stdout if result.returncode == 0 else '', file.read_text())
        )
    print('\n'.join(failures) if failures else 'OK: no new raw speaker interpolation')
    return int(bool(failures))



REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOT = Path('backend')
# Tool environments under backend/ (the venv, the OpenAPI runner's venv, ...) are
# not repository source: they contain third-party code that need not even parse.
EXCLUDED_DIRS = {'tests', 'testing', 'node_modules', 'site-packages'}
ALLOWED_FILES = {'backend/utils/speaker_display.py'}
_DYNAMIC_NODES = (ast.Name, ast.Call, ast.Attribute, ast.Subscript, ast.BinOp, ast.IfExp, ast.JoinedStr)
_SPEAKER_SUFFIX = re.compile(r'(?<![_A-Za-z])Speaker[ \t]*$')
_FORMAT_TEMPLATE = re.compile(r'(?<![_A-Za-z])Speaker[ \t]*\{')
_PERCENT_TEMPLATE = re.compile(r'(?<![_A-Za-z])Speaker[ \t]*%')


def _violation(node: ast.AST, detail: str) -> str:
    return f'{node.lineno}:{node.col_offset} {detail}'


def _check_joined_string(node: ast.JoinedStr) -> list[str]:
    """A constant chunk ending in the word ``Speaker`` directly before a dynamic value."""
    errors = []
    values = node.values
    for index, (chunk, following) in enumerate(zip(values, values[1:])):
        if not isinstance(chunk, ast.Constant) or not isinstance(chunk.value, str):
            continue
        if isinstance(following, ast.FormattedValue) and _SPEAKER_SUFFIX.search(chunk.value):
            errors.append(_violation(node, f'f-string interpolates a value into "Speaker {chunk.value.strip()}"'))
    return errors


def _check_concatenation(node: ast.BinOp) -> list[str]:
    if not isinstance(node.op, ast.Add):
        return []
    for literal, dynamic in ((node.left, node.right), (node.right, node.left)):
        if (
            isinstance(literal, ast.Constant)
            and isinstance(literal.value, str)
            and _SPEAKER_SUFFIX.search(literal.value)
            and isinstance(dynamic, _DYNAMIC_NODES)
        ):
            return [
                _violation(node, f'string concatenation appends a dynamic value to "Speaker {literal.value.strip()}"')
            ]
    return []


def _check_percent(node: ast.BinOp) -> list[str]:
    if not isinstance(node.op, ast.Mod) or not isinstance(node.left, ast.Constant):
        return []
    template = node.left.value
    if isinstance(template, str) and _PERCENT_TEMPLATE.search(template):
        return [_violation(node, f'"%" template interpolates a value into a Speaker label: {template!r}')]
    return []


def _check_format_call(node: ast.Call) -> list[str]:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != 'format':
        return []
    receiver = func.value
    if isinstance(receiver, ast.Constant) and isinstance(receiver.value, str):
        template = receiver.value
        if _FORMAT_TEMPLATE.search(template):
            return [_violation(node, f'.format() template interpolates a value into a Speaker label: {template!r}')]
    return []


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.errors: list[str] = []

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self.errors.extend(_check_joined_string(node))
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        self.errors.extend(_check_concatenation(node))
        self.errors.extend(_check_percent(node))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self.errors.extend(_check_format_call(node))
        self.generic_visit(node)


def check_source(source: str, filename: str = '<unknown>') -> list[str]:
    visitor = _Visitor()
    visitor.visit(ast.parse(source, filename=filename))
    return visitor.errors


def _is_excluded(parts: tuple[str, ...]) -> bool:
    return any(part in EXCLUDED_DIRS or part.endswith('venv') for part in parts[1:])


def collect_violations(repository_root: Path, scan_root: Path) -> dict[str, list[str]]:
    violations = {}
    for path in sorted((repository_root / scan_root).rglob('*.py')):
        relative = path.relative_to(repository_root).as_posix()
        if _is_excluded(Path(relative).parts):
            continue
        if relative in ALLOWED_FILES:
            continue
        errors = check_source(path.read_text(encoding='utf-8'), relative)
        if errors:
            violations[relative] = errors
    return violations


def _self_test() -> int:
    caught = check_source('label = f"Speaker {seg.speaker_id}: {text}"')
    assert caught, 'f-string interpolation must be caught'
    assert check_source('label = "Speaker " + str(sid)')
    assert check_source("label = 'Speaker %d' % sid")
    assert check_source("label = 'Speaker {}'.format(sid)")
    assert check_source("label = 'Speaker {sid}:'.format(sid=sid)")
    assert check_source('parts = ["Speaker " + name]')
    # Adjacent-but-not-label uses stay legal.
    assert not check_source('log.warning(f"Speaker assignment failed: {e}")')
    assert not check_source('log.warning(f"Speaker cap ({n}) reached; merging into SPEAKER_{best}")')
    assert not check_source('label = "Speaker A"')
    assert not check_source('prompt = "never write Speaker 2 in the people field"')
    print('self-test passed')
    return 0


def _main_fullscan(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPOSITORY_ROOT)
    parser.add_argument('--scan-root', type=Path, default=SCAN_ROOT)
    parser.add_argument('--self-test', action='store_true', help='run embedded fixtures and exit')
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    violations = collect_violations(args.root.resolve(), args.scan_root)
    if not violations:
        return 0
    print('FAIL: "Speaker" labels must not interpolate a raw id; use utils.speakers.display.display_participants:', file=sys.stderr)
    for path, errors in sorted(violations.items()):
        for error in errors:
            print(f'  {path}:{error}', file=sys.stderr)
    return 1



def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if '--changed-files' in arguments or '--base' in arguments:
        return _main_ratchet(arguments)
    return _main_fullscan(arguments)


if __name__ == '__main__':
    raise SystemExit(main())

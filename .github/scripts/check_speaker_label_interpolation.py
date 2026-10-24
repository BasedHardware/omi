#!/usr/bin/env python3
"""Reject interpolated ``Speaker {speaker_id}`` display labels in backend source.

A ``speaker_id`` is a per-conversation diarization counter, not a person. When a
formatter interpolates it into a ``Speaker N`` label, summarizer models copy the
label verbatim into user-visible notes (#23381). Unnamed voices must be labeled
through ``backend/utils/speaker_display.SpeakerLabeler`` (dense "Speaker A/B/..."
per rendered transcript), which is the only allowlisted builder of ``Speaker ``
labels.

The check is AST-based and zero-tolerance outside that allowlist: f-strings,
``str.format`` templates, ``%`` templates, and concatenation all count when a
constant chunk ends with the word ``Speaker`` right before a dynamic value. Log
messages that merely mention a speaker ("Speaker assignment failed: ...") do not
match, and the provider-internal ``SPEAKER_00`` namespace is a different string.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

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


def main(argv: list[str] | None = None) -> int:
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
    print('FAIL: "Speaker" labels must not interpolate a raw id; use utils.speaker_display.SpeakerLabeler:', file=sys.stderr)
    for path, errors in sorted(violations.items()):
        for error in errors:
            print(f'  {path}:{error}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

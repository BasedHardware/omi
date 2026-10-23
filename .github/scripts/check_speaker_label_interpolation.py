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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--changed-files', required=True)
    parser.add_argument('--base', required=True)
    args = parser.parse_args()
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


if __name__ == '__main__':
    raise SystemExit(main())

"""Static tripwire for the exclusive conversation lifecycle writer (#9687).

This is intentionally a static checker, not behavioral coverage. Its job is to
prevent a future router or processor from reviving a second lifecycle mutation
path after the service migration. Behavioral ordering remains covered by the
lifecycle contracts and finalization fuzzer.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = ('backend/database', 'backend/routers', 'backend/services', 'backend/utils')
LIFECYCLE_SERVICE = 'backend/utils/conversations/lifecycle.py'
RAW_STORAGE_ALLOWLIST = {
    'backend/database/conversations.py',
    'backend/database/conversation_finalization_jobs.py',
}
LIFECYCLE_METHODS = {
    '_upsert_conversation_with_lifecycle',
    '_create_conversation_if_absent_with_lifecycle',
    '_transition_conversation_status',
    '_claim_conversation_status',
    '_set_conversation_as_discarded',
}
FINALIZATION_ADMISSION_METHODS = {
    'create_or_get_finalization_intent',
    'resume_blocked_byok_job_for_live_session',
}
LIFECYCLE_FIELDS = {
    'status',
    'discarded',
    'finalization_job_id',
    'finalization_revision',
    'finalization_status',
}


def _literal_lifecycle_fields(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.Dict):
        return set()
    fields: set[str] = set()
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value in LIFECYCLE_FIELDS:
            fields.add(key.value)
    return fields


class _LifecycleWriteVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.errors: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - AST visitor name
        function = node.func
        if isinstance(function, ast.Attribute) and function.attr in LIFECYCLE_METHODS:
            if self.relative_path != LIFECYCLE_SERVICE:
                self.errors.append(
                    f'{self.relative_path}:{node.lineno}: direct lifecycle database call {function.attr}; '
                    f'use utils.conversations.lifecycle instead'
                )

        if isinstance(function, ast.Attribute) and function.attr in FINALIZATION_ADMISSION_METHODS:
            if self.relative_path != LIFECYCLE_SERVICE:
                self.errors.append(
                    f'{self.relative_path}:{node.lineno}: direct finalization admission {function.attr}; '
                    f'use utils.conversations.lifecycle instead'
                )

        if isinstance(function, ast.Attribute) and function.attr in {'update', 'set'}:
            fields = set()
            for argument in node.args:
                fields.update(_literal_lifecycle_fields(argument))
            for keyword in node.keywords:
                fields.update(_literal_lifecycle_fields(keyword.value))
            receiver = ''
            if isinstance(function.value, ast.Name):
                receiver = function.value.id
            elif isinstance(function.value, ast.Attribute):
                receiver = function.value.attr
            raw_conversation_write = 'conversation' in receiver or any(
                isinstance(argument, ast.Name) and 'conversation' in argument.id for argument in node.args[:1]
            )
            if fields and raw_conversation_write and self.relative_path not in RAW_STORAGE_ALLOWLIST:
                self.errors.append(
                    f'{self.relative_path}:{node.lineno}: raw lifecycle fields {sorted(fields)}; '
                    f'only the lifecycle service may own the transition'
                )
        self.generic_visit(node)


def violations(source: str, relative_path: str) -> list[str]:
    tree = ast.parse(source, filename=relative_path)
    visitor = _LifecycleWriteVisitor(relative_path)
    visitor.visit(tree)
    return visitor.errors


def _source_files() -> list[Path]:
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        files.extend((REPO_ROOT / root).rglob('*.py'))
    return sorted(path for path in files if '__pycache__' not in path.parts)


def main() -> int:
    errors: list[str] = []
    for path in _source_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        errors.extend(violations(path.read_text(encoding='utf-8'), relative))
    if errors:
        print('Conversation lifecycle write guard failed:', file=sys.stderr)
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Conversation lifecycle write guard passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

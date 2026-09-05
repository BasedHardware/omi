#!/usr/bin/env python3
"""Prevent notification producers from growing direct transport ownership."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys
from typing import Mapping, Optional

BASELINE_PATH = Path('.github/scripts/notification_dispatch_boundary_baseline.json')
TRANSPORT_MODULE = 'utils.notifications'
TRANSPORT_CALLS = frozenset(
    {
        '_send_to_user',
        '_send_to_user_async',
        'send_bulk_notification',
        'send_notification',
        'send_notification_async',
    }
)
EXCLUDED_PATHS = frozenset(
    {
        'backend/utils/notification_dispatch.py',
        'backend/utils/notifications.py',
    }
)


class _TransportCallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.direct_names: set[str] = set()
        self.module_names: set[str] = set()
        self.called_name_nodes: set[int] = set()
        self.count = 0

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == TRANSPORT_MODULE:
            for alias in node.names:
                if alias.name in TRANSPORT_CALLS:
                    self.direct_names.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == TRANSPORT_MODULE:
                self.module_names.add(alias.asname or alias.name.split('.')[0])
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in self.direct_names:
            self.count += 1
            self.called_name_nodes.add(id(node.func))
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in TRANSPORT_CALLS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.module_names
        ):
            self.count += 1
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        # Passing or assigning a transport function is still an ownership escape
        # even when the eventual call uses a local wrapper name.
        if isinstance(node.ctx, ast.Load) and node.id in self.direct_names and id(node) not in self.called_name_nodes:
            self.count += 1


def scan_direct_transport_calls(root: Path) -> dict[str, int]:
    observed: dict[str, int] = {}
    for path in sorted((root / 'backend').rglob('*.py')):
        relative = path.relative_to(root).as_posix()
        backend_parts = path.relative_to(root / 'backend').parts
        if (
            relative in EXCLUDED_PATHS
            or relative.startswith('backend/tests/')
            or any(part.startswith('.') or part == '__pycache__' for part in backend_parts)
        ):
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=relative)
        except (OSError, SyntaxError) as exc:
            raise RuntimeError(f'cannot inspect {relative}: {exc}') from exc
        visitor = _TransportCallVisitor()
        visitor.visit(tree)
        if visitor.count:
            observed[relative] = visitor.count
    return observed


def validate_baseline(
    observed: Mapping[str, int], current: Mapping[str, int], previous: Optional[Mapping[str, int]]
) -> list[str]:
    errors: list[str] = []
    if dict(current) != dict(observed):
        errors.append(
            'baseline must exactly match current direct transport calls; '
            f'observed={dict(observed)!r} baseline={dict(current)!r}'
        )

    if previous is None:
        return errors

    for path, count in current.items():
        previous_count = previous.get(path, 0)
        if count > previous_count:
            errors.append(f'{path}: direct transport calls grew from {previous_count} to {count}')
    return errors


def _load_json(raw: str, source: str) -> dict[str, int]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'invalid dispatch baseline {source}: {exc}') from exc
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(count, int) for key, count in value.items()
    ):
        raise RuntimeError(f'dispatch baseline {source} must be a JSON object of path-to-integer counts')
    return dict(sorted(value.items()))


def _baseline_at_revision(root: Path, revision: str) -> Optional[dict[str, int]]:
    result = subprocess.run(
        ['git', 'show', f'{revision}:{BASELINE_PATH.as_posix()}'],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return _load_json(result.stdout, f'at {revision}')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--base', help='target-branch revision used to enforce the shrink-only ratchet')
    args = parser.parse_args()

    root = args.root.resolve()
    try:
        current = _load_json((root / BASELINE_PATH).read_text(encoding='utf-8'), 'in working tree')
        previous = _baseline_at_revision(root, args.base) if args.base else None
        errors = validate_baseline(scan_direct_transport_calls(root), current, previous)
    except (OSError, RuntimeError) as exc:
        print(f'notification dispatch boundary: {exc}', file=sys.stderr)
        return 1

    if errors:
        print('notification dispatch boundary failed:', file=sys.stderr)
        for error in errors:
            print(f'  - {error}', file=sys.stderr)
        print('Route new notification producers through utils.notification_dispatch.', file=sys.stderr)
        return 1

    print(f'notification dispatch boundary: {sum(current.values())} legacy direct calls (ratchet held)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

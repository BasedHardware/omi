#!/usr/bin/env python3
"""Fail closed when a new collection/by-id reader has not been classified.

Registry entries are exact module:operation pairs, not directory exemptions.
--inventory prints every reference with its policy for review.
"""

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / 'backend/docs/conversations-v3-readers.json'
OPERATIONS = {
    'collection',
    'collection_group',
    'get_conversation',
    'get_conversation_raw_snapshot',
    'get_conversations_by_id',
    '_get_conversations_by_id',
    'iter_all_conversations',
    'get_in_progress_conversation',
    'get_processing_conversations',
    'user_conversations',
}


def references(root=ROOT):
    for base in ('backend/database', 'backend/routers', 'backend/services', 'backend/utils', 'backend/scripts'):
        for path in sorted((root / base).rglob('*.py')):
            if path.name == Path(__file__).name:
                continue
            tree = ast.parse(path.read_text())
            aliases = {
                alias.asname or alias.name
                for node in tree.body
                if isinstance(node, ast.ImportFrom) and node.module == 'database.conversations'
                for alias in node.names
                if alias.name in OPERATIONS
            }
            constants = {
                target.id: node.value.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and node.value.value == 'conversations'
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            for node in ast.walk(tree):
                # Also inventory a DB method passed to run_blocking or to the
                # product guard; it is a reader reference even without Call.
                if isinstance(node, ast.Attribute) and node.attr in OPERATIONS - {'collection', 'collection_group'}:
                    yield str(path.relative_to(root)), node.attr, node.lineno
                    continue
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in aliases:
                    yield str(path.relative_to(root)), node.id, node.lineno
                    continue
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                name = node.func.attr
                if name == 'document' and node.args:
                    arg = node.args[0]
                    values = [
                        part.value
                        for part in ast.walk(arg)
                        if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    ]
                    if any('/conversations/' in part for part in values):
                        yield str(path.relative_to(root)), 'document_path', node.lineno
                    continue
                if name not in {'collection', 'collection_group'}:
                    continue
                if name in {'collection', 'collection_group'}:
                    if not node.args:
                        continue
                    arg = node.args[0]
                    if not (
                        (isinstance(arg, ast.Constant) and arg.value == 'conversations')
                        or isinstance(arg, ast.Name)
                        and (arg.id == 'conversations_collection' or arg.id in constants)
                        or isinstance(arg, ast.Attribute)
                        and arg.attr == 'CONVERSATIONS_COLLECTION'
                    ):
                        continue
                yield str(path.relative_to(root)), name, node.lineno


def check(registry, *, root=ROOT, inventory=False):
    missing = []
    count = 0
    for path, operation, line in references(root):
        key = path + ':' + operation
        rule = registry.get(key)
        count += 1
        if (
            not rule
            or rule.get('policy') not in {'conversations', 'both', 'storage', 'operator'}
            or not rule.get('reason')
        ):
            missing.append(f'{path}:{line} unclassified {operation}')
        elif inventory:
            print(f'{path}:{line} {operation}: {rule["policy"]} — {rule["reason"]}')
    if missing:
        print('\n'.join(missing))
        return 1
    print(f'PASS: {count} conversation reader references classified')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', action='store_true')
    args = parser.parse_args()
    return check(json.loads(REGISTRY.read_text()), inventory=args.inventory)


if __name__ == '__main__':
    raise SystemExit(main())

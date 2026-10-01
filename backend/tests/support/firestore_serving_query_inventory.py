from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
from typing import Any

from tests.support.firestore_query_drivers import discover_query_functions

EXCLUDED_DIRECTORIES = frozenset({'tests', 'scripts', 'migrations', 'testing', '__pycache__', 'node_modules'})
BUILDERS = frozenset({'where', 'order_by', 'collection_group', 'count', 'sum', 'avg'})
CHAINS = BUILDERS | {'collection', 'limit', 'select', 'start_after', 'start_at', 'end_at', 'end_before'}


def _query_call(call: ast.Call, collection_names: set[str]) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in {'budgeted_stream_iter', 'budgeted_stream_list', 'mcp_auth_stream'}
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr in BUILDERS:
        if func.attr in {'count', 'sum', 'avg'}:
            return (
                isinstance(func.value, ast.Name)
                and func.value.id in collection_names
                or any(
                    isinstance(node, ast.Attribute) and node.attr in {'collection', 'collection_group', 'where'}
                    for node in ast.walk(func.value)
                )
            )
        return True
    if func.attr == 'build':
        return isinstance(func.value, ast.Name) and func.value.id.endswith('_QUERY')
    if func.attr == 'stream':
        return not call.args and all(keyword.arg in {'transaction', 'retry', 'timeout'} for keyword in call.keywords)
    if func.attr == 'get':
        return (isinstance(func.value, ast.Name) and func.value.id in collection_names) or (
            isinstance(func.value, ast.Call)
            and isinstance(func.value.func, ast.Attribute)
            and func.value.func.attr in CHAINS
        )
    return False


def discover_serving_query_functions(backend_root: str | Path) -> list[dict[str, Any]]:
    root = Path(backend_root)
    rows = discover_query_functions(root / 'database') if (root / 'database').is_dir() else []
    paths = []
    for directory, children, filenames in os.walk(root):
        children[:] = sorted(
            child
            for child in children
            if child not in EXCLUDED_DIRECTORIES
            and not child.startswith('.')
            and not (Path(directory) == root and child == 'database')
        )
        paths.extend(Path(directory) / filename for filename in filenames if filename.endswith('.py'))
    for path in sorted(paths):
        relative = path.relative_to(root)
        tree = ast.parse(path.read_text())
        functions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            functions.update(
                {
                    f'{cls.name}.{node.name}': node
                    for node in cls.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
            )
        for name, node in functions.items():
            collection_names: set[str] = set()
            for assignment in ast.walk(node):
                if isinstance(assignment, (ast.Assign, ast.AnnAssign)) and assignment.value is not None:
                    value = assignment.value
                    if (
                        isinstance(value, ast.Call)
                        and isinstance(value.func, ast.Attribute)
                        and value.func.attr in CHAINS
                    ):
                        targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
                        collection_names.update(target.id for target in targets if isinstance(target, ast.Name))
            if any(_query_call(call, collection_names) for call in ast.walk(node) if isinstance(call, ast.Call)):
                rows.append(
                    {
                        'key': '.'.join(relative.with_suffix('').parts) + '.' + name,
                        'file': str(path),
                        'line': node.lineno,
                        'public': not name.split('.')[-1].startswith('_'),
                        'direct': True,
                        'signature': ast.unparse(node.args),
                    }
                )
    return sorted(rows, key=lambda row: row['key'])


def serving_function_body_digest(key: str, backend_root: str | Path | None = None) -> str:
    root = Path(backend_root) if backend_root is not None else Path(__file__).resolve().parents[2]
    parts = key.split('.')
    for split in range(len(parts) - 1, 0, -1):
        path = root.joinpath(*parts[:split]).with_suffix('.py')
        if path.is_file():
            names = parts[split:]
            nodes = ast.parse(path.read_text()).body
            target = None
            for name in names:
                target = next(
                    node
                    for node in nodes
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name
                )
                nodes = target.body
            return hashlib.sha256(
                ast.dump(target, annotate_fields=False, include_attributes=False).encode()
            ).hexdigest()
    raise ValueError(f'query function source not found: {key}')

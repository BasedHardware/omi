"""Discover migrated boolean declarations and derive their fail field from the parser.

Only the missing-value policy is encoded by ``fail``. During this migration,
shadow/off retain the original token grammar and serve uses refactor_modes.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys


def parser_defaults(root: Path) -> dict[str, str]:
    if not (root / 'backend/config/refactor_modes.py').is_file():
        return {}
    sys.path.insert(0, str(root / 'backend'))
    from config.refactor_modes import default_off, default_on

    failures = {
        'on': 'open' if default_on('__registry_default__', environ={}) else 'closed',
        'off': 'open' if default_off('__registry_default__', environ={}) else 'closed',
    }
    declarations: dict[str, str] = {}
    for path in sorted((root / 'backend/config').rglob('*.py')):
        tree = ast.parse(path.read_text())
        constants = {}
        aliases = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value.value
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in (
                'config.refactor_switches',
                'config.refactor_modes',
            ):
                for imported in node.names:
                    if imported.name in ('default_on', 'default_off'):
                        aliases[imported.asname or imported.name] = imported.name.removeprefix('default_')
        boolean_calls = {'boolean': (1, 2)}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                parameters = [argument.arg for argument in node.args.args]
                for call in ast.walk(node):
                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                        and call.func.id == 'boolean'
                        and len(call.args) > 2
                        and all(isinstance(argument, ast.Name) for argument in call.args[1:3])
                    ):
                        key, default = (argument.id for argument in call.args[1:3])
                        if key in parameters and default in parameters:
                            boolean_calls[node.name] = (parameters.index(key), parameters.index(default))
        # A few legacy modules retain a local wrapper; resolve its callers too.
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                kinds = {
                    aliases[c.func.id]
                    for c in ast.walk(node)
                    if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in aliases
                }
                if len(kinds) == 1:
                    aliases[node.name] = next(iter(kinds))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or not node.args:
                continue
            kind = aliases.get(node.func.id)
            if node.func.id in boolean_calls:
                key_position, default_position = boolean_calls[node.func.id]
                kind = (
                    'on'
                    if len(node.args) > default_position
                    and isinstance(node.args[default_position], ast.Constant)
                    and node.args[default_position].value == 'true'
                    else 'off'
                )
                argument = node.args[key_position] if len(node.args) > key_position else None
            else:
                argument = node.args[0]
            key = (
                argument.value
                if isinstance(argument, ast.Constant)
                else constants.get(argument.id) if isinstance(argument, ast.Name) else None
            )
            if kind and isinstance(key, str) and key.isupper():
                fail = failures[kind]
                if key in declarations and declarations[key] != fail:
                    raise ValueError(f'conflicting boolean parser defaults for {key}')
                declarations[key] = fail
        if path.name == 'kill_switches.py':
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == 'KILL_SWITCHES' for t in node.targets
                ):
                    for key, value in ast.literal_eval(node.value).items():
                        declarations[key] = failures['on' if value else 'off']
    return declarations

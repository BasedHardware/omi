"""Pin audited People-reference and generation-writer bodies.

This inventory detects new/changed writers, not transactional correctness by
itself. Re-audit writer generation coverage and run the strict transaction and
emulator contracts before intentionally replacing the committed fingerprints.
"""

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = 'backend/docs/people-generation-writers.json'
HELPERS = frozenset({'bump_people_generation', 'write_person', 'read_people_generation', 'generation_ref'})
TOKENS = re.compile(
    r"collection\s*\(\s*(['\"])people\1|bump_people_generation|write_person|read_people_generation|generation_ref"
)


def _name(call):
    function = call.func
    return function.id if isinstance(function, ast.Name) else getattr(function, 'attr', '')


def fingerprints(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    result = {}

    def visit(node, parents):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            parents = [*parents, node.name]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls = [part for part in ast.walk(node) if isinstance(part, ast.Call)]
            has_people = any(
                _name(call) == 'collection'
                and call.args
                and isinstance(call.args[0], ast.Constant)
                and call.args[0].value == 'people'
                for call in calls
            )
            if has_people or any(_name(call) in HELPERS for call in calls) or node.name in HELPERS:
                body = ast.dump(node, include_attributes=False)
                result['.'.join(parents)] = hashlib.sha256(body.encode()).hexdigest()
        for child in ast.iter_child_nodes(node):
            visit(child, parents)

    visit(tree, [])
    return result


def inventory(root: Path) -> dict[str, str]:
    result = {}
    for directory in ('database', 'utils', 'routers'):
        for path in sorted((root / 'backend' / directory).rglob('*.py')):
            source = path.read_text()
            if not TOKENS.search(source):
                continue
            for scope, digest in fingerprints(source).items():
                result[f'{path.relative_to(root)}:{scope}'] = digest
    return result


def changes(expected: dict, current: dict) -> dict[str, list[str]]:
    return {
        'new': sorted(current.keys() - expected.keys()),
        'removed': sorted(expected.keys() - current.keys()),
        'changed': sorted(key for key in current.keys() & expected.keys() if current[key] != expected[key]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Only after writer audit and transaction verification')
    args = parser.parse_args()
    current = inventory(ROOT)
    target = ROOT / INVENTORY
    if args.write:
        target.write_text(json.dumps(current, indent=2, sort_keys=True) + '\n')
        print(f'Pinned {len(current)} audited People/generation scopes')
        return 0
    delta = changes(json.loads(target.read_text()), current)
    print(json.dumps(delta, sort_keys=True))
    return int(any(delta.values()))


if __name__ == '__main__':
    raise SystemExit(main())

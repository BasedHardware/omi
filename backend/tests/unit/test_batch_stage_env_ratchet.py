"""Ratchet: no new environment reads in batch stages (contract (c), invariant 3).

Batch-stage behaviour is decided by the policy snapshot admitted with the work
(``config/policy``), not by whatever the process environment says when a stage
happens to run. This test fails when an ``os.getenv`` / ``os.environ`` read is
added under:

- ``utils/batch_pipeline/**``
- ``database/batch_pipeline_*.py``
- ``utils/enrichment/**``
- ``utils/workers/**``
- ``database/outbox*.py``

Today's reads are a shrink-only baseline in
``fixtures/batch_stage_env_baseline.json``, keyed by (path, enclosing def,
variable name or ``<dynamic>``) with a count, never line numbers. The test
fails when a read appears or grows and when a baseline entry is gone or shrank.
E1's CI grep check supersedes it when E1 lands.

Regenerate (keeps existing ``why`` strings)::

    cd backend && python tests/unit/test_batch_stage_env_ratchet.py --write
"""

from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BACKEND_DIR = Path(__file__).resolve().parents[2]
BASELINE_PATH = BACKEND_DIR / 'tests' / 'unit' / 'fixtures' / 'batch_stage_env_baseline.json'
UNREVIEWED = 'pre-existing; unreviewed'

SCOPE_GLOBS = (
    'utils/batch_pipeline/**/*.py',
    'database/batch_pipeline_*.py',
    'utils/enrichment/**/*.py',
    'utils/workers/**/*.py',
    'database/outbox*.py',
)
DYNAMIC = '<dynamic>'


def scoped_modules() -> list[Path]:
    found: set[Path] = set()
    for pattern in SCOPE_GLOBS:
        found.update(path for path in BACKEND_DIR.glob(pattern) if path.is_file())
    return sorted(found)


def _literal_key(node: ast.expr | None) -> str:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else DYNAMIC


class _Visitor(ast.NodeVisitor):
    """Counts reads: os.getenv(), os.environ[...], os.environ.get(...), `in os.environ`, bare iteration."""

    def __init__(self) -> None:
        self.scope: list[str] = []
        self.sites: Counter[tuple[str, str]] = Counter()
        # Local names bound to the os module, os.getenv and os.environ (import aliases included).
        self.os_names = {'os'}
        self.getenv_names: set[str] = set()
        self.environ_names: set[str] = set()
        self._claimed: set[int] = set()

    def _add(self, key: str) -> None:
        self.sites[('.'.join(self.scope) or '<module>', key)] += 1

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == 'os':
                self.os_names.add(alias.asname or 'os')

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == 'os':
            for alias in node.names:
                if alias.name == '*':
                    self.getenv_names.add('getenv')
                    self.environ_names.add('environ')
                elif alias.name == 'getenv':
                    self.getenv_names.add(alias.asname or alias.name)
                elif alias.name == 'environ':
                    self.environ_names.add(alias.asname or alias.name)

    def _is_os_attr(self, node: ast.AST, attr: str) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == attr
            and isinstance(node.value, ast.Name)
            and node.value.id in self.os_names
        )

    def _enter(self, node: ast.AST) -> None:
        self.scope.append(node.name)  # type: ignore[attr-defined]
        self.generic_visit(node)
        self.scope.pop()

    visit_ClassDef = visit_FunctionDef = visit_AsyncFunctionDef = _enter

    def _environ_expr(self, node: ast.AST) -> bool:
        return self._is_os_attr(node, 'environ') or (isinstance(node, ast.Name) and node.id in self.environ_names)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        is_getenv = self._is_os_attr(func, 'getenv') or (isinstance(func, ast.Name) and func.id in self.getenv_names)
        if is_getenv:
            self._add(_literal_key(node.args[0] if node.args else None))
        elif (
            isinstance(func, ast.Attribute)
            and func.attr in {'get', 'pop', 'setdefault'}
            and self._environ_expr(func.value)
        ):
            self._claimed.add(id(func.value))
            self._add(_literal_key(node.args[0] if node.args else None))
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if self._environ_expr(node.value) and isinstance(node.ctx, ast.Load):
            self._claimed.add(id(node.value))
            self._add(_literal_key(node.slice))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)) and self._environ_expr(comparator):
                self._claimed.add(id(comparator))
                self._add(_literal_key(node.left))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # A bare `os.environ` that is passed around or iterated (copy, items(), ...).
        if self._is_os_attr(node, 'environ') and id(node) not in self._claimed:
            self._claimed.add(id(node))
            self._add(DYNAMIC)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        # A bare imported `environ` (or alias) used as a mapping: dict(env), env.items(), {**env}, ...
        if node.id in self.environ_names and isinstance(node.ctx, ast.Load) and id(node) not in self._claimed:
            self._claimed.add(id(node))
            self._add(DYNAMIC)


def scan_source(source: str) -> Counter[tuple[str, str]]:
    visitor = _Visitor()
    tree = ast.parse(source)
    # ImportFrom may appear after use inside a function; resolve imports first.
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            visitor.visit_ImportFrom(node)
    visitor.visit(tree)
    return visitor.sites


def scan() -> dict[tuple[str, str, str], int]:
    sites: dict[tuple[str, str, str], int] = {}
    for path in scoped_modules():
        relative = path.relative_to(BACKEND_DIR).as_posix()
        for (qualname, name), count in scan_source(path.read_text(encoding='utf-8')).items():
            sites[(relative, qualname, name)] = count
    return sites


def load_baseline() -> dict[tuple[str, str, str], dict]:
    data = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
    return {(e['path'], e['function'], e['name']): e for e in data['entries']}


def _describe(key: tuple[str, str, str]) -> str:
    return f'{key[0]}::{key[1]} reads {key[2]}'


@pytest.fixture(scope='module')
def scanned():
    return scan()


def _pending_allowance(key: tuple[str, str, str]) -> int:
    """Reads that are being *moved* here by another lane (never new): `pending` entries, `name` may end in `*`."""
    total = 0
    for (path, function, name), entry in load_baseline().items():
        if not entry.get('pending') or (path, function) != key[:2]:
            continue
        if name == key[2] or (name.endswith('*') and key[2].startswith(name[:-1])):
            total += entry['count']
    return total


def test_batch_stage_env_reads_match_baseline(scanned):
    baseline = load_baseline()
    problems = []
    for key, count in sorted(scanned.items()):
        allowed = baseline.get(key, {}).get('count', 0) if not baseline.get(key, {}).get('pending') else 0
        allowed += _pending_allowance(key)
        if count > allowed:
            problems.append(
                f'NEW {_describe(key)} count {count} > baseline {allowed}: batch stages read their policy from the '
                f'admitted policy snapshot (config/policy), not the process environment.'
            )
    for key, entry in sorted(baseline.items()):
        if entry.get('pending'):
            continue  # moved-in reads: the allowance is dropped (delete the entry) once the move lands or is abandoned
        if scanned.get(key, 0) < entry['count']:
            problems.append(
                f'STALE {_describe(key)} baseline count {entry["count"]} > current {scanned.get(key, 0)}: '
                f'lower or delete the entry in {BASELINE_PATH.relative_to(BACKEND_DIR)}.'
            )
    assert not problems, '\n'.join(problems)


def test_every_baseline_entry_has_a_reason():
    for key, entry in load_baseline().items():
        assert isinstance(entry.get('why'), str) and entry['why'].strip(), _describe(key)
        assert isinstance(entry.get('count'), int) and entry['count'] > 0, _describe(key)


def test_pending_allowance_matches_names_and_prefixes(tmp_path, monkeypatch):
    entries = {
        ('a.py', 'f', 'X_*'): {'pending': True, 'count': 2},
        ('a.py', 'f', 'Y'): {'pending': True, 'count': 1},
        ('a.py', 'g', 'Z'): {'count': 5},
    }
    monkeypatch.setattr(sys.modules[__name__], 'load_baseline', lambda: entries)
    assert _pending_allowance(('a.py', 'f', 'X_ONE')) == 2
    assert _pending_allowance(('a.py', 'f', 'Y')) == 1
    assert _pending_allowance(('a.py', 'f', 'W')) == 0
    assert _pending_allowance(('a.py', 'g', 'Z')) == 0


def test_scope_covers_the_contract_paths():
    modules = {path.relative_to(BACKEND_DIR).as_posix() for path in scoped_modules()}
    assert 'utils/batch_pipeline/errors.py' in modules
    assert any(m.startswith('database/batch_pipeline_') for m in modules)


def test_scanner_finds_every_read_shape():
    source = '''
import os
from os import getenv, environ

def f(name):
    os.getenv('A')
    os.getenv(name)
    os.getenv('A', 'x')
    os.environ['B']
    os.environ.get('C')
    getenv('D')
    environ.get('E')
    'F' in os.environ
    dict(os.environ)
    os.environ['W'] = '1'
    os.environ.setdefault('S', '1')
'''
    assert dict(scan_source(source)) == {
        ('f', 'A'): 2,
        ('f', DYNAMIC): 3,
        ('f', 'B'): 1,
        ('f', 'C'): 1,
        ('f', 'D'): 1,
        ('f', 'E'): 1,
        ('f', 'F'): 1,
        ('f', 'S'): 1,
    }


def test_scanner_follows_import_aliases():
    """L14-3: an aliased import must not hide a read."""
    source = '''
import os as operating_system
from os import getenv as read_env, environ as env

def f():
    read_env('BATCH_PIPELINE_PERCENT')
    operating_system.getenv('A')
    operating_system.environ['B']
    env.get('C')
    'D' in env
'''
    assert dict(scan_source(source)) == {
        ('f', 'BATCH_PIPELINE_PERCENT'): 1,
        ('f', 'A'): 1,
        ('f', 'B'): 1,
        ('f', 'C'): 1,
        ('f', 'D'): 1,
    }
    mappings = '''
from os import environ as env
from os import *

def g():
    dict(env)
    env.items()
    {**env}
    getenv('E')
    environ.copy()
'''
    assert dict(scan_source(mappings)) == {('g', DYNAMIC): 4, ('g', 'E'): 1}


def _write_baseline() -> None:
    previous = load_baseline() if BASELINE_PATH.exists() else {}
    entries = [
        {
            'path': key[0],
            'function': key[1],
            'name': key[2],
            'count': count,
            'why': previous.get(key, {}).get('why', UNREVIEWED),
        }
        for key, count in sorted(scan().items())
    ]
    entries += [e for e in previous.values() if e.get('pending')]  # keep moved-in allowances
    BASELINE_PATH.write_text(json.dumps({'entries': entries}, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {len(entries)} entries ({sum(e["count"] for e in entries)} reads) to {BASELINE_PATH}')


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        _write_baseline()
    else:
        raise SystemExit(f'usage: {sys.argv[0]} --write')

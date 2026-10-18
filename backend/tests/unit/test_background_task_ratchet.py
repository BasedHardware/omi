"""Ratchet: un-awaited background work on the Cloud Run task-handler request paths.

Why: Cloud Run keeps an instance alive only while it has in-flight requests.
When a revision is replaced, idle instances get SIGTERM, a ~10 s grace, then
SIGKILL, and CPU may be throttled outside requests. Work that outlives the
request (``start_background_task``, ``asyncio.create_task``,
``submit_with_context``, executor submits, FastAPI ``BackgroundTasks``,
threads) is not protected by that drain. On 2026-10-18 a paid STT recovery
owned by such work died mid-flight during a rollout (fixed by #22149, which
moved it into the awaited ``/v2/batch-pipeline/recover-quarantine`` handler).

Scope (exact): every module under ``backend/`` reachable through first-party
``utils.*`` / ``routers.*`` top-level imports (``import x`` and
``from x import y`` with level 0, transitively, ``database.*`` excluded) from
the router modules that own the Cloud Tasks / sync handlers:

- ``routers/sync.py`` (``/v2/sync-local-files``, ``/v2/sync-jobs/run``,
  ``/v2/audio-merge-jobs/run``)
- ``routers/batch_pipeline.py`` (``/v2/batch-pipeline/*`` incl. recover-quarantine)
- ``routers/users.py`` (``/v1/users/account-deletion-wipes/run``)
- ``routers/conversation_finalization.py`` (``/v1/conversation-finalization-jobs/run``)

plus every module in ``utils/batch_pipeline/`` and ``utils/sync/`` whether or
not it is currently imported. Function-local imports are not followed.

Inventoried call kinds and when a call counts as un-awaited:

- always: ``start_background_task(``, ``BackgroundTasks.add_task(`` (any
  ``.add_task(``), ``threading.Thread(``
- when the returned handle is not consumed in the enclosing function:
  ``asyncio.create_task(`` / ``create_task(``, ``asyncio.ensure_future(``,
  ``<loop>.create_task(`` (receiver named ``*loop`` or ``get_*loop()``),
  ``submit_with_context(``, ``<executor>.submit(``. "Not consumed" means the
  result is discarded (expression statement or lambda body), stored on an
  attribute/subscript, or bound to a local name that is never read again.

Each site is keyed by (backend-relative path, enclosing def/class qualname,
call kind) with a ``count`` -- never line numbers, so unrelated edits do not
churn the baseline. The test fails when a site appears or its count grows (await
it, or add it to the baseline with a ``why``) and when a baseline entry is gone
or its count shrank (delete/lower it so the baseline stays tight).

Regenerate (keeps existing ``why`` strings; new entries get the unreviewed
placeholder)::

    cd backend && python tests/unit/test_background_task_ratchet.py --write
"""

from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
BASELINE_PATH = BACKEND_DIR / 'tests' / 'unit' / 'fixtures' / 'background_task_baseline.json'
ROOT_MODULES = (
    'routers/sync.py',
    'routers/batch_pipeline.py',
    'routers/users.py',
    'routers/conversation_finalization.py',
)
WHOLE_PACKAGES = ('utils/batch_pipeline', 'utils/sync')
FOLLOWED_PREFIXES = ('utils.', 'routers.')
UNREVIEWED = 'pre-existing; unreviewed'

ALWAYS_FLAGGED = {'start_background_task', 'BackgroundTasks.add_task', 'threading.Thread'}


def _module_path(name: str) -> Path | None:
    relative = name.replace('.', '/')
    for candidate in (BACKEND_DIR / f'{relative}.py', BACKEND_DIR / relative / '__init__.py'):
        if candidate.is_file():
            return candidate
    return None


def _imported_names(node: ast.AST) -> set[str]:
    """Import-time imports: everything outside function bodies (incl. guarded/try blocks)."""
    names: set[str] = set()
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Import):
            names.update(alias.name for alias in child.names)
        elif isinstance(child, ast.ImportFrom) and child.module and child.level == 0:
            names.add(child.module)
            names.update(f'{child.module}.{alias.name}' for alias in child.names)
        else:
            names.update(_imported_names(child))
    return names


def scoped_modules() -> list[Path]:
    seen: set[Path] = set()
    stack = [BACKEND_DIR / root for root in ROOT_MODULES]
    for package in WHOLE_PACKAGES:
        stack.extend(sorted((BACKEND_DIR / package).glob('*.py')))
    while stack:
        path = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        for name in _imported_names(ast.parse(path.read_text(encoding='utf-8'))):
            if not name.startswith(FOLLOWED_PREFIXES):
                continue
            target = _module_path(name)
            if target is not None and target not in seen:
                stack.append(target)
    return sorted(seen)


def _is_loop_receiver(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id.lower().endswith('loop')
    if isinstance(node, ast.Attribute):
        return node.attr.lower().endswith('loop')
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')
        return name in {'get_running_loop', 'get_event_loop'}
    return False


def call_kind(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return {
            'start_background_task': 'start_background_task',
            'submit_with_context': 'submit_with_context',
            'create_task': 'asyncio.create_task',
            'ensure_future': 'asyncio.ensure_future',
            'Thread': 'threading.Thread',
        }.get(func.id)
    if not isinstance(func, ast.Attribute):
        return None
    receiver_is_asyncio = isinstance(func.value, ast.Name) and func.value.id == 'asyncio'
    if func.attr == 'create_task':
        if receiver_is_asyncio:
            return 'asyncio.create_task'
        return 'loop.create_task' if _is_loop_receiver(func.value) else None
    if func.attr == 'ensure_future':
        return 'asyncio.ensure_future'
    if func.attr in {'start_background_task', 'submit_with_context'}:
        return func.attr
    if func.attr == 'submit':
        return 'executor.submit'
    if func.attr == 'add_task':
        return 'BackgroundTasks.add_task'
    if func.attr == 'Thread' and isinstance(func.value, ast.Name) and func.value.id == 'threading':
        return 'threading.Thread'
    return None


class _SiteVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[str] = []
        self.functions: list[ast.AST] = []
        self.parents: dict[ast.AST, ast.AST] = {}
        self.sites: Counter[tuple[str, str]] = Counter()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        self.functions.append(node)
        self.generic_visit(node)
        self.functions.pop()
        self.scope.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def generic_visit(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            self.parents[child] = node
        super().generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        kind = call_kind(node)
        if kind is not None and (kind in ALWAYS_FLAGGED or not self._handle_consumed(node)):
            self.sites[('.'.join(self.scope) or '<module>', kind)] += 1
        self.generic_visit(node)

    def _handle_consumed(self, call: ast.Call) -> bool:
        parent = self.parents.get(call)
        if isinstance(parent, (ast.Expr, ast.Lambda)):
            return False
        if isinstance(parent, (ast.Assign, ast.AnnAssign)):
            targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                return False  # Stored on an object/collection: the handle outlives this call.
            name = targets[0].id
            body = self.functions[-1] if self.functions else None
            if body is None:
                return False
            return any(
                isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load)
                for node in ast.walk(body)
            )
        return True  # Awaited, returned, passed on, or collected into a larger expression.


def scan() -> dict[tuple[str, str, str], int]:
    sites: dict[tuple[str, str, str], int] = {}
    for path in scoped_modules():
        visitor = _SiteVisitor()
        visitor.visit(ast.parse(path.read_text(encoding='utf-8')))
        relative = path.relative_to(BACKEND_DIR).as_posix()
        for (qualname, kind), count in visitor.sites.items():
            sites[(relative, qualname, kind)] = count
    return sites


def load_baseline() -> dict[tuple[str, str, str], dict]:
    data = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
    return {(entry['path'], entry['function'], entry['kind']): entry for entry in data['entries']}


def _describe(key: tuple[str, str, str]) -> str:
    return f'{key[0]}::{key[1]} [{key[2]}]'


@pytest.fixture(scope='module')
def scanned():
    # Parsing ~450 modules is shared setup, not per-test work (fast-unit CPU guard measures calls only).
    return scoped_modules(), scan()


def test_scope_includes_handler_routers_and_owned_packages(scanned):
    modules = {path.relative_to(BACKEND_DIR).as_posix() for path in scanned[0]}
    assert set(ROOT_MODULES) <= modules
    assert 'utils/batch_pipeline/quarantine_recovery.py' in modules
    assert 'utils/sync/pipeline.py' in modules
    assert 'utils/executors.py' in modules


def test_background_task_sites_match_baseline(scanned):
    current = scanned[1]
    baseline = load_baseline()
    by_kind = Counter()
    for (_, _, kind), count in current.items():
        by_kind[kind] += count
    print(f'background-task ratchet: {sum(current.values())} un-awaited sites in scope {dict(sorted(by_kind.items()))}')

    problems = []
    for key, count in sorted(current.items()):
        allowed = baseline.get(key, {}).get('count', 0)
        if count > allowed:
            problems.append(
                f'NEW {_describe(key)} count {count} > baseline {allowed}: await the work inside the request '
                f'(or move it to a request-backed Cloud Tasks handler), or add it to '
                f'{BASELINE_PATH.relative_to(BACKEND_DIR)} with a "why" explaining why losing it at SIGKILL is safe.'
            )
    for key, entry in sorted(baseline.items()):
        if current.get(key, 0) < entry['count']:
            problems.append(
                f'STALE {_describe(key)} baseline count {entry["count"]} > current {current.get(key, 0)}: '
                f'lower or delete the baseline entry so the ratchet stays tight.'
            )
    assert not problems, '\n'.join(problems)


def test_every_baseline_entry_has_a_reason():
    for key, entry in load_baseline().items():
        assert isinstance(entry.get('why'), str) and entry['why'].strip(), _describe(key)
        assert isinstance(entry.get('count'), int) and entry['count'] > 0, _describe(key)


def test_scanner_classifies_consumed_and_discarded_handles():
    source = '''
import asyncio, threading
async def handler(executor, loop, background_tasks):
    asyncio.create_task(work())
    kept = asyncio.create_task(work())
    await kept
    orphan = asyncio.ensure_future(work())
    self_task = executor.submit(fn)
    return_value = submit_with_context(executor, fn)
    return_value.result()
    executor.submit(fn)
    loop.create_task(work())
    start_background_task(work(), name='x')
    background_tasks.add_task(fn)
    threading.Thread(target=fn).start()
    client.create_task(parent='p', task={})
    await asyncio.gather(asyncio.create_task(work()))
'''
    visitor = _SiteVisitor()
    visitor.visit(ast.parse(source))
    assert dict(visitor.sites) == {
        ('handler', 'asyncio.create_task'): 1,
        ('handler', 'asyncio.ensure_future'): 1,
        ('handler', 'executor.submit'): 2,
        ('handler', 'loop.create_task'): 1,
        ('handler', 'start_background_task'): 1,
        ('handler', 'BackgroundTasks.add_task'): 1,
        ('handler', 'threading.Thread'): 1,
    }


def _write_baseline() -> None:
    previous = load_baseline() if BASELINE_PATH.exists() else {}
    entries = [
        {
            'path': key[0],
            'function': key[1],
            'kind': key[2],
            'count': count,
            'why': previous.get(key, {}).get('why', UNREVIEWED),
        }
        for key, count in sorted(scan().items())
    ]
    BASELINE_PATH.write_text(json.dumps({'entries': entries}, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {len(entries)} entries ({sum(e["count"] for e in entries)} sites) to {BASELINE_PATH}')


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        _write_baseline()
    else:
        print('usage: python tests/unit/test_background_task_ratchet.py --write')

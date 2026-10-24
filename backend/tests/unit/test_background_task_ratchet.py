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
``utils.*`` / ``routers.*`` / ``services.*`` top-level imports (``import x``
and ``from x import y`` with level 0, transitively, ``database.*`` excluded)
from the router modules that own the Cloud Tasks / sync handlers:

- ``routers/sync.py`` (``/v2/sync-local-files``, ``/v2/sync-jobs/run``,
  ``/v2/audio-merge-jobs/run``)
- ``routers/batch_pipeline.py`` (``/v2/batch-pipeline/*`` incl. recover-quarantine)
- ``routers/users.py`` (``/v1/users/account-deletion-wipes/run``; the wipe
  itself is delegated to ``services/users/account_deletion.py``)
- ``routers/conversation_finalization.py`` (``/v1/conversation-finalization-jobs/run``)

plus every module in ``utils/batch_pipeline/`` and ``utils/sync/`` whether or
not it is currently imported. Function-local imports are not followed.

The scope is shared with CI path selection (``tests/support/
background_task_ratchet_scope.py``): changing any module under a scanned
top-level directory selects this ratchet, and a test below asserts the walk's
closure never escapes those directories.

Inventoried call kinds and when a call counts as un-awaited:

- always: ``start_background_task(``, ``BackgroundTasks.add_task(`` (any
  ``.add_task(``), ``threading.Thread(``
- when the returned handle is not *consumed* in the enclosing function:
  ``asyncio.create_task(`` / ``create_task(``, ``asyncio.ensure_future(``,
  ``<loop>.create_task(`` (receiver named ``*loop`` or ``get_*loop()``),
  ``submit_with_context(``, ``<executor>.submit(``. "Consumed" means the
  completion is actually observed: the handle is awaited (incl. inside
  ``asyncio.gather/wait/wait_for/as_completed/shield``), ``.result()`` is
  called on it, or it is returned to the caller. Merely reading the name --
  attaching a done callback, checking ``.done()``, logging it -- does not
  count: the work still outlives the request and dies at SIGKILL.

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

if __package__ in (None, ''):  # ``python tests/unit/test_background_task_ratchet.py --write``
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support.background_task_ratchet_scope import (  # noqa: E402
    BACKEND_DIR,
    EXTRA_MODULES,
    ROOT_MODULES,
    ratchet_selection_prefixes,
    scoped_modules,
)

BASELINE_PATH = BACKEND_DIR / 'tests' / 'unit' / 'fixtures' / 'background_task_baseline.json'
UNREVIEWED = 'pre-existing; unreviewed'

ALWAYS_FLAGGED = {'start_background_task', 'BackgroundTasks.add_task', 'threading.Thread'}

# Calls that observe completion of the handles passed to them as arguments.
_COMPLETION_HELPERS = {'gather', 'wait', 'wait_for', 'as_completed', 'shield'}


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

    def visit(self, node: ast.AST) -> None:
        # Consumption checks look at *later* statements (e.g. the `await renew`
        # in a finally block), so the parent map must cover the whole tree
        # before any Call is classified -- generic_visit only fills it lazily.
        for descendant in ast.walk(node):
            for child in ast.iter_child_nodes(descendant):
                self.parents[child] = descendant
        super().visit(node)

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
        # parents is pre-populated for the whole tree in visit(); nothing to do here.
        super().generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        kind = call_kind(node)
        if kind is not None and (kind in ALWAYS_FLAGGED or not self._handle_consumed(node)):
            self.sites[('.'.join(self.scope) or '<module>', kind)] += 1
        self.generic_visit(node)

    def _completion_helper(self, node: ast.AST) -> bool:
        """``asyncio.gather/wait/wait_for/as_completed/shield`` (or a same-named import)."""
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute):
            return func.attr in _COMPLETION_HELPERS
        return isinstance(func, ast.Name) and func.id in _COMPLETION_HELPERS

    def _reaches_completion_helper(self, node: ast.AST) -> bool:
        for _ in range(3):  # name -> Starred/List/... -> helper call
            parent = self.parents.get(node)
            if parent is None:
                return False
            if self._completion_helper(parent):
                return True
            node = parent
        return False

    def _name_consumed(self, name: str) -> bool:
        """Whether ``name``'s completion is observed in the enclosing function.

        Awaits, ``.result()`` calls, ``return name`` (ownership moves to the
        caller), appearance inside a completion helper's arguments, and
        collection into a local container that is itself consumed count.
        Receiver-only reads — ``name.add_done_callback(...)``, ``name.done()``,
        ``name.cancel()``, logging the handle — do not: the work still
        outlives the request.
        """
        body = self.functions[-1] if self.functions else None
        if body is None:
            return False
        for use in ast.walk(body):
            if not (isinstance(use, ast.Name) and use.id == name and isinstance(use.ctx, ast.Load)):
                continue
            parent = self.parents.get(use)
            if isinstance(parent, (ast.Await, ast.Return)):
                return True
            if isinstance(parent, ast.Attribute):
                # ``x.result()`` observes completion; ``x.done()`` / ``x.add_done_callback(...)`` do not.
                if parent.attr == 'result' and isinstance(self.parents.get(parent), ast.Call):
                    return True
                continue  # Receiver-only read: x.done() / x.add_done_callback(...) / x.cancel().
            if isinstance(parent, ast.Call):
                if self._completion_helper(parent):
                    return True
                func = parent.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr in {'append', 'add', 'insert'}
                    and isinstance(func.value, ast.Name)
                ):
                    if self._name_consumed(func.value.id):
                        return True  # Collected into a container that is awaited later.
                continue
            if self._reaches_completion_helper(use):
                return True  # e.g. gather(*tasks) / wait([task, other])
        return False

    def _handle_consumed(self, call: ast.Call) -> bool:
        parent = self.parents.get(call)
        if isinstance(parent, (ast.Expr, ast.Lambda)):
            return False
        if isinstance(parent, (ast.Await, ast.Return, ast.Yield, ast.YieldFrom)):
            return True  # Completion observed here, or ownership moves to the caller.
        if isinstance(parent, ast.Attribute):
            # ``create_task(...).result()`` observes completion; ``.done()`` / ``.add_done_callback(...)`` do not.
            return parent.attr == 'result'
        if isinstance(parent, ast.Call):
            if self._completion_helper(parent):
                return True  # e.g. ``await asyncio.gather(asyncio.create_task(...))``.
            func = parent.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in {'append', 'add', 'insert'}
                and isinstance(func.value, ast.Name)
            ):
                return self._name_consumed(func.value.id)  # Collected into a local container.
            return False  # Passed to an arbitrary callable: consumption is not observable here.
        if isinstance(parent, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            owner = self.parents.get(parent)
            if isinstance(owner, (ast.Assign, ast.AnnAssign)):
                targets = owner.targets if isinstance(owner, ast.Assign) else [owner.target]
                if len(targets) == 1 and isinstance(targets[0], ast.Name):
                    return self._name_consumed(targets[0].id)
            return False
        if isinstance(parent, (ast.Assign, ast.AnnAssign)):
            targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                return False  # Stored on an object/collection: the handle outlives this call.
            return self._name_consumed(targets[0].id)
        return False  # Truthiness test, comparison, arithmetic, ...: no completion observed.


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
    assert set(EXTRA_MODULES) <= modules
    assert 'utils/batch_pipeline/quarantine_recovery.py' in modules
    assert 'utils/sync/pipeline.py' in modules
    assert 'utils/executors.py' in modules
    # routers/users.py delegates the wipe handler to services.users.account_deletion.
    assert 'services/users/account_deletion.py' in modules


def test_scope_never_escapes_the_ci_selection_prefixes(scanned):
    """The AST walk (scanner scope) must stay inside the cheap prefix superset
    the CI selector uses (see tests/support/background_task_ratchet_scope.py);
    otherwise a changed scanned module would stop selecting this ratchet."""
    prefixes = ratchet_selection_prefixes()
    for path in scanned[0]:
        relative = path.relative_to(BACKEND_DIR).as_posix()
        assert relative.startswith(prefixes), relative


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
    tracked = asyncio.create_task(work(), name='tracked')
    tracked.add_done_callback(lambda task: None)
    watched = asyncio.ensure_future(work())
    if watched.done():
        return
    logged = executor.submit(fn)
    logger.info('submitted %s', logged)
    collected = executor.submit(fn)
    tasks.append(collected)
    await asyncio.gather(*tasks)
    waited = submit_with_context(executor, fn)
    await asyncio.wait_for(waited, timeout=1)
'''
    visitor = _SiteVisitor()
    visitor.visit(ast.parse(source))
    assert dict(visitor.sites) == {
        ('handler', 'asyncio.create_task'): 2,
        ('handler', 'asyncio.ensure_future'): 2,
        ('handler', 'executor.submit'): 3,
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

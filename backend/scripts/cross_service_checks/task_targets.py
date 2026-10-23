"""Invariant ``task-target-retry-semantics`` (contract (d); swarm lane 4, cross-plan L5).

A Cloud Tasks target answers 2xx when a delivery is consumed, 409 ``retry_response`` for every
expected condition, 400 for a malformed task, and 500 only from an unexpected-exception fallback.
Never 429 or 503: Cloud Tasks ignores ``Retry-After`` and system-throttles a queue on fast 5xx /
429 / 503 (the 10-18 18:14Z ``sync-jobs`` and 10-19 04:52Z ``sync-backfill`` stalls).

Static half of the contract. For every ``TaskEdge.route`` this AST-scans the route handler plus
the functions it calls in the same module or in another ``routers`` module (two levels deep) and
reports:

- a ``status_code`` of 429 or 503 anywhere (``JSONResponse``/``Response``/``HTTPException``,
  keyword or first positional argument, or ``status.HTTP_429_*``/``HTTP_503_*``);
- a ``status_code`` of 500 that is not inside an ``except Exception`` / ``except BaseException`` /
  bare ``except`` handler;
- an ``except ExpectedRetry`` handler that does not answer with ``retry_response``.

The behavioural half is ``testing/fakes/cloud_tasks_queue.py`` (scenario
``enrichment_fast_500_throttle``): a 500 inside the fallback is legal here, but returning it for an
*expected* condition still collapses the queue, which only the model can show.

Known violators are accepted through ``deploy/cross_service_known_gaps.json`` like every other
invariant (new keys fail; a key that stops occurring is reported stale). Keys carry no line numbers:
``task-target-retry-semantics|code|<edge>/<file>:<function>/<status>``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Iterable

INVARIANT = 'task-target-retry-semantics'
ENV = 'code'
ROUTERS_DIR = 'backend/routers'
FORBIDDEN = {429, 503}
FALLBACK_EXCEPTIONS = {'Exception', 'BaseException'}
STATUS_NAMES = {
    'HTTP_429_TOO_MANY_REQUESTS': 429,
    'HTTP_500_INTERNAL_SERVER_ERROR': 500,
    'HTTP_503_SERVICE_UNAVAILABLE': 503,
}
RESPONSE_CALLS = {'JSONResponse', 'Response', 'HTTPException', 'PlainTextResponse', 'ORJSONResponse'}
MAX_DEPTH = 2


@dataclass(frozen=True)
class Finding:
    file: str  # repository-relative
    function: str
    status: int | str  # int status, or 'expected-retry-shape'
    line: int


@dataclass
class _Module:
    rel: str
    name: str  # dotted, e.g. routers.sync
    tree: ast.Module
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    imports: dict[str, tuple[str, str]]  # local name -> (module, function)
    prefixes: dict[str, str]  # router variable -> prefix
    routes: dict[str, str]  # full path -> function name


def _const_str(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _status_value(node: ast.AST | None) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.Attribute) and node.attr in STATUS_NAMES:
        return STATUS_NAMES[node.attr]
    if isinstance(node, ast.Name) and node.id in STATUS_NAMES:
        return STATUS_NAMES[node.id]
    return None


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def parse_module(rel: str, text: str) -> _Module:
    tree = ast.parse(text)
    name = rel.removeprefix('backend/').removesuffix('.py').replace('/', '.')
    functions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    imports: dict[str, tuple[str, str]] = {}
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('routers'):
            for alias in node.names:
                imports[alias.asname or alias.name] = (node.module, alias.name)
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if _call_name(node.value.func) == 'APIRouter':
                prefix = next((_const_str(k.value) for k in node.value.keywords if k.arg == 'prefix'), None) or ''
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        prefixes[target.id] = prefix
    routes: dict[str, str] = {}
    for fn in functions.values():
        for deco in fn.decorator_list:
            if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)):
                continue
            owner = deco.func.value
            if not isinstance(owner, ast.Name) or owner.id not in prefixes:
                continue
            if deco.func.attr not in {'post', 'get', 'put', 'patch', 'delete', 'api_route'}:
                continue
            path = _const_str(deco.args[0]) if deco.args else None
            if path is not None:
                routes[prefixes[owner.id] + path] = fn.name
    return _Module(rel, name, tree, functions, imports, prefixes, routes)


def _in_fallback(handler_stack: list[ast.ExceptHandler]) -> bool:
    for handler in handler_stack:
        if handler.type is None:
            return True
        names = [handler.type] if not isinstance(handler.type, ast.Tuple) else list(handler.type.elts)
        if any(_call_name(n) in FALLBACK_EXCEPTIONS for n in names):
            return True
    return False


def _catches_expected_retry(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return False
    names = [handler.type] if not isinstance(handler.type, ast.Tuple) else list(handler.type.elts)
    return any(_call_name(n) == 'ExpectedRetry' for n in names)


def scan_function(rel: str, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[list[Finding], set[str]]:
    """Findings in one function body (nested defs excluded) and the names it calls."""
    findings: list[Finding] = []
    calls: set[str] = set()

    def visit(node: ast.AST, handlers: list[ast.ExceptHandler]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)) and node is not fn:
            return
        if isinstance(node, ast.Try):
            for child in node.body + node.orelse + node.finalbody:
                visit(child, handlers)
            for handler in node.handlers:
                if _catches_expected_retry(handler):
                    answers = any(
                        isinstance(n, ast.Call) and _call_name(n.func) == 'retry_response' for n in ast.walk(handler)
                    )
                    if not answers:
                        findings.append(Finding(rel, fn.name, 'expected-retry-shape', handler.lineno))
                for child in handler.body:
                    visit(child, handlers + [handler])
            return
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name:
                calls.add(name)
            if name in RESPONSE_CALLS:
                status = next((_status_value(k.value) for k in node.keywords if k.arg == 'status_code'), None)
                if status is None and node.args and name == 'HTTPException':
                    status = _status_value(node.args[0])
                if status in FORBIDDEN or (status == 500 and not _in_fallback(handlers)):
                    findings.append(Finding(rel, fn.name, status, node.lineno))
        for child in ast.iter_child_nodes(node):
            visit(child, handlers)

    visit(fn, [])
    return findings, calls


def scan_route(modules: dict[str, _Module], route: str) -> tuple[str | None, list[Finding]]:
    """(handler module rel or None when no handler is mounted, findings) for one route."""
    start = next(((m, m.routes[route]) for m in modules.values() if route in m.routes), None)
    if start is None:
        return None, []
    by_name = {m.name: m for m in modules.values()}
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    frontier = [(start[0], start[1], 0)]
    while frontier:
        module, function, depth = frontier.pop()
        if (module.name, function) in seen:
            continue
        seen.add((module.name, function))
        fn = module.functions.get(function)
        if fn is None:
            continue
        found, calls = scan_function(module.rel, fn)
        findings.extend(found)
        if depth >= MAX_DEPTH:
            continue
        for call in calls:
            if call in module.functions:
                frontier.append((module, call, depth + 1))
            elif call in module.imports:
                target_mod, target_fn = module.imports[call]
                if target_mod in by_name:
                    frontier.append((by_name[target_mod], target_fn, depth + 1))
    return start[0].rel, sorted(set(findings), key=lambda f: (f.file, f.function, str(f.status), f.line))


def load_router_modules(source) -> dict[str, _Module]:
    out: dict[str, _Module] = {}
    root = source.directory(ROUTERS_DIR)
    for path in sorted(root.rglob('*.py')):
        rel = f'{ROUTERS_DIR}/{path.relative_to(root).as_posix()}'
        try:
            out[rel] = parse_module(rel, source.read(rel))
        except SyntaxError:
            continue
    return out


def violations_for(edges: Iterable, modules: dict[str, _Module], violation_cls) -> list:
    out = []
    reported: set[str] = set()
    for edge in edges:
        _, findings = scan_route(modules, edge.route)
        counts: dict[str, int] = {}
        for f in findings:
            scope = f'{edge.id}/{f.file.removeprefix("backend/")}:{f.function}/{f.status}'
            counts[scope] = counts.get(scope, 0) + 1
        for scope, count in sorted(counts.items()):
            if scope in reported:
                continue
            reported.add(scope)
            status = scope.rsplit('/', 1)[1]
            message = (
                'except ExpectedRetry must answer retry_response (409)'
                if status == 'expected-retry-shape'
                else f'task target returns {status}'
                + ('' if status != '500' else ' outside an unexpected-exception fallback')
                + f' ({count} site(s)); expected retries answer 409 retry_response'
            )
            out.append(violation_cls(INVARIANT, ENV, scope, message))
    return out


def check_task_target_retry_semantics(ctx) -> list:
    """Registered in scripts/cross_service_contract.py INVARIANTS by lane 1."""
    from scripts.cross_service_contract import TASK_EDGES, Violation

    return violations_for(TASK_EDGES, load_router_modules(ctx.source), Violation)

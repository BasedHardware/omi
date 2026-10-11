"""Combinatorial drivers that execute real ``database.*`` query functions against the recording fake.

Registry entries live in ``tests.support.firestore_query_driver_registry``; this
module provides the entry model, the AST sentinel used by the completeness test
(``discover_query_functions`` — detection only, never shape construction), and
``run_driver`` / ``run_all_drivers`` which execute each entry over the full
cartesian product of its shape-affecting parameter domains while recording
every terminal query shape.
"""

from __future__ import annotations

import ast
import asyncio
import copy
import datetime as datetime_module
import functools
import hashlib
import importlib
import inspect
import itertools
import os
import re
import socket
import sys
import unittest.mock
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from testing.hermetic_network import block_outbound_network
from tests.support.firestore_shape_recorder import (
    QueryShape,
    RecordingDocumentReference,
    RecordingFirestore,
    RecordingQuery,
    install_recorder,
)

FROZEN_NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
FROZEN_LATER = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
FROZEN_TODAY = date(2026, 1, 1)
SHAPE_UID = 'shape-user'


class _FrozenDateTimeMeta(type):
    def __instancecheck__(cls, instance: Any) -> bool:
        return isinstance(instance, datetime_module.datetime)


class _FrozenDateTime(datetime, metaclass=_FrozenDateTimeMeta):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        if tz is not None:
            return FROZEN_NOW.astimezone(tz)
        return FROZEN_NOW.replace(tzinfo=None)

    @classmethod
    def utcnow(cls) -> datetime:
        return FROZEN_NOW.replace(tzinfo=None)

    @classmethod
    def today(cls) -> datetime:
        return FROZEN_NOW

    @classmethod
    def fromtimestamp(cls, timestamp: float, tz: Any = None) -> datetime:
        return datetime.fromtimestamp(timestamp, tz=tz)


class _FrozenDateMeta(type):
    def __instancecheck__(cls, instance: Any) -> bool:
        return isinstance(instance, datetime_module.date)


class _FrozenDate(date, metaclass=_FrozenDateMeta):
    @classmethod
    def today(cls) -> date:
        return FROZEN_TODAY


class _FrozenDatetimeModule:
    """Drop-in for ``import datetime`` style modules while a driver runs."""

    datetime = _FrozenDateTime
    date = _FrozenDate
    time = time
    timedelta = timedelta
    timezone = timezone
    tzinfo = datetime_module.tzinfo
    MINYEAR = datetime_module.MINYEAR
    MAXYEAR = datetime_module.MAXYEAR


class _BlockedConnectionError(AssertionError):
    pass


def _blocked_connect_factory(attempts: list[Any]) -> Callable[..., None]:
    def _blocked_connect(self: Any, address: Any, *args: Any, **kwargs: Any) -> None:
        attempts.append(address)
        raise _BlockedConnectionError(f'network connection attempt during driver run: {address!r}')

    return _blocked_connect


@contextmanager
def _block_all_sockets() -> Iterator[list[Any]]:
    """Fail loudly on any connect, including loopback (Redis is not loopback-safe here).

    Yields the list of attempted addresses; serving code that swallows the
    raised error still leaves the attempt recorded.
    """
    attempts: list[Any] = []

    def _blocked_create_connection(*args: Any, **kwargs: Any) -> None:
        attempts.append(args[0] if args else kwargs.get('address'))
        raise _BlockedConnectionError('network connection attempt during driver run')

    with (
        unittest.mock.patch.object(socket.socket, 'connect', _blocked_connect_factory(attempts)),
        unittest.mock.patch.object(socket.socket, 'connect_ex', _blocked_connect_factory(attempts)),
        unittest.mock.patch.object(socket, 'create_connection', _blocked_create_connection),
    ):
        yield attempts


class _MissRedis:
    """Deterministic always-miss fake standing in for every bound Redis handle."""

    def __call__(self, *args: Any, **kwargs: Any) -> list:
        return []

    def get(self, *args: Any, **kwargs: Any) -> None:
        return None

    def getset(self, *args: Any, **kwargs: Any) -> None:
        return None

    def mget(self, keys: Any, *args: Any, **kwargs: Any) -> list:
        return [None] * len(list(keys))

    def exists(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def sismember(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def smembers(self, *args: Any, **kwargs: Any) -> set:
        return set()

    def hgetall(self, *args: Any, **kwargs: Any) -> dict:
        return {}

    def lrange(self, *args: Any, **kwargs: Any) -> list:
        return []

    def zrange(self, *args: Any, **kwargs: Any) -> list:
        return []

    def scard(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def ttl(self, *args: Any, **kwargs: Any) -> int:
        return -1

    def incr(self, *args: Any, **kwargs: Any) -> int:
        return 1

    def incrby(self, *args: Any, **kwargs: Any) -> int:
        return 1

    def expire(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def set(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def setnx(self, *args: Any, **kwargs: Any) -> int:
        return 1

    def delete(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def sadd(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def publish(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def eval(self, *args: Any, **kwargs: Any) -> list:
        return []

    def evalsha(self, *args: Any, **kwargs: Any) -> list:
        return []

    def script_load(self, *args: Any, **kwargs: Any) -> str:
        return 'miss'

    def pipeline(self, *args: Any, **kwargs: Any) -> '_MissRedis':
        return self

    def execute(self, *args: Any, **kwargs: Any) -> list:
        return []

    def register_script(self, *args: Any, **kwargs: Any) -> Callable:
        return lambda *a, **k: []

    def __getattr__(self, name: str) -> Any:
        if name.startswith('_'):
            raise AttributeError(name)
        return lambda *a, **k: None


def _redis_patches(stack: ExitStack) -> None:
    """Swap every bound Redis client/script in loaded backend modules for ``_MissRedis``."""
    for module in list(sys.modules.values()):
        name = getattr(module, '__name__', '') or ''
        if not (name == 'database' or name.startswith('database.') or name.startswith('utils')):
            continue
        for attr, value in list(vars(module).items()):
            module_name = type(value).__module__ or ''
            if module_name.startswith('redis'):
                stack.enter_context(unittest.mock.patch.object(module, attr, _MissRedis()))


@contextmanager
def _freeze_module_clocks() -> Iterator[None]:
    """Freeze ``datetime``/``date`` clock reads in every loaded ``database.*`` module."""
    with ExitStack() as stack:
        for module in list(sys.modules.values()):
            name = getattr(module, '__name__', '') or ''
            if name != 'database' and not name.startswith(('database.', 'utils.', 'routers.', 'services.', 'jobs.')):
                continue
            for attr in ('datetime', 'date'):
                bound = module.__dict__.get(attr)
                if bound is datetime:
                    stack.enter_context(unittest.mock.patch.object(module, attr, _FrozenDateTime))
                elif bound is date:
                    stack.enter_context(unittest.mock.patch.object(module, attr, _FrozenDate))
                elif bound is datetime_module:
                    stack.enter_context(unittest.mock.patch.object(module, attr, _FrozenDatetimeModule))
        yield


class _ClientSentinel:
    def __repr__(self) -> str:
        return 'CLIENT'


CLIENT = _ClientSentinel()

CLIENT_PARAMETER_NAMES = frozenset({'firestore_client', 'db_client', 'client', 'db'})


@dataclass(frozen=True)
class RefSpec:
    """A fake reference argument resolved against the driver client at call time."""

    kind: str
    path: str


def ref_query(path: str) -> RefSpec:
    return RefSpec('query', path)


def ref_collection(path: str) -> RefSpec:
    return RefSpec('query', path)


def ref_document(path: str) -> RefSpec:
    return RefSpec('document', path)


def collection_group(group_id: str) -> RefSpec:
    return RefSpec('collection_group', group_id)


def noop(*args: Any, **kwargs: Any) -> None:
    return None


def noop_true(*args: Any, **kwargs: Any) -> bool:
    return True


@dataclass(frozen=True)
class CallerProfile:
    name: str
    domains: dict[str, list[Any]]
    serving: bool = True


@dataclass
class DriverEntry:
    """A driven registry entry: every parameter is base, a domain member, or a named neutral."""

    function: str
    base: dict[str, Any] = field(default_factory=dict)
    domains: dict[str, list[Any]] = field(default_factory=dict)
    neutrals: dict[str, tuple[Any, str]] = field(default_factory=dict)
    setup: Callable[[RecordingFirestore, dict[str, Any], int], None] | None = None
    patchers: tuple[Callable[[RecordingFirestore], Any], ...] = ()
    trials: int = 1
    profiles: tuple[CallerProfile, ...] = ()


@dataclass
class CoveredByEntry:
    """A function whose query shapes are exercised by other registry drivers."""

    function: str
    covered_by: tuple[str, ...]
    reason: str
    expect_observed: bool = True
    body_digest: str | None = None


@dataclass
class SkipEntry:
    """An explicit, reasoned non-driven entry (admin/migration/AST false positive)."""

    function: str
    reason: str
    body_digest: str | None = None


@dataclass
class DriverError:
    function: str
    combo: dict[str, Any]
    error: str


@dataclass
class DriverResult:
    function: str
    shapes: list[QueryShape]
    errors: list[DriverError]


def import_function(dotted: str) -> Callable[..., Any]:
    # Query owners may be repository classes as well as module functions.
    parts = dotted.split('.')
    for split in range(len(parts) - 1, 0, -1):
        module_name = '.'.join(parts[:split])
        try:
            target = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name != module_name:
                raise
            continue
        for part in parts[split:]:
            target = getattr(target, part)
        return target
    raise ImportError(dotted)


def _function_module(dotted: str) -> str:
    module_name, _ = dotted.rsplit('.', 1)
    return module_name


def ref_transaction() -> RefSpec:
    return RefSpec('transaction', '')


def _materialize(value: Any, client: RecordingFirestore) -> Any:
    if isinstance(value, _ClientSentinel):
        return client
    if isinstance(value, RefSpec):
        if value.kind == 'document':
            return RecordingDocumentReference(client, value.path)
        if value.kind == 'collection_group':
            return client.collection_group(value.path)
        if value.kind == 'transaction':
            return client.transaction()
        return RecordingQuery._collection(client, value.path)
    return value


def calling_key(calling_function: str) -> str:
    """Map a recorded ``calling_function`` to its enclosing function's registry key."""
    parts = calling_function.split('.')
    if '<locals>' in parts:
        parts = parts[: parts.index('<locals>')]
    return '.'.join(parts)


def _copy_arg(value: Any) -> Any:
    if isinstance(value, (RefSpec, _ClientSentinel)) or callable(value):
        return value
    return copy.deepcopy(value)


def run_driver(entry: DriverEntry, client: RecordingFirestore | None = None) -> DriverResult:
    """Execute one registry entry across the full product of its domains.

    The network guard is installed before the target module is imported. Each
    driver defaults to a fresh client; per combo/trial the seeded-document map,
    consume-once queue, and auto-id counter reset so trials stay deterministic,
    and every argument is deep-copied so a function mutating inputs cannot
    corrupt later combos or the registry itself.
    """
    if entry.profiles:
        shapes: list[QueryShape] = []
        errors: list[DriverError] = []
        for profile in entry.profiles:
            result = run_driver(replace(entry, domains={**entry.domains, **profile.domains}, profiles=()), client)
            shapes.extend(
                replace(
                    shape,
                    parameter_combo={**shape.parameter_combo, 'caller_profile': profile.name},
                    serving=profile.serving,
                )
                for shape in result.shapes
            )
            errors.extend(
                replace(error, combo={**error.combo, 'caller_profile': profile.name}) for error in result.errors
            )
        return DriverResult(entry.function, shapes, errors)
    client = client or RecordingFirestore()
    initial_documents = copy.deepcopy(client.documents)
    errors: list[DriverError] = []
    shapes_before = len(client.shapes)

    with (
        block_outbound_network(),
        _block_all_sockets() as socket_attempts,
        install_recorder(client),
        ExitStack() as patch_stack,
    ):
        try:
            fn = import_function(entry.function)
            signature = inspect.signature(fn)
        except Exception as error:
            errors.append(DriverError(entry.function, {}, f'{type(error).__name__}: {error}'))
            return DriverResult(entry.function, client.shapes[shapes_before:], errors)
        _redis_patches(patch_stack)
        patch_stack.enter_context(_freeze_module_clocks())
        for patcher in entry.patchers:
            patch_stack.enter_context(patcher(client))
        fn = import_function(entry.function)

        unclassified: list[str] = []
        for name, param in signature.parameters.items():
            if name in entry.domains or name in entry.base or name in entry.neutrals:
                continue
            if name in CLIENT_PARAMETER_NAMES:
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            unclassified.append(name)
        errors.extend(DriverError(entry.function, {}, f'unclassified parameter: {name}') for name in unclassified)
        for name in entry.base:
            param = signature.parameters.get(name)
            if (
                param is not None
                and param.default is not inspect.Parameter.empty
                and name not in CLIENT_PARAMETER_NAMES
            ):
                errors.append(
                    DriverError(
                        entry.function,
                        {},
                        f'defaulted parameter {name} must be a domain or a reasoned neutral, not base',
                    )
                )
        for name, values in entry.domains.items():
            if not values:
                errors.append(DriverError(entry.function, {}, f'domain {name} is empty'))
        for name, spec in entry.neutrals.items():
            if not isinstance(spec, tuple) or len(spec) != 2 or not str(spec[1]).strip():
                errors.append(DriverError(entry.function, {}, f'neutral {name} lacks a reason'))

        domain_names = list(entry.domains)
        combos = [
            dict(zip(domain_names, values)) for values in itertools.product(*(entry.domains[k] for k in domain_names))
        ] or [{}]

        for combo in combos:
            for trial in range(entry.trials):
                client.documents.clear()
                client.documents.update(copy.deepcopy(initial_documents))
                client.reset_queues()
                if entry.setup is not None:
                    entry.setup(client, combo, trial)
                kwargs: dict[str, Any] = {}
                for name, value in entry.base.items():
                    kwargs[name] = _materialize(_copy_arg(value), client)
                for name, (value, _reason) in entry.neutrals.items():
                    kwargs[name] = _materialize(_copy_arg(value), client)
                for name, value in combo.items():
                    kwargs[name] = _materialize(_copy_arg(value), client)
                for name in signature.parameters:
                    if name in CLIENT_PARAMETER_NAMES and name not in kwargs:
                        kwargs[name] = client
                with client.recording_context(entry.function, combo):
                    try:
                        result = fn(**kwargs)
                        if inspect.isawaitable(result):
                            result = asyncio.run(result)
                        if inspect.isgenerator(result) or isinstance(result, Iterator):
                            list(result)
                    except Exception as error:
                        errors.append(DriverError(entry.function, combo, f'{type(error).__name__}: {error}'))
                if client.queued_leftovers():
                    errors.append(
                        DriverError(
                            entry.function,
                            combo,
                            'leftover queued responses after trial — fixture rows were never consumed',
                        )
                    )
    for address in dict.fromkeys(repr(a) for a in socket_attempts):
        errors.append(
            DriverError(
                entry.function,
                {},
                f'network connection attempt during driver run: {address} — a caught attempt still fails',
            )
        )
    return DriverResult(entry.function, client.shapes[shapes_before:], errors)


def run_all_drivers(entries: dict[str, DriverEntry]) -> dict[str, DriverResult]:
    """Run every driver on its own fresh client."""
    return {key: run_driver(entry) for key, entry in entries.items()}


_QUERY_METHODS = {'where', 'order_by', 'count', 'sum', 'avg', 'stream', 'collection_group'}
_CHAIN_METHODS = _QUERY_METHODS | {
    'limit',
    'limit_to_last',
    'offset',
    'select',
    'start_after',
    'start_at',
    'end_before',
    'end_at',
    'collection',
}
_STREAM_HELPERS = {'budgeted_stream_iter', 'budgeted_stream_list', 'mcp_auth_stream'}
_QUERY_GET_RECEIVER = re.compile(r'query|.*_query')


def _is_query_terminal(call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != 'get':
        return False
    receiver = func.value
    if isinstance(receiver, ast.Call):
        inner = receiver.func
        if isinstance(inner, ast.Attribute) and inner.attr in _CHAIN_METHODS:
            return True
    if isinstance(receiver, ast.Name) and _QUERY_GET_RECEIVER.fullmatch(receiver.id):
        return True
    return False


def discover_query_functions(database_root: str | Path) -> list[dict[str, Any]]:
    """Statically enumerate candidate querying functions under ``database/``.

    Sentinel for the completeness test: a top-level function (or one reached
    transitively within the same module) that invokes a query builder method,
    a ``.get()`` on a query/collection chain, or a known streaming helper is a
    candidate that must have a registry entry. Document/dict ``.get`` calls are
    excluded by construction. Nested function bodies are walked via
    ``ast.walk`` exactly like the settled inventory recipe.
    """
    root = Path(database_root)
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob('*.py')):
        source = path.read_text()
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for class_node in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            for member in class_node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions[f'{class_node.name}.{member.name}'] = member
        querying: set[str] = set()
        for name, node in functions.items():
            for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
                func = call.func
                if isinstance(func, ast.Attribute) and func.attr in _QUERY_METHODS:
                    querying.add(name)
                    break
                if isinstance(func, ast.Name) and func.id in _STREAM_HELPERS:
                    querying.add(name)
                    break
                if _is_query_terminal(call):
                    querying.add(name)
                    break
        direct = set(querying)
        while True:
            extra = {
                name
                for name, node in functions.items()
                if any(
                    isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in querying
                    for call in ast.walk(node)
                )
            }
            if extra <= querying:
                break
            querying |= extra
        for name in sorted(querying):
            node = functions[name]
            key = str(path.relative_to(root.parent).with_suffix('')).replace('/', '.') + '.' + name
            public = not name.split('.')[-1].startswith('_')
            rows.append(
                {
                    'key': key,
                    'file': str(path),
                    'line': node.lineno,
                    'public': public,
                    'direct': name in direct,
                    'signature': ast.unparse(node.args),
                }
            )
    return rows


def discover_target_references(
    root: str | Path,
    targets: frozenset[str],
    modules: frozenset[str] = frozenset(),
    exclude_dirs: frozenset[str] = frozenset({'tests', 'testing', 'scripts', '__pycache__'}),
) -> dict[str, dict[str, Any]]:
    """Statically find references to ``targets`` (dotted callables) or ``modules``.

    Sentinel only — detection, never shape construction. Walks ``*.py`` under
    ``root`` (skipping ``exclude_dirs`` and dot-directories), resolves imports
    and name aliases, and keys each hit ``relative/path.py:owner:resolved``.
    Plain module references (attribute access or name use) resolve to the
    module itself so ``module.func()`` wrappers are caught too.
    """
    root = Path(root)
    found: dict[str, dict[str, Any]] = {}
    needles = {t.rsplit('.', 1)[-1] for t in targets} | {m.rsplit('.', 1)[-1] for m in modules}
    paths: list[Path] = []
    for directory, folders, files in os.walk(root):
        folders[:] = sorted(name for name in folders if name not in exclude_dirs and not name.startswith('.'))
        paths.extend(Path(directory) / name for name in files if name.endswith('.py'))
    for path in sorted(paths):
        relative = path.relative_to(root)
        module_dotted = relative.with_suffix('').as_posix().replace('/', '.')
        source = path.read_text()
        if not any(re.search(rf'\b{re.escape(needle)}\b', source) for needle in needles):
            continue
        tree = ast.parse(source)
        imports: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name.split('.')[0]] = (
                        alias.name if alias.asname else alias.name.split('.')[0]
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = f'{node.module}.{alias.name}'

        def resolve(node):
            if isinstance(node, ast.Name):
                return imports.get(node.id, node.id)
            if isinstance(node, ast.Attribute):
                base = resolve(node.value)
                return f'{base}.{node.attr}' if base else ''
            return ''

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and resolve(node.value) in targets | modules:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        imports[target.id] = resolve(node.value)

        def visit(node, owners=()):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                owners = (*owners, node)
            if isinstance(node, (ast.Call, ast.Name, ast.Attribute)):
                references = []
                if isinstance(node, ast.Call):
                    references = [node.func, *node.args, *(kw.value for kw in node.keywords)]
                else:
                    references = [node]
                for reference in references:
                    resolved = resolve(reference)
                    if resolved in targets or resolved in modules:
                        qualified = resolved
                    elif f'{module_dotted}.{resolved}' in targets | modules:
                        qualified = f'{module_dotted}.{resolved}'
                    else:
                        continue
                    owner_name = '.'.join(item.name for item in owners) or '<module>'
                    key = f'{relative.as_posix()}:{owner_name}:{qualified}'
                    record = found.setdefault(key, {'target': qualified, 'references': 0})
                    record['references'] += 1
            for child in ast.iter_child_nodes(node):
                visit(child, owners)

        visit(tree)
    return found


def discover_textual_registrations(paths: Iterable[str | Path], needles: Iterable[str]) -> dict[str, list[str]]:
    """Textual scan of non-Python inventories (workflows, charts, image manifests).

    Returns ``{path: [needle, ...]}`` for every file containing a needle —
    entrypoint scripts registered by name rather than imported as a module.
    """
    found: dict[str, list[str]] = {}
    for candidate in paths:
        candidate = Path(candidate)
        files = [candidate] if candidate.is_file() else sorted(p for p in candidate.rglob('*') if p.is_file())
        for path in files:
            try:
                text = path.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            hits = [needle for needle in needles if needle in text]
            if hits:
                found[str(path)] = hits
    return found


@functools.lru_cache(maxsize=256)
def _source_function_nodes(path: str, mtime_ns: int, size: int) -> dict[str, ast.AST]:
    """Parse and index a stable source snapshot once for repeated digest checks."""
    del mtime_ns, size  # Included in the cache key to invalidate edited files.
    tree = ast.parse(Path(path).read_text())
    candidates: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            candidates[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    candidates[f'{node.name}.{member.name}'] = member
    return candidates


def function_body_digest(dotted: str, database_root: str | Path | None = None) -> str:
    """SHA-256 of the normalized AST dump of the whole function node.

    Covers signature, defaults, decorators, and body. Pinned on
    ``expect_observed=False`` covered-by entries and skip entries so any edit
    to the helper forces a coverage review. Source-only; the module is never
    imported.
    """
    root = Path(database_root) if database_root else Path(__file__).resolve().parents[2] / 'database'
    parts = dotted.split('.')
    for split in range(len(parts) - 1, 0, -1):
        module_rel = '.'.join(parts[1:split])
        attr_path = '.'.join(parts[split:])
        path = root / (module_rel + '.py')
        if path.exists():
            break
    stat = path.stat()
    candidates = _source_function_nodes(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    node = candidates[attr_path]
    dump = ast.dump(node, annotate_fields=False, include_attributes=False)
    return hashlib.sha256(dump.encode('utf-8')).hexdigest()


def shape_id(shape: QueryShape) -> str:
    return hashlib.sha256(shape.signature().encode('utf-8')).hexdigest()[:16]

#!/usr/bin/env python3
"""M8: a new Firestore queue/job/lease collection must declare a read budget.

The batch pipeline's Firestore job, queue and lease collections grew to ~1.36B of
~1.83B reads/day before anyone wrote the number down (firestore-reads-program
diagnosis, 2026-11-11). This guard makes the next subsystem state its read budget
in the same PR that introduces the collection, so a 530-reads/unit pipeline has to
be a reviewed decision instead of a surprise on the bill.

Scope: collections that hold *work state* -- queues, jobs, leases, claims, retry
and dispatch state, progress and recovery markers. User-data collections are out
of scope. The guard scans the two in-repo Firestore surfaces: Python under
``backend/`` (``.collection()`` / ``.collection_group()``) and TypeScript and
JavaScript under ``web/`` (``db.collection()``, ``db.collectionGroup()``,
``collection(db, ...)`` and ``doc(db, ...)``).

Two shapes are gated, both diff-scoped against the base revision:

* A **collection name** that first appears in this change (a literal, a module
  constant, or an imported constant) and matches a work-state token must have an
  entry in ``.github/firestore-collection-budgets.json`` ``budgets`` or a
  reviewed ``exempt`` entry.
* A **computed collection name** -- one the scanner cannot resolve statically,
  such as ``client.collection(f'new_{stage}_jobs')`` or
  ``db.collection(collectionName)`` -- that first appears in this change must
  have a ``dynamic`` entry naming the site, the expression, the collection
  pattern and the family budget. A collection path whose *collection* segments
  are static (``f'users/{uid}/jobs'``) resolves normally; only a dynamic
  collection segment is unresolved.
* A **computed family that grows** -- a computed site that already exists at the
  base revision keeps its ``site::expression`` key when the literal namespace
  tuple it reads gains a member (``NAMESPACES = ('prod', 'dev')`` becoming
  ``('prod', 'dev', 'preview')``), so the key-level check above cannot see the
  new collection. When the guard can enumerate the family from a literal
  sequence, a member that first appears in this change needs its own reviewed
  ``budgets`` entry or an ``exempt`` entry: the family budget was reviewed
  against the old membership, and a new namespace is a new read surface.

This is a disclosure ratchet, not semantic analysis. A name assembled from config
or a runtime registry cannot be seen at all, and only families the guard can
enumerate from literal sequences are compared between revisions. ``exempt`` is the
reviewed escape hatch for a name or site the heuristic misclassifies, and ``done``
is never inferred from the shape of the code.

Kill switch: ``FIRESTORE_COLLECTION_BUDGET_GUARD_ENABLED=0`` disables the guard
for an approved rollback and requires ``FIRESTORE_COLLECTION_BUDGET_GUARD_DISABLE_REASON``
so the disable is visible in the run log. Any other value fails closed.
"""

from __future__ import annotations

import argparse
import ast
import itertools
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REGISTRY = Path('.github/firestore-collection-budgets.json')
PYTHON_ROOT = 'backend'
WEB_ROOT = 'web'
WEB_SUFFIXES = ('.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs')
ENABLED_ENV = 'FIRESTORE_COLLECTION_BUDGET_GUARD_ENABLED'
REASON_ENV = 'FIRESTORE_COLLECTION_BUDGET_GUARD_DISABLE_REASON'
COLLECTION_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_]{2,60}$')
COLLECTION_PATTERN = re.compile(r'^[A-Za-z0-9_*]{2,80}$')
REVIEWED_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
BASIS_VALUES = frozenset({'measured', 'planning-bound'})

# A collection is work state when one of its words is a queue, job, lease,
# dispatch, retry, progress or recovery word. Deliberately narrow: ``state``,
# ``status``, ``ledger``, ``receipt`` and ``control`` are ordinary user-data
# words and would flag half the database.
WORK_STATE_TOKENS = frozenset(
    {
        # queues and work items
        'job',
        'jobs',
        'queue',
        'queues',
        'task',
        'tasks',
        'work',
        'worker',
        'workers',
        'backlog',
        'inbox',
        'spool',
        'buffer',
        'staging',
        'staged',
        'batch',
        'batches',
        # leases, claims and locks
        'lease',
        'leases',
        'claim',
        'claims',
        'lock',
        'locks',
        'reservation',
        'reservations',
        'hold',
        'holds',
        'inflight',
        'idempotency',
        'dedupe',
        # dispatch, retry and scheduling
        'dispatch',
        'dispatches',
        'outbox',
        'retry',
        'retries',
        'redrive',
        'deferral',
        'deferrals',
        'attempt',
        'attempts',
        'scheduler',
        'sequencer',
        'schedule',
        'schedules',
        'timer',
        'timers',
        'poll',
        'polls',
        'polling',
        'due',
        'overdue',
        'pending',
        'stuck',
        'dirty',
        'stale',
        'orphan',
        'orphans',
        'deadletter',
        'dlq',
        # progress, recovery and maintenance
        'run',
        'runs',
        'progress',
        'phase',
        'stage',
        'step',
        'iteration',
        'loop',
        'cycle',
        'tick',
        'checkpoint',
        'checkpoints',
        'cursor',
        'cursors',
        'heartbeat',
        'heartbeats',
        'recovery',
        'recoveries',
        'repair',
        'repairs',
        'rebuild',
        'rebuilds',
        'backfill',
        'backfills',
        'purge',
        'purges',
        'cleanup',
        'cleanups',
        'retention',
        'ttl',
        'expiry',
        'maintenance',
        'sweep',
        'shard',
        'watcher',
        'watchers',
        'supervisor',
        'coordinator',
        'leader',
        'election',
        'membership',
    }
)

BUDGET_FIELDS = (
    'owner',
    'unit',
    'reads_per_unit_budget',
    'reads_per_day_budget',
    'basis',
    'source',
    'reviewed',
)
DYNAMIC_FIELDS = ('site', 'expression', 'collection_pattern', *BUDGET_FIELDS)
TS_CALL = re.compile(
    r'(?P<legacy>\.(?P<legacy_kind>collection|collectionGroup)\s*\()'
    r'|(?<![.\w$])(?P<kind>collection|collectionGroup|doc)\s*\('
)
TS_CONSTANT = re.compile(
    r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*'
    r'(?:"([^"\n]*)"|\'([^\'\n]*)\'|`([^`\n$]*)`)'
    r'\s*(?:as\s+const)?\s*[;,]?\s*(?://.*)?$',
    re.MULTILINE,
)
TS_IDENTIFIER = re.compile(r'^[A-Za-z_$][\w$]*$')
COLLECTION_KEYWORDS = ('collection_id', 'collection_group_id')
# A module constant whose whole value is one string literal. Implicit concatenation
# and arithmetic intentionally do not match: they fall through to the computed-name
# path and fail closed instead of resolving to a partial name.
PYTHON_CONSTANT = re.compile(
    r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*(?::[ \t]*str)?[ \t]*=[ \t]*"
    r"(?:'([^'\n]*)'|\"([^\"\n]*)\")[ \t]*(?:#.*)?$",
    re.MULTILINE,
)
# A module-level tuple or list of plain string literals -- the namespace registry a
# computed collection name iterates over (``NAMESPACES = ('prod', 'dev')``). The
# membership of this sequence is the collection family a computed site can reach.
PYTHON_SEQUENCE = re.compile(
    r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*(?::[^=\n]+)?[ \t]*=[ \t]*" r"(?:\(([^\)]*)\)|\[([^\]]*)\])[ \t]*(?:#.*)?$",
    re.MULTILINE,
)
# A family is enumerated, never sampled: past this many combinations the guard stops
# claiming it knows the membership and leaves the site unexpanded, exactly as before.
MAX_FAMILY_MEMBERS = 64


@dataclass
class Inventory:
    collections: dict[str, list[str]] = field(default_factory=dict)
    dynamic: dict[str, list[str]] = field(default_factory=dict)
    # Concrete collection names a computed site can produce, when the guard can
    # enumerate them from a literal namespace sequence. Keyed like ``dynamic``.
    families: dict[str, set[str]] = field(default_factory=dict)


def work_state_token(name: str) -> str | None:
    """Return the word that makes ``name`` work state, or None."""
    words = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower().split('_')
    for word in words:
        if word in WORK_STATE_TOKENS:
            return word
    return None


def _excluded(relative: str) -> bool:
    parts = Path(relative).parts
    if 'node_modules' in parts or '.next' in parts:
        return True
    # Installed packages are not product code. Every worktree owns backend/.venv
    # and backend/.openapi-venv, so scanning them reports Firestore's own library
    # as "computed collection name" sites and rejects every backend push. Only
    # those two exact roots are skipped: a product directory that happens to be
    # named venv or site-packages is still scanned.
    if parts[:2] in (('backend', '.venv'), ('backend', '.openapi-venv')):
        return True
    if '/tests/' in relative or '/__tests__/' in relative or '/.test/' in relative:
        return True
    name = Path(relative).name
    return name.startswith('test_') or '.test.' in name or '.spec.' in name


def _path_names(value: str) -> list[str] | None:
    """Collection names along a Firestore path, or None when a name is not static.

    Firestore paths alternate collection/document, so the even-index segments are
    the collections. A single segment is the common ``.collection('name')`` shape.
    """
    names: list[str] = []
    for index, segment in enumerate(value.split('/')):
        if index % 2:
            continue
        if not COLLECTION_ID.match(segment):
            return None
        names.append(segment)
    return names or None


def _template_names(body: str) -> list[str] | None:
    """Collection names from a JS template literal body, or None if a name is dynamic."""
    names: list[str] = []
    for index, segment in enumerate(body.split('/')):
        if index % 2:
            continue
        if '${' in segment or not COLLECTION_ID.match(segment):
            return None
        names.append(segment)
    return names or None


# ---------------------------------------------------------------- Python surface


def _parse(sources: list[tuple[str, str]]) -> list[tuple[str, ast.Module]]:
    parsed: list[tuple[str, ast.Module]] = []
    for path, source in sources:
        try:
            parsed.append((path, ast.parse(source)))
        except SyntaxError:
            continue
    return parsed


def _fstring_names(node: ast.JoinedStr) -> list[str] | None:
    """Collection names from an f-string, or None when a collection segment is computed."""
    segments: list[tuple[str, bool]] = []
    text = ''
    dynamic = False
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for index, piece in enumerate(value.value.split('/')):
                if index:
                    segments.append((text, dynamic))
                    text, dynamic = '', False
                text += piece
        else:
            dynamic = True
    segments.append((text, dynamic))
    names: list[str] = []
    for index, (segment, is_dynamic) in enumerate(segments):
        if index % 2:
            continue
        if is_dynamic or not COLLECTION_ID.match(segment):
            return None
        names.append(segment)
    return names or None


def _python_resolve(argument: ast.expr, constants: dict[str, set[str]]) -> list[str] | None:
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return _path_names(argument.value)
    if isinstance(argument, ast.JoinedStr):
        return _fstring_names(argument)
    if isinstance(argument, ast.Name):
        return sorted(constants.get(argument.id, ())) or None
    if isinstance(argument, ast.Attribute):
        return sorted(constants.get(argument.attr, ())) or None
    return None


def _python_call_argument(node: ast.Call) -> ast.expr | None:
    """The collection argument of ``.collection()`` / ``.collection_group()``, positional or keyword.

    ``google.cloud.firestore`` accepts ``collection_id`` as a keyword, so a
    keyword-only call must resolve exactly like the positional form; returning
    None makes the caller record a dynamic site instead of skipping the call.
    """
    if node.args:
        return node.args[0]
    for keyword in node.keywords:
        if keyword.arg in COLLECTION_KEYWORDS:
            return keyword.value
    return None


def _sequence_values(body: str) -> list[str] | None:
    """Plain string members of a tuple/list literal body, or None if any member is not literal."""
    values: list[str] = []
    for piece in body.split(','):
        piece = piece.strip()
        if not piece:
            continue
        quote = piece[0]
        if len(piece) < 2 or quote not in ('"', "'") or piece[-1] != quote:
            return None
        values.append(piece[1:-1])
    return values or None


def _sequence_reference(node: ast.expr, sequences: dict[str, set[str]]) -> list[str] | None:
    """Literal values behind ``NAMESPACES``, ``NAMESPACES[index]`` or an inline tuple."""
    if isinstance(node, ast.Name):
        values = sequences.get(node.id)
        return sorted(values) if values else None
    if isinstance(node, ast.Subscript):
        return _sequence_reference(node.value, sequences)
    if isinstance(node, (ast.Tuple, ast.List)):
        values: list[str] = []
        for element in node.elts:
            if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
                return None
            values.append(element.value)
        return values or None
    return None


def _python_bindings(
    parsed: list[tuple[str, ast.Module]], sequences: dict[str, set[str]]
) -> dict[str, dict[str, set[str]]]:
    """Names whose value is drawn from a literal sequence, by ``for`` loop or assignment.

    ``for namespace in NAMESPACES`` and ``namespace = NAMESPACES[index]`` both make
    ``namespace`` one of the sequence's members. Bindings are kept per file: a name
    that is a parameter in one module must not inherit a same-named loop variable from
    another, or an unrelated tuple edit would flag every site that shares the name.
    """
    bindings: dict[str, dict[str, set[str]]] = {}
    for path, tree in parsed:
        local = bindings.setdefault(path, {})
        for node in ast.walk(tree):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                values = _sequence_reference(node.iter, sequences)
                if values:
                    local.setdefault(node.target.id, set()).update(values)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if node.value is None:
                    continue
                values = _sequence_reference(node.value, sequences)
                if not values:
                    continue
                for target in targets:
                    if isinstance(target, ast.Name):
                        local.setdefault(target.id, set()).update(values)
    return bindings


def _python_parts(node: ast.expr, bindings: dict[str, set[str]]) -> list[list[str]] | None:
    """Split a computed name into its literal and variable parts, each with its options."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [[node.value]]
    if isinstance(node, ast.Name):
        options = bindings.get(node.id)
        return [sorted(options)] if options else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _python_parts(node.left, bindings)
        right = _python_parts(node.right, bindings)
        if left is None or right is None:
            return None
        return left + right
    if isinstance(node, ast.JoinedStr):
        parts: list[list[str]] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append([value.value])
                continue
            if (
                isinstance(value, ast.FormattedValue)
                and value.conversion == -1
                and value.format_spec is None
                and isinstance(value.value, ast.Name)
            ):
                options = bindings.get(value.value.id)
                if not options:
                    return None
                parts.append(sorted(options))
                continue
            return None
        return parts or None
    return None


def _python_family(argument: ast.expr, bindings: dict[str, set[str]]) -> set[str] | None:
    """Every collection name a computed argument can produce, or None when unbounded.

    A grandfathered computed site keeps its ``site::expression`` key when the namespace
    tuple it reads grows, so the key-level check in ``findings`` never sees the new
    collection. Enumerating the family makes that growth comparable between revisions.
    """
    parts = _python_parts(argument, bindings)
    if parts is None:
        return None
    combinations = 1
    for part in parts:
        combinations *= len(part)
    if combinations > MAX_FAMILY_MEMBERS:
        return None
    names: set[str] = set()
    for combination in itertools.product(*parts):
        resolved = _path_names(''.join(combination))
        if resolved is None:
            return None
        names.update(resolved)
    return names or None


def _scan_python(sources: list[tuple[str, str]], inventory: Inventory) -> None:
    constants: dict[str, set[str]] = {}
    for _path, source in sources:
        for match in PYTHON_CONSTANT.finditer(source):
            value = match.group(2) if match.group(2) is not None else match.group(3)
            constants.setdefault(match.group(1), set()).update(_path_names(value) or [])

    sequences: dict[str, set[str]] = {}
    for _path, source in sources:
        for match in PYTHON_SEQUENCE.finditer(source):
            body = match.group(2) if match.group(2) is not None else match.group(3)
            values = _sequence_values(body)
            if values is not None:
                sequences.setdefault(match.group(1), set()).update(values)

    # Only files that name a Firestore collection call can contain a call site, so
    # parsing stays proportional to the Firestore surface instead of the backend.
    parsed = _parse([(path, source) for path, source in sources if 'collection' in source.lower()])
    bindings = _python_bindings(parsed, sequences)
    call_sites: list[tuple[str, int, ast.expr | None, str]] = []
    for path, tree in parsed:
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ('collection', 'collection_group')
            ):
                call_sites.append((path, node.lineno, _python_call_argument(node), ast.unparse(node)))

    for path, lineno, argument, call_text in call_sites:
        reference = f'{path}:{lineno}'
        resolved = None if argument is None else _python_resolve(argument, constants)
        if resolved is None:
            expression = call_text if argument is None else ast.unparse(argument)
            key = f'{path}::{expression}'
            inventory.dynamic.setdefault(key, []).append(reference)
            family = None if argument is None else _python_family(argument, bindings.get(path, {}))
            if family:
                inventory.families.setdefault(key, set()).update(family)
            continue
        for name in resolved:
            inventory.collections.setdefault(name, []).append(reference)


# --------------------------------------------------------------- web TS/JS surface


def _split_arguments(text: str, open_index: int) -> list[str] | None:
    """Top-level comma-separated argument texts of the call whose ``(`` is at open_index."""
    depth = 0
    quote: str | None = None
    current: list[str] = []
    arguments: list[str] = []
    index = open_index
    while index < len(text):
        char = text[index]
        if quote is not None:
            current.append(char)
            if char == '\\' and index + 1 < len(text):
                current.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ('"', "'", '`'):
            quote = char
            current.append(char)
            index += 1
            continue
        if char in '([{':
            depth += 1
            if depth > 1:
                current.append(char)
            index += 1
            continue
        if char in ')]}':
            depth -= 1
            if depth == 0:
                arguments.append(''.join(current).strip())
                return arguments
            current.append(char)
            index += 1
            continue
        if char == ',' and depth == 1:
            arguments.append(''.join(current).strip())
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    return None


def _ts_string(argument: str) -> tuple[str, bool] | None:
    """Return (body, is_template) for a quoted argument, or None."""
    argument = argument.strip()
    if len(argument) < 2 or argument[0] not in ('"', "'", '`') or argument[-1] != argument[0]:
        return None
    body = argument[1:-1]
    if '\\' in body:
        return None
    return body, argument[0] == '`'


def _ts_resolve(argument: str, constants: dict[str, set[str]]) -> list[str] | None:
    string = _ts_string(argument)
    if string is not None:
        body, is_template = string
        return _template_names(body) if is_template else _path_names(body)
    identifier = argument.strip()
    if TS_IDENTIFIER.match(identifier):
        values = constants.get(identifier)
        if not values:
            return None
        names: list[str] = []
        for value in sorted(values):
            resolved = _path_names(value)
            if resolved is None:
                return None
            names.extend(resolved)
        return names or None
    return None


def _blank(text: str) -> str:
    """Replace every character with a space, keeping newlines and therefore offsets."""
    return ''.join('\n' if char == '\n' else ' ' for char in text)


def strip_ts_comments(text: str) -> str:
    """Blank out ``//`` and ``/* */`` comments without moving a single offset.

    Comments name collections in prose (``// messages, rating in {1,-1}``) and a
    scanner that reads them would invent work-state collections from documentation.
    """
    output: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote is not None:
            output.append(char)
            if char == '\\' and index + 1 < len(text):
                output.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ('"', "'", '`'):
            quote = char
            output.append(char)
            index += 1
            continue
        if char == '/' and index + 1 < len(text):
            if text[index + 1] == '/':
                end = text.find('\n', index)
                end = len(text) if end == -1 else end
                output.append(_blank(text[index:end]))
                index = end
                continue
            if text[index + 1] == '*':
                end = text.find('*/', index + 2)
                end = len(text) if end == -1 else end + 2
                output.append(_blank(text[index:end]))
                index = end
                continue
        output.append(char)
        index += 1
    return ''.join(output)


def _scan_web(sources: list[tuple[str, str]], inventory: Inventory) -> None:
    sources = [(path, strip_ts_comments(text)) for path, text in sources]
    constants: dict[str, set[str]] = {}
    for _path, text in sources:
        for match in TS_CONSTANT.finditer(text):
            value = next((group for group in match.groups()[1:] if group is not None), None)
            if value is not None:
                constants.setdefault(match.group(1), set()).add(value)

    for path, text in sources:
        for match in TS_CALL.finditer(text):
            arguments = _split_arguments(text, text.index('(', match.start()))
            if not arguments:
                continue
            # Legacy ``db.collection(x)`` takes the collection first; the modular
            # ``collection(db, ...)`` and ``doc(db, ...)`` forms take the db first.
            segments = arguments if match.group('legacy') else arguments[1:]
            lineno = text.count('\n', 0, match.start()) + 1
            reference = f'{path}:{lineno}'
            for index, segment in enumerate(segments):
                if index % 2:  # odd segments are document ids, never collection names
                    continue
                resolved = _ts_resolve(segment, constants)
                if resolved is None:
                    inventory.dynamic.setdefault(f'{path}::{" ".join(segment.split())}', []).append(reference)
                    continue
                for name in resolved:
                    inventory.collections.setdefault(name, []).append(reference)


# --------------------------------------------------------------------- scanning


def scan_sources(python_sources: list[tuple[str, str]], web_sources: list[tuple[str, str]]) -> Inventory:
    inventory = Inventory()
    _scan_python(python_sources, inventory)
    _scan_web(web_sources, inventory)
    return inventory


def _read_tree(root: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    python_sources: list[tuple[str, str]] = []
    for path in sorted((root / PYTHON_ROOT).rglob('*.py')):
        relative = path.relative_to(root).as_posix()
        if _excluded(relative):
            continue
        python_sources.append((relative, path.read_text(encoding='utf-8')))
    web_sources: list[tuple[str, str]] = []
    for path in sorted((root / WEB_ROOT).rglob('*')):
        if not path.is_file() or path.suffix not in WEB_SUFFIXES:
            continue
        relative = path.relative_to(root).as_posix()
        if _excluded(relative):
            continue
        web_sources.append((relative, path.read_text(encoding='utf-8', errors='replace')))
    return python_sources, web_sources


def scan_tree(root: Path) -> Inventory:
    """Scan the working tree under ``root``."""
    return scan_sources(*_read_tree(root))


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ['git', *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def scan_git_tree(root: Path, revision: str) -> Inventory:
    """Scan the Firestore source surface at a git revision without checking it out."""
    listing = _git(root, 'ls-tree', '-r', '-z', revision, '--', PYTHON_ROOT, WEB_ROOT)
    entries: list[tuple[str, str]] = []
    for record in listing.decode('utf-8', errors='replace').split('\0'):
        if not record:
            continue
        meta, _, path = record.partition('\t')
        parts = meta.split()
        if len(parts) != 3 or parts[1] != 'blob' or _excluded(path):
            continue
        if path.endswith('.py') or Path(path).suffix in WEB_SUFFIXES:
            entries.append((path, parts[2]))
    if not entries:
        return Inventory()
    payload = ''.join(f'{sha}\n' for _path, sha in entries).encode()
    output = subprocess.run(
        ['git', 'cat-file', '--batch'],
        cwd=root,
        check=True,
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    python_sources: list[tuple[str, str]] = []
    web_sources: list[tuple[str, str]] = []
    position = 0
    for path, _sha in entries:
        newline = output.index(b'\n', position)
        header = output[position:newline].decode('utf-8', errors='replace').split()
        if len(header) != 3 or header[1] != 'blob':
            raise ValueError(f'{revision}:{path}: unexpected cat-file header {header!r}')
        size = int(header[2])
        start = newline + 1
        text = output[start : start + size].decode('utf-8', errors='replace')
        (python_sources if path.endswith('.py') else web_sources).append((path, text))
        position = start + size + 1
    return scan_sources(python_sources, web_sources)


# --------------------------------------------------------------------- registry


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_budget(entry: dict, where: str, errors: list[str]) -> None:
    if not isinstance(entry['owner'], str) or not entry['owner'].strip():
        errors.append(f'{where}: owner must name the lane that owns the collection')
    if not isinstance(entry['unit'], str) or not entry['unit'].strip():
        errors.append(f'{where}: unit must name the unit of work the budget divides by')
    if not _positive_int(entry['reads_per_unit_budget']):
        errors.append(f'{where}: reads_per_unit_budget must be a positive integer')
    if not _positive_int(entry['reads_per_day_budget']):
        errors.append(f'{where}: reads_per_day_budget must be a positive integer')
    if entry['basis'] not in BASIS_VALUES:
        errors.append(f'{where}: basis must be one of {sorted(BASIS_VALUES)}')
    if not isinstance(entry['source'], str) or not entry['source'].strip():
        errors.append(f'{where}: source must say where the number came from')
    if not isinstance(entry['reviewed'], str) or not REVIEWED_DATE.match(entry['reviewed']):
        errors.append(f'{where}: reviewed must be a YYYY-MM-DD date')


def load_registry(path: Path) -> tuple[dict[str, dict], dict[str, str], dict[str, dict], list[str]]:
    """Return (budgets, exemptions, dynamic declarations, schema errors)."""
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}, {}, {}, [f'{path}: registry is missing; every new work-state collection needs a budget entry']
    except json.JSONDecodeError as exc:
        return {}, {}, {}, [f'{path}: invalid JSON: {exc}']
    if not isinstance(payload, dict):
        return {}, {}, {}, [f'{path}: registry must be a JSON object']

    budgets: dict[str, dict] = {}
    for index, entry in enumerate(payload.get('budgets', [])):
        where = f'{path}: budgets[{index}]'
        if not isinstance(entry, dict):
            errors.append(f'{where}: must be an object')
            continue
        missing = [name for name in ('collection', *BUDGET_FIELDS) if name not in entry]
        if missing:
            errors.append(f'{where}: missing {", ".join(missing)}')
            continue
        collection = entry['collection']
        if not isinstance(collection, str) or not COLLECTION_ID.match(collection):
            errors.append(f'{where}: collection must be a Firestore collection id, got {collection!r}')
            continue
        if collection in budgets:
            errors.append(f'{where}: duplicate budget for {collection}')
            continue
        _validate_budget(entry, where, errors)
        budgets[collection] = entry

    dynamic: dict[str, dict] = {}
    for index, entry in enumerate(payload.get('dynamic', [])):
        where = f'{path}: dynamic[{index}]'
        if not isinstance(entry, dict):
            errors.append(f'{where}: must be an object')
            continue
        missing = [name for name in DYNAMIC_FIELDS if name not in entry]
        if missing:
            errors.append(f'{where}: missing {", ".join(missing)}')
            continue
        site = entry['site']
        expression = entry['expression']
        pattern = entry['collection_pattern']
        if not isinstance(site, str) or not site.strip():
            errors.append(f'{where}: site must be a repository-relative path')
            continue
        if not isinstance(expression, str) or not expression.strip():
            errors.append(f'{where}: expression must be the computed argument as the scanner sees it')
            continue
        if not isinstance(pattern, str) or not COLLECTION_PATTERN.match(pattern):
            errors.append(f'{where}: collection_pattern must be a collection pattern such as new_*_jobs')
            continue
        key = f'{site}::{" ".join(expression.split())}'
        if key in dynamic:
            errors.append(f'{where}: duplicate dynamic declaration for {key}')
            continue
        _validate_budget(entry, where, errors)
        dynamic[key] = entry

    exempt: dict[str, str] = {}
    for index, entry in enumerate(payload.get('exempt', [])):
        where = f'{path}: exempt[{index}]'
        if not isinstance(entry, dict):
            errors.append(f'{where}: must be an object')
            continue
        reason = entry.get('reason')
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f'{where}: reason must explain why this name or site is not work state')
            continue
        collection = entry.get('collection')
        site = entry.get('site')
        expression = entry.get('expression')
        if collection is not None and (site is not None or expression is not None):
            errors.append(f'{where}: declare either a collection or a site and expression, not both')
            continue
        if collection is not None:
            if not isinstance(collection, str) or not COLLECTION_ID.match(collection):
                errors.append(f'{where}: collection must be a Firestore collection id, got {collection!r}')
                continue
            key = collection
        elif site is not None and expression is not None:
            if not isinstance(site, str) or not site.strip():
                errors.append(f'{where}: site must be a repository-relative path')
                continue
            if not isinstance(expression, str) or not expression.strip():
                errors.append(f'{where}: expression must be the computed argument as the scanner sees it')
                continue
            key = f'{site}::{" ".join(expression.split())}'
        else:
            errors.append(f'{where}: needs a collection, or a site and expression')
            continue
        if key in exempt:
            errors.append(f'{where}: duplicate exemption for {key}')
            continue
        if key in budgets or key in dynamic:
            errors.append(f'{where}: {key} is both declared and exempt')
            continue
        exempt[key] = reason
    return budgets, exempt, dynamic, errors


# ---------------------------------------------------------------------- verdict


def findings(
    head: Inventory,
    base: Inventory,
    budgets: dict[str, dict],
    exempt: dict[str, str],
    dynamic: dict[str, dict],
) -> list[str]:
    """New work-state collections and undeclared computed names in this change."""
    errors: list[str] = []
    for name in sorted(set(head.collections) - set(base.collections)):
        token = work_state_token(name)
        if token is None or name in budgets or name in exempt:
            continue
        errors.append(f'{name} (matched {token!r}) at {", ".join(head.collections[name][:3])}')
    for key in sorted(set(head.dynamic) - set(base.dynamic)):
        if key in dynamic or key in exempt:
            continue
        site, _, expression = key.partition('::')
        references = ', '.join(head.dynamic[key][:3])
        errors.append(
            f'computed collection name at {references}: {expression} '
            f'(site {site}); declare a dynamic entry with the collection pattern and family budget'
        )
    # A grandfathered computed site keeps its key when the namespace tuple it reads
    # grows, so the key-level check above cannot see the new collection. Compare the
    # enumerable family instead: a member that first appears in this change needs its
    # own reviewed budget (or exemption), because the family budget was reviewed
    # against the old membership.
    for key in sorted(set(head.dynamic) & set(base.dynamic)):
        if key in exempt:
            continue
        base_family = base.families.get(key)
        if not base_family:
            continue
        site, _, expression = key.partition('::')
        references = ', '.join(head.dynamic[key][:3])
        for name in sorted(head.families.get(key, set()) - base_family):
            if name in budgets or name in exempt:
                continue
            errors.append(
                f'computed collection family at {references}: {expression} (site {site}) '
                f'gained {name}; budget the new collection or exempt it'
            )
    return errors


def kill_switch() -> tuple[str, str]:
    """Return (state, detail) where state is enabled, disabled or invalid."""
    raw = os.environ.get(ENABLED_ENV, '1').strip()
    if raw in ('', '1'):
        return 'enabled', ''
    if raw == '0':
        reason = os.environ.get(REASON_ENV, '').strip()
        if not reason:
            return 'invalid', f'{ENABLED_ENV}=0 requires {REASON_ENV} so the disable is visible'
        return 'disabled', reason
    return 'invalid', f'{ENABLED_ENV} must be 1 or 0, got {raw!r}'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--base', default='origin/main', help='git revision the change is compared against')
    parser.add_argument('--registry', type=Path, default=REGISTRY)
    parser.add_argument(
        '--print-inventory', action='store_true', help='print every collection and computed site in the working tree'
    )
    args = parser.parse_args()

    state, detail = kill_switch()
    if state == 'invalid':
        print(f'FAIL: {detail}')
        return 1
    if state == 'disabled':
        print(f'WARNING: Firestore collection budget guard disabled by {ENABLED_ENV}=0: {detail}')
        return 0

    root = args.root.resolve()
    head = scan_tree(root)
    if args.print_inventory:
        print(
            json.dumps(
                {
                    'collections': head.collections,
                    'dynamic': head.dynamic,
                    'families': {key: sorted(values) for key, values in sorted(head.families.items())},
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    registry_path = args.registry if args.registry.is_absolute() else root / args.registry
    budgets, exempt, dynamic, errors = load_registry(registry_path)
    if errors:
        print('FAIL: .github/firestore-collection-budgets.json is not a valid budget registry.')
        print(*errors, sep='\n')
        return 1

    try:
        base = scan_git_tree(root, args.base)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f'FAIL: cannot read the base revision {args.base!r}: {exc}')
        print('The guard compares against the merge base; fetch it (git fetch origin main) and rerun.')
        return 1

    errors = findings(head, base, budgets, exempt, dynamic)
    if not errors:
        return 0
    print('FAIL: new Firestore queue/job/lease collection without a read budget (M8).')
    print('The batch pipeline reached ~1.36B reads/day on unbudgeted job/queue/lease state.')
    print(*errors, sep='\n')
    print(
        'Add a reviewed entry to .github/firestore-collection-budgets.json with owner, unit, '
        'reads_per_unit_budget, reads_per_day_budget, basis, source and reviewed date.'
    )
    print('A computed name needs a dynamic entry (site, expression, collection_pattern, same budget fields).')
    print('A computed family that gained a member needs a budget entry for that collection, or an exemption.')
    print('If the name or site is not work state, add it to the registry\'s exempt list with a reason.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

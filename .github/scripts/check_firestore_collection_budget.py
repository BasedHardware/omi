#!/usr/bin/env python3
"""M8: a new Firestore queue/job/lease collection must declare a read budget.

The batch pipeline's Firestore job, queue and lease collections grew to ~1.36B of
~1.83B reads/day before anyone wrote the number down (firestore-reads-program
diagnosis, 2026-11-11). This guard makes the next subsystem state its read budget
in the same PR that introduces the collection, so a 530-reads/unit pipeline has to
be a reviewed decision instead of a surprise on the bill.

Scope: collections that hold *work state* -- queues, jobs, leases, claims, retry
and dispatch state, progress and recovery markers. User-data collections are out
of scope. The check is diff-scoped: a collection that already exists at the base
revision is grandfathered, and only a name that first appears in this change needs
an entry in ``.github/firestore-collection-budgets.json``.

This is a disclosure ratchet, not semantic analysis. A collection name built at
runtime (an f-string, a function argument, a value read from config) cannot be
resolved statically and escapes detection; reviewers still read the diff. The
registry's ``exempt`` list is the reviewed escape hatch for a name the token
heuristic misclassifies.

Kill switch: ``FIRESTORE_COLLECTION_BUDGET_GUARD_ENABLED=0`` disables the guard
for an approved rollback and requires ``FIRESTORE_COLLECTION_BUDGET_GUARD_DISABLE_REASON``
so the disable is visible in the run log. Any other value fails closed.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path('.github/firestore-collection-budgets.json')
SCAN_ROOT = Path('backend')
ENABLED_ENV = 'FIRESTORE_COLLECTION_BUDGET_GUARD_ENABLED'
REASON_ENV = 'FIRESTORE_COLLECTION_BUDGET_GUARD_DISABLE_REASON'
COLLECTION_ID = re.compile(r'^[a-z][a-z0-9_]{2,60}$')
REVIEWED_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
BASIS_VALUES = frozenset({'measured', 'planning-bound'})

# A collection is work state when one of its underscore-separated tokens is a
# queue, job, lease, dispatch, retry, progress or recovery word. Deliberately
# narrow: ``state``, ``status``, ``ledger``, ``receipt`` and ``control`` are
# ordinary user-data words and would flag half the database.
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
    'collection',
    'owner',
    'unit',
    'reads_per_unit_budget',
    'reads_per_day_budget',
    'basis',
    'source',
    'reviewed',
)


def work_state_token(name: str) -> str | None:
    """Return the token that makes ``name`` work state, or None."""
    for token in name.split('_'):
        if token in WORK_STATE_TOKENS:
            return token
    return None


def _excluded(relative: str) -> bool:
    return '/tests/' in relative or Path(relative).name.startswith('test_')


def _literal_collection(value: ast.AST) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str) and COLLECTION_ID.match(value.value):
        return value.value
    return None


def _parse(sources: list[tuple[str, str]]) -> list[tuple[str, ast.Module]]:
    parsed: list[tuple[str, ast.Module]] = []
    for path, source in sources:
        try:
            parsed.append((path, ast.parse(source)))
        except SyntaxError:
            continue
    return parsed


def scan_sources(sources: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Map each Firestore collection name to the ``path:line`` references that use it."""
    parsed = _parse(sources)
    constants: dict[str, set[str]] = {}
    call_sites: list[tuple[str, int, ast.expr]] = []
    for path, tree in parsed:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                value = _literal_collection(node.value)
                if value is None:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        constants.setdefault(target.id, set()).add(value)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'collection'
                and node.args
            ):
                call_sites.append((path, node.lineno, node.args[0]))

    found: dict[str, list[str]] = {}
    for path, lineno, argument in call_sites:
        names: list[str] = []
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            names = [argument.value]
        elif isinstance(argument, ast.Name):
            names = sorted(constants.get(argument.id, ()))
        elif isinstance(argument, ast.Attribute):
            names = sorted(constants.get(argument.attr, ()))
        for name in names:
            if COLLECTION_ID.match(name):
                found.setdefault(name, []).append(f'{path}:{lineno}')
    return found


def scan_tree(root: Path) -> dict[str, list[str]]:
    """Scan the working tree under ``root``."""
    sources: list[tuple[str, str]] = []
    for path in sorted((root / SCAN_ROOT).rglob('*.py')):
        relative = path.relative_to(root).as_posix()
        if _excluded(relative):
            continue
        sources.append((relative, path.read_text(encoding='utf-8')))
    return scan_sources(sources)


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ['git', *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def scan_git_tree(root: Path, revision: str) -> dict[str, list[str]]:
    """Scan ``backend/**/*.py`` at a git revision without checking it out."""
    listing = _git(root, 'ls-tree', '-r', '-z', revision, '--', SCAN_ROOT.as_posix())
    entries: list[tuple[str, str]] = []
    for record in listing.decode('utf-8', errors='replace').split('\0'):
        if not record:
            continue
        meta, _, path = record.partition('\t')
        parts = meta.split()
        if len(parts) != 3 or parts[1] != 'blob' or not path.endswith('.py') or _excluded(path):
            continue
        entries.append((path, parts[2]))
    if not entries:
        return {}
    payload = ''.join(f'{sha}\n' for _path, sha in entries).encode()
    output = subprocess.run(
        ['git', 'cat-file', '--batch'],
        cwd=root,
        check=True,
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    sources: list[tuple[str, str]] = []
    position = 0
    for path, _sha in entries:
        newline = output.index(b'\n', position)
        header = output[position:newline].decode('utf-8', errors='replace').split()
        if len(header) != 3 or header[1] != 'blob':
            raise ValueError(f'{revision}:{path}: unexpected cat-file header {header!r}')
        size = int(header[2])
        start = newline + 1
        sources.append((path, output[start : start + size].decode('utf-8', errors='replace')))
        position = start + size + 1
    return scan_sources(sources)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def load_registry(path: Path) -> tuple[dict[str, dict], dict[str, str], list[str]]:
    """Return (budgets by collection, exemptions by collection, schema errors)."""
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}, {}, [f'{path}: registry is missing; every new work-state collection needs a budget entry']
    except json.JSONDecodeError as exc:
        return {}, {}, [f'{path}: invalid JSON: {exc}']
    if not isinstance(payload, dict):
        return {}, {}, [f'{path}: registry must be a JSON object']

    budgets: dict[str, dict] = {}
    for index, entry in enumerate(payload.get('budgets', [])):
        where = f'{path}: budgets[{index}]'
        if not isinstance(entry, dict):
            errors.append(f'{where}: must be an object')
            continue
        missing = [field for field in BUDGET_FIELDS if field not in entry]
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
        budgets[collection] = entry

    exempt: dict[str, str] = {}
    for index, entry in enumerate(payload.get('exempt', [])):
        where = f'{path}: exempt[{index}]'
        if not isinstance(entry, dict):
            errors.append(f'{where}: must be an object')
            continue
        collection = entry.get('collection')
        reason = entry.get('reason')
        if not isinstance(collection, str) or not COLLECTION_ID.match(collection):
            errors.append(f'{where}: collection must be a Firestore collection id, got {collection!r}')
            continue
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f'{where}: reason must explain why this name is not work state')
            continue
        if collection in exempt:
            errors.append(f'{where}: duplicate exemption for {collection}')
            continue
        if collection in budgets:
            errors.append(f'{where}: {collection} is both budgeted and exempt')
            continue
        exempt[collection] = reason
    return budgets, exempt, errors


def unbudgeted(
    head: dict[str, list[str]],
    base: dict[str, list[str]],
    budgets: dict[str, dict],
    exempt: dict[str, str],
) -> list[str]:
    """New work-state collections that have neither a budget nor a reviewed exemption."""
    errors: list[str] = []
    for name in sorted(set(head) - set(base)):
        token = work_state_token(name)
        if token is None or name in budgets or name in exempt:
            continue
        references = ', '.join(head[name][:3])
        errors.append(f'{name} (matched {token!r}) at {references}')
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
        '--print-inventory', action='store_true', help='print every collection found in the working tree'
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
        print(json.dumps(head, indent=2, sort_keys=True))
        return 0

    registry_path = args.registry if args.registry.is_absolute() else root / args.registry
    budgets, exempt, errors = load_registry(registry_path)
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

    errors = unbudgeted(head, base, budgets, exempt)
    if not errors:
        return 0
    print('FAIL: new Firestore queue/job/lease collection without a read budget (M8).')
    print('The batch pipeline reached ~1.36B reads/day on unbudgeted job/queue/lease state.')
    print(*errors, sep='\n')
    print(
        'Add a reviewed entry to .github/firestore-collection-budgets.json with owner, unit, '
        'reads_per_unit_budget, reads_per_day_budget, basis, source and reviewed date.'
    )
    print('If the name is not work state, add it to the registry\'s exempt list with a reason.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

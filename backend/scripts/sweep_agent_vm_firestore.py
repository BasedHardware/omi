#!/usr/bin/env python3
"""One-time sweep of the retired Agent VM Firestore state.

PR #11795 removed the Cloud Agent VM control plane. The Firestore records it
wrote are now inert: nothing in `main` reads them, and the fleet is empty. This
script removes the leftovers so the account-deletion cleanup path that still
references them can be retired in turn.

Targets, in the order the runbook runs them:

  1. `users/{uid}.agentVm` maps, plus the legacy no-writer top-level fields
     `restartFailures`, `lastRestartFailureAt`, `lastQueryAt` when a document
     still carries them.
  2. `users/{uid}/agentVmMigrations` subcollection documents.
  3. `account_deletions/{uid}.late_agent_vm_cleanup` markers.
  4. The standalone `agent_vm_reconciler_leases` collection.

Safety properties:

  * Dry run is the default. Nothing is written without `--apply`.
  * Output is aggregate counts only. Firebase uids and VM names are never
    printed, because the legacy VM naming embeds `uid[:12]`.
  * Every target is idempotent: a second run reports zero and writes nothing.
  * Writes are batched (Firestore caps a batch at 500 operations) and each
    target is independently resumable via `--target`.

Usage:
    python scripts/sweep_agent_vm_firestore.py                    # dry run, all targets
    python scripts/sweep_agent_vm_firestore.py --target users --limit 100
    python scripts/sweep_agent_vm_firestore.py --apply            # execute
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, cast

import firebase_admin
from firebase_admin import firestore

# firebase_admin ships partial/py.typed stubs that surface as partially-unknown
# member types; the SDK boundary is treated as Any (mirrors database/_client.py).
fa: Any = cast(Any, firebase_admin)
fs: Any = cast(Any, firestore)

USERS = 'users'
ACCOUNT_DELETIONS = 'account_deletions'
MIGRATIONS = 'agentVmMigrations'
LEASES = 'agent_vm_reconciler_leases'

# `agentVm` is the live map. The three scalars were written by earlier
# provisioners directly on the user document and have had no writer since.
LEGACY_USER_FIELDS = ('restartFailures', 'lastRestartFailureAt', 'lastQueryAt')

BATCH_LIMIT = 500
PAGE_SIZE = 500

TARGETS = ('users', 'migrations', 'markers', 'leases')


class _Counter:
    def __init__(self) -> None:
        self.scanned = 0
        self.matched = 0
        self.written = 0
        self.failed = 0

    def report(self, target: str, *, applied: bool) -> None:
        mode = 'APPLIED' if applied else 'DRY-RUN'
        print(
            f'{mode} {target}: scanned={self.scanned} matched={self.matched} '
            f'written={self.written} failed={self.failed}'
        )


def _flush(db: Any, batch: Any, counter: _Counter, *, applied: bool) -> Any:
    """Commit a batch when it is full, returning a fresh one."""
    if not applied:
        return batch
    try:
        batch.commit()
    except Exception as exc:  # noqa: BLE001 — one bad batch must not abort the sweep
        counter.failed += 1
        print(f'WARN batch commit failed: {type(exc).__name__}', file=sys.stderr)
    return db.batch()


def _sweep_users(db: Any, *, applied: bool, limit: int) -> _Counter:
    counter = _Counter()
    batch = db.batch()
    pending = 0
    last_doc: Any = None

    while True:
        if limit and counter.scanned >= limit:
            break
        query = db.collection(USERS).order_by('__name__').limit(PAGE_SIZE)
        if last_doc is not None:
            query = query.start_after(last_doc)
        page: list[Any] = list(query.stream())
        if not page:
            break

        for snapshot in page:
            if limit and counter.scanned >= limit:
                break
            counter.scanned += 1
            last_doc = snapshot
            data = cast(dict[str, Any], snapshot.to_dict() or {})

            update: dict[str, Any] = {}
            if 'agentVm' in data:
                update['agentVm'] = fs.DELETE_FIELD
            for field in LEGACY_USER_FIELDS:
                if field in data:
                    update[field] = fs.DELETE_FIELD
            if not update:
                continue

            counter.matched += 1
            if applied:
                batch.update(snapshot.reference, update)
                pending += 1
                counter.written += 1
                if pending >= BATCH_LIMIT:
                    batch = _flush(db, batch, counter, applied=applied)
                    pending = 0

        if counter.scanned % 5000 == 0:
            print(f'  users: scanned={counter.scanned} matched={counter.matched}')

    if applied and pending:
        _flush(db, batch, counter, applied=applied)
    return counter


def _sweep_migrations(db: Any, *, applied: bool, limit: int) -> _Counter:
    """Delete every `users/{uid}/agentVmMigrations` document.

    A collection-group query finds the journals without walking all 100K+ user
    documents. Deleting the documents leaves an empty subcollection, which
    Firestore does not bill or expose.
    """
    counter = _Counter()
    batch = db.batch()
    pending = 0

    for snapshot in db.collection_group(MIGRATIONS).stream():
        if limit and counter.scanned >= limit:
            break
        counter.scanned += 1
        counter.matched += 1
        if applied:
            batch.delete(snapshot.reference)
            pending += 1
            counter.written += 1
            if pending >= BATCH_LIMIT:
                batch = _flush(db, batch, counter, applied=applied)
                pending = 0

    if applied and pending:
        _flush(db, batch, counter, applied=applied)
    return counter


def _sweep_markers(db: Any, *, applied: bool, limit: int) -> _Counter:
    counter = _Counter()
    batch = db.batch()
    pending = 0
    last_doc: Any = None

    while True:
        if limit and counter.scanned >= limit:
            break
        query = db.collection(ACCOUNT_DELETIONS).order_by('__name__').limit(PAGE_SIZE)
        if last_doc is not None:
            query = query.start_after(last_doc)
        page: list[Any] = list(query.stream())
        if not page:
            break

        for snapshot in page:
            if limit and counter.scanned >= limit:
                break
            counter.scanned += 1
            last_doc = snapshot
            data = cast(dict[str, Any], snapshot.to_dict() or {})
            if 'late_agent_vm_cleanup' not in data:
                continue

            counter.matched += 1
            if applied:
                batch.update(snapshot.reference, {'late_agent_vm_cleanup': fs.DELETE_FIELD})
                pending += 1
                counter.written += 1
                if pending >= BATCH_LIMIT:
                    batch = _flush(db, batch, counter, applied=applied)
                    pending = 0

    if applied and pending:
        _flush(db, batch, counter, applied=applied)
    return counter


def _sweep_leases(db: Any, *, applied: bool, limit: int) -> _Counter:
    counter = _Counter()
    batch = db.batch()
    pending = 0

    for snapshot in db.collection(LEASES).stream():
        if limit and counter.scanned >= limit:
            break
        counter.scanned += 1
        counter.matched += 1
        if applied:
            batch.delete(snapshot.reference)
            pending += 1
            counter.written += 1
            if pending >= BATCH_LIMIT:
                batch = _flush(db, batch, counter, applied=applied)
                pending = 0

    if applied and pending:
        _flush(db, batch, counter, applied=applied)
    return counter


_SWEEPERS = {
    'users': _sweep_users,
    'migrations': _sweep_migrations,
    'markers': _sweep_markers,
    'leases': _sweep_leases,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Write the deletions. Without this flag the run is a dry run.',
    )
    parser.add_argument(
        '--target',
        action='append',
        choices=TARGETS,
        help='Sweep only this target (repeatable). Defaults to every target.',
    )
    parser.add_argument('--limit', type=int, default=0, help='Max documents to scan per target (0 = all)')
    args = parser.parse_args()

    if not fa._apps:
        fa.initialize_app()
    db: Any = fs.client()

    selected = tuple(args.target) if args.target else TARGETS
    print(f'{"APPLY" if args.apply else "DRY-RUN"}: targets={",".join(selected)} limit={args.limit or "all"}')

    failed = 0
    for target in selected:
        counter = _SWEEPERS[target](db, applied=args.apply, limit=args.limit)
        counter.report(target, applied=args.apply)
        failed += counter.failed

    if not args.apply:
        print('Dry run only. Re-run with --apply to delete.')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())

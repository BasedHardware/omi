#!/usr/bin/env python3
"""One-time sweep of the retired Agent VM Firestore state.

PR #11795 removed the Cloud Agent VM control plane. The Firestore records it
wrote are retired in source. Before using this script, the operator must
independently verify deployed writers and fleet retirement; source removal is
not evidence that the deployed fleet is empty. This script removes leftovers
so the account-deletion cleanup path can be retired in turn.

Targets, in the order the runbook runs them:

  1. `users/{uid}.agentVm` maps, plus the legacy no-writer top-level fields
     `restartFailures`, `lastRestartFailureAt`, `lastQueryAt` when a document
     still carries them.
  2. `users/{uid}/agentVmMigrations` subcollection documents.
  3. `account_deletions/{uid}.late_agent_vm_cleanup` markers.
  4. The standalone `agent_vm_reconciler_leases` collection.

Safety properties:

  * `--project` is required. There is no ambient default: the operator names the
    Firestore project on the command line, the client is built for exactly that
    project through the Firebase app's projectId option. The printed client
    project confirms that binding, not that the operator chose the right project
    or that ambient credentials belong to it. The operator verifies those facts.
  * Dry run is the default. Nothing is written without `--apply`.
  * Every receipt line carries the selected project, and separately reports the
    operations `queued` into batches versus the operations `committed` by a
    successful batch commit. A batch whose commit fails moves its queued
    operations to `failed_ops`; they are never reported as written.
  * Output is aggregate counts only. Firebase uids and VM names are never
    printed, because the legacy VM naming embeds `uid[:12]`.
  * Every target is idempotent: a second run reports zero and writes nothing.
    A failed batch is re-scanned and retried by the next run.
  * Writes are batched (Firestore caps a batch at 500 operations) and each
    target is independently resumable via `--target`.

Usage:
    python scripts/sweep_agent_vm_firestore.py --project based-hardware
    python scripts/sweep_agent_vm_firestore.py --project based-hardware --target users --limit 100
    python scripts/sweep_agent_vm_firestore.py --project based-hardware --apply
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
    """Per-target accounting.

    ``queued`` counts operations staged into a batch; ``committed`` counts
    operations whose batch commit returned successfully. They are only equal
    when every commit was acknowledged. ``failed_ops`` are queued operations
    whose commit was not acknowledged; a transport error can leave the server
    outcome unknown, so a post-run scan is still required.
    """

    def __init__(self) -> None:
        self.scanned = 0
        self.matched = 0
        self.queued = 0
        self.committed = 0
        self.failed_ops = 0
        self.failed_batches = 0

    @property
    def failed(self) -> bool:
        return self.failed_batches > 0

    def report(self, target: str, *, project: str, applied: bool) -> None:
        mode = 'APPLIED' if applied else 'DRY-RUN'
        print(
            f'{mode} project={project} target={target} scanned={self.scanned} matched={self.matched} '
            f'queued={self.queued} committed={self.committed} '
            f'failed_ops={self.failed_ops} failed_batches={self.failed_batches}'
        )


def _flush(db: Any, batch: Any, counter: _Counter, pending: int, *, project: str, applied: bool) -> Any:
    """Commit a full batch, returning a fresh one.

    A failed commit is not fatal to the sweep, but it is never counted as a
    write: the batch's queued operations move to ``failed_ops`` and the caller
    gets an empty batch so the remaining documents still get their attempt.
    """
    if not applied:
        return batch
    try:
        batch.commit()
    except Exception as exc:  # noqa: BLE001 — one bad batch must not abort the sweep
        counter.failed_batches += 1
        counter.failed_ops += pending
        print(
            f'WARN project={project} batch commit failed ({pending} ops): {type(exc).__name__}',
            file=sys.stderr,
        )
    else:
        counter.committed += pending
    return db.batch()


def _sweep_users(db: Any, *, project: str, applied: bool, limit: int) -> _Counter:
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
                counter.queued += 1
                if pending >= BATCH_LIMIT:
                    batch = _flush(db, batch, counter, pending, project=project, applied=applied)
                    pending = 0

        if counter.scanned and counter.scanned % 5000 == 0:
            print(f'  project={project} target=users scanned={counter.scanned} matched={counter.matched}')

    if applied and pending:
        _flush(db, batch, counter, pending, project=project, applied=applied)
    return counter


def _sweep_migrations(db: Any, *, project: str, applied: bool, limit: int) -> _Counter:
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
            counter.queued += 1
            if pending >= BATCH_LIMIT:
                batch = _flush(db, batch, counter, pending, project=project, applied=applied)
                pending = 0

    if applied and pending:
        _flush(db, batch, counter, pending, project=project, applied=applied)
    return counter


def _sweep_markers(db: Any, *, project: str, applied: bool, limit: int) -> _Counter:
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
                counter.queued += 1
                if pending >= BATCH_LIMIT:
                    batch = _flush(db, batch, counter, pending, project=project, applied=applied)
                    pending = 0

    if applied and pending:
        _flush(db, batch, counter, pending, project=project, applied=applied)
    return counter


def _sweep_leases(db: Any, *, project: str, applied: bool, limit: int) -> _Counter:
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
            counter.queued += 1
            if pending >= BATCH_LIMIT:
                batch = _flush(db, batch, counter, pending, project=project, applied=applied)
                pending = 0

    if applied and pending:
        _flush(db, batch, counter, pending, project=project, applied=applied)
    return counter


_SWEEPERS = {
    'users': _sweep_users,
    'migrations': _sweep_migrations,
    'markers': _sweep_markers,
    'leases': _sweep_leases,
}


def _client_project(db: Any) -> str:
    """The project the live client resolves to, or an empty string when unknown."""
    project = getattr(db, 'project', None)
    return project if isinstance(project, str) else ''


def _refuse_project_mismatch(requested: str, actual: str) -> int:
    """Abort before any read or write when the client is not on the selected project."""
    print(
        f'REFUSED: --project={requested} but the Firestore client resolves to project={actual or "unknown"}. '
        'Nothing was read or written.',
        file=sys.stderr,
    )
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--project',
        required=True,
        help='Firestore/GCP project id to sweep. Required: the run never inherits an ambient project.',
    )
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

    project = args.project.strip()
    if not project:
        print('REFUSED: --project must name a Firestore project.', file=sys.stderr)
        return 2

    # Firebase Admin binds Firestore's project through the App options; its
    # firestore.client() API does not accept a project keyword. A named app also
    # avoids inheriting an already-initialized default app's ambient project.
    app = fa.initialize_app(options={'projectId': project}, name='agent-vm-retirement-sweep')
    db: Any = fs.client(app=app)
    actual_project = _client_project(db)
    if actual_project != project:
        return _refuse_project_mismatch(project, actual_project)

    selected = tuple(args.target) if args.target else TARGETS
    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'{mode} project={project} targets={",".join(selected)} limit={args.limit or "all"}')

    failed_targets: list[str] = []
    totals = _Counter()
    for target in selected:
        counter = _SWEEPERS[target](db, project=project, applied=args.apply, limit=args.limit)
        counter.report(target, project=project, applied=args.apply)
        totals.scanned += counter.scanned
        totals.matched += counter.matched
        totals.queued += counter.queued
        totals.committed += counter.committed
        totals.failed_ops += counter.failed_ops
        totals.failed_batches += counter.failed_batches
        if counter.failed:
            failed_targets.append(target)

    totals.report('TOTAL', project=project, applied=args.apply)
    if failed_targets:
        print(
            f'INCOMPLETE project={project} targets_with_failed_batches={",".join(failed_targets)} '
            'retry before treating the sweep as complete.',
            file=sys.stderr,
        )
    if not args.apply:
        print(f'Dry run only. Re-run with --project {project} --apply to delete.')
    return 1 if failed_targets else 0


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())

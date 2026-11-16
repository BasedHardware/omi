"""One bounded operator page with a private, target-bound durable checkpoint.

Run under a supervised hard process deadline, with retained-target IAM auth.
No new target, owner identity, retention interval or production cohort is
inferred. A copy-source pass remains available with all mirror kills off.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile

from database.batch_pipeline_store import FirestoreStore
from database.jobstore.connection import Pool, iam_connector
from database.jobstore.dual_store import DualStore, MIRRORED_TABLES
from database.jobstore.postgres_store import PostgresStore
from database.jobstore.reconcile import decode_cursor, process_page
from utils.staging_fence import (
    PROD_JOBSTORE_NAMESPACE,
    is_staging,
    jobstore_production_context_matches,
    jobstore_production_mirror_configured,
    jobstore_shadow_admits,
)

_MAX_CHECKPOINT_BYTES = 32768
_MAX_CURSOR_BYTES = 16384


def _private_regular(descriptor: int) -> None:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o077
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
    ):
        raise ValueError('operator state must be a private owned regular file')


@contextmanager
def _checkpoint_lock(path: Path):
    # Keep this inode after closing: unlinking a lock lets another process lock
    # a different inode while a previous waiter still holds the original one.
    lock_path = path.with_name(path.name + '.lock')
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    try:
        _private_regular(descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def _checkpoint_read(path: Path, scope: str) -> dict:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        return {'version': 1, 'scope': scope, 'cursor': None, 'passes': 0}
    try:
        _private_regular(descriptor)
        # Bound bytes actually read, including a file that grows after fstat.
        with os.fdopen(descriptor, 'rb', closefd=False) as source:
            payload = source.read(_MAX_CHECKPOINT_BYTES + 1)
        if len(payload) > _MAX_CHECKPOINT_BYTES:
            raise ValueError('checkpoint exceeds bound')
        value = json.loads(payload)
    finally:
        os.close(descriptor)
    if (
        not isinstance(value, dict)
        or type(value.get('version')) is not int
        or value.get('version') != 1
        or value.get('scope') != scope
        or type(value.get('passes')) is not int
        or value['passes'] < 0
        or 'cursor' not in value
        or (
            value['cursor'] is not None
            and (not isinstance(value['cursor'], str) or len(value['cursor']) > _MAX_CURSOR_BYTES)
        )
    ):
        raise ValueError('checkpoint scope or format mismatch')
    return value


def _checkpoint_write(path: Path, state: dict) -> None:
    descriptor, name = tempfile.mkstemp(prefix='.jobstore-page-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(state, output)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def reconcile_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='python -m database.jobstore reconcile-page')
    parser.add_argument('namespace')
    parser.add_argument('--source', choices=['primary', 'copy'], required=True)
    parser.add_argument('--table', choices=sorted(MIRRORED_TABLES), required=True)
    parser.add_argument('--state-file', type=Path, required=True)
    parser.add_argument('--max-rows', type=int, required=True)
    parser.add_argument('--max-primary-reads', type=int, required=True)
    parser.add_argument('--max-statements', type=int, required=True)
    parser.add_argument('--page-seconds', type=float, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if (
        not 1 <= args.max_rows <= 1000
        or args.max_primary_reads < (2 if args.source == 'primary' else 1)
        or args.max_statements <= 0
        or not math.isfinite(args.page_seconds)
        or args.page_seconds <= 0
    ):
        print(json.dumps({'outcome': 'refused', 'reason': 'invalid_budgets'}))
        return 2
    if args.namespace == PROD_JOBSTORE_NAMESPACE and not is_staging():
        admitted = jobstore_production_context_matches()
        if args.source == 'primary':
            admitted = admitted and jobstore_production_mirror_configured()
    else:
        admitted = jobstore_shadow_admits(args.namespace)
    if not admitted:
        print(json.dumps({'outcome': 'refused', 'reason': 'namespace_or_context'}))
        return 2
    target = tuple(
        os.environ.get(name, '').strip() for name in ('JOBSTORE_PG_HOST', 'JOBSTORE_PG_DATABASE', 'JOBSTORE_PG_USER')
    )
    if not all(target) or not args.state_file.is_absolute() or not args.state_file.parent.is_dir():
        print(json.dumps({'outcome': 'refused', 'reason': 'target_or_checkpoint'}))
        return 2
    # Separate checkpoints for apply/dry-run prevent a census from skipping unapplied pages.
    scope = hashlib.sha256(
        json.dumps([target, args.namespace, args.source, args.table, args.apply]).encode()
    ).hexdigest()
    pool = None
    try:
        with _checkpoint_lock(args.state_file):
            state = _checkpoint_read(args.state_file, scope)
            # Validate cursor syntax and its embedded scope before any client,
            # credential refresh or connection. Public output never includes it.
            decode_cursor(state['cursor'], args.namespace, args.source, args.table)
            primary = FirestoreStore(args.namespace)
            pool = Pool('', size=1, connect=iam_connector(*target))
            # Connection/auth is outside the warm page budget. The supervising
            # job bounds startup and the whole process; no cursor advances here.
            with pool.connection(timeout=args.page_seconds):
                pass
            mirror = DualStore(primary, PostgresStore(args.namespace, pool=pool, customer_client=None))
            result = process_page(
                mirror,
                source=args.source,
                table=args.table,
                cursor=state['cursor'],
                max_rows=args.max_rows,
                max_primary_reads=args.max_primary_reads,
                max_statements=args.max_statements,
                budget_s=args.page_seconds,
                apply=args.apply,
            )
            state.update(cursor=result.cursor, passes=state['passes'] + int(result.end_of_pass))
            _checkpoint_write(args.state_file, state)
            print(
                json.dumps(
                    {'outcome': 'completed', 'apply': args.apply, 'passes': state['passes'], **result.public_report()}
                )
            )
        return 0
    except Exception:
        # Do not print provider text, identifiers, target, checkpoint or cursor.
        print(json.dumps({'outcome': 'retry_required', 'reason': 'operation_failed'}))
        return 1
    finally:
        if pool is not None:
            try:
                pool.close()
            except Exception:
                # A cleanup provider exception must not expose target/cursor
                # text or replace the already-published operation result.
                pass

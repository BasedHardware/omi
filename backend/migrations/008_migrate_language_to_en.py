"""Backfill conversations with missing/empty language to 'en'.

Conversation ``language`` now defaults to 'en' for new conversations; this
one-off migration backfills existing Firestore conversations that were
created with the language field unset or empty. Values already set (any
non-empty language) are preserved, regardless of conversation source.

Operational safety:
- Users are read in bounded pages ordered by document id; conversations are
  streamed per user and projected to the ``language`` field only, so no full
  collection is materialized in memory.
- Concurrency is configurable (default 8 workers) instead of an unbounded
  parallel sweep.
- ``--max-users`` / ``--max-writes`` bound a staged rollout.
- ``--start-after <uid>`` resumes from a logged user id (reruns are
  idempotent: already-migrated documents are skipped).
- Any per-user failure makes the process exit non-zero, so automation cannot
  record the migration as successful with records left unmigrated.
- ``--dry-run`` reports prospective updates without writing.

Usage:
    # Preview (no writes)
    python 008_migrate_language_to_en.py --dry-run

    # Staged rollout, first 1000 users
    python 008_migrate_language_to_en.py --max-users 1000

    # Resume after the last user id logged by a previous run
    python 008_migrate_language_to_en.py --start-after <uid>

    # Full run
    python 008_migrate_language_to_en.py

Environment:
    Uses the backend's shared Firestore client (``database._client``), which
    honors SERVICE_ACCOUNT_JSON and GOOGLE_APPLICATION_CREDENTIALS.
"""

import argparse
import logging
import os
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

# Add project root to the Python path before local imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database._client import get_firestore_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BATCH_SIZE = 499  # Firestore batch write ceiling


def iter_user_ids(db, start_after=None, page_size=1000, max_users=0):
    """Yield user ids in bounded pages ordered by document id."""
    collected = 0
    last_id = start_after
    users_col = db.collection('users')
    while not max_users or collected < max_users:
        query = users_col.order_by('__name__').limit(page_size)
        if last_id:
            query = query.start_after({'__name__': users_col.document(last_id)})
        page = list(query.stream())
        if not page:
            break
        for doc in page:
            if max_users and collected >= max_users:
                return
            yield doc.id
            collected += 1
        last_id = page[-1].id


def process_user_conversations(db, uid, dry_run=False):
    """Migrate empty language fields to 'en' for a single user.

    Returns (updates, writes): conversations needing the field set, and batch
    writes actually committed (0 when dry_run). Raises on Firestore failure so
    the caller can fail the run instead of reporting success.
    """
    conversations_ref = db.collection('users').document(uid).collection('conversations').select(['language'])

    updates = 0
    writes = 0
    batch = db.batch()
    batch_count = 0

    for doc in conversations_ref.stream():
        language = doc.to_dict().get('language')

        # We only update if language is None or empty string
        if not language:
            updates += 1
            if not dry_run:
                batch.update(doc.reference, {'language': 'en'})
                batch_count += 1
                if batch_count >= BATCH_SIZE:
                    batch.commit()
                    writes += batch_count
                    batch = db.batch()
                    batch_count = 0

    if batch_count > 0 and not dry_run:
        batch.commit()
        writes += batch_count

    return updates, writes


def main():
    parser = argparse.ArgumentParser(description='Migrate empty conversation language to en')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    parser.add_argument('--workers', type=int, default=8, help='Concurrent users to process (default: 8)')
    parser.add_argument('--max-users', type=int, default=0, help='Stop after this many users (0 = unlimited)')
    parser.add_argument(
        '--max-writes', type=int, default=0, help='Stop scheduling after this many writes (0 = unlimited)'
    )
    parser.add_argument('--start-after', default=None, help='Resume after this user id')
    parser.add_argument('--page-size', type=int, default=1000, help='Users per page when paging')
    args = parser.parse_args()

    db = get_firestore_client()

    started = time.time()
    total_updates = 0
    total_writes = 0
    users_processed = 0
    failures = 0
    contiguous_uid = args.start_after

    uid_iter = iter_user_ids(db, start_after=args.start_after, page_size=args.page_size, max_users=args.max_users)
    write_budget_exhausted = False

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        pending = {}

        def submit_next() -> None:
            nonlocal pending, uid_iter
            try:
                uid = next(uid_iter)
            except StopIteration:
                return
            pending[executor.submit(process_user_conversations, db, uid, args.dry_run)] = uid

        for _ in range(args.workers):
            submit_next()

        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                uid = pending.pop(future)
                try:
                    updates, writes = future.result()
                except Exception as e:
                    failures += 1
                    logger.error('Error processing %s: %s', uid, e)
                    continue
                users_processed += 1
                contiguous_uid = uid
                if updates:
                    total_updates += updates
                    total_writes += writes
                    if args.max_writes and total_writes >= args.max_writes:
                        write_budget_exhausted = True
                        logger.info('Reached --max-writes %d, stopping', args.max_writes)
            if write_budget_exhausted:
                break
            for _ in done:
                submit_next()

    elapsed = time.time() - started
    if failures:
        logger.error('Finished in %.1fs with %d failed user(s)', elapsed, failures)
        logger.error(
            'Re-run the migration WITHOUT --start-after: it is idempotent, and the checkpoint after '
            'out-of-order completion may skip users that failed earlier. To resume from the last '
            'contiguous successfully processed user, pass --start-after %s.',
            contiguous_uid,
        )
        sys.exit(1)

    verb = 'would be updated' if args.dry_run else 'updated'
    logger.info('Done in %.1fs', elapsed)
    logger.info(
        'Results: %d conversations %s across %d users (%d writes).', total_updates, verb, users_processed, total_writes
    )


if __name__ == '__main__':
    main()

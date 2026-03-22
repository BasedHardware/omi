"""Migration: unlock conversations/memories/action_items incorrectly locked by sync soft cap bug.

PR #5878 incorrectly set should_lock=True when fair-use soft caps triggered in
the sync endpoint. This locked conversations for users who exceeded the 2h daily
soft cap via sync, regardless of subscription tier. Fixed in PR #5896.

This script reads impacted UIDs from a file (one per line), verifies each user
has an active paid (unlimited/pro) subscription, then unlocks their conversations,
memories, and action items.

Usage:
    # Dry run (default) — shows what would be unlocked:
    python scripts/unlock_soft_cap_locked.py --uids-file /tmp/impacted_uids.txt

    # Execute the unlock:
    python scripts/unlock_soft_cap_locked.py --uids-file /tmp/impacted_uids.txt --execute

    # The UIDs file should contain one UID per line (blank lines and # comments ignored).
"""

import argparse
import logging
import sys

import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

PAID_PLANS = {'unlimited', 'pro'}


def read_uids(filepath: str) -> list[str]:
    """Read UIDs from a file, one per line. Ignores blank lines and # comments."""
    uids = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                uids.append(line)
    return uids


def get_subscription_plan(db, uid: str) -> str | None:
    """Read the user's subscription plan from Firestore."""
    doc = db.collection('users').document(uid).get(['subscription'])
    if not doc.exists:
        return None
    data = doc.to_dict()
    sub = data.get('subscription', {})
    return sub.get('plan')


def count_locked(db, uid: str, collection_name: str) -> int:
    """Count documents with is_locked=True in a user's subcollection."""
    ref = db.collection('users').document(uid).collection(collection_name)
    query = ref.where(filter=FieldFilter('is_locked', '==', True))
    return sum(1 for _ in query.stream())


def unlock_collection(db, uid: str, collection_name: str) -> int:
    """Unlock all documents with is_locked=True. Returns count unlocked."""
    ref = db.collection('users').document(uid).collection(collection_name)
    query = ref.where(filter=FieldFilter('is_locked', '==', True))

    batch = db.batch()
    count = 0
    for doc in query.stream():
        batch.update(doc.reference, {'is_locked': False})
        count += 1
        if count % 499 == 0:
            batch.commit()
            batch = db.batch()

    if count % 499 != 0:
        batch.commit()

    return count


def main():
    parser = argparse.ArgumentParser(
        description='Unlock conversations/memories/action_items incorrectly locked by sync soft cap bug (PR #5878)'
    )
    parser.add_argument('--uids-file', required=True, help='Path to file with one UID per line')
    parser.add_argument('--execute', action='store_true', help='Actually unlock (default is dry-run)')
    args = parser.parse_args()

    uids = read_uids(args.uids_file)
    if not uids:
        logger.error('No UIDs found in %s', args.uids_file)
        sys.exit(1)

    logger.info('Loaded %d UIDs from %s', len(uids), args.uids_file)
    logger.info('Mode: %s', 'EXECUTE' if args.execute else 'DRY-RUN')

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    db = firestore.client()

    collections = ['conversations', 'memories', 'action_items']
    total_unlocked = 0
    skipped_uids = []

    for uid in uids:
        plan = get_subscription_plan(db, uid)

        if plan not in PAID_PLANS:
            logger.warning('SKIP uid=%s plan=%s (not a paid plan, will not unlock)', uid, plan)
            skipped_uids.append((uid, plan))
            continue

        # Count locked items
        counts = {c: count_locked(db, uid, c) for c in collections}
        locked_total = sum(counts.values())

        if locked_total == 0:
            logger.info('uid=%s plan=%s — no locked items found, nothing to do', uid, plan)
            continue

        logger.info(
            'uid=%s plan=%s — locked: conversations=%d memories=%d action_items=%d',
            uid,
            plan,
            counts['conversations'],
            counts['memories'],
            counts['action_items'],
        )

        if args.execute:
            for collection_name in collections:
                if counts[collection_name] > 0:
                    unlocked = unlock_collection(db, uid, collection_name)
                    logger.info('  UNLOCKED %d %s for uid=%s', unlocked, collection_name, uid)
                    total_unlocked += unlocked
        else:
            logger.info('  (dry-run, no changes made)')
            total_unlocked += locked_total

    logger.info('--- Summary ---')
    logger.info('Total UIDs processed: %d', len(uids))
    logger.info('Skipped (not paid): %d', len(skipped_uids))
    for uid, plan in skipped_uids:
        logger.info('  skipped uid=%s plan=%s', uid, plan)
    if args.execute:
        logger.info('Total items unlocked: %d', total_unlocked)
    else:
        logger.info('Total items WOULD unlock: %d (run with --execute to apply)', total_unlocked)


if __name__ == '__main__':
    main()

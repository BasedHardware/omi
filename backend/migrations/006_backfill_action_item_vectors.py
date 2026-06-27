"""
Backfill existing action items to Pinecone vector database (ns4).

Iterates all users' action_items subcollections, generates embeddings
for each description, and upserts to Pinecone. Same approach as
005_backfill_memory_vectors.py.

Usage:
    python 006_backfill_action_item_vectors.py [--dry-run] [--uid USER_ID] [--workers N]

Environment:
    GOOGLE_APPLICATION_CREDENTIALS: Path to Firebase service account key
    PINECONE_API_KEY: Pinecone API key
    PINECONE_INDEX_NAME: Pinecone index name
    OPENAI_API_KEY: OpenAI API key for embeddings
"""

import firebase_admin
from firebase_admin import credentials, firestore
import sys
import os
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load backend/.env before importing modules that read env at import time
# (vector_db.py and utils.llm.clients build Pinecone/OpenAI clients eagerly)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from database.vector_db import upsert_action_item_vectors_batch
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
except ValueError:
    pass
except Exception as e:
    logger.error("Error initializing Firebase Admin SDK. Make sure GOOGLE_APPLICATION_CREDENTIALS is set.")
    logger.error(e)
    sys.exit(1)

db = firestore.client()


def get_all_user_ids():
    users_ref = db.collection('users')
    return [doc.id for doc in users_ref.stream()]


def get_user_action_items(uid: str):
    items_ref = db.collection('users').document(uid).collection('action_items')
    items = []
    for doc in items_ref.stream():
        data = doc.to_dict()
        data['id'] = doc.id
        items.append(data)
    return items


BATCH_SIZE = 100


def process_user(uid: str, dry_run: bool = False) -> dict:
    logger.info(f"Processing user: {uid}")
    items = get_user_action_items(uid)
    logger.info(f"  Found {len(items)} action items")

    eligible = [item for item in items if item.get('description', '')]
    skipped = len(items) - len(eligible)
    results = {'total': len(items), 'success': 0, 'skipped': skipped, 'errors': 0}

    if dry_run:
        results['success'] = len(eligible)
        logger.info(f"  Dry run: {len(eligible)} would be upserted, {skipped} skipped (empty description)")
        return results

    for i in range(0, len(eligible), BATCH_SIZE):
        batch = eligible[i : i + BATCH_SIZE]
        batch_items = [{'action_item_id': item['id'], 'description': item['description']} for item in batch]
        try:
            written = upsert_action_item_vectors_batch(uid, batch_items)
            results['success'] += written
        except Exception as e:
            results['errors'] += len(batch)
            logger.error(f"  Batch error at offset {i}: {e}")

    logger.info(f"  Done: {results['success']} ok, {results['skipped']} skipped, {results['errors']} errors")
    return results


def main():
    parser = argparse.ArgumentParser(description='Backfill action item vectors to Pinecone')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    parser.add_argument('--uid', type=str, help='Process a single user')
    parser.add_argument('--workers', type=int, default=8, help='Parallel user workers (default: 8)')
    args = parser.parse_args()

    if args.uid:
        user_ids = [args.uid]
    else:
        user_ids = get_all_user_ids()

    workers = 1 if args.uid else max(1, args.workers)
    logger.info(f"Processing {len(user_ids)} users (dry_run={args.dry_run}, workers={workers})")
    start = time.time()

    totals = {'users': 0, 'items': 0, 'success': 0, 'skipped': 0, 'errors': 0}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_user, uid, args.dry_run): uid for uid in user_ids}
        for future in as_completed(futures):
            uid = futures[future]
            try:
                result = future.result()
                totals['users'] += 1
                totals['items'] += result['total']
                totals['success'] += result['success']
                totals['skipped'] += result['skipped']
                totals['errors'] += result['errors']
            except Exception as e:
                logger.error(f"Failed to process user {uid}: {e}")
                totals['errors'] += 1

    elapsed = time.time() - start
    logger.info(f"\nDone in {elapsed:.1f}s")
    logger.info(f"Users: {totals['users']}, Items: {totals['items']}")
    logger.info(f"Success: {totals['success']}, Skipped: {totals['skipped']}, Errors: {totals['errors']}")


if __name__ == '__main__':
    main()

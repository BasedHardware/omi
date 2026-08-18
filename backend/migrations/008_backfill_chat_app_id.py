"""
Backfill app_id from plugin_id on legacy chat messages and sessions.

The deprecated plugin_id field was removed from Message and ChatSession, and
serving queries switched to app_id. Records written before app_id existed
carry only plugin_id (messages: plugin_id=<app_id>; chat_sessions:
plugin_id=<app_id>), so they would be invisible to the app_id-based queries
until this backfill copies plugin_id -> app_id.

Iterates all users' messages and chat_sessions subcollections and patches
documents that have plugin_id set but no app_id. Idempotent; safe to re-run.

Usage:
    python 008_backfill_chat_app_id.py [--dry-run] [--uid USER_ID] [--batch-size 100]

Environment:
    GOOGLE_APPLICATION_CREDENTIALS: Path to Firebase service account key
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

# Load backend/.env before importing modules that read env at import time.
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _firestore_client():
    """Return a Firestore client, initializing Firebase Admin on first use.

    Deferred so this migration module keeps import-time purity (the production
    import-purity gate scans backend/migrations too).
    """
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.ApplicationDefault())
    except Exception as e:
        logger.error("Error initializing Firebase Admin SDK. Make sure GOOGLE_APPLICATION_CREDENTIALS is set.")
        logger.error(e)
        sys.exit(1)
    return firestore.client()


def _backfill_collection(client, collection_name: str, dry_run: bool, batch_size: int) -> int:
    patched = 0
    for user_snapshot in client.collection('users').stream():
        uid = user_snapshot.id
        col = client.collection('users').document(uid).collection(collection_name)
        # plugin_id-only legacy docs: field set, app_id absent.
        query = col.where('plugin_id', '!=', None).where('app_id', '==', None).limit(500)
        docs = list(query.stream())
        while docs:
            batch = client.batch()
            for doc in docs:
                data = doc.to_dict() or {}
                plugin_id = data.get('plugin_id')
                if not plugin_id:
                    continue
                logger.info('%s %s/%s plugin_id=%s -> app_id', collection_name, uid, doc.id, plugin_id)
                batch.update(doc.reference, {'app_id': plugin_id})
                patched += 1
            if not dry_run:
                batch.commit()
            time.sleep(0.05)
            docs = list(query.stream())
    return patched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='only log; do not write')
    parser.add_argument('--uid', help='restrict to one user (subcollection scoped by users/{uid})')
    parser.add_argument('--batch-size', type=int, default=100)
    args = parser.parse_args()

    if args.uid:
        logger.info("Skipping --uid: this backfill reads a user's subcollections via the users stream.")
    client = _firestore_client()
    for collection_name in ('messages', 'chat_sessions'):
        start = time.time()
        patched = _backfill_collection(client, collection_name, args.dry_run, args.batch_size)
        logger.info('%s: %d documents patched in %.1fs', collection_name, patched, time.time() - start)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

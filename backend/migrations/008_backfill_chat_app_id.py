"""
Backfill app_id from plugin_id on legacy chat messages and sessions.

The deprecated plugin_id field was removed from Message and ChatSession, and
serving queries switched to app_id. Records written before app_id existed
carry only plugin_id (messages: plugin_id=<app_id>; chat_sessions:
plugin_id=<app_id>), so they would be invisible to the app_id-based queries
until this backfill copies plugin_id -> app_id.

Iterates all users' messages and chat_sessions subcollections and patches
documents missing app_id. Copies plugin_id when present; otherwise writes
explicit app_id=None so main-chat / missing-field rows become visible to
app_id == None serving queries. Idempotent; safe to re-run.

Usage:
    python 008_backfill_chat_app_id.py [--dry-run] [--uid USER_ID] [--batch-size 100]

Environment:
    GOOGLE_APPLICATION_CREDENTIALS: Path to Firebase service account key
"""

import sys
import os
import argparse
import time
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from database._client import get_firestore_client

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _firestore_client():
    """Pin to the customer-data project via SERVICE_ACCOUNT_JSON.

    ADC / GOOGLE_CLOUD_PROJECT can identify the compute or dev project;
    get_firestore_client() uses the customer-data service account when present.
    """
    return get_firestore_client()


def _backfill_collection(client, collection_name: str, dry_run: bool, batch_size: int, uid: str | None) -> int:
    """
    Scan documents missing app_id (including main-chat rows with no plugin_id).

    Uses an unfiltered, name-ordered cursor so missing-field documents are not
    skipped by plugin_id != None. Dry-run advances each page. Honors --uid.
    """
    patched = 0
    if uid:
        doc_ref = client.collection('users').document(uid)
        user_snapshots = [doc_ref.get()] if doc_ref.get().exists else []
    else:
        user_snapshots = client.collection('users').stream()

    for user_snapshot in user_snapshots:
        uid_val = user_snapshot.id
        col = client.collection('users').document(uid_val).collection(collection_name)

        # Full-collection cursor: do not require plugin_id != None. That filter
        # hides missing-field and main-chat (plugin_id null) rows.
        cursor = None
        while True:
            query = col.order_by('__name__').limit(batch_size)
            if cursor is not None:
                query = query.start_after(cursor)

            docs = list(query.stream())
            if not docs:
                break

            batch = client.batch()
            page_patched = 0
            for doc in docs:
                data = doc.to_dict() or {}
                plugin_id_val = data.get('plugin_id')
                if 'app_id' not in data:
                    # Missing field is invisible to app_id == None queries.
                    app_id_val = plugin_id_val if plugin_id_val else None
                    logger.info('%s %s/%s missing app_id -> %s', collection_name, uid_val, doc.id, app_id_val)
                    batch.update(doc.reference, {'app_id': app_id_val})
                    page_patched += 1
                elif data.get('app_id') is None and plugin_id_val:
                    logger.info('%s %s/%s plugin_id=%s -> app_id', collection_name, uid_val, doc.id, plugin_id_val)
                    batch.update(doc.reference, {'app_id': plugin_id_val})
                    page_patched += 1

            patched += page_patched
            if not dry_run and page_patched:
                batch.commit()
                time.sleep(0.05)

            cursor = docs[-1]

    return patched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='only log; do not write')
    parser.add_argument('--uid', help='restrict to one user (subcollection scoped by users/{uid})')
    parser.add_argument('--batch-size', type=int, default=100, help='batch size (Firestore max 500)')
    args = parser.parse_args()

    batch_size = min(args.batch_size, 500)
    client = _firestore_client()
    for collection_name in ('messages', 'chat_sessions'):
        start = time.time()
        patched = _backfill_collection(client, collection_name, args.dry_run, batch_size, args.uid)
        logger.info('%s: %d documents patched in %.1fs', collection_name, patched, time.time() - start)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

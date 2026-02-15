"""
Migration script to backfill existing memories to Pinecone vector database.

This script:
1. Fetches all existing memories from Firestore
2. Generates embeddings for each memory
3. Upserts the vectors to Pinecone in the 'ns2' namespace
4. Updates legacy categories to 'system', 'interesting', or 'manual'

Usage:
    python 005_backfill_memory_vectors.py [--dry-run] [--batch-size 100] [--uid USER_ID]

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
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Add project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.vector_db import upsert_memory_vector, MEMORIES_NAMESPACE
from models.memories import LEGACY_TO_NEW_CATEGORY

# Initialize Firebase Admin SDK
try:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
except ValueError:
    # App already initialized
    pass
except Exception as e:
    print("Error initializing Firebase Admin SDK. Make sure GOOGLE_APPLICATION_CREDENTIALS is set.")
    print(e)
    sys.exit(1)

db = firestore.client()


def get_all_user_ids():
    """Get all user IDs from Firestore."""
    users_ref = db.collection('users')
    return [doc.id for doc in users_ref.stream()]


def get_user_memories(uid: str):
    """Get all memories for a user."""
    memories_ref = db.collection('users').document(uid).collection('memories')
    memories = []
    for doc in memories_ref.stream():
        memory_data = doc.to_dict()
        memory_data['id'] = doc.id
        memories.append(memory_data)
    return memories


def normalize_category(category: str) -> str:
    """Normalize legacy categories to new format (system/interesting/manual)."""
    if category == 'manual':
        return 'manual'
    if category == 'system':
        return 'system'
    if category == 'interesting':
        return 'interesting'
    # Legacy categories map via LEGACY_TO_NEW_CATEGORY (to system or interesting)
    if category in LEGACY_TO_NEW_CATEGORY:
        return LEGACY_TO_NEW_CATEGORY[category]
    # Default to system for unknown categories (including 'auto')
    return 'system'


def update_memory_category(uid: str, memory_id: str, new_category: str):
    """Update memory category in Firestore."""
    memory_ref = db.collection('users').document(uid).collection('memories').document(memory_id)
    memory_ref.update({'category': new_category})


def process_memory(uid: str, memory: dict, dry_run: bool = False) -> dict:
    """Process a single memory - generate embedding and upsert to Pinecone."""
    memory_id = memory['id']
    content = memory.get('content', '')
    old_category = memory.get('category', 'system')
    new_category = normalize_category(old_category)

    if not content:
        return {'status': 'skipped', 'reason': 'empty content', 'memory_id': memory_id}

    result = {
        'memory_id': memory_id,
        'old_category': old_category,
        'new_category': new_category,
    }

    if dry_run:
        result['status'] = 'dry_run'
        return result

    try:
        # Upsert vector to Pinecone
        upsert_memory_vector(uid, memory_id, content, new_category)

        # Update category in Firestore if it changed
        if old_category != new_category:
            update_memory_category(uid, memory_id, new_category)
            result['category_updated'] = True

        result['status'] = 'success'
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)

    return result


def process_user(uid: str, dry_run: bool = False, batch_size: int = 100) -> dict:
    """Process all memories for a user."""
    print(f"\nProcessing user: {uid}")

    memories = get_user_memories(uid)
    total = len(memories)

    if total == 0:
        print(f"  No memories found for user {uid}")
        return {'uid': uid, 'total': 0, 'processed': 0, 'errors': 0}

    print(f"  Found {total} memories")

    processed = 0
    errors = 0
    category_updates = 0

    for i, memory in enumerate(memories):
        result = process_memory(uid, memory, dry_run)

        if result['status'] == 'success':
            processed += 1
            if result.get('category_updated'):
                category_updates += 1
        elif result['status'] == 'error':
            errors += 1
            print(f"    Error processing memory {result['memory_id']}: {result.get('error')}")
        elif result['status'] == 'dry_run':
            processed += 1

        # Progress update every batch_size memories
        if (i + 1) % batch_size == 0:
            print(f"    Processed {i + 1}/{total} memories...")

        # Rate limiting to avoid overwhelming the APIs
        if not dry_run and (i + 1) % 10 == 0:
            time.sleep(0.1)

    print(f"  Completed: {processed} processed, {errors} errors, {category_updates} category updates")

    return {
        'uid': uid,
        'total': total,
        'processed': processed,
        'errors': errors,
        'category_updates': category_updates,
    }


def main():
    parser = argparse.ArgumentParser(description='Backfill memory vectors to Pinecone')
    parser.add_argument('--dry-run', action='store_true', help='Run without making changes')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for progress updates')
    parser.add_argument('--uid', type=str, help='Process only a specific user ID')
    parser.add_argument('--limit', type=int, help='Limit number of users to process')

    args = parser.parse_args()

    print("=" * 60)
    print("Memory Vector Backfill Migration")
    print("=" * 60)

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")

    print(f"Pinecone namespace: {MEMORIES_NAMESPACE}")
    print()

    # Get users to process
    if args.uid:
        user_ids = [args.uid]
    else:
        print("Fetching all user IDs...")
        user_ids = get_all_user_ids()
        print(f"Found {len(user_ids)} users")

        if args.limit:
            user_ids = user_ids[: args.limit]
            print(f"Limiting to {args.limit} users")

    # Process users
    total_stats = {
        'users_processed': 0,
        'total_memories': 0,
        'total_processed': 0,
        'total_errors': 0,
        'total_category_updates': 0,
    }

    start_time = time.time()

    for uid in user_ids:
        try:
            result = process_user(uid, dry_run=args.dry_run, batch_size=args.batch_size)
            total_stats['users_processed'] += 1
            total_stats['total_memories'] += result['total']
            total_stats['total_processed'] += result['processed']
            total_stats['total_errors'] += result['errors']
            total_stats['total_category_updates'] += result.get('category_updates', 0)
        except Exception as e:
            print(f"Error processing user {uid}: {e}")
            total_stats['total_errors'] += 1

    elapsed_time = time.time() - start_time

    # Summary
    print()
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Users processed: {total_stats['users_processed']}")
    print(f"Total memories: {total_stats['total_memories']}")
    print(f"Successfully processed: {total_stats['total_processed']}")
    print(f"Errors: {total_stats['total_errors']}")
    print(f"Category updates: {total_stats['total_category_updates']}")
    print(f"Elapsed time: {elapsed_time:.2f} seconds")

    if args.dry_run:
        print("\nThis was a DRY RUN. Run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()

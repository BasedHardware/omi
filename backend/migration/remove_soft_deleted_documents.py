import os
import sys
import argparse
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

import time
import concurrent.futures
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

# Initialize Firestore client directly.
# Assumes GOOGLE_APPLICATION_CREDENTIALS environment variable is set.
db = firestore.Client()

NUM_THREADS = 16

USER_SUBCOLLECTIONS = ['conversations', 'memories', 'messages', 'files', 'chat_sessions', 'people']

ROOT_COLLECTIONS = ['plugins_data']


def get_users_uid():
    """Fetches all user UIDs from the 'users' collection."""
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]
    # return ['eLCxTds6QyUAHraZug48i8ZlGL23']


def delete_documents_in_batch(query, batch_size=450):
    """
    Deletes documents returned by a query in batches.
    Returns the number of documents deleted.
    """
    deleted_count = 0
    processed_in_call = 0
    while True:
        docs = query.limit(batch_size).stream()
        batch = db.batch()
        num_docs_in_batch = 0
        for doc in docs:
            batch.delete(doc.reference)
            num_docs_in_batch += 1

        if num_docs_in_batch == 0:
            break

        batch.commit()
        deleted_count += num_docs_in_batch
        processed_in_call += num_docs_in_batch
        print(f"    Deleted {num_docs_in_batch} documents from a batch.")  # Verbose
    return deleted_count


def process_user_subcollections(user_id: str) -> int:
    """Processes all specified subcollections for a single user to delete soft-deleted documents."""
    user_deleted_count = 0
    user_ref = db.collection('users').document(user_id)
    # print(f"  Processing subcollections for user: {user_id}")
    for subcollection_name in USER_SUBCOLLECTIONS:
        # print(f"    Checking subcollection: {subcollection_name} for user {user_id}")
        collection_ref = user_ref.collection(subcollection_name)
        query = collection_ref.where(filter=FieldFilter('deleted', '==', True))
        deleted_in_subcollection = delete_documents_in_batch(query)
        if deleted_in_subcollection > 0:
            print(f"    Deleted {deleted_in_subcollection} docs from {subcollection_name} for user {user_id}.")
        user_deleted_count += deleted_in_subcollection
    return user_deleted_count


def format_time(seconds):
    """Formats seconds into a human-readable string H:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Remove soft-deleted documents from Firestore.")
    parser.add_argument(
        '--ignore-users-file', type=str, help='Path to a file containing user UIDs to ignore, one UID per line.'
    )
    return parser.parse_args()


def migrate_remove_soft_deleted_data(ignore_users_file=None):
    """
    Removes documents that were soft-deleted (marked with deleted: true)
    using multiple threads for user processing and provides ETA.
    """
    print("Starting migration to remove soft-deleted documents...")
    total_deleted_count = 0
    start_time = time.time()

    all_user_ids = get_users_uid()

    ignored_user_ids = set()
    if ignore_users_file:
        try:
            with open(ignore_users_file, 'r') as f:
                ignored_user_ids = {line.strip() for line in f if line.strip()}
            print(f"Ignoring {len(ignored_user_ids)} users from file: {ignore_users_file}")
        except FileNotFoundError:
            print(f"Warning: Ignore users file not found: {ignore_users_file}. Processing all users.")
        except Exception as e:
            print(f"Warning: Error reading ignore users file {ignore_users_file}: {e}. Processing all users.")

    user_ids = [uid for uid in all_user_ids if uid not in ignored_user_ids]

    total_users = len(user_ids)
    if total_users == 0:
        print("No users found to process after applying ignore list (if any).")
    else:
        print(
            f"Found {len(all_user_ids)} total users. Processing {total_users} users (after ignore list) with {NUM_THREADS} threads..."
        )

        processed_users_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            future_to_user = {executor.submit(process_user_subcollections, uid): uid for uid in user_ids}
            for future in concurrent.futures.as_completed(future_to_user):
                user_id = future_to_user[future]
                try:
                    deleted_for_user = future.result()
                    total_deleted_count += deleted_for_user
                    if deleted_for_user > 0:
                        print(f"  User {user_id}: Total {deleted_for_user} documents deleted from subcollections.")
                except Exception as exc:
                    print(f"  User {user_id} generated an exception: {exc}")
                finally:
                    processed_users_count += 1
                    elapsed_time = time.time() - start_time
                    avg_time_per_user = elapsed_time / processed_users_count if processed_users_count > 0 else 0
                    remaining_users = total_users - processed_users_count
                    eta_seconds = remaining_users * avg_time_per_user if avg_time_per_user > 0 else 0

                    print(
                        f"Progress: {processed_users_count}/{total_users} users processed. "
                        f"Elapsed: {format_time(elapsed_time)}. "
                        f"ETA: {format_time(eta_seconds) if eta_seconds > 0 else 'Calculating...'}"
                    )

    print("\nProcessing root collections (sequentially)...")
    for collection_name in ROOT_COLLECTIONS:
        print(f"  Checking root collection: {collection_name}")
        collection_ref = db.collection(collection_name)
        query = collection_ref.where(filter=FieldFilter('deleted', '==', True))
        deleted_in_root_collection = delete_documents_in_batch(query)
        if deleted_in_root_collection > 0:
            print(f"  Deleted {deleted_in_root_collection} documents from {collection_name}.")
        total_deleted_count += deleted_in_root_collection

    end_time = time.time()
    total_duration = end_time - start_time
    print(f"\nMigration completed in {format_time(total_duration)}. Total documents removed: {total_deleted_count}")


if __name__ == '__main__':
    args = parse_arguments()
    print("Running migration script: remove_soft_deleted_documents.py")
    print("Ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set.")

    migrate_remove_soft_deleted_data(ignore_users_file=args.ignore_users_file)

"""
Migration Script: Migrate Action Items to Dedicated Collection

This script migrates all existing action items from the conversations collection
to the new dedicated action_items collection while maintaining backward compatibility.

Usage:
    python migrations/004_migrate_action_items_to_collection.py
"""

import os
import sys
import time
import random
import threading
from datetime import datetime, timezone
from typing import List, Dict, Any
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import firebase_admin
from firebase_admin import credentials, firestore

# Add project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Initialize Firebase Admin SDK
try:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
except Exception as e:
    print("Error initializing Firebase Admin SDK. Make sure GOOGLE_APPLICATION_CREDENTIALS is set.")
    print(e)
    sys.exit(1)

db = firestore.client()

# Configuration
BATCH_SIZE = 500  # Number of conversations to process per batch
NUM_THREADS = 12  # Number of concurrent processing threads
SLEEP_BETWEEN_BATCHES = 1.0  # Seconds to sleep between batches
USER_BATCH_SIZE = 500  # Number of users to process in each batch
CONVERSATION_BATCH_SIZE = 2000  # Number of conversations to fetch per user batch
FIRESTORE_BATCH_SIZE = 450  # Number of operations per Firestore batch write

processed_conversations = 0
processed_action_items = 0
errors = 0
migrated_users = defaultdict(int)
lock = threading.Lock()


def log_progress(message: str):
    """Thread-safe logging with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def retry_with_backoff(func, max_retries=3, base_delay=1.0, max_delay=60.0):
    """
    Retry a function with exponential backoff and jitter.

    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries

    Returns:
        Result of the function call

    Raises:
        Exception: The last exception if all retries fail
    """
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e

            # Calculate delay with exponential backoff and jitter
            delay = min(base_delay * (2**attempt), max_delay)
            jitter = random.uniform(0, delay * 0.1)
            total_delay = delay + jitter

            log_progress(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {total_delay:.2f}s...")
            time.sleep(total_delay)


def safe_firestore_operation(operation_func, operation_name="Firestore operation"):
    """
    Safely execute a Firestore operation with retry logic
    """

    def wrapped_operation():
        try:
            return operation_func()
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['_retry', 'grpc', 'deadline', 'unavailable']):
                log_progress(f"{operation_name} failed with gRPC/retry error: {str(e)}")
                raise e
            else:
                log_progress(f"{operation_name} failed with other error: {str(e)}")
                raise e

    return retry_with_backoff(wrapped_operation, max_retries=3)


def process_conversation_batch(conversations_batch: List[Dict[str, Any]], batch_num: int) -> Dict[str, int]:
    """
    Process a batch of conversations and migrate their action items.

    Returns:
        Dict with counts of processed conversations, action items, and errors
    """
    global processed_conversations, processed_action_items, errors, migrated_users

    batch_conversations = 0
    batch_action_items = 0
    batch_errors = 0
    batch_user_items = defaultdict(int)

    # Prepare batch write for action items
    batch_write = db.batch()
    batch_operations = 0

    for conv_data in conversations_batch:
        try:
            uid = conv_data.get('uid')
            conversation_id = conv_data.get('id')
            structured = conv_data.get('structured', {})
            action_items = structured.get('action_items', [])

            if not uid or not conversation_id or not action_items:
                batch_conversations += 1
                continue

            # Process each action item in the conversation
            for action_item in action_items:
                if not isinstance(action_item, dict):
                    continue

                description = action_item.get('description', '')
                completed = action_item.get('completed', False)

                if not description:
                    continue

                # Use conversation's started_at date, fallback to now if not available
                conversation_started_at = conv_data.get('started_at')
                if conversation_started_at:
                    # Handle both datetime objects and timestamp formats
                    if hasattr(conversation_started_at, 'timestamp'):
                        # Firestore timestamp object
                        base_date = datetime.fromtimestamp(conversation_started_at.timestamp(), tz=timezone.utc)
                    elif isinstance(conversation_started_at, datetime):
                        # Already a datetime object
                        base_date = (
                            conversation_started_at.replace(tzinfo=timezone.utc)
                            if conversation_started_at.tzinfo is None
                            else conversation_started_at
                        )
                    else:
                        # Fallback to now if format is unexpected
                        base_date = datetime.now(timezone.utc)
                else:
                    base_date = datetime.now(timezone.utc)

                # Create action item data for the new collection
                action_item_data = {
                    'description': description,
                    'completed': completed,
                    'created_at': base_date,
                    'updated_at': base_date,
                    'due_at': None,  # Legacy items don't have due dates
                    'completed_at': base_date if completed else None,
                    'conversation_id': conversation_id,
                }

                # Add to batch write
                user_ref = db.collection('users').document(uid)
                action_items_ref = user_ref.collection('action_items')
                new_doc_ref = action_items_ref.document()  # Auto-generate ID

                batch_write.set(new_doc_ref, action_item_data)
                batch_operations += 1
                batch_action_items += 1
                batch_user_items[uid] += 1

                if batch_operations >= FIRESTORE_BATCH_SIZE:
                    safe_firestore_operation(lambda: batch_write.commit(), f"Batch commit for batch {batch_num}")
                    batch_write = db.batch()
                    batch_operations = 0
                    time.sleep(0.2)

            batch_conversations += 1

        except Exception as e:
            batch_errors += 1
            log_progress(f"Error processing conversation {conversation_id}: {str(e)}")

    # Commit remaining operations
    if batch_operations > 0:
        try:
            safe_firestore_operation(lambda: batch_write.commit(), f"Final batch commit for batch {batch_num}")
        except Exception as e:
            log_progress(f"Error committing final batch: {str(e)}")
            batch_errors += 1

    with lock:
        processed_conversations += batch_conversations
        processed_action_items += batch_action_items
        errors += batch_errors
        for uid, count in batch_user_items.items():
            migrated_users[uid] += count
            log_progress(f"✅ Migration completed for user: {uid} ({count} action items)")

    log_progress(
        f"Batch {batch_num}: Processed {batch_conversations} conversations, "
        f"migrated {batch_action_items} action items, {batch_errors} errors"
    )

    return {'conversations': batch_conversations, 'action_items': batch_action_items, 'errors': batch_errors}


def get_users_batch(offset=0, limit=None):
    """
    Get a batch of users without streaming to avoid timeout issues.
    """
    if limit is None:
        limit = USER_BATCH_SIZE

    try:
        users_ref = db.collection('users')
        query = users_ref.offset(offset).limit(limit)

        users_docs = safe_firestore_operation(
            lambda: query.get(), f"Get users batch (offset: {offset}, limit: {limit})"
        )

        return [doc for doc in users_docs]
    except Exception as e:
        log_progress(f"Error getting users batch: {str(e)}")
        return []


def get_conversations_for_user_batch(uid, offset=0, limit=None):
    """
    Get conversations with action items for a specific user in batches.
    """
    if limit is None:
        limit = CONVERSATION_BATCH_SIZE
    try:
        user_ref = db.collection('users').document(uid)
        conversations_ref = user_ref.collection('conversations')

        query = (
            conversations_ref.where(filter=firestore.FieldFilter('structured.action_items', '!=', []))
            .offset(offset)
            .limit(limit)
        )

        conversations_docs = safe_firestore_operation(
            lambda: query.get(), f"Get conversations for user {uid} (offset: {offset}, limit: {limit})"
        )

        conversations = []
        for conv_doc in conversations_docs:
            conv_data = conv_doc.to_dict()
            conv_data['id'] = conv_doc.id
            conv_data['uid'] = uid
            conversations.append(conv_data)

        return conversations
    except Exception as e:
        log_progress(f"Error getting conversations for user {uid}: {str(e)}")
        return []


def get_conversations_with_action_items():
    """
    Generator that yields batches of conversations that have action items.
    Uses batch retrieval instead of streaming to avoid timeout issues.
    """
    log_progress("Starting to fetch conversations with action items...")

    batch = []
    total_conversations = 0
    user_offset = 0

    while True:
        users_batch = get_users_batch(offset=user_offset)

        if not users_batch:
            break

        log_progress(f"Processing {len(users_batch)} users (offset: {user_offset})")

        for user_doc in users_batch:
            uid = user_doc.id
            conv_offset = 0

            while True:
                user_conversations = get_conversations_for_user_batch(uid, offset=conv_offset)

                if not user_conversations:
                    break

                batch.extend(user_conversations)
                total_conversations += len(user_conversations)
                conv_offset += CONVERSATION_BATCH_SIZE

                if len(batch) >= BATCH_SIZE:
                    log_progress(f"Yielding batch of {len(batch)} conversations (total found: {total_conversations})")
                    yield batch
                    batch = []

                if len(user_conversations) < CONVERSATION_BATCH_SIZE:
                    break

            time.sleep(0.1)

        user_offset += USER_BATCH_SIZE

        if len(users_batch) < USER_BATCH_SIZE:
            break

    # Yield remaining conversations
    if batch:
        log_progress(f"Yielding final batch of {len(batch)} conversations (total found: {total_conversations})")
        yield batch

    log_progress(f"Finished fetching conversations. Total found: {total_conversations}")


def migrate_action_items():
    """
    Main migration function that processes all conversations with action items.

    This function:
    1. Fetches all conversations containing action items in batches
    2. Processes them using multiple threads for efficiency
    3. Migrates action items to the dedicated collection
    4. Maintains backward compatibility by keeping items in conversations
    5. Provides comprehensive progress tracking and error handling

    Returns:
        bool: True if migration completed without errors, False otherwise
    """
    start_time = time.time()
    log_progress("Starting action items migration...")

    log_progress("Counting total conversations with action items...")

    batch_num = 0

    try:
        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            future_to_batch = {}

            for conversations_batch in get_conversations_with_action_items():
                batch_num += 1

                # Submit batch for processing
                future = executor.submit(process_conversation_batch, conversations_batch, batch_num)
                future_to_batch[future] = batch_num

                if len(future_to_batch) >= NUM_THREADS * 2:
                    completed_futures = []
                    for future in as_completed(list(future_to_batch.keys())):
                        try:
                            result = future.result()
                            completed_futures.append(future)
                        except Exception as e:
                            batch_id = future_to_batch[future]
                            log_progress(f"Error in batch {batch_id}: {str(e)}")
                            completed_futures.append(future)

                    # Remove completed futures
                    for future in completed_futures:
                        del future_to_batch[future]

                    time.sleep(SLEEP_BETWEEN_BATCHES)

            for future in as_completed(future_to_batch.keys()):
                try:
                    result = future.result()
                except Exception as e:
                    batch_id = future_to_batch[future]
                    log_progress(f"Error in batch {batch_id}: {str(e)}")

    except Exception as e:
        log_progress(f"Critical error during migration: {str(e)}")
        return False

    end_time = time.time()
    duration = end_time - start_time

    log_progress("=" * 60)
    log_progress("MIGRATION COMPLETED")
    log_progress("=" * 60)
    log_progress(f"Total conversations processed: {processed_conversations}")
    log_progress(f"Total action items migrated: {processed_action_items}")
    log_progress(f"Total users affected: {len(migrated_users)}")
    log_progress(f"Total errors: {errors}")
    log_progress(f"Duration: {duration:.2f} seconds")

    if processed_action_items > 0:
        log_progress(f"Average speed: {processed_action_items / duration:.2f} action items/second")

    if migrated_users:
        sorted_users = sorted(migrated_users.items(), key=lambda x: x[1], reverse=True)
        log_progress(f"Top users by migrated items:")
        for uid, count in sorted_users[:5]:  # Show top 5
            log_progress(f"  - User {uid}: {count} items")

    return errors == 0


def verify_migration():
    """
    Verify that the migration was successful by sampling some data.
    """
    log_progress("Starting migration verification...")

    # Sample a few users and check if their action items were migrated
    users_ref = db.collection('users')
    sample_users_docs = safe_firestore_operation(lambda: users_ref.limit(5).get(), "Get sample users for verification")

    for user_doc in sample_users_docs:
        uid = user_doc.id

        conversations_ref = user_doc.reference.collection('conversations')
        conversations_with_items_docs = safe_firestore_operation(
            lambda: conversations_ref.where(filter=firestore.FieldFilter('structured.action_items', '!=', []))
            .limit(10)
            .get(),
            f"Get conversations with items for user {uid}",
        )

        conv_action_items_count = 0
        for conv_doc in conversations_with_items_docs:
            conv_data = conv_doc.to_dict()
            action_items = conv_data.get('structured', {}).get('action_items', [])
            conv_action_items_count += len(action_items)

        # Count action items in dedicated collection
        action_items_ref = user_doc.reference.collection('action_items')
        dedicated_action_items_docs = safe_firestore_operation(
            lambda: action_items_ref.limit(100).get(), f"Get dedicated action items for user {uid}"
        )
        dedicated_count = len(dedicated_action_items_docs)

        log_progress(
            f"User {uid}: {conv_action_items_count} items in conversations, "
            f"{dedicated_count} items in dedicated collection"
        )

    log_progress("Verification completed!")


if __name__ == "__main__":
    try:
        # Run the migration
        success = migrate_action_items()

        if success:
            log_progress("Migration completed successfully!")

            # Run verification
            verify_migration()

        else:
            log_progress("Migration completed with errors. Please review the logs.")

    except KeyboardInterrupt:
        log_progress("Migration interrupted by user")
    except Exception as e:
        log_progress(f"Migration failed with critical error: {str(e)}")
        raise

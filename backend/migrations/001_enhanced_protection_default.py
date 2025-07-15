import firebase_admin
from firebase_admin import credentials, firestore
import sys
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import users as users_db
from database import conversations as conversations_db
from database import memories as memories_db
from database import chat as chat_db

# Initialize Firebase Admin SDK
# IMPORTANT: Set the GOOGLE_APPLICATION_CREDENTIALS environment variable
# to the path of your service account key file before running this script.
try:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
except Exception as e:
    print("Error initializing Firebase Admin SDK. Make sure GOOGLE_APPLICATION_CREDENTIALS is set.")
    print(e)
    sys.exit(1)


db = firestore.client()


def load_ignore_uids(filepath: str) -> set:
    """Loads UIDs from a file to be ignored during migration."""
    if not filepath:
        return set()
    try:
        with open(filepath, 'r') as f:
            # Read UIDs, strip whitespace, and ignore empty lines
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        print(f"Warning: Ignore file not found at {filepath}. Continuing without ignoring any UIDs.")
        return set()


def migrate_user_to_enhanced(uid: str):
    """Migrates a single user's data from 'standard' to 'enhanced' protection."""
    print(f"Starting migration for user: {uid}")

    # 1. Get all items to migrate
    conversations_to_migrate = [item['id'] for item in conversations_db.get_conversations_to_migrate(uid, 'enhanced')]
    memories_to_migrate = [item['id'] for item in memories_db.get_memories_to_migrate(uid, 'enhanced')]
    chats_to_migrate = [item['id'] for item in chat_db.get_chats_to_migrate(uid, 'enhanced')]

    total_items = len(conversations_to_migrate) + len(memories_to_migrate) + len(chats_to_migrate)
    if total_items == 0:
        print(f"User {uid} is already at enhanced or has no data to migrate. Setting level to enhanced.")
        users_db.set_data_protection_level(uid, 'enhanced')
        return

    print(
        f"Found {len(conversations_to_migrate)} conversations, {len(memories_to_migrate)} memories, and {len(chats_to_migrate)} chats to migrate for user {uid}."
    )

    # 2. Migrate data in batches
    try:
        batch_size = 100
        if conversations_to_migrate:
            print(f"Migrating {len(conversations_to_migrate)} conversations for {uid}...")
            for i in range(0, len(conversations_to_migrate), batch_size):
                batch_ids = conversations_to_migrate[i : i + batch_size]
                print(f"  Migrating conversation batch {i//batch_size + 1} for {uid} ({len(batch_ids)} items)")
                conversations_db.migrate_conversations_level_batch(uid, batch_ids, 'enhanced')
            print(f"Conversations migrated for {uid}.")

        if memories_to_migrate:
            print(f"Migrating {len(memories_to_migrate)} memories for {uid}...")
            for i in range(0, len(memories_to_migrate), batch_size):
                batch_ids = memories_to_migrate[i : i + batch_size]
                print(f"  Migrating memory batch {i//batch_size + 1} for {uid} ({len(batch_ids)} items)")
                memories_db.migrate_memories_level_batch(uid, batch_ids, 'enhanced')
            print(f"Memories migrated for {uid}.")

        if chats_to_migrate:
            print(f"Migrating {len(chats_to_migrate)} chats for {uid}...")
            for i in range(0, len(chats_to_migrate), batch_size):
                batch_ids = chats_to_migrate[i : i + batch_size]
                print(f"  Migrating chat batch {i//batch_size + 1} for {uid} ({len(batch_ids)} items)")
                chat_db.migrate_chats_level_batch(uid, batch_ids, 'enhanced')
            print(f"Chats migrated for {uid}.")

        # 3. Finalize migration by updating user's protection level
        users_db.finalize_migration(uid, 'enhanced')
        print(f"Successfully migrated user {uid} to enhanced protection.")

    except Exception as e:
        print(f"ERROR migrating user {uid}: {e}")
        # Re-raise the exception to be caught by the future in the main loop
        raise


def main():
    """Main function to run the migration for all users."""
    parser = argparse.ArgumentParser(description="Migrate user data to 'enhanced' protection level.")
    parser.add_argument('--ignore-file', type=str, help='Path to a file containing UIDs to ignore, one per line.')
    args = parser.parse_args()

    print("Starting migration of users to 'enhanced' data protection...")

    ignore_uids = load_ignore_uids(args.ignore_file)
    if ignore_uids:
        print(f"Loaded {len(ignore_uids)} UIDs to ignore from {args.ignore_file}.")

    print("Fetching list of users to migrate...")
    users_ref = db.collection('users')
    all_users = users_ref.stream()

    users_to_migrate = []
    total_user_count = 0
    skipped_user_count = 0

    for user_doc in all_users:
        total_user_count += 1
        uid = user_doc.id
        if uid in ignore_uids:
            print(f"User {uid} is in the ignore list. Skipping.")
            skipped_user_count += 1
            continue

        user_data = user_doc.to_dict()
        current_level = user_data.get('data_protection_level', 'standard')

        if current_level == 'standard':
            users_to_migrate.append(uid)
        else:
            print(f"User {uid} is already at '{current_level}' protection level. Skipping.")
            skipped_user_count += 1

    print(f"\nChecked {total_user_count} total users.")
    print(f"Found {len(users_to_migrate)} users to migrate.")
    print(f"{skipped_user_count} users will be skipped.")

    if not users_to_migrate:
        print("No users to migrate. Exiting.")
        return

    with ThreadPoolExecutor(max_workers=64) as executor:
        print(f"\nStarting migration with 64 threads...")
        futures = {executor.submit(migrate_user_to_enhanced, uid): uid for uid in users_to_migrate}

        completed_count = 0
        for future in as_completed(futures):
            uid = futures[future]
            completed_count += 1
            try:
                future.result()  # This will re-raise any exception from the thread
                print(f"({completed_count}/{len(users_to_migrate)}) COMPLETED: User {uid}")
            except Exception as exc:
                print(f"({completed_count}/{len(users_to_migrate)}) FAILED: User {uid} generated an exception: {exc}")

    print(f"\nMigration script finished. Processed {len(users_to_migrate)} users.")


if __name__ == '__main__':
    main()

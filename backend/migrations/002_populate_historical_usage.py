import argparse
import copy
import json
import os
import re
import sys
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone

import firebase_admin
from firebase_admin import credentials, firestore

# Add project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import user_usage as user_usage_db
from models.conversation import Conversation
from models.memories import MemoryDB
from utils import encryption

# Initialize Firebase Admin SDK
try:
    if os.getenv('SERVICE_ACCOUNT_JSON'):
        # This path is for Modal environment
        service_account_info = os.environ["SERVICE_ACCOUNT_JSON"]
        cred = credentials.Certificate(
            eval(service_account_info) if service_account_info.startswith('{') else service_account_info
        )
    else:
        # This path is for local development, GOOGLE_APPLICATION_CREDENTIALS should be set
        cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
except Exception as e:
    print(
        "Error initializing Firebase Admin SDK. Make sure GOOGLE_APPLICATION_CREDENTIALS is set for local dev or SERVICE_ACCOUNT_JSON for Modal."
    )
    print(e)
    sys.exit(1)


db = firestore.client()


def _decrypt_conversation_data(data: dict, uid: str) -> dict:
    """Helper to decrypt conversation fields. Mimics logic from conversations_db."""
    decrypted_data = copy.deepcopy(data)

    if 'transcript_segments' not in decrypted_data:
        return decrypted_data

    if isinstance(decrypted_data['transcript_segments'], str):
        try:
            decrypted_payload = encryption.decrypt(decrypted_data['transcript_segments'], uid)
            if decrypted_data.get('transcript_segments_compressed'):
                compressed_bytes = bytes.fromhex(decrypted_payload)
                decompressed_json = zlib.decompress(compressed_bytes).decode('utf-8')
                decrypted_data['transcript_segments'] = json.loads(decompressed_json)
            # backward compatibility, will be removed soon
            else:
                decrypted_data['transcript_segments'] = json.loads(decrypted_payload)
        except (json.JSONDecodeError, TypeError, zlib.error, ValueError) as e:
            print(e, uid)
            decrypted_data['transcript_segments'] = []
    # backward compatibility, will be removed soon
    elif isinstance(decrypted_data['transcript_segments'], bytes):
        try:
            compressed_bytes = decrypted_data['transcript_segments']
            if decrypted_data.get('transcript_segments_compressed'):
                decompressed_json = zlib.decompress(compressed_bytes).decode('utf-8')
                decrypted_data['transcript_segments'] = json.loads(decompressed_json)
        except (json.JSONDecodeError, TypeError, zlib.error, ValueError) as e:
            print(e, uid)
            decrypted_data['transcript_segments'] = []

    return decrypted_data


def get_all_conversations_for_user(uid: str) -> list[Conversation]:
    """Fetches and decrypts all conversations for a user directly from Firestore."""
    conversations_ref = db.collection('users').document(uid).collection('conversations')
    conversations = []
    for doc in conversations_ref.stream():
        data = doc.to_dict()
        if data.get('data_protection_level') == 'enhanced':
            data = _decrypt_conversation_data(data, uid)
        elif data.get('transcript_segments_compressed') and isinstance(data.get('transcript_segments'), bytes):
            try:
                decompressed_json = zlib.decompress(data['transcript_segments']).decode('utf-8')
                data['transcript_segments'] = json.loads(decompressed_json)
            except (json.JSONDecodeError, TypeError, zlib.error, ValueError) as e:
                print(f"Warning: Could not decompress transcript segments for user {uid}. Error: {e}")
                data['transcript_segments'] = []
        try:
            conversations.append(Conversation(**data))
        except Exception as e:
            print(f"Warning: Could not parse conversation {doc.id} for user {uid}. Error: {e}")
    return conversations


def _decrypt_memory_data(memory_data: dict, uid: str) -> dict:
    """Helper to decrypt memory content, inspired by memories_db."""
    data = copy.deepcopy(memory_data)
    if 'content' in data and isinstance(data['content'], str):
        try:
            data['content'] = encryption.decrypt(data['content'], uid)
        except Exception:
            pass  # Ignore decryption errors for now
    return data


def get_all_memories_for_user(uid: str) -> list[MemoryDB]:
    """Fetches and decrypts all memories for a user directly from Firestore."""
    memories_ref = db.collection('users').document(uid).collection('memories')
    memories = []
    for doc in memories_ref.stream():
        data = doc.to_dict()
        if data.get('data_protection_level') == 'enhanced':
            data = _decrypt_memory_data(data, uid)
        try:
            memories.append(MemoryDB(**data))
        except Exception as e:
            print(f"Warning: Could not parse memory {doc.id} for user {uid}. Error: {e}")
    return memories


def delete_hourly_usage_for_user(uid: str):
    """Deletes all documents in the hourly_usage subcollection for a user to ensure idempotency."""
    print(f"Deleting existing hourly usage data for user {uid}...")
    coll_ref = db.collection('users').document(uid).collection('hourly_usage')
    batch_size = 200
    while True:
        docs = list(coll_ref.limit(batch_size).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()
        if len(docs) < batch_size:
            break
    print(f"Finished deleting hourly usage data for user {uid}.")


def migrate_user_usage(uid: str):
    """Calculates and stores historical usage stats for a single user."""
    try:
        print(f"Starting usage migration for user: {uid}")

        delete_hourly_usage_for_user(uid)

        hourly_updates = defaultdict(
            lambda: {'transcription_seconds': 0, 'words_transcribed': 0, 'insights_gained': 0, 'memories_created': 0}
        )

        # Process Conversations
        conversations = get_all_conversations_for_user(uid)
        if conversations:
            print(f"  Processing {len(conversations)} conversations for {uid}...")
            for conv in conversations:
                if not conv.created_at or conv.discarded:
                    continue

                hour_key = conv.created_at.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)

                duration = 0
                if conv.transcript_segments:
                    duration = max(conv.transcript_segments[-1].end - conv.transcript_segments[0].start, 0)

                if duration <= 0 and conv.started_at and conv.finished_at:
                    duration = (conv.finished_at - conv.started_at).total_seconds()

                hourly_updates[hour_key]['transcription_seconds'] += int(max(duration, 0))

                if conv.transcript_segments:
                    words = sum(len(s.text.split()) for s in conv.transcript_segments if s.text)
                    hourly_updates[hour_key]['words_transcribed'] += words

                insights = 0
                if conv.structured:
                    for text in [conv.structured.title, conv.structured.overview]:
                        if text:
                            sentences = re.split(r'[.!?]+', text)
                            insights += sum(1 for s in sentences if len(s.split()) > 5)
                    insights += len(conv.structured.action_items)
                    insights += len(conv.structured.events)

                for result in conv.apps_results:
                    if result.content:
                        sentences = re.split(r'[.!?]+', result.content)
                        insights += sum(1 for s in sentences if len(s.split()) > 5)

                hourly_updates[hour_key]['insights_gained'] += insights

        # Process Memories
        memories = get_all_memories_for_user(uid)
        if memories:
            print(f"  Processing {len(memories)} memories for {uid}...")
            for mem in memories:
                if not mem.created_at:
                    continue
                hour_key = mem.created_at.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
                hourly_updates[hour_key]['memories_created'] += 1

        if not hourly_updates:
            print(f"No usage data found to migrate for user {uid}.")
            return

        print(f"  Storing {len(hourly_updates)} hourly usage records for user {uid}.")
        user_usage_db.batch_update_hourly_usage(uid, hourly_updates)
        print(f"  Finished storing hourly usage for user {uid}.")

    except Exception as e:
        print(f"ERROR migrating usage for user {uid}: {e}")
        raise


def load_ignore_uids(filepath: str) -> set:
    """Loads UIDs from a file to be ignored during migration."""
    if not filepath:
        return set()
    try:
        with open(filepath, 'r') as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        print(f"Warning: Ignore file not found at {filepath}. Continuing without ignoring any UIDs.")
        return set()


def main():
    """Main function to run the migration for all users."""
    parser = argparse.ArgumentParser(description="Migrate historical user usage data.")
    parser.add_argument('--ignore-file', type=str, help='Path to a file containing UIDs to ignore, one per line.')
    parser.add_argument('--uids', type=str, help='A comma-separated list of specific UIDs to migrate.')
    args = parser.parse_args()

    print("Starting migration of historical user usage data...")

    if args.uids:
        users_to_migrate = [uid.strip() for uid in args.uids.split(',')]
        print(f"Migrating specific UIDs: {users_to_migrate}")
    else:
        ignore_uids = load_ignore_uids(args.ignore_file)
        if ignore_uids:
            print(f"Loaded {len(ignore_uids)} UIDs to ignore from {args.ignore_file}.")

        print("Fetching list of all users...")
        users_ref = db.collection('users')
        all_users = [user.id for user in users_ref.stream()]
        users_to_migrate = [uid for uid in all_users if uid not in ignore_uids]
        print(f"Found {len(users_to_migrate)} users to migrate.")

    if not users_to_migrate:
        print("No users to migrate. Exiting.")
        return

    with ThreadPoolExecutor(max_workers=16) as executor:
        print(f"\nStarting migration with 16 threads...")
        futures = {executor.submit(migrate_user_usage, uid): uid for uid in users_to_migrate}

        completed_count = 0
        for future in as_completed(futures):
            uid = futures[future]
            completed_count += 1
            try:
                future.result()
                print(f"({completed_count}/{len(users_to_migrate)}) COMPLETED: User {uid}")
            except Exception as exc:
                print(f"({completed_count}/{len(users_to_migrate)}) FAILED: User {uid} generated an exception: {exc}")

    print(f"\nMigration script finished. Processed {len(users_to_migrate)} users.")


if __name__ == '__main__':
    main()

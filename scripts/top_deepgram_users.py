"""
Query top lifetime users by transcription (DeepGram) consumption.
Iterates all users in Firestore, sums their all-time hourly_usage transcription_seconds,
and prints the top N users sorted by total consumption.

Usage:
    python scripts/top_deepgram_users.py [--top N]
"""

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import firebase_admin
from firebase_admin import auth, credentials, firestore

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Initialize Firebase
try:
    if os.getenv('SERVICE_ACCOUNT_JSON'):
        service_account_info = os.environ["SERVICE_ACCOUNT_JSON"]
        cred = credentials.Certificate(
            eval(service_account_info) if service_account_info.startswith('{') else service_account_info
        )
    else:
        cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
except Exception as e:
    logger.error(f"Firebase init failed: {e}")
    logger.error("Set GOOGLE_APPLICATION_CREDENTIALS for local dev.")
    sys.exit(1)

db = firestore.client()


def get_all_time_transcription(uid: str) -> tuple[str, int, int]:
    """Returns (uid, total_transcription_seconds, total_words_transcribed) for a user."""
    try:
        docs = db.collection('users').document(uid).collection('hourly_usage').stream()
        total_seconds = 0
        total_words = 0
        for doc in docs:
            data = doc.to_dict()
            total_seconds += data.get('transcription_seconds', 0)
            total_words += data.get('words_transcribed', 0)
        return uid, total_seconds, total_words
    except Exception as e:
        logger.error(f"Error for user {uid}: {e}")
        return uid, 0, 0


def get_user_email(uid: str) -> str:
    try:
        user = auth.get_user(uid)
        return user.email or 'N/A'
    except Exception:
        return 'N/A'


def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def main():
    parser = argparse.ArgumentParser(description="Find top users by lifetime transcription consumption.")
    parser.add_argument('--top', type=int, default=5, help='Number of top users to show (default: 5)')
    args = parser.parse_args()

    logger.info("Fetching all user UIDs from Firestore...")
    all_uids = [doc.id for doc in db.collection('users').stream()]
    logger.info(f"Found {len(all_uids)} users. Querying all-time usage...")

    results = []
    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = {executor.submit(get_all_time_transcription, uid): uid for uid in all_uids}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 500 == 0:
                logger.info(f"Progress: {done}/{len(all_uids)}")
            uid, seconds, words = future.result()
            if seconds > 0:
                results.append((uid, seconds, words))

    # Sort by transcription_seconds descending
    results.sort(key=lambda x: x[1], reverse=True)
    top = results[: args.top]

    # Fetch emails for top users
    logger.info(f"\nFetching emails for top {args.top} users...")
    emails = {}
    for uid, _, _ in top:
        emails[uid] = get_user_email(uid)

    # Print results
    print(f"\n{'='*80}")
    print(f"  TOP {args.top} LIFETIME USERS BY TRANSCRIPTION (STT/DeepGram) CONSUMPTION")
    print(f"{'='*80}\n")
    print(f"  {'Rank':<6} {'Transcription':<18} {'Words':<14} {'Email':<35} {'UID'}")
    print(f"  {'-'*6} {'-'*18} {'-'*14} {'-'*35} {'-'*36}")

    for i, (uid, seconds, words) in enumerate(top, 1):
        email = emails.get(uid, 'N/A')
        duration = format_duration(seconds)
        print(f"  {i:<6} {duration:<18} {words:<14,} {email:<35} {uid}")

    print(f"\n  Total users with any usage: {len(results)}")
    total_seconds = sum(s for _, s, _ in results)
    print(f"  Total transcription across all users: {format_duration(total_seconds)}")
    print()


if __name__ == '__main__':
    main()

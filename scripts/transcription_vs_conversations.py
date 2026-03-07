"""
Analyze transcription usage vs conversation count per user.
Finds users with the highest transcription-to-conversation ratio,
i.e. lots of STT time but very few conversations created.

Formula: ratio = transcription_seconds / conversations_count
Higher ratio = more "wasted" transcription per conversation.

Usage:
    python3 scripts/transcription_vs_conversations.py [--top N] [--min-seconds 3600]
"""

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import firebase_admin
from firebase_admin import auth, credentials, firestore
from google.cloud.firestore_v1 import FieldFilter

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
    sys.exit(1)

db = firestore.client()


def get_user_stats(uid: str) -> tuple[str, int, int]:
    """Returns (uid, total_transcription_seconds, conversation_count)."""
    try:
        # Get all-time transcription seconds
        docs = db.collection('users').document(uid).collection('hourly_usage').stream()
        total_seconds = 0
        for doc in docs:
            data = doc.to_dict()
            total_seconds += data.get('transcription_seconds', 0)

        if total_seconds == 0:
            return uid, 0, 0

        # Count non-discarded conversations using Firestore count()
        conv_ref = db.collection('users').document(uid).collection('conversations')
        conv_query = conv_ref.where(filter=FieldFilter('discarded', '==', False)).count()
        result = conv_query.get()
        conv_count = result[0][0].value

        return uid, total_seconds, conv_count
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
    days = seconds / 86400
    if days >= 1:
        return f"{days:.1f} days"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def main():
    parser = argparse.ArgumentParser(description="Find users with highest transcription-to-conversation ratio.")
    parser.add_argument('--top', type=int, default=20, help='Number of top users to show (default: 20)')
    parser.add_argument(
        '--min-seconds', type=int, default=3600, help='Minimum transcription seconds to include (default: 3600 = 1hr)'
    )
    args = parser.parse_args()

    logger.info("Fetching all user UIDs from Firestore...")
    all_uids = [doc.id for doc in db.collection('users').stream()]
    logger.info(f"Found {len(all_uids)} users. Querying usage + conversation counts...")

    results = []
    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = {executor.submit(get_user_stats, uid): uid for uid in all_uids}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 500 == 0:
                logger.info(f"Progress: {done}/{len(all_uids)}")
            uid, seconds, convs = future.result()
            if seconds >= args.min_seconds:
                results.append((uid, seconds, convs))

    # Calculate ratio: transcription_seconds / max(conversations, 1)
    # Higher ratio = more transcription time per conversation = more "wasteful"
    scored = []
    for uid, seconds, convs in results:
        ratio = seconds / max(convs, 1)
        scored.append((uid, seconds, convs, ratio))

    # Sort by ratio descending (highest waste first)
    scored.sort(key=lambda x: x[3], reverse=True)
    top = scored[: args.top]

    # Fetch emails
    logger.info(f"\nFetching emails for top {len(top)} users...")
    emails = {}
    for uid, _, _, _ in top:
        emails[uid] = get_user_email(uid)

    # Print results
    print(f"\n{'='*110}")
    print(f"  TOP {args.top} USERS: HIGHEST TRANSCRIPTION-TO-CONVERSATION RATIO")
    print(f"  (users with >= {format_duration(args.min_seconds)} transcription)")
    print(f"  Formula: ratio = transcription_seconds / max(conversations, 1)")
    print(f"{'='*110}\n")
    print(
        f"  {'Rank':<6} {'Transcription':<16} {'Convos':<10} {'Ratio':<14} {'Sec/Conv':<12} {'Email':<35} {'UID'}"
    )
    print(f"  {'-'*6} {'-'*16} {'-'*10} {'-'*14} {'-'*12} {'-'*35} {'-'*36}")

    for i, (uid, seconds, convs, ratio) in enumerate(top, 1):
        email = emails.get(uid, 'N/A')
        duration = format_duration(seconds)
        ratio_str = f"{ratio:,.0f}"
        sec_per_conv = format_duration(int(ratio))
        print(f"  {i:<6} {duration:<16} {convs:<10,} {ratio_str:<14} {sec_per_conv:<12} {email:<35} {uid}")

    # Also print summary stats
    print(f"\n  {'='*60}")
    print(f"  SUMMARY (users with >= {format_duration(args.min_seconds)} transcription)")
    print(f"  {'='*60}")
    print(f"  Total qualifying users: {len(results)}")

    zero_conv = sum(1 for _, _, c, _ in scored if c == 0)
    print(f"  Users with 0 conversations: {zero_conv}")

    avg_ratio = sum(r for _, _, _, r in scored) / len(scored) if scored else 0
    median_idx = len(scored) // 2
    median_ratio = scored[median_idx][3] if scored else 0
    print(f"  Average ratio: {avg_ratio:,.0f} sec/conv ({format_duration(int(avg_ratio))})")
    print(f"  Median ratio:  {median_ratio:,.0f} sec/conv ({format_duration(int(median_ratio))})")
    print()


if __name__ == '__main__':
    main()

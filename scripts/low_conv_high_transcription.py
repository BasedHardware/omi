"""
Analyze users with high transcription but low conversation counts (<5 conversations).
Provides overall stats on wasted transcription.

Usage:
    python3 scripts/low_conv_high_transcription.py
"""

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import FieldFilter

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

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
        docs = db.collection('users').document(uid).collection('hourly_usage').stream()
        total_seconds = 0
        for doc in docs:
            data = doc.to_dict()
            total_seconds += data.get('transcription_seconds', 0)

        if total_seconds == 0:
            return uid, 0, 0

        conv_ref = db.collection('users').document(uid).collection('conversations')
        conv_query = conv_ref.where(filter=FieldFilter('discarded', '==', False)).count()
        result = conv_query.get()
        conv_count = result[0][0].value

        return uid, total_seconds, conv_count
    except Exception as e:
        logger.error(f"Error for user {uid}: {e}")
        return uid, 0, 0


def fmt(seconds: int) -> str:
    days = seconds / 86400
    if days >= 1:
        return f"{days:,.1f} days"
    hours = seconds / 3600
    if hours >= 1:
        return f"{hours:,.1f} hrs"
    return f"{seconds // 60} min"


def main():
    logger.info("Fetching all user UIDs from Firestore...")
    all_uids = [doc.id for doc in db.collection('users').stream()]
    logger.info(f"Found {len(all_uids)} users. Querying usage + conversation counts...")

    all_stats = []
    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = {executor.submit(get_user_stats, uid): uid for uid in all_uids}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 500 == 0:
                logger.info(f"Progress: {done}/{len(all_uids)}")
            uid, seconds, convs = future.result()
            if seconds > 0:
                all_stats.append((uid, seconds, convs))

    # Bucket users by conversation count
    buckets = {
        '0 conversations': [],
        '1 conversation': [],
        '2-4 conversations': [],
        '<5 total': [],
        '5+ conversations': [],
    }

    for uid, seconds, convs in all_stats:
        if convs == 0:
            buckets['0 conversations'].append((uid, seconds, convs))
            buckets['<5 total'].append((uid, seconds, convs))
        elif convs == 1:
            buckets['1 conversation'].append((uid, seconds, convs))
            buckets['<5 total'].append((uid, seconds, convs))
        elif convs <= 4:
            buckets['2-4 conversations'].append((uid, seconds, convs))
            buckets['<5 total'].append((uid, seconds, convs))
        else:
            buckets['5+ conversations'].append((uid, seconds, convs))

    total_users_with_usage = len(all_stats)
    total_seconds_all = sum(s for _, s, _ in all_stats)

    print(f"\n{'='*90}")
    print(f"  TRANSCRIPTION WASTE ANALYSIS: USERS WITH <5 CONVERSATIONS")
    print(f"{'='*90}\n")

    print(f"  Total users with any transcription: {total_users_with_usage:,}")
    print(f"  Total transcription across all users: {fmt(total_seconds_all)}")
    print()

    # Per-bucket stats
    print(f"  {'Bucket':<22} {'Users':<10} {'% Users':<10} {'Total Transcription':<22} {'% of Total':<12} {'Avg/User':<14}")
    print(f"  {'-'*22} {'-'*10} {'-'*10} {'-'*22} {'-'*12} {'-'*14}")

    for label in ['0 conversations', '1 conversation', '2-4 conversations', '<5 total', '5+ conversations']:
        users = buckets[label]
        count = len(users)
        total_sec = sum(s for _, s, _ in users)
        pct_users = (count / total_users_with_usage * 100) if total_users_with_usage else 0
        pct_transcription = (total_sec / total_seconds_all * 100) if total_seconds_all else 0
        avg_per_user = total_sec // max(count, 1)

        prefix = "  " if label != '<5 total' else "  "
        bold = ">>>" if label == '<5 total' else "   "

        print(
            f"{bold}{prefix}{label:<22} {count:<10,} {pct_users:<10.1f}% {fmt(total_sec):<22} {pct_transcription:<12.1f}% {fmt(avg_per_user):<14}"
        )
        if label == '<5 total':
            print()

    # Transcription hour buckets for <5 conv users
    low_conv = buckets['<5 total']
    print(f"\n  {'='*60}")
    print(f"  BREAKDOWN OF <5 CONV USERS BY TRANSCRIPTION AMOUNT")
    print(f"  {'='*60}\n")

    hour_buckets = [
        ('1-10 min', 60, 600),
        ('10-60 min', 600, 3600),
        ('1-6 hrs', 3600, 21600),
        ('6-24 hrs', 21600, 86400),
        ('1-7 days', 86400, 604800),
        ('7+ days', 604800, float('inf')),
    ]

    print(f"  {'Transcription Range':<22} {'Users':<10} {'Total Transcription':<22} {'Avg Convos':<12}")
    print(f"  {'-'*22} {'-'*10} {'-'*22} {'-'*12}")

    for label, lo, hi in hour_buckets:
        in_bucket = [(u, s, c) for u, s, c in low_conv if lo <= s < hi]
        if not in_bucket:
            continue
        count = len(in_bucket)
        total_sec = sum(s for _, s, _ in in_bucket)
        avg_convs = sum(c for _, _, c in in_bucket) / count
        print(f"  {label:<22} {count:<10,} {fmt(total_sec):<22} {avg_convs:<12.1f}")

    # Cost estimate (Deepgram Nova-2 pay-as-you-go: ~$0.0043/sec = $0.258/min)
    low_conv_seconds = sum(s for _, s, _ in low_conv)
    cost_per_second = 0.0043  # approximate Deepgram Nova cost
    wasted_cost = low_conv_seconds * cost_per_second

    print(f"\n  {'='*60}")
    print(f"  ESTIMATED COST IMPACT")
    print(f"  {'='*60}")
    print(f"  (Using ~$0.0043/sec Deepgram Nova estimate)")
    print()
    print(f"  Transcription by <5 conv users: {fmt(low_conv_seconds)}")
    print(f"  Estimated cost of that transcription: ${wasted_cost:,.0f}")
    total_cost = total_seconds_all * cost_per_second
    print(f"  Total estimated transcription cost: ${total_cost:,.0f}")
    print(f"  % attributable to <5 conv users: {(wasted_cost / total_cost * 100):.1f}%")
    print()


if __name__ == '__main__':
    main()

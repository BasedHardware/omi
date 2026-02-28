"""
Migration script to auto-set single_language_mode based on each user's language preference.

Languages in Deepgram Nova-3 multi-language set → single_language_mode = False
Languages NOT in the set → single_language_mode = True
Users with no language set are skipped.

Usage:
    python 006_auto_set_transcription_mode.py [--dry-run]

Environment:
    GOOGLE_APPLICATION_CREDENTIALS: Path to Firebase service account key
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

from utils.stt.streaming import deepgram_nova3_multi_languages
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
try:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
except ValueError:
    pass
except Exception as e:
    logger.error("Error initializing Firebase Admin SDK. Make sure GOOGLE_APPLICATION_CREDENTIALS is set.")
    logger.error(e)
    sys.exit(1)

db = firestore.client()


def get_all_users():
    """Get all user documents with language and transcription_preferences fields."""
    users_ref = db.collection('users')
    return list(users_ref.stream())


def process_user(user_doc, dry_run=False):
    """Check and update a single user's transcription mode based on their language."""
    uid = user_doc.id
    data = user_doc.to_dict()

    language = data.get('language')
    if not language:
        return 'skipped_no_language'

    expected_single_language_mode = language not in deepgram_nova3_multi_languages

    current_prefs = data.get('transcription_preferences', {})
    current_mode = current_prefs.get('single_language_mode')

    if current_mode == expected_single_language_mode:
        return 'already_correct'

    if dry_run:
        logger.info(
            f"[DRY RUN] {uid}: language={language}, current={current_mode}, would_set={expected_single_language_mode}"
        )
        return 'would_update'

    db.collection('users').document(uid).update(
        {
            'transcription_preferences.single_language_mode': expected_single_language_mode,
        }
    )
    return 'updated'


def main():
    parser = argparse.ArgumentParser(description='Auto-set transcription mode based on user language')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    args = parser.parse_args()

    logger.info("Fetching all users...")
    users = get_all_users()
    logger.info(f"Found {len(users)} users")

    counts = {'skipped_no_language': 0, 'already_correct': 0, 'would_update': 0, 'updated': 0, 'error': 0}
    start = time.time()

    with ThreadPoolExecutor(max_workers=64) as executor:
        futures = {executor.submit(process_user, user, args.dry_run): user.id for user in users}
        for future in as_completed(futures):
            uid = futures[future]
            try:
                result = future.result()
                counts[result] += 1
            except Exception as e:
                logger.error(f"Error processing {uid}: {e}")
                counts['error'] += 1

    elapsed = time.time() - start
    logger.info(f"Done in {elapsed:.1f}s")
    logger.info(f"Results: {counts}")


if __name__ == '__main__':
    main()

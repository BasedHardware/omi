import argparse
import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import firebase_admin
from firebase_admin import auth, credentials, firestore

# Add project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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


def get_user_usage(uid: str) -> tuple[str, dict | None]:
    """
    Calculates all usage metrics for a single user in the last 24 hours from hourly usage data.
    Returns totals and hourly distributions for each metric.
    """
    try:
        now = datetime.now(timezone.utc)
        time_24_hours_ago = now - timedelta(days=1)
        start_of_hour_24_hours_ago = time_24_hours_ago.replace(minute=0, second=0, microsecond=0)
        start_doc_id = start_of_hour_24_hours_ago.strftime('%Y-%m-%d-%H')

        hourly_usage_ref = db.collection('users').document(uid).collection('hourly_usage')
        docs = hourly_usage_ref.where('id', '>=', start_doc_id).stream()

        # Store all fetched hourly data, keyed by doc ID (e.g. '2023-01-01-15')
        hourly_docs_data = {doc.id: doc.to_dict() for doc in docs}

        if not hourly_docs_data:
            return uid, None  # No usage, so skip this user.

        metric_keys = ['transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created']
        usage_totals = {key: 0 for key in metric_keys}

        # Determine the hourly buckets for the last 24 hours to create distributions
        hour_buckets = []
        current_hour = start_of_hour_24_hours_ago
        end_hour = now.replace(minute=0, second=0, microsecond=0)
        while current_hour <= end_hour:
            hour_buckets.append(current_hour)
            current_hour += timedelta(hours=1)

        distributions = {f"{key}_dist": [] for key in metric_keys}

        for hour_bucket in hour_buckets:
            doc_id = hour_bucket.strftime('%Y-%m-%d-%H')
            doc_data = hourly_docs_data.get(doc_id, {})
            for key in metric_keys:
                value = doc_data.get(key, 0)
                usage_totals[key] += value
                distributions[f"{key}_dist"].append(str(value))

        # Combine totals and string-joined distributions
        final_data = usage_totals
        for key, value_list in distributions.items():
            final_data[key] = ",".join(value_list)

        return uid, final_data
    except Exception as e:
        print(f"ERROR calculating usage for user {uid}: {e}")

    return uid, None


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
    """Main function to export user usage analytics for the last 24 hours to a CSV file."""
    parser = argparse.ArgumentParser(description="Export user usage analytics for the last 24 hours to a CSV file.")
    parser.add_argument('--uids', type=str, help='A comma-separated list of specific UIDs to process.')
    parser.add_argument('--ignore-file', type=str, help='Path to a file containing UIDs to ignore, one per line.')
    parser.add_argument('--output', type=str, default='user_usage_report.csv', help='Path to the output CSV file.')
    args = parser.parse_args()

    print("Starting user usage analytics export for the last 24 hours...")

    if args.uids:
        uids_to_process = [uid.strip() for uid in args.uids.split(',')]
        print(f"Processing specific UIDs: {uids_to_process}")
    else:
        ignore_uids = load_ignore_uids(args.ignore_file)
        if ignore_uids:
            print(f"Loaded {len(ignore_uids)} UIDs to ignore from {args.ignore_file}.")

        print("Fetching list of all users from Firestore...")
        users_ref = db.collection('users')
        all_uids = [user.id for user in users_ref.stream()]
        uids_to_process = [uid for uid in all_uids if uid not in ignore_uids]
        print(f"Found {len(uids_to_process)} users to process.")

    if not uids_to_process:
        print("No users to process. Exiting.")
        return

    # Calculate usage and filter for users with recent activity
    print(f"\nCalculating usage for {len(uids_to_process)} users...")
    all_user_usage = []
    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = {executor.submit(get_user_usage, uid): uid for uid in uids_to_process}

        completed_count = 0
        for future in as_completed(futures):
            uid = futures[future]
            completed_count += 1
            try:
                user_uid, usage = future.result()
                if usage:
                    all_user_usage.append((user_uid, usage))
                    print(f"({completed_count}/{len(uids_to_process)}) COMPLETED: Found usage for user {uid}")
                else:
                    print(f"({completed_count}/{len(uids_to_process)}) COMPLETED: No recent usage for user {uid}")
            except Exception as exc:
                print(f"({completed_count}/{len(uids_to_process)}) FAILED: User {uid} generated an exception: {exc}")

    if not all_user_usage:
        print("\nNo users with recent usage found. Exiting.")
        return

    # For users with usage, fetch email addresses
    print(f"\nFound {len(all_user_usage)} users with recent usage. Fetching their emails...")
    uids_with_usage = [uid for uid, usage in all_user_usage]
    user_emails = {}
    # get_users can take a list of up to 100 identifiers
    for i in range(0, len(uids_with_usage), 100):
        chunk = uids_with_usage[i : i + 100]
        try:
            get_users_result = auth.get_users([auth.UidIdentifier(uid) for uid in chunk])
            for user in get_users_result.users:
                user_emails[user.uid] = user.email or 'N/A'
            for user_identifier in get_users_result.not_found:
                print(f"Warning: User with UID {user_identifier.uid} not found in Firebase Auth.")
                user_emails[user_identifier.uid] = 'Not Found'
        except Exception as e:
            print(f"Error fetching users batch: {e}")
            for uid in chunk:
                if uid not in user_emails:
                    user_emails[uid] = "Error fetching email"

    # Write results to CSV
    try:
        with open(args.output, 'w', newline='') as csvfile:
            fieldnames = [
                'uid',
                'email',
                'transcription_seconds',
                'words_transcribed',
                'insights_gained',
                'memories_created',
                'transcription_seconds_dist',
                'words_transcribed_dist',
                'insights_gained_dist',
                'memories_created_dist',
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for uid, usage in all_user_usage:
                email = user_emails.get(uid, 'N/A')
                writer.writerow({'uid': uid, 'email': email, **usage})

        print(f"\nScript finished. Usage data for {len(all_user_usage)} users exported to {args.output}")
    except IOError as e:
        print(f"Error writing to file {args.output}: {e}")


if __name__ == '__main__':
    main()

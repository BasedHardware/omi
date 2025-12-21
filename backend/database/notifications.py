"""
Notifications database module

Structure:
users/{uid}/fcm_tokens (subcollection)
  └── {device_key} (document)
      ├── token: "actual_token_value"
      ├── created_at: timestamp
      └── time_zone: "America/New_York"
"""

import asyncio

from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud import firestore
from google.cloud.firestore import DELETE_FIELD
from ._client import db


def save_token(uid: str, data: dict):
    """
    Store token in subcollection with device key as document ID
    Structure: users/{uid}/fcm_tokens/{device_key}
    Also maintains time_zone in main user document for backward compatibility
    Migrates legacy fcm_token to subcollection
    """
    device_key = data.get('device_key', 'unknown_default')
    token = data.get('fcm_token')
    time_zone = data.get('time_zone')

    user_ref = db.collection('users').document(uid)

    # Step 1: Migrate legacy token if exists
    user_doc = user_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        legacy_token = user_data.get('fcm_token')

        if legacy_token:
            # Check if legacy token already exists in subcollection
            existing_tokens = [doc.to_dict().get('token') for doc in user_ref.collection('fcm_tokens').stream()]

            if legacy_token not in existing_tokens:
                # Migrate to unknown_default
                user_ref.collection('fcm_tokens').document('unknown_default').set(
                    {
                        'token': legacy_token,
                        'time_zone': user_data.get('time_zone'),
                        'created_at': firestore.SERVER_TIMESTAMP,
                    },
                    merge=True,
                )

            # Remove legacy field
            user_ref.update({'fcm_token': DELETE_FIELD})

    # Step 2: If new token has proper device_key, replace unknown_default
    if device_key != 'unknown_default':
        unknown_ref = user_ref.collection('fcm_tokens').document('unknown_default')
        unknown_doc = unknown_ref.get()
        if unknown_doc.exists:
            unknown_token = unknown_doc.to_dict().get('token')
            # Only delete if it's the same token being migrated to proper device_key
            if unknown_token == token:
                unknown_ref.delete()

    # Step 3: Save new token to subcollection
    user_ref.collection('fcm_tokens').document(device_key).set(
        {'token': token, 'time_zone': time_zone, 'created_at': firestore.SERVER_TIMESTAMP}, merge=True
    )

    # Also update time_zone in main user document (for backward compatibility and efficient queries)
    if time_zone:
        user_ref.set({'time_zone': time_zone}, merge=True)


def get_user_time_zone(uid: str):
    """Get timezone from main user document"""
    user_ref = db.collection('users').document(uid).get()
    if user_ref.exists:
        user_data = user_ref.to_dict()
        return user_data.get('time_zone')
    return None


def get_all_tokens(uid: str) -> list[str]:
    """Get all device tokens for a user from subcollection and legacy field"""
    tokens = []

    # Get tokens from new subcollection
    token_docs = db.collection('users').document(uid).collection('fcm_tokens').stream()
    for doc in token_docs:
        token_data = doc.to_dict()
        if token_data.get('token'):
            tokens.append(token_data['token'])

    # Get legacy token from main user document (backward compatibility)
    user_ref = db.collection('users').document(uid).get()
    if user_ref.exists:
        user_data = user_ref.to_dict()
        legacy_token = user_data.get('fcm_token')
        if legacy_token and legacy_token not in tokens:
            tokens.append(legacy_token)

    return tokens


def remove_invalid_token(token: str):
    """Remove invalid token using collection group query (rare operation)"""
    # Query across ALL users' fcm_tokens subcollections
    query = db.collection_group('fcm_tokens').where(filter=FieldFilter('token', '==', token)).limit(1)

    for doc in query.stream():
        doc.reference.delete()
        return


def remove_bulk_tokens(tokens: list[str]):
    """Remove multiple invalid tokens efficiently using IN queries and batch deletes"""
    if not tokens:
        return

    # Firestore IN queries support up to 30 items
    chunk_size = 30
    token_chunks = [tokens[i : i + chunk_size] for i in range(0, len(tokens), chunk_size)]

    for chunk in token_chunks:
        # Query for all tokens in this chunk at once
        query = db.collection_group('fcm_tokens').where(filter=FieldFilter('token', 'in', chunk))

        # Batch delete for efficiency
        batch = db.batch()
        count = 0

        for doc in query.stream():
            batch.delete(doc.reference)
            count += 1

            # Firestore batch limit is 500 operations
            if count >= 500:
                batch.commit()
                batch = db.batch()
                count = 0

        # Commit remaining deletes
        if count > 0:
            batch.commit()


async def get_users_token_in_timezones(timezones: list[str]):
    return await _get_users_in_timezones(timezones, 'fcm_token')


async def get_users_id_in_timezones(timezones: list[str]):
    return await _get_users_in_timezones(timezones, 'id')


async def _get_users_in_timezones(timezones: list[str], filter: str):
    """Query main user documents by timezone, then get tokens from subcollection and legacy field"""
    users = []

    # 'Where in' query only supports 30 or fewer items in list so we split in chunks
    timezone_chunks = [timezones[i : i + 30] for i in range(0, len(timezones), 30)]

    async def query_chunk(chunk):
        def sync_query():
            chunk_users = []
            try:
                # Query main user documents by time_zone
                query = db.collection('users').where(filter=FieldFilter('time_zone', 'in', chunk))

                for user_doc in query.stream():
                    uid = user_doc.id
                    user_data = user_doc.to_dict()

                    # Collect tokens from subcollection
                    tokens = []
                    token_docs = db.collection('users').document(uid).collection('fcm_tokens').stream()
                    for token_doc in token_docs:
                        token_data = token_doc.to_dict()
                        if token_data.get('token'):
                            tokens.append(token_data['token'])

                    # Add legacy token if exists and not already in list
                    legacy_token = user_data.get('fcm_token')
                    if legacy_token and legacy_token not in tokens:
                        tokens.append(legacy_token)

                    # Skip users with no tokens
                    if not tokens:
                        continue

                    if filter == 'fcm_token':
                        # Return flat list of tokens
                        chunk_users.extend(tokens)
                    else:
                        # Return list of (uid, [tokens], time_zone) tuples
                        time_zone = user_data.get('time_zone')
                        chunk_users.append((uid, tokens, time_zone))

            except Exception as e:
                print(f"Error querying chunk {chunk}: {e}")
            return chunk_users

        return await asyncio.to_thread(sync_query)

    tasks = [query_chunk(chunk) for chunk in timezone_chunks]
    results = await asyncio.gather(*tasks)

    for chunk_users in results:
        users.extend(chunk_users)

    return users

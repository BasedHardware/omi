"""
Notifications database module

DEPRECATION NOTICE (Nov 23, 2025):
- The 'fcm_token' field is DEPRECATED and will be removed after Feb 23, 2026
- Use 'fcm_tokens' dict structure instead for multi-device support
- Backward compatibility maintained until Feb 23, 2026
"""

import asyncio

from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore import DELETE_FIELD
from ._client import db


def save_token(uid: str, data: dict):
    """
    Store token with device key (e.g., ios_abc123, android_xyz456)
    Structure: {
      'fcm_tokens': {
        'ios_abc123': 'token_1',
        'android_xyz456': 'token_2'
      }
    }
    
    NOTE: Legacy 'fcm_token' field will be DEPRECATED after Feb 23, 2026
    """
    device_key = data.get('device_key', 'unknown_default')
    token = data.get('fcm_token')
    
    # Migrate legacy token if exists
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    user_data = user_doc.to_dict() if user_doc.exists else {}
    
    updates = {
        f'fcm_tokens.{device_key}': token,
        'time_zone': data.get('time_zone'),
    }
    
    # Migrate old token value to new structure before deleting
    if 'fcm_token' in user_data and user_data['fcm_token']:
        old_token = user_data['fcm_token']
        # Only migrate if it's not already in the new structure
        existing_tokens = user_data.get('fcm_tokens', {}).values()
        if old_token not in existing_tokens:
            updates['fcm_tokens.unknown_default'] = old_token
        # Now remove the old field
        updates['fcm_token'] = DELETE_FIELD
    
    user_ref.set(updates, merge=True)


def get_user_time_zone(uid: str):
    user_ref = db.collection('users').document(uid)
    user_ref = user_ref.get()
    if user_ref.exists:
        user_ref = user_ref.to_dict()
        return user_ref.get('time_zone')
    return None


def get_all_tokens(uid: str) -> list[str]:
    """
    Get all device tokens for a user
    
    NOTE: Support for legacy 'fcm_token' field will be REMOVED after Feb 23, 2026
    """
    user_ref = db.collection('users').document(uid).get()
    if not user_ref.exists:
        return []
    
    user_data = user_ref.to_dict()
    tokens = []
    
    # Get new format tokens
    tokens_dict = user_data.get('fcm_tokens', {})
    tokens.extend([token for token in tokens_dict.values() if token])
    
    # Backward compatibility: Get legacy token if exists (DEPRECATED - remove after Feb 23, 2026)
    legacy_token = user_data.get('fcm_token')
    if legacy_token and legacy_token not in tokens:
        tokens.append(legacy_token)
    
    return tokens


def remove_token(token: str):
    """Deprecated: Use remove_invalid_token instead"""
    remove_invalid_token(token)


def remove_invalid_token(token: str):
    """Remove invalid token from any user's device list"""
    users_ref = db.collection('users')
    
    # Stream through all users to find and remove the invalid token
    for user_doc in users_ref.stream():
        user_data = user_doc.to_dict()
        tokens_dict = user_data.get('fcm_tokens', {})
        
        # Find and remove the invalid token
        for device_key, stored_token in tokens_dict.items():
            if stored_token == token:
                user_doc.reference.update({
                    f'fcm_tokens.{device_key}': DELETE_FIELD
                })
                return


async def get_users_token_in_timezones(timezones: list[str]):
    return await get_users_in_timezones(timezones, 'fcm_token')


async def get_users_id_in_timezones(timezones: list[str]):
    return await get_users_in_timezones(timezones, 'id')


async def get_users_in_timezones(timezones: list[str], filter: str):
    """
    NOTE: Support for legacy 'fcm_token' field will be REMOVED after Feb 23, 2026
    """
    users = []
    users_ref = db.collection('users')

    # 'Where in' query only supports 30 or fewer items in list to we split in chunks
    timezone_chunks = [timezones[i : i + 30] for i in range(0, len(timezones), 30)]

    async def query_chunk(chunk):
        def sync_query():
            chunk_users = []
            try:
                query = users_ref.where(filter=FieldFilter('time_zone', 'in', chunk))
                for doc in query.stream():
                    doc_data = doc.to_dict()
                    
                    # Check both new and old format (backward compatibility until Feb 23, 2026)
                    if 'fcm_tokens' not in doc_data and 'fcm_token' not in doc_data:
                        continue
                    
                    if filter == 'fcm_token':
                        # Get all tokens (new + legacy)
                        tokens = []
                        if 'fcm_tokens' in doc_data:
                            tokens.extend([t for t in doc_data['fcm_tokens'].values() if t])
                        if 'fcm_token' in doc_data and doc_data['fcm_token'] not in tokens:
                            tokens.append(doc_data['fcm_token'])
                        chunk_users.extend(tokens)
                    else:
                        # Return user ID with all tokens
                        tokens = []
                        if 'fcm_tokens' in doc_data:
                            tokens.extend([t for t in doc_data['fcm_tokens'].values() if t])
                        if 'fcm_token' in doc_data and doc_data['fcm_token'] not in tokens:
                            tokens.append(doc_data['fcm_token'])
                        if tokens:
                            chunk_users.append((doc.id, tokens))

            except Exception as e:
                print(f"Error querying chunk {chunk}: {e}")
            return chunk_users

        return await asyncio.to_thread(sync_query)

    tasks = [query_chunk(chunk) for chunk in timezone_chunks]
    results = await asyncio.gather(*tasks)

    for chunk_users in results:
        users.extend(chunk_users)

    return users

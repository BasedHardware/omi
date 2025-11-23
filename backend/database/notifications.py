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
    """
    device_key = data.get('device_key', 'unknown')
    token = data.get('fcm_token')
    
    db.collection('users').document(uid).set({
        f'fcm_tokens.{device_key}': token,
        'time_zone': data.get('time_zone'),
    }, merge=True)


def get_user_time_zone(uid: str):
    user_ref = db.collection('users').document(uid)
    user_ref = user_ref.get()
    if user_ref.exists:
        user_ref = user_ref.to_dict()
        return user_ref.get('time_zone')
    return None


def get_all_tokens(uid: str) -> list[str]:
    """Get all device tokens for a user"""
    user_ref = db.collection('users').document(uid).get()
    if not user_ref.exists:
        return []
    
    user_data = user_ref.to_dict()
    tokens_dict = user_data.get('fcm_tokens', {})
    
    # Return list of all tokens
    return [token for token in tokens_dict.values() if token]


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
                    if 'fcm_token' not in doc.to_dict():
                        continue
                    if filter == 'fcm_token':
                        token = doc.get('fcm_token')
                    else:
                        token = doc.id, doc.get('fcm_token')
                    if token:
                        chunk_users.append(token)

            except Exception as e:
                print(f"Error querying chunk {chunk}: {e}")
            return chunk_users

        return await asyncio.to_thread(sync_query)

    tasks = [query_chunk(chunk) for chunk in timezone_chunks]
    results = await asyncio.gather(*tasks)

    for chunk_users in results:
        users.extend(chunk_users)

    return users

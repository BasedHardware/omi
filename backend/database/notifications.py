import asyncio

from google.cloud.firestore_v1.base_query import FieldFilter

from ._client import db


def save_token(uid: str, data: dict):
    db.collection('users').document(uid).set(data, merge=True)


def get_token_only(uid: str):
    user_ref = db.collection('users').document(uid)
    user_ref = user_ref.get()
    if user_ref.exists:
        user_ref = user_ref.to_dict()
        return user_ref.get('fcm_token')
    return None


def get_token(uid: str):
    user_ref = db.collection('users').document(uid)
    user_ref = user_ref.get()
    if user_ref.exists:
        user_ref = user_ref.to_dict()
        return user_ref.get('fcm_token'), user_ref.get('time_zone')
    return None


async def get_users_in_timezones(timezones: list[str]):
    users = []
    users_ref = db.collection('users')

    # 'Where in' query only supports 30 or fewer items in list to we split in chunks
    timezone_chunks = [timezones[i:i + 30] for i in range(0, len(timezones), 30)]

    async def query_chunk(chunk):
        def sync_query():
            chunk_users = []
            try:
                query = users_ref.where(filter=FieldFilter('time_zone', 'in', chunk))
                for doc in query.stream():
                    token = doc.get('fcm_token')
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

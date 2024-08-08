from ._client import db

from google.cloud import firestore
import asyncio
from google.cloud.firestore_v1.base_query import FieldFilter
# from google.cloud import GoogleAPICallError

def save_token(uid: str, token: str, time_zone: str):
    user_ref = db.collection('users').document(uid)
    user_ref.set({'token': token, 'time_zone': time_zone}, merge=True)

def get_token_only(uid: str):
    user_ref = db.collection('users').document(uid)
    user_ref = user_ref.get()
    if user_ref.exists:
        user_ref = user_ref.to_dict()
        return user_ref.get('token')
    return None

def get_token(uid: str):
    user_ref = db.collection('users').document(uid)
    user_ref = user_ref.get()
    if user_ref.exists:
        user_ref = user_ref.to_dict()
        return user_ref.get('token'), user_ref.get('time_zone')
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
                    token = doc.get('token')
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

import os

import redis

r = redis.Redis(
    host=os.getenv('REDIS_DB_HOST'),
    port=int(os.getenv('REDIS_DB_PORT')) if os.getenv('REDIS_DB_PORT') is not None else 6379,
    username='default',
    password=os.getenv('REDIS_DB_PASSWORD'),
    health_check_interval=30
)


def try_catch_decorator(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f'Error calling {func.__name__}', e)
            return None

    return wrapper


def store_notion_crm_api_key(uid: str, api_key: str):
    r.set(f'notion_crm_api_key:{uid}', api_key)


def store_notion_database_id(uid: str, database_id: str):
    r.set(f'notion_database_id:{uid}', database_id)


def get_notion_crm_api_key(uid: str) -> str:
    val = r.get(f'notion_crm_api_key:{uid}')
    return val.decode('utf-8') if val else None


def get_notion_database_id(uid: str) -> str:
    val = r.get(f'notion_database_id:{uid}')
    return val.decode('utf-8') if val else None


def append_segment_to_transcript(uid: str, session_id: str, new_segments: list[dict]):
    key = f'transcript:{uid}:{session_id}'
    segments = r.get(key)
    if not segments:
        segments = []
    else:
        segments = eval(segments)

    segments.extend(new_segments)
    # order the segments by start time, in case they are not ordered, and save them
    segments = sorted(segments, key=lambda x: x['start'])
    r.set(key, str(segments))
    return segments


def remove_transcript(uid: str, session_id: str):
    r.delete(f'transcript:{uid}:{session_id}')


def clean_all_transcripts_except(uid: str, session_id: str):
    for key in r.scan_iter(f'transcript:{uid}:*'):
        if key.decode().split(':')[2] != session_id:
            r.delete(key)

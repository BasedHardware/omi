import os
from typing import List

import redis

from models import TranscriptSegment

r = redis.Redis(
    host=os.getenv('REDIS_DB_HOST'),
    port=int(os.getenv('REDIS_DB_PORT')) if os.getenv('REDIS_DB_PORT') is not None else 6379,
    username='default',
    password=os.getenv('REDIS_DB_PASSWORD'),
    health_check_interval=30,
)


def try_catch_decorator(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f'Error calling {func.__name__}', e)
            return None

    return wrapper


# **********************************************************
# ************ BASIC AUTH PLUGIN (NOTION) UTILS ************
# **********************************************************
def store_notion_crm_api_key(uid: str, api_key: str):
    r.set(f'notion_crm_api_key:{uid}', api_key)


def store_notion_database_id(uid: str, database_id: str):
    r.set(f'notion_database_id:{uid}', database_id)


def get_notion_crm_api_key(uid: str) -> str:
    val = r.get(f'notion_crm_api_key:{uid}')
    return val.decode('utf-8') if val else None


# noinspection PyUnresolvedReferences
def get_notion_database_id(uid: str) -> str:
    val = r.get(f'notion_database_id:{uid}')
    return val.decode('utf-8') if val else None


# **********************************************************
# ************ ZAPIER UTILS ************
# **********************************************************
def store_zapier_user_status(uid: str, status: str):
    r.set(f'zapier_user_status:{uid}', status)


def get_zapier_user_status(uid: str) -> str:
    val = r.get(f'zapier_user_status:{uid}')
    return val.decode('utf-8') if val else None


def get_zapier_subscribes(uid: str):
    return r.smembers(f'zapier_subscribes:{uid}')


def store_zapier_subscribes(uid: str, target_url: str):
    r.sadd(f'zapier_subscribes:{uid}', target_url)


def remove_zapier_subscribes(uid: str, target_url: str):
    r.srem(f'zapier_subscribes:{uid}', target_url)


# **********************************************************
# ************ MULTION UTILS ************
# **********************************************************


def store_multion_user_id(uid: str, user_id: str):
    r.set(f'multion_user_id:{uid}', user_id)


def get_multion_user_id(uid: str) -> str:
    result = r.get(f'multion_user_id:{uid}')
    return result.decode('utf-8') if result else None


# *******************************************************
# ************ MENTOR PLUGIN UTILS ***********
# *******************************************************


def get_upsert_segment_to_transcript_plugin(
    plugin_id: str, session_id: str, new_segments: list[TranscriptSegment]
) -> List[dict]:
    key = f'plugin:{plugin_id}:session:{session_id}:transcript_segments'
    segments = r.get(key)
    if not segments:
        segments = []
    else:
        segments = eval(segments)

    segments.extend([segment.dict() for segment in new_segments])

    # keep 1000
    if len(segments) > 1000:
        segments = segments[-1000:]

    r.set(key, str(segments))

    # expire 5m
    r.expire(key, 60 * 5)

    return [TranscriptSegment(**segment) for segment in segments]

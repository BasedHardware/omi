import json
import time

import redis.asyncio as aioredis

from app.config import REDIS_URL, CHUNK_THRESHOLD, TIME_THRESHOLD_SECONDS


_redis = aioredis.from_url(REDIS_URL, decode_responses=True)

BUFFER_TTL = 300  # 5 min expiry for stale buffers


async def add_segments(session_id: str, segments: list[dict]) -> tuple[bool, list[dict]]:
    buf_key = f'sandbox:buf:{session_id}'
    meta_key = f'sandbox:meta:{session_id}'

    pipe = _redis.pipeline()
    for seg in segments:
        pipe.rpush(buf_key, json.dumps(seg))
    pipe.expire(buf_key, BUFFER_TTL)
    await pipe.execute()

    now = time.time()
    started = await _redis.hget(meta_key, 'started_at')
    if not started:
        await _redis.hset(meta_key, mapping={'started_at': str(now)})
        await _redis.expire(meta_key, BUFFER_TTL)
        started = now
    else:
        started = float(started)

    count = await _redis.llen(buf_key)
    elapsed = now - started

    if count >= CHUNK_THRESHOLD or elapsed >= TIME_THRESHOLD_SECONDS:
        raw = await _redis.lrange(buf_key, 0, -1)
        await _redis.delete(buf_key, meta_key)
        return True, [json.loads(r) for r in raw]

    return False, []


async def close():
    await _redis.aclose()

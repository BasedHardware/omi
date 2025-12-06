from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from typing import Optional
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_pool: Optional[ArqRedis] = None


def get_redis_settings() -> RedisSettings:
    settings = get_settings()
    redis_url = settings.redis_url
    
    if redis_url.startswith("redis://"):
        redis_url = redis_url[8:]
    elif redis_url.startswith("rediss://"):
        redis_url = redis_url[9:]
    
    if "@" in redis_url:
        auth_part, host_part = redis_url.rsplit("@", 1)
        password = auth_part.split(":", 1)[1] if ":" in auth_part else auth_part
    else:
        password = None
        host_part = redis_url
    
    if ":" in host_part:
        host, port_db = host_part.split(":", 1)
        if "/" in port_db:
            port, db = port_db.split("/", 1)
            database = int(db) if db else 0
        else:
            port = port_db
            database = 0
        port = int(port)
    else:
        if "/" in host_part:
            host, db = host_part.split("/", 1)
            database = int(db) if db else 0
        else:
            host = host_part
            database = 0
        port = 6379
    
    return RedisSettings(
        host=host,
        port=port,
        password=password,
        database=database,
    )


async def get_redis_pool() -> ArqRedis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(get_redis_settings())
        logger.info("Redis pool created")
    return _redis_pool


async def close_redis_pool():
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("Redis pool closed")


async def enqueue_job(func_name: str, *args, **kwargs):
    pool = await get_redis_pool()
    job = await pool.enqueue_job(func_name, *args, **kwargs)
    if job:
        logger.info(f"Enqueued job: {func_name} with id {job.job_id}")
    return job

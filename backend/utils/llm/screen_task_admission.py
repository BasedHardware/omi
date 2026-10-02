"""Runtime ops stop for screen-task admission, shared by gate and screenshot proxy."""

import os
import redis
from fastapi import HTTPException
from database.redis_db import check_rate_limit
from utils.rate_limit_config import get_effective_limit


def screen_task_stopped() -> bool:
    return os.getenv('SCREEN_TASK_STOP', 'false').strip().lower() in {'1', 'true', 'on'}


def check_screen_task_limit(uid: str, policy: str) -> None:
    maximum, window = get_effective_limit(policy)
    try:
        allowed, _, retry_after = check_rate_limit(uid, policy, maximum, window)
    except redis.exceptions.RedisError as error:
        raise HTTPException(
            503, detail={'error': 'gate_admission_unavailable'}, headers={'X-Omi-Retryable': 'false'}
        ) from error
    if not allowed:
        raise HTTPException(
            429, detail={'error': 'gate_quota'}, headers={'X-Omi-Retryable': 'false', 'Retry-After': str(retry_after)}
        )

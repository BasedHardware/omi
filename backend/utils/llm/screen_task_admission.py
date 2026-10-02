"""Runtime ops stop and macOS build floor for screen-task admission."""

import logging
import os
from collections.abc import Mapping

from redis.exceptions import RedisError
from fastapi import HTTPException
from database.redis_db import check_rate_limit
from utils.llm.desktop_reservation_policy import identified_macos_build, positive_build
from utils.metrics import SCREEN_TASK_BUILD_FLOOR_REFUSALS_TOTAL
from utils.rate_limit_config import get_effective_limit

logger = logging.getLogger(__name__)

# First macOS build whose screen-task pipeline includes the reviewed fixes.
DEFAULT_SCREEN_TASK_MIN_MACOS_BUILD = 12435
SCREEN_TASK_MIN_MACOS_BUILD_ENV = 'SCREEN_TASK_MIN_MACOS_BUILD'
BUILD_FLOOR_ERROR = 'screen_task_build_below_floor'
_BUILD_FLOOR_SURFACES = frozenset({'gate', 'admission', 'proxy'})


def screen_task_stopped() -> bool:
    return os.getenv('SCREEN_TASK_STOP', 'false').strip().lower() in {'1', 'true', 'on'}


def screen_task_min_macos_build() -> int:
    # Read at the request, not import. Invalid values keep the declared floor.
    parsed = positive_build(os.getenv(SCREEN_TASK_MIN_MACOS_BUILD_ENV, '').strip())
    return parsed if parsed is not None else DEFAULT_SCREEN_TASK_MIN_MACOS_BUILD


def screen_task_build_floor_refusal(headers: Mapping[str, str], surface: str) -> HTTPException | None:
    """Refuse one positively identified macOS build below the floor.

    Unidentified, unparseable, conflicting, and non-macOS callers return None
    and stay on the existing path. The body is a typed non-retryable 409.
    """
    if surface not in _BUILD_FLOOR_SURFACES:
        return None
    build = identified_macos_build(headers)
    if build is None or build >= screen_task_min_macos_build():
        return None
    SCREEN_TASK_BUILD_FLOOR_REFUSALS_TOTAL.labels(surface=surface).inc()
    logger.info('screen_task_build_floor_refused surface=%s reason=build_below_floor', surface)
    return HTTPException(
        status_code=409,
        detail={'error': BUILD_FLOOR_ERROR},
        headers={'X-Omi-Retryable': 'false'},
    )


def check_screen_task_limit(uid: str, policy: str) -> None:
    maximum, window = get_effective_limit(policy)
    try:
        allowed, _, retry_after = check_rate_limit(uid, policy, maximum, window)
    except RedisError as error:
        raise HTTPException(
            503, detail={'error': 'gate_admission_unavailable'}, headers={'X-Omi-Retryable': 'false'}
        ) from error
    if not allowed:
        raise HTTPException(
            429, detail={'error': 'gate_quota'}, headers={'X-Omi-Retryable': 'false', 'Retry-After': str(retry_after)}
        )

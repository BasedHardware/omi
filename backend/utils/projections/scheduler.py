"""Hourly cron integration for one owner-scoped projection per local day."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database import notifications as notifications_db
from database import projections as projections_db
from database import redis_db
from utils.executors import db_executor, postprocess_executor, run_blocking
from utils.projections.errors import NoProjectionSubject
from utils.projections.generation import generate_projection

logger = logging.getLogger(__name__)

PROJECTION_ENABLED_USERS_ENV = 'PROJECTION_ENABLED_USERS'
PROJECTION_GENERATION_HOUR_LOCAL = 8
PROJECTION_GENERATION_BATCH_SIZE = 4
_PROJECTION_ID_NAMESPACE = uuid.UUID('d16f13bb-37e7-4932-b847-50ea4266c96d')


@dataclass(frozen=True)
class ProjectionCronResult:
    eligible: int
    generated: int
    skipped: int
    errors: int


def enabled_user_ids() -> tuple[str, ...]:
    """Return the explicit dogfood cohort; an empty value keeps ambient generation off."""
    configured = os.getenv(PROJECTION_ENABLED_USERS_ENV, '')
    return tuple(dict.fromkeys(uid.strip() for uid in configured.split(',') if uid.strip()))


def should_run_job() -> bool:
    """The shared hourly job owns cadence, while this explicit cohort owns rollout."""
    return bool(enabled_user_ids())


def daily_projection_id(uid: str, local_date: date) -> str:
    """Stable id is the durable duplicate guard when a Redis lease is unavailable."""
    return str(uuid.uuid5(_PROJECTION_ID_NAMESPACE, f'{uid}:{local_date.isoformat()}'))


def generate_daily_projection(uid: str, local_date: date) -> bool:
    """Generate at most one scheduled projection for an owner and local calendar day.

    Redis avoids duplicate model/image work during overlapping cron attempts. The deterministic
    Firestore document id is the durable authority: even if Redis is unavailable, concurrent
    attempts converge on one artifact instead of appending duplicates.
    """
    cadence_key = local_date.isoformat()
    projection_id = daily_projection_id(uid, local_date)

    try:
        acquired = redis_db.try_acquire_projection_generation_lock(uid, cadence_key)
    except Exception as error:
        acquired = True
        logger.warning(
            'projection lock unavailable; relying on deterministic id uid=%s cadence=%s error=%s',
            uid,
            cadence_key,
            error,
        )
    if not acquired:
        return False

    if projections_db.get_projection(uid, projection_id):
        return False

    try:
        projection = generate_projection(uid, projection_id=projection_id, cadence_key=cadence_key)
    except NoProjectionSubject as error:
        logger.info('scheduled projection skipped uid=%s cadence=%s reason=%s', uid, cadence_key, error)
        return False

    projections_db.create_projection(uid, projection)
    return True


async def start_cron_job(*, now: datetime | None = None) -> ProjectionCronResult:
    """Generate the daily projection for allowlisted users whose local clock is 08:xx."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('projection cron time must be timezone-aware')

    user_ids = enabled_user_ids()
    time_zones = await asyncio.gather(
        *[run_blocking(db_executor, notifications_db.get_user_time_zone, uid) for uid in user_ids],
        return_exceptions=True,
    )

    eligible: list[tuple[str, date]] = []
    for uid, time_zone in zip(user_ids, time_zones):
        if isinstance(time_zone, Exception):
            logger.error('scheduled projection skipped uid=%s reason=timezone_lookup_failed error=%s', uid, time_zone)
            continue
        if not time_zone:
            logger.info('scheduled projection skipped uid=%s reason=missing_timezone', uid)
            continue
        try:
            local_now = now.astimezone(ZoneInfo(time_zone))
        except ZoneInfoNotFoundError:
            logger.warning('scheduled projection skipped uid=%s reason=invalid_timezone', uid)
            continue
        if local_now.hour == PROJECTION_GENERATION_HOUR_LOCAL:
            eligible.append((uid, local_now.date()))

    generated = 0
    skipped = 0
    errors = 0
    for index in range(0, len(eligible), PROJECTION_GENERATION_BATCH_SIZE):
        batch = eligible[index : index + PROJECTION_GENERATION_BATCH_SIZE]
        results = await asyncio.gather(
            *[
                run_blocking(postprocess_executor, generate_daily_projection, uid, local_date)
                for uid, local_date in batch
            ],
            return_exceptions=True,
        )
        for (uid, local_date), result in zip(batch, results):
            if isinstance(result, Exception):
                errors += 1
                logger.error('scheduled projection failed uid=%s cadence=%s error=%s', uid, local_date, result)
            elif result:
                generated += 1
            else:
                skipped += 1

    result = ProjectionCronResult(
        eligible=len(eligible),
        generated=generated,
        skipped=skipped,
        errors=errors,
    )
    logger.info('projection cron completed result=%s', result)
    return result

"""Hourly cron integration for one owner-scoped projection per local day."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database import notifications as notifications_db
from database import projections as projections_db
from database import redis_db
from utils.executors import db_executor, postprocess_executor, run_blocking
from utils.observability.fallback import record_fallback
from utils.projections.errors import NoProjectionSubject
from utils.projections.generation import generate_projection
from utils.projections.storage import uses_gcs

logger = logging.getLogger(__name__)

PROJECTION_ENABLED_USERS_ENV = 'PROJECTION_ENABLED_USERS'
PROJECTION_GENERATION_HOUR_LOCAL = 8
PROJECTION_GENERATION_BATCH_SIZE = 4
PROJECTION_RESERVATION_TTL = timedelta(minutes=15)
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
    """Return the stable id reserved atomically for one owner's local day."""
    return str(uuid.uuid5(_PROJECTION_ID_NAMESPACE, f'{uid}:{local_date.isoformat()}'))


def generate_daily_projection(uid: str, local_date: date) -> bool:
    """Generate at most one scheduled projection for an owner and local calendar day.

    Redis avoids unnecessary Firestore contention. The Firestore reservation is the durable
    authority: one attempt token owns generation and finalization, and every attempt writes to
    its own image path so a stale render cannot replace the current owner's bytes.
    """
    cadence_key = local_date.isoformat()
    projection_id = daily_projection_id(uid, local_date)

    try:
        acquired = redis_db.try_acquire_projection_generation_lock(uid, cadence_key)
    except Exception as error:
        acquired = True
        record_fallback(
            component='projections',
            from_mode='redis_lease',
            to_mode='firestore_reservation',
            reason='provider_unavailable',
            outcome='degraded',
            log=logger,
        )
        logger.warning(
            'projection lock unavailable; relying on Firestore reservation uid=%s cadence=%s error=%s',
            uid,
            cadence_key,
            error,
        )
    if not acquired:
        return False

    try:
        attempt_token = str(uuid.uuid4())
        reserved_at = datetime.now(timezone.utc)
        if not projections_db.reserve_projection_generation(
            uid,
            projection_id,
            cadence_key,
            attempt_token,
            now=reserved_at,
            expires_at=reserved_at + PROJECTION_RESERVATION_TTL,
        ):
            return False
        projection = generate_projection(
            uid,
            projection_id=projection_id,
            cadence_key=cadence_key,
            attempt_token=attempt_token,
        )
        finalized = projections_db.finalize_projection_generation(
            uid,
            projection,
            attempt_token,
            now=datetime.now(timezone.utc),
        )
        if not finalized:
            logger.warning(
                'projection attempt lost reservation before finalization uid=%s cadence=%s attempt=%s',
                uid,
                cadence_key,
                attempt_token,
            )
        return finalized
    except NoProjectionSubject as error:
        logger.info('scheduled projection skipped uid=%s cadence=%s reason=%s', uid, cadence_key, error)
        return False
    except Exception:
        try:
            redis_db.release_projection_generation_lock(uid, cadence_key)
        except Exception as release_error:
            logger.warning(
                'projection lock release failed uid=%s cadence=%s error=%s',
                uid,
                cadence_key,
                release_error,
            )
        raise


async def start_cron_job(*, now: datetime | None = None) -> ProjectionCronResult:
    """Generate the daily projection for allowlisted users after 08:00 local time."""
    if (os.getenv('K_SERVICE') or os.getenv('KUBERNETES_SERVICE_HOST')) and not uses_gcs():
        raise RuntimeError('ambient projection generation requires BUCKET_PROJECTION_IMAGES in hosted runtimes')
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
        if isinstance(time_zone, BaseException):
            if not isinstance(time_zone, Exception):
                raise time_zone
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
        if local_now.hour >= PROJECTION_GENERATION_HOUR_LOCAL:
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
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
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

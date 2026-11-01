"""Backend-only spend policy RPC. GPU images must not import Redis/provider code."""

from utils.observability.stt_cap_dispatch import DispatchPath, DispatchReason, record_decision

import asyncio
import logging
import math
import time

from prometheus_client import Histogram

from config.stt_cap_dispatch import offline_admission_enabled as cap_dispatch_enabled
from config.sync_telemetry import bounded_exception_class
from utils.stt_cap_dispatch import sync_admission
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.scheduler import owns_lease
from utils.fair_use import get_hard_restriction_status, is_daily_audio_ceiling_exceeded
from utils.executors import db_executor, run_blocking
from utils.sync.backfill import reserve_backfill_speech, retry_after_next_utc_day

logger = logging.getLogger(__name__)
# Leave transport/serialization headroom under the running worker's 5s timeout.
AUTHORIZE_SECONDS = 4.0
STAGE_SECONDS = Histogram(
    'omi_batch_compute_admission_stage_seconds',
    'Admission substage wall time including executor wait; bounded stages, no identifiers',
    ['stage'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8),
)


def admitted_as_byok(job: object) -> bool:
    """Admission decides funding once (contract (c)): a BYOK unit is never re-held at GPU dispatch.

    The dispatch re-check runs without the user's keys or BYOK consent, so for a BYOK owner it
    would hold the unit on every lease. Only the admission-time policy snapshot can say BYOK;
    a missing or malformed policy keeps today's re-check (fail closed).
    """
    policy = job.get('policy') if isinstance(job, dict) else None  # pyright: ignore[reportUnknownMemberType]
    return isinstance(policy, dict) and policy.get('provider_reason') == 'byok'


def batch_admission(job: dict, seconds: float, provider: str, *, path: DispatchPath) -> tuple[bool, str]:
    """Spend gate with its bounded DispatchReason surfaced for the durable per-unit record."""
    if admitted_as_byok(job):
        return record_decision(path, True, DispatchReason.BYOK), DispatchReason.BYOK.value
    return sync_admission(job['owner_id'], seconds, provider, lane='batch', path=path)


async def authorize(store, leases: list[dict], *, now: float | None = None) -> dict:
    """Return completed decisions within 4s; unfinished work never gets an allow.

    Keep leases serial: fresh funding/fair-use is check-then-act, not an atomic
    reservation. Parallel evaluation would widen the existing overshoot risk.
    Cancelling an executor await cannot stop an in-flight Redis/Firestore RPC
    (including transaction retries/commit). It can finish conservatively, but
    cannot schedule another stage or mutate this receipt after the deadline.
    """
    current = time.time() if now is None else now
    deadline = time.monotonic() + AUTHORIZE_SECONDS
    allowed, retries, held_reason = [], {lease['segment_id']: 30 for lease in leases}, {}

    async def stage(name, fn, *args, **kwargs):
        # Check in the executor too: a queued call must not start after expiry.
        def run():
            if time.monotonic() >= deadline:
                raise TimeoutError('admission deadline')
            return fn(*args, **kwargs)

        with STAGE_SECONDS.labels(stage=name).time():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('admission deadline')
            result = await asyncio.wait_for(run_blocking(db_executor, run), timeout=remaining)
            # A dependency may return at the boundary before the timer runs.
            if time.monotonic() >= deadline:
                raise TimeoutError('admission deadline')
            return result

    for lease in leases:
        if time.monotonic() >= deadline:
            break
        segment, token = lease['segment_id'], lease['token']
        try:

            def read(tx):
                job = tx.get('jobs', segment)
                if not owns_lease(job, token, current):
                    return None
                tx.check_privacy(
                    job['owner_id'],
                    (job['conversation_id'],) if job.get('conversation_id') else (),
                    job.get('privacy_generation'),
                )
                binding = job.get('projection_binding') or {}
                intake = tx.get('intakes', binding.get('job_id', 'missing'))
                return job, binding, intake

            snapshot = await stage('read', store.run, read)
            if snapshot is None:
                retries[segment] = 30
                continue
            job, binding, intake = snapshot
            # Latest admission decision, not a sticky last denial: the same
            # transaction that seals (or defers) the unit records {reason,
            # outcome, at} so an outside reader can tell an exhausted-owner
            # hold from a wedge without inventing an age TTL.
            allow_reason = 'scope_disabled'
            if await stage('scope', cap_dispatch_enabled, job['owner_id'], 'batch'):
                permitted, reason = await stage(
                    'funding',
                    batch_admission,
                    job,
                    float(job.get('duration_seconds', 0)),
                    'parakeet',
                    path=DispatchPath.BATCH_GPU,
                )
                if not permitted:
                    retries[segment] = 60
                    held_reason[segment] = reason
                    continue
                allow_reason = reason
            # The recorded sync lane picks the spend policy, not the GPU
            # priority: fresh-lane catch-up leases at RECENT after fresh
            # uploads but keeps the fresh-audio fair-use checks.
            fresh_lane = intake['lane'] == 'fresh' if intake.get('lane') else int(job['priority']) == 0
            if fresh_lane:
                # Known overshoot, intentionally unchanged: these fair-use reads
                # are check-then-act with no reservation, and the meter advances
                # only at projection, so in-flight audio is invisible. Each
                # worker replica can admit one batch past an exhausted ceiling;
                # the bound scales with replicas x batch size x unit length.
                restricted, retry_after = await stage('restriction', get_hard_restriction_status, job['owner_id'])
                if restricted:
                    retries[segment] = max(1, min(86400, retry_after or 3600))
                    held_reason[segment] = 'fair_use_restricted'
                    continue
                if await stage('daily_ceiling', is_daily_audio_ceiling_exceeded, job['owner_id']):
                    retries[segment] = await stage('retry_day', retry_after_next_utc_day)
                    held_reason[segment] = 'daily_audio_ceiling'
                    continue
            else:
                # Speech is unknown before GPU VAD. Reserve an upper bound
                # once per content key using the exact existing Redis guard.
                duration = float(intake.get('total_audio_seconds', 0))
                if not binding.get('content_id') or not math.isfinite(duration) or duration <= 0:
                    raise ValueError('durable content duration required for spend admission')
                reservation = await stage(
                    'backfill_reservation',
                    reserve_backfill_speech,
                    job['owner_id'],
                    binding['content_id'],
                    math.ceil(duration * 1000),
                )
                if not reservation.allowed:
                    retries[segment] = max(1, min(86400, reservation.retry_after or 3600))
                    held_reason[segment] = 'backfill_reservation'
                    continue

            def seal(tx):
                if time.monotonic() >= deadline:
                    return False
                latest = tx.get('jobs', segment)
                if not owns_lease(latest, token, time.time() if now is None else current):
                    return False
                latest['compute_admission_token'] = token
                latest['compute_decision'] = {'reason': allow_reason, 'outcome': 'allowed', 'at': current}
                latest.pop('last_policy_hold', None)  # an allow ends the parked hold
                if time.monotonic() >= deadline:
                    return False
                tx.put('jobs', segment, latest)
                return True

            if await stage('seal', store.run, seal):
                allowed.append(segment)
                retries.pop(segment, None)
            else:
                retries[segment] = 30
        except BatchPrivacyBlocked:
            retries[segment] = 30
            held_reason[segment] = 'privacy_blocked'
        except Exception as error:
            # Policy backend failure is never permission to spend GPU capacity,
            # and never a durable decision either: an unevaluated unit stays
            # unclassified for outside readers (BLIND), not falsely held/allowed.
            retries[segment] = 30
            logger.warning(
                'event=batch_compute_admission_unevaluated exception_class=%s', bounded_exception_class(error)
            )
    return {'allowed': allowed, 'retry_after': retries, 'held_reason': held_reason}

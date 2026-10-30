"""Backend-only spend policy RPC. GPU images must not import Redis/provider code."""

from utils.observability.stt_cap_dispatch import DispatchPath, DispatchReason, record_decision

import math
import time

from config.stt_cap_dispatch import offline_admission_enabled as cap_dispatch_enabled
from utils.stt_cap_dispatch import sync_admission
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.scheduler import owns_lease
from utils.fair_use import get_hard_restriction_status, is_daily_audio_ceiling_exceeded
from utils.sync.backfill import reserve_backfill_speech, retry_after_next_utc_day


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


def authorize(store, leases: list[dict], *, now: float | None = None) -> dict:
    current = time.time() if now is None else now
    allowed, retries, held_reason = [], {}, {}
    for lease in leases:
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

            snapshot = store.run(read)
            if snapshot is None:
                retries[segment] = 30
                continue
            job, binding, intake = snapshot
            # Latest admission decision, not a sticky last denial: the same
            # transaction that seals (or defers) the unit records {reason,
            # outcome, at} so an outside reader can tell an exhausted-owner
            # hold from a wedge without inventing an age TTL.
            allow_reason = 'scope_disabled'
            if cap_dispatch_enabled(job['owner_id'], 'batch'):
                permitted, reason = batch_admission(
                    job, float(job.get('duration_seconds', 0)), 'parakeet', path=DispatchPath.BATCH_GPU
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
                restricted, retry_after = get_hard_restriction_status(job['owner_id'])
                if restricted:
                    retries[segment] = max(1, min(86400, retry_after or 3600))
                    held_reason[segment] = 'fair_use_restricted'
                    continue
                if is_daily_audio_ceiling_exceeded(job['owner_id']):
                    retries[segment] = retry_after_next_utc_day()
                    held_reason[segment] = 'daily_audio_ceiling'
                    continue
            else:
                # Speech is unknown before GPU VAD. Reserve an upper bound
                # once per content key using the exact existing Redis guard.
                duration = float(intake.get('total_audio_seconds', 0))
                if not binding.get('content_id') or not math.isfinite(duration) or duration <= 0:
                    raise ValueError('durable content duration required for spend admission')
                reservation = reserve_backfill_speech(
                    job['owner_id'], binding['content_id'], math.ceil(duration * 1000)
                )
                if not reservation.allowed:
                    retries[segment] = max(1, min(86400, reservation.retry_after or 3600))
                    held_reason[segment] = 'backfill_reservation'
                    continue

            def seal(tx):
                latest = tx.get('jobs', segment)
                if not owns_lease(latest, token, time.time() if now is None else current):
                    return False
                latest['compute_admission_token'] = token
                latest['compute_decision'] = {'reason': allow_reason, 'outcome': 'allowed', 'at': current}
                latest.pop('last_policy_hold', None)  # an allow ends the parked hold
                tx.put('jobs', segment, latest)
                return True

            if store.run(seal):
                allowed.append(segment)
            else:
                retries[segment] = 30
        except BatchPrivacyBlocked:
            retries[segment] = 30
            held_reason[segment] = 'privacy_blocked'
        except Exception:
            # Policy backend failure is never permission to spend GPU capacity,
            # and never a durable decision either: an unevaluated unit stays
            # unclassified for outside readers (BLIND), not falsely held/allowed.
            retries[segment] = 30
    return {'allowed': allowed, 'retry_after': retries, 'held_reason': held_reason}

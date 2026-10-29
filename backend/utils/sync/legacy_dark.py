"""Legacy-sync kill switch ("legacy dark"): contract (h) of the legacy-retire swarm.

One runtime switch, ``rollout_cohorts/_ramp.envs.<env>.legacy_sync``, moves the
legacy sync lane through ``on`` -> ``draining`` -> ``dark`` without a deploy.
The value is read through ``utils.rollout.runtime_percent.legacy_sync_mode``
(contract (f): 30s TTL, last-known-good on read errors). This module owns what
the legacy call sites do with it:

* ``on``: today's behaviour, byte for byte.
* ``draining``: no new legacy admission and no new sequencer owner. Accepted
  legacy work (running tasks, ``sync_backfill_pending`` entries) finishes.
* ``dark``: as ``draining``, and the sequencer sweep stops claiming.

Fail-safe direction. Any failure to read the mode serves ``on``. While the soak
runs the legacy image, queues and jobs are untouched, so ``on`` is the one-write
rollback (h, "Reversibility window"); a read failure therefore degrades to the
known-good path instead of refusing uploads.

The double-processing fence (h, invariant 4) is decided here from the content
ledger row the batch intake already reads. Call sites only translate the
decision into their response. Nothing in this module logs a uid.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping, Optional

from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)

# The four live legacy queues (h, Grounding). ``sync-backfill-fresh`` is the
# 10-19 04:52Z re-point and is the live backfill queue until deletion.
LEGACY_QUEUES = ('sync-jobs', 'sync-jobs-fresh', 'sync-backfill', 'sync-backfill-fresh')
LEGACY_TRANSCRIPTION_QUEUES = ('sync-jobs', 'sync-backfill', 'sync-backfill-fresh')
# Matches database.sync_ledger.CLAIM_STALE_SECONDS; asserted equal in tests so
# this module stays importable without a Firestore client.
CLAIM_STALE_SECONDS = 2 * 24 * 60 * 60
DARK_RETRY_AFTER_SECONDS = 60
# A legacy job is created only on a mode read at most this old; an older read is
# taken again first. With the 30s ramp cache that bounds how long after a flip a
# stale 'on' can still create a legacy job, which is what final_pass_rehome's
# flip grace relies on (it must exceed this plus the cache TTL).
ADMISSION_REVALIDATE_SECONDS = 60


class LegacySyncMode(StrEnum):
    ON = 'on'
    DRAINING = 'draining'
    DARK = 'dark'


class LegacyAdmissionReason(StrEnum):
    """Why a new legacy job was created (``omi_legacy_sync_admissions_total``)."""

    UNKNOWN = 'unknown'
    BATCH_NOT_ENABLED = 'batch_not_enabled'
    INTAKE_FALLBACK = 'intake_fallback'
    LEGACY_RECORD_OWNER = 'legacy_record_owner'
    LEGACY_FRESH = 'legacy_fresh'


class LegacyDarkReason(StrEnum):
    """Outcomes of the dark fence and sequencer exits (``omi_legacy_dark_ack_total``).

    Lane 14 may re-home this enum into ``utils.observability.reasons`` under
    ``ReasonFamily.LEGACY_DARK``; the values are the contract, not the location.
    """

    UNKNOWN = 'unknown'
    LEGACY_COMPLETED = 'legacy_completed'
    LEGACY_HELD = 'legacy_held'
    LEGACY_ACTIVE = 'legacy_active'
    LEGACY_ACTIVE_IN_DARK = 'legacy_active_in_dark'
    LEGACY_STRANDED = 'legacy_stranded'
    LEGACY_STRANDED_ADOPTED = 'legacy_stranded_adopted'
    LEGACY_FINAL_PASS_REHOMED = 'legacy_final_pass_rehomed'
    LEGACY_CAPPED = 'legacy_capped'
    ADMISSION_REFUSED = 'admission_refused'
    SEQUENCER_DARK = 'sequencer_dark'
    SEQUENCER_REGISTRATION_SKIPPED = 'sequencer_registration_skipped'
    SEQUENCER_OWNS_JOB = 'sequencer_owns_job'
    SEQUENCER_OWNER_ACTIVE = 'sequencer_owner_active'


class LegacyOwnership(StrEnum):
    """Who owns a content id according to its ``sync_content_ledger`` row."""

    NONE = 'none'
    BATCH = 'batch'
    COMPLETED = 'completed'
    HELD = 'held'
    ACTIVE = 'active'
    CAPPED = 'capped'
    STRANDED = 'stranded'


class FenceAction(StrEnum):
    LEGACY = 'legacy'  # mode on: today's path (the legacy claimant stays authoritative)
    ADMIT_BATCH = 'admit_batch'  # not legacy-owned, or a stranded row batch adopts
    ACK = 'ack'  # already accepted: answer without creating any job
    RETRY = 'retry'  # 409 + Retry-After; the client keeps its audio


OMI_LEGACY_SYNC_ADMISSIONS_TOTAL = Counter(
    'omi_legacy_sync_admissions_total',
    'New legacy sync jobs created, by bounded reason; flat in draining and dark',
    ['reason'],
)
OMI_LEGACY_DARK_ACK_TOTAL = Counter(
    'omi_legacy_dark_ack_total',
    'Legacy-owned uploads and sequencer calls answered by the legacy-dark fence',
    ['reason'],
)
OMI_LEGACY_SYNC_MODE = Gauge(
    'omi_legacy_sync_mode',
    'Legacy sync mode last served by this process (1 for the active mode)',
    ['mode'],
)
OMI_LEGACY_SYNC_MODE_READ_TOTAL = Counter(
    'omi_legacy_sync_mode_read_total',
    'Legacy sync mode reads that fell back to on, by bounded source',
    ['source'],
)


def _label(value: object, enum: type[StrEnum]) -> str:
    try:
        return enum(value).value
    except ValueError:
        return 'unknown'


def _publish_mode(mode: LegacySyncMode) -> None:
    try:
        for member in LegacySyncMode:
            OMI_LEGACY_SYNC_MODE.labels(mode=member.value).set(1 if member is mode else 0)
    except Exception:
        pass


def _fallback(source: str) -> LegacySyncMode:
    try:
        OMI_LEGACY_SYNC_MODE_READ_TOTAL.labels(source=source).inc()
    except Exception:
        pass
    _publish_mode(LegacySyncMode.ON)
    return LegacySyncMode.ON


def current_mode() -> LegacySyncMode:
    """The served mode. Never raises; every failure serves ``on``."""
    try:
        # Imported per call (a cached module lookup): router test harnesses replace
        # ``utils`` wholesale, and a missing reader must serve ``on``, not fail import.
        from utils.rollout import runtime_percent
    except Exception:  # ImportError, or a harness's stub package without __spec__
        return _fallback('absent')
    try:
        raw: object = runtime_percent.legacy_sync_mode()
    except NotImplementedError:
        # The (f) stub before lane 6's implementation: the switch does not exist yet.
        return _fallback('absent')
    except Exception as error:
        logger.error('event=legacy_dark action=mode_read outcome=error exception_type=%s', type(error).__name__)
        return _fallback('error')
    try:
        mode = LegacySyncMode(raw)
    except ValueError:
        logger.error('event=legacy_dark action=mode_read outcome=malformed')
        return _fallback('malformed')
    _publish_mode(mode)
    return mode


def legacy_admission_allowed(mode: Optional[LegacySyncMode] = None) -> bool:
    """Whether a new legacy job may be created (admission, legacy-fresh, intake fallback)."""
    return (mode or current_mode()) is LegacySyncMode.ON


def mode_age_seconds(now: Optional[datetime] = None) -> Optional[float]:
    """Seconds since the served ramp document was last written; None when that is unknown.

    A request that read ``on`` just before a flip keeps serving it for the rest
    of that request (the mode is read once, from a 30s cache), so a caller that
    must not race such a request waits this long after the write.
    """
    try:
        from utils.rollout import runtime_percent

        written = getattr(runtime_percent.ramp_snapshot(), 'updated_at', None)
    except Exception:
        return None
    if not isinstance(written, str) or not written:
        return None
    try:
        parsed = datetime.fromisoformat(written.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - parsed).total_seconds()


def sequencer_registration_allowed(mode: Optional[LegacySyncMode] = None) -> bool:
    """New sequencer owners and the pre-sequencer migration branch exist only in ``on``."""
    return (mode or current_mode()) is LegacySyncMode.ON


def sequencer_dispatch_allowed(mode: Optional[LegacySyncMode] = None) -> bool:
    """``draining`` still dispatches accepted ``sync_backfill_pending`` entries; ``dark`` does not."""
    return (mode or current_mode()) is not LegacySyncMode.DARK


def record_legacy_admission(reason: LegacyAdmissionReason | str, mode: Optional[LegacySyncMode] = None) -> None:
    """Count one new legacy job. A count in ``draining``/``dark`` is a bug (h, invariant 1)."""
    label = _label(reason, LegacyAdmissionReason)
    try:
        OMI_LEGACY_SYNC_ADMISSIONS_TOTAL.labels(reason=label).inc()
    except Exception:
        pass
    if mode is not None and mode is not LegacySyncMode.ON:
        logger.error(
            'event=legacy_dark action=legacy_admission outcome=invariant_violation mode=%s reason=%s', mode.value, label
        )


def record_dark_ack(reason: LegacyDarkReason | str) -> None:
    try:
        OMI_LEGACY_DARK_ACK_TOTAL.labels(reason=_label(reason, LegacyDarkReason)).inc()
    except Exception:
        pass


def _as_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _valid_completed(result: Any) -> bool:
    from database.sync_ledger import is_valid_completed_sync_content_result

    return is_valid_completed_sync_content_result(result)


def _valid_held(result: Any) -> bool:
    from database.sync_ledger import is_valid_held_sync_content_result

    return is_valid_held_sync_content_result(result)


def classify_ledger_row(
    row: Optional[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    owner_job_present: Optional[bool] = None,
) -> LegacyOwnership:
    """Classify a ``sync_content_ledger`` row the way ``_claim_transaction`` would.

    ``owner_job_present`` is the Redis legacy job's existence when the caller
    knows it; ``False`` makes a fresh processing claim STRANDED (the 24h Redis
    expiry before the 48h claim expiry), ``None`` trusts the claim's age.
    """
    if not row:
        return LegacyOwnership.NONE
    now = now or datetime.now(timezone.utc)
    protocol = row.get('dispatch_protocol')
    status = row.get('status')
    if protocol == 'batch_v1':
        return LegacyOwnership.BATCH
    if protocol == 'stt_cap_hold_v1' and status == 'held':
        return LegacyOwnership.HELD if _valid_held(row.get('result')) else LegacyOwnership.ACTIVE
    if status == 'completed':
        return LegacyOwnership.COMPLETED if _valid_completed(row.get('result')) else LegacyOwnership.STRANDED
    pause_until = _as_utc(row.get('repeat_failure_pause_until'))
    if pause_until is not None and pause_until > now:
        return LegacyOwnership.CAPPED
    if status == 'retryable':
        return LegacyOwnership.STRANDED
    if status == 'processing' and row.get('job_id'):
        if owner_job_present is False:
            return LegacyOwnership.STRANDED
        updated_at = _as_utc(row.get('updated_at'))
        # ``_claim_transaction`` takes over a claim without a timestamp, and one
        # past the stale window (M1 review L10-3).
        if updated_at is None or (now - updated_at).total_seconds() >= CLAIM_STALE_SECONDS:
            return LegacyOwnership.STRANDED
        return LegacyOwnership.ACTIVE
    # Unknown or partial rows: legacy would replace them on the next claim.
    return LegacyOwnership.STRANDED


def legacy_owner_job_present(row: Optional[Mapping[str, Any]]) -> Optional[bool]:
    """Whether a processing claim's Redis legacy job still exists, else None.

    The same existence check ``claim_sync_content`` makes before re-claiming:
    Redis expires at 24h, the ledger claim at 48h, so a fresh-looking claim
    whose owner job is gone is stranded (M1 review L10-3). Blocking: call from
    the db executor.
    """
    if not row or row.get('status') != 'processing' or row.get('dispatch_protocol') in ('batch_v1', 'stt_cap_hold_v1'):
        return None
    job_id = row.get('job_id')
    if not isinstance(job_id, str) or not job_id:
        return None
    try:
        from database.sync_jobs import get_sync_job

        return get_sync_job(job_id) is not None
    except Exception as error:
        # Unknown is not absent: trust the claim's age (ACTIVE answers 409, the
        # client keeps the audio) rather than adopting a possibly live owner.
        logger.warning('event=legacy_dark_owner_probe outcome=unavailable exception_type=%s', type(error).__name__)
        return None


def read_ledger_row(uid: str, content_id: str) -> Optional[Mapping[str, Any]]:
    """The content's ``sync_content_ledger`` row, or None. Blocking: call from the db executor."""
    from database._client import get_firestore_client
    from database.sync_ledger import sync_content_ledger_ref

    snapshot = sync_content_ledger_ref(get_firestore_client(), uid, content_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    return snapshot.to_dict() or {}


@dataclass(frozen=True)
class FenceDecision:
    action: FenceAction
    reason: Optional[LegacyDarkReason]
    ownership: LegacyOwnership
    job_id: Optional[str] = None
    result: Optional[Mapping[str, Any]] = None
    retry_after_seconds: Optional[int] = None


def fence_decision(
    row: Optional[Mapping[str, Any]],
    mode: LegacySyncMode,
    *,
    now: Optional[datetime] = None,
    owner_job_present: Optional[bool] = None,
    batch_adopts_stranded: bool = False,
) -> FenceDecision:
    """Decide what an upload of already-claimed content gets (h, invariant 4).

    In ``on`` legacy-owned content keeps today's route (the original claimant
    remains the sole authority). In ``draining``/``dark`` no legacy job is
    created and nothing legacy owns is re-admitted to batch, except STRANDED
    rows: legacy will never finish those, so they are adopted by batch when
    the caller supports the ledger takeover (lane 8's intake), and otherwise
    answered 409 so the client keeps the audio (invariant 2). A CAPPED row
    keeps its repeat-failure pause: 409 for the remaining pause.
    """
    ownership = classify_ledger_row(row, now=now, owner_job_present=owner_job_present)
    if ownership in (LegacyOwnership.NONE, LegacyOwnership.BATCH):
        return FenceDecision(FenceAction.ADMIT_BATCH, None, ownership)
    if mode is LegacySyncMode.ON:
        return FenceDecision(FenceAction.LEGACY, None, ownership)
    row = row or {}
    job_id = row.get('job_id') if isinstance(row.get('job_id'), str) else None
    if ownership is LegacyOwnership.COMPLETED:
        return FenceDecision(FenceAction.ACK, LegacyDarkReason.LEGACY_COMPLETED, ownership, job_id, row.get('result'))
    if ownership is LegacyOwnership.HELD:
        return FenceDecision(FenceAction.ACK, LegacyDarkReason.LEGACY_HELD, ownership, job_id, row.get('result'))
    if ownership is LegacyOwnership.ACTIVE:
        reason = (
            LegacyDarkReason.LEGACY_ACTIVE
            if mode is LegacySyncMode.DRAINING
            else LegacyDarkReason.LEGACY_ACTIVE_IN_DARK
        )
        return FenceDecision(FenceAction.ACK, reason, ownership, job_id)
    retry_after = DARK_RETRY_AFTER_SECONDS
    # A live repeat-failure pause is never adopted (M1 review L10-4): 409 for
    # the remaining pause, whatever the caller supports.
    if ownership is LegacyOwnership.CAPPED:
        pause_until = _as_utc(row.get('repeat_failure_pause_until'))
        if pause_until is not None:
            seconds = (pause_until - (now or datetime.now(timezone.utc))).total_seconds()
            if math.isfinite(seconds):
                retry_after = max(1, min(86400, int(seconds) + 1))
        return FenceDecision(FenceAction.RETRY, LegacyDarkReason.LEGACY_CAPPED, ownership, job_id, None, retry_after)
    if batch_adopts_stranded:
        return FenceDecision(FenceAction.ADMIT_BATCH, LegacyDarkReason.LEGACY_STRANDED_ADOPTED, ownership, job_id)
    return FenceDecision(FenceAction.RETRY, LegacyDarkReason.LEGACY_STRANDED, ownership, job_id, None, retry_after)


def fence_response(decision: FenceDecision, *, total_files: int, lane: str) -> Optional[JSONResponse]:
    """Translate an ACK/RETRY decision into the shipped v2 upload contract.

    ``None`` for LEGACY/ADMIT_BATCH: the caller continues on its own path.
    The 409 shapes are the ones shipped clients already follow for the same
    content (``utils.sync.admission_responses``); no 503 (invariant 2).
    """
    if decision.action is FenceAction.ACK:
        record_dark_ack(decision.reason or LegacyDarkReason.UNKNOWN)
        if decision.ownership in (LegacyOwnership.COMPLETED, LegacyOwnership.HELD):
            result = decision.result if isinstance(decision.result, Mapping) else {}
            segments = result.get('total_segments')
            return JSONResponse(
                status_code=202,
                content={
                    'job_id': decision.job_id,
                    'status': 'completed',
                    'total_files': total_files,
                    'total_segments': segments if isinstance(segments, int) and not isinstance(segments, bool) else 0,
                    'poll_after_ms': 0,
                    'lane': lane,
                },
            )
        from utils.sync.admission_responses import sync_content_in_progress_response

        # Same response an active legacy owner gets in ``on``: the client
        # follows the owner's job id; the running legacy task finishes it.
        return sync_content_in_progress_response(decision.job_id)
    if decision.action is FenceAction.RETRY:
        record_dark_ack(decision.reason or LegacyDarkReason.UNKNOWN)
        retry_after = decision.retry_after_seconds or DARK_RETRY_AFTER_SECONDS
        return JSONResponse(
            status_code=409,
            headers={'Retry-After': str(retry_after)},
            content={
                'code': 'sync_content_retry_later',
                'reason': 'dependency_warming',
                'detail': 'This audio will be processed shortly; local audio was not consumed',
                'poll_after_ms': retry_after * 1000,
            },
        )
    return None


def admission_refused_response() -> JSONResponse:
    """The upload path would have created a legacy job in ``draining``/``dark``.

    Batch or provider-STT should have taken it (lanes 6 and 8); this is the
    invariant-2 backstop: a 409 that keeps the client's audio, never a 503.
    """
    record_dark_ack(LegacyDarkReason.ADMISSION_REFUSED)
    logger.error('event=legacy_dark action=admission outcome=refused_no_batch_route')
    return JSONResponse(
        status_code=409,
        headers={'Retry-After': str(DARK_RETRY_AFTER_SECONDS)},
        content={
            'code': 'sync_content_retry_later',
            'reason': 'dependency_warming',
            'detail': 'Sync is moving to a new pipeline; local audio was not consumed',
            'poll_after_ms': DARK_RETRY_AFTER_SECONDS * 1000,
        },
    )


def sequencer_dark_response() -> JSONResponse:
    """``dark`` sweep and wake: consumed (200) without claiming (h, Sequencer column)."""
    record_dark_ack(LegacyDarkReason.SEQUENCER_DARK)
    return JSONResponse(status_code=200, content={'status': 'legacy_dark', 'outcomes': {'legacy_dark': 1}})


# --- Drain census (h, ``dark`` entry precondition and soak checks 2, 3, 5) ---

# Fields that gate ``dark``. Inline (non-Cloud-Tasks) legacy jobs have no
# aggregate source; they are bounded by ``legacy_admissions_window`` (no new
# job for 30 minutes) plus the 10-minute confirmation.
CENSUS_FIELDS = (
    'sync_backfill_pending',
    'sequencer_active_owners',
    'redrive_required',
    'cap_holds_awaiting_legacy',
    'queue_depth_sync_jobs',
    'queue_depth_sync_jobs_fresh',
    'queue_depth_sync_backfill',
    'queue_depth_sync_backfill_fresh',
    'legacy_admissions_window',
)


@dataclass(frozen=True)
class DrainCensus:
    """Aggregate counts only. ``None`` means the read was unavailable (fails closed).

    ``cap_holds_awaiting_legacy`` is an upper bound (every ``stt_cap_holds``
    row); the ledger status counts need a collection-group index prod does not
    have, so they are informational and never gate.
    """

    observed_at: float
    sync_backfill_pending: Optional[int]
    sequencer_active_owners: Optional[int]
    redrive_required: Optional[int]
    cap_holds_awaiting_legacy: Optional[int]
    queue_depth_sync_jobs: Optional[int]
    queue_depth_sync_jobs_fresh: Optional[int]
    queue_depth_sync_backfill: Optional[int]
    queue_depth_sync_backfill_fresh: Optional[int]
    legacy_admissions_window: Optional[int]
    ledger_processing_legacy: Optional[int] = None
    ledger_retryable_legacy: Optional[int] = None

    def nonzero(self) -> dict[str, Optional[int]]:
        """Fields that block ``dark``: non-zero or unavailable."""
        return {name: getattr(self, name) for name in CENSUS_FIELDS if getattr(self, name) != 0}


DARK_CONFIRMATION_SECONDS = 600


@dataclass(frozen=True)
class DarkEntryVerdict:
    ready: bool
    blockers: tuple[str, ...]


def dark_entry_verdict(first: DrainCensus, second: DrainCensus) -> DarkEntryVerdict:
    """``draining`` reached zero, confirmed by two reads >= 10 minutes apart (h)."""
    blockers: list[str] = []
    if second.observed_at - first.observed_at < DARK_CONFIRMATION_SECONDS:
        blockers.append('confirmation_gap_under_10m')
    for label, census in (('first', first), ('second', second)):
        for name, value in census.nonzero().items():
            blockers.append(f'{label}:{name}={"unavailable" if value is None else value}')
    return DarkEntryVerdict(not blockers, tuple(blockers))

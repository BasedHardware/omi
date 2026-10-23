"""Re-home a conversation stranded on ``legacy_final_pass_v1`` to batch sync.

``record_lane_owner`` decides which pipeline serves a conversation's WAL
uploads. ``legacy_final_pass_v1`` is claimed by the transcription-shadow final
pass (``utils.conversations.transcription_shadow``) and by an ownerless
conversation's first WAL upload while its uid is outside the batch ramp
(``utils.batch_pipeline.live_upload``). Nothing clears it: a completed or dead
final pass leaves it on the conversation for good.

In ``on`` that is harmless, legacy sync still serves the conversation. In
``draining``/``dark`` no legacy job may be created, so every later upload for
such a conversation is acknowledged with the shipped in-progress 409 and the
phone keeps that audio until the owner changes (M3 review; lead ruling
b209a5). This module is the owner change: when no live legacy job holds the
uid, transfer the route to ``batch_sync_v1`` with the same revision-fenced
CAS every other owner transition uses, and let the caller admit the upload
through the unchanged batch intake, so its privacy, binding and predecessor
fences apply as they do to any batch upload.

Blocking helpers: call from the db executor. Nothing here logs a uid.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any, Callable, Optional

from utils.sync import legacy_dark

logger = logging.getLogger(__name__)

LEGACY_FINAL_PASS_OWNER = 'legacy_final_pass_v1'
BATCH_SYNC_OWNER = 'batch_sync_v1'
BATCH_OWNERS = frozenset({'batch_live_v1', BATCH_SYNC_OWNER})
# The mode is read once per request from a 30s cache; no upload request lives
# anywhere near this long between that read and its legacy job creation.
FLIP_GRACE_SECONDS = 300


class RehomeOutcome(StrEnum):
    REHOMED = 'rehomed'  # this call moved legacy_final_pass_v1 -> batch_sync_v1
    ELIGIBLE = 'eligible'  # dry run (apply=False): every fence passed, no write made
    ALREADY_BATCH = 'already_batch'  # a batch owner holds it, now or through a concurrent winner
    HELD = 'held'  # a live legacy job, an unavailable probe or a lost CAS: keep today's ACK
    NOT_APPLICABLE = 'not_applicable'  # not legacy-owned, missing, a tombstone or a deleting account


def rehomes_to_batch(outcome: RehomeOutcome) -> bool:
    return outcome in (RehomeOutcome.REHOMED, RehomeOutcome.ALREADY_BATCH)


def live_legacy_jobs(uid: str) -> Optional[int]:
    """Queued or processing legacy sync jobs for this uid; None when the probe is unavailable.

    A legacy job records no conversation id, so the uid's pending index is the
    lease: any live job may still write this conversation. Unknown is not zero
    (the same fail-safe as ``legacy_dark.legacy_owner_job_present``).
    """
    try:
        from database.sync_jobs import pending_sync_jobs

        return len(pending_sync_jobs(uid))
    except Exception as error:
        logger.warning(
            'event=legacy_dark action=final_pass_rehome outcome=job_probe_unavailable exception_type=%s',
            type(error).__name__,
        )
        return None


def rehome_final_pass_owner(
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
    live_jobs: Optional[Callable[[str], Optional[int]]] = None,
    apply: bool = True,
) -> RehomeOutcome:
    """One revision-fenced attempt to move the conversation's route owner to batch.

    Callers decide when: uploads only in ``draining``/``dark`` (``upload_rehome``),
    the operator sweep before the ``draining`` flip. ``live_jobs`` is the uid's
    live legacy job count (the Redis pending index in-process; the sweep, which
    has no Redis, passes a ledger probe); None or non-zero holds. ``apply=False``
    stops before the CAS and answers ELIGIBLE. Never two owners: the CAS is the
    ``claim_record_lane_owner`` the shadow pass and live admission use, so a
    final pass claiming concurrently either loses here (HELD; the client retries)
    or finds a batch owner and stops, and ``promote_final_pass_if_current``
    refuses a batch-owned conversation, so a pass already running cannot promote
    over batch's work.
    """
    from database import conversations as conversations_db
    from database._client import get_firestore_client

    client = firestore_client if firestore_client is not None else get_firestore_client()
    probe = live_jobs if live_jobs is not None else live_legacy_jobs
    ref = (
        client.collection('users')
        .document(uid)
        .collection(conversations_db.conversations_collection)
        .document(conversation_id)
    )
    snapshot = ref.get()
    if not getattr(snapshot, 'exists', False):
        return RehomeOutcome.NOT_APPLICABLE
    row = snapshot.to_dict() or {}
    owner = row.get('record_lane_owner')
    if owner in BATCH_OWNERS:
        return RehomeOutcome.ALREADY_BATCH
    if owner != LEGACY_FINAL_PASS_OWNER:
        return RehomeOutcome.NOT_APPLICABLE
    # Privacy: a tombstone or a deleting account gets no new processing route.
    if conversations_db.is_soft_deleted(row):
        return RehomeOutcome.NOT_APPLICABLE
    if client.collection('account_deletions').document(uid).get().exists:
        return RehomeOutcome.NOT_APPLICABLE
    pending = probe(uid)
    if pending is None or pending > 0:
        logger.info('event=legacy_dark action=final_pass_rehome outcome=held pending_jobs=%s', pending)
        return RehomeOutcome.HELD
    if not apply:
        return RehomeOutcome.ELIGIBLE
    revision = conversations_db.claim_record_lane_owner(
        uid, conversation_id, BATCH_SYNC_OWNER, snapshot.update_time, firestore_client=client
    )
    if revision is None:
        # Lost the CAS: a concurrent claim or edit moved the revision. Read once;
        # a batch winner is ours to follow, anything else is held (one attempt per call).
        current = ref.get()
        if getattr(current, 'exists', False) and (current.to_dict() or {}).get('record_lane_owner') in BATCH_OWNERS:
            return RehomeOutcome.ALREADY_BATCH
        logger.info('event=legacy_dark action=final_pass_rehome outcome=held reason=contended')
        return RehomeOutcome.HELD
    legacy_dark.record_dark_ack(legacy_dark.LegacyDarkReason.LEGACY_FINAL_PASS_REHOMED)
    logger.info('event=legacy_dark action=final_pass_rehome outcome=rehomed')
    return RehomeOutcome.REHOMED


def upload_rehome(
    mode: legacy_dark.LegacySyncMode,
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
    mode_age: Optional[float] = None,
) -> RehomeOutcome:
    """The upload-time re-home: only once legacy sync can no longer serve the conversation.

    Held for ``FLIP_GRACE_SECONDS`` after the ramp document was last written (an
    unknown age holds): a request that read ``on`` just before the flip can still
    create a legacy job for this uid after it, and its job is only visible to the
    live-job probe once created. Every such request has finished well inside the
    grace, so from then on the probe sees every boundary job before any re-home.
    """
    if mode is legacy_dark.LegacySyncMode.ON:
        return RehomeOutcome.NOT_APPLICABLE
    age = mode_age if mode_age is not None else legacy_dark.mode_age_seconds()
    if age is None or age < FLIP_GRACE_SECONDS:
        logger.info('event=legacy_dark action=final_pass_rehome outcome=held reason=flip_grace')
        return RehomeOutcome.HELD
    return rehome_final_pass_owner(uid, conversation_id, firestore_client=firestore_client)

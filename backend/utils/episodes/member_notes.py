"""Default-on live-member notes gate; explicit recording detail is a narrow escalation.

Lifecycle: ops_kill; owner home-overlap; permanent env kill switch.
"""

import logging
import time
import importlib
from datetime import datetime, timezone

from config.home_processing import live_member_notes_enabled, bounded_member_notes_enabled
from database import episodes, live_member_notes
from database.outbox_firestore import ENRICHMENT_OUTBOX
from utils.conversations import demand_processing
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.summary_delivery import PROCESS_CONTEXT
from utils.enrichment import outbox
from utils.episodes.policy import owned_member_ids, idle_close_due, utc
from utils.sync import processing_hold, stage
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
# Cover the full bounded hold, plus one quiet window for worker delivery.
DETAIL_LEASE_SECONDS = processing_hold.MAX_HOLD_SECONDS + processing_hold.QUIET_SECONDS
# Job creation already follows the ratified 30-minute occasion window. Allow
# three minutes of ordinary settlement, then one member-revision fallback.
LIVE_MEMBER_NOTES_MAX_DEFERRAL_SECONDS = 180
EXPLICIT = frozenset(
    {
        ProcessingTrigger.FIRST_OPEN,
        ProcessingTrigger.USER_REPROCESS,
        ProcessingTrigger.CLIENT_FINALIZE,
        ProcessingTrigger.BACKLOG_CHOICE,
        ProcessingTrigger.MERGE,
        ProcessingTrigger.HISTORICAL_OPEN,
    }
)


class LiveMemberNotesDeferred(processing_hold.ProcessingDeferred):
    """A live episode still owns these notes; this is a scheduling wait."""


def _unavailable(outcome: str, error: Exception) -> None:
    record_fallback(
        component='conversation_finalization', from_mode='none', to_mode='none', reason='other', outcome='degraded'
    )
    logger.warning('event=home_member_detail outcome=%s exception_type=%s', outcome, type(error).__name__)


def _key(uid, cid):
    return stage.redis_key(f'home-member-detail:{uid}:{cid}')


def _aged_job(uid, row):
    job_id = row.get('finalization_job_id')
    if not job_id or row.get('status') == 'in_progress':
        return False
    job = importlib.import_module('database.conversation_finalization_jobs').get_finalization_job(job_id)
    created = utc((job or {}).get('created_at'))
    return bool(
        job
        and job.get('uid') == uid
        and job.get('conversation_id') == row['id']
        and created
        and time.time() - created.timestamp() >= LIVE_MEMBER_NOTES_MAX_DEFERRAL_SECONDS
    )


def _bounded_retry(row):
    return (
        row.get('finalization_job_id')
        and row.get('status') != 'in_progress'
        and row.get('source') == 'omi'
        and row.get('record_lane_owner') != 'batch_live_v1'
    )


def _settle_idle_owner(uid, owner):
    # Fetch full state only on a deferred durable retry. Reuse Home's exact
    # close helper, including the last_activity_at transaction fence.
    full = episodes.get_episode(uid, owner['id'], follow_redirects=False) if owner.get('id') else None
    if full and idle_close_due(full, datetime.fromtimestamp(time.time(), timezone.utc)):
        service = importlib.import_module('utils.episodes.service')
        return service.settle_episode_for_read(uid, full, service.Collaborators())
    return full or owner


def waits(uid: str, row: dict, trigger=ProcessingTrigger.SYNC_UPDATE) -> bool:
    if not live_member_notes_enabled(uid) or trigger in EXPLICIT or not row.get('id'):
        return False
    try:
        owner = episodes.get_episode_owner_snapshot(uid, row['id'])
    except Exception as error:
        _unavailable('owner_unavailable', error)
        return False
    if not owner or owner.get('status') != 'live' or row['id'] not in owned_member_ids(owner):
        return False
    if bounded_member_notes_enabled() and _bounded_retry(row):
        try:
            owner = _settle_idle_owner(uid, owner)
            if owner.get('status') != 'live' or row['id'] not in owned_member_ids(owner):
                return False
        except Exception as error:
            _unavailable('bounded_recovery_unavailable', error)
        try:
            if _aged_job(uid, row):
                return False
        except Exception as error:
            _unavailable('job_unavailable', error)
    # Unlike owner-wide attention, this lease names just the detail being read.
    try:
        return not bool(demand_processing.client().get(_key(uid, row['id'])))
    except Exception as error:
        _unavailable('lease_unavailable', error)
        return False  # Redis loss fails eager; durable processing remains authoritative.


def before_notes(uid, conversation, trigger, *, finalization_fence=None):
    if (
        getattr(conversation, 'transcript_segments', None)
        and live_member_notes_enabled(uid)
        and waits(
            uid,
            {
                'id': getattr(conversation, 'id', None),
                'status': getattr(conversation, 'status', None),
                'source': getattr(conversation, 'source', None),
                'record_lane_owner': getattr(conversation, 'record_lane_owner', None),
                'finalization_job_id': finalization_fence[0] if finalization_fence else None,
            },
            trigger,
        )
    ):
        if PROCESS_CONTEXT.get() is None and finalization_fence is None:
            # Legacy direct sync has no durable notes owner yet. Enroll it before
            # yielding; the same key coalesces with any concurrent outbox writer.
            outbox.mark(uid, conversation.id, getattr(conversation, 'language', None) or 'en', sync_hold=True)
        raise LiveMemberNotesDeferred('live_episode_notes', time.time() + 60)


def before_model(uid, conversation, trigger, *, finalization_fence=None):
    """The timeout's extra paid attempt is fenced separately from worker retries."""
    if not bounded_member_notes_enabled() or not live_member_notes_enabled(uid) or trigger in EXPLICIT:
        return
    if finalization_fence is None:
        return
    row = {
        'id': conversation.id,
        'finalization_job_id': finalization_fence[0],
        'source': getattr(conversation, 'source', None),
        'record_lane_owner': getattr(conversation, 'record_lane_owner', None),
    }
    if not _bounded_retry(row):
        return
    if not _aged_job(uid, row):
        return
    try:
        owner = episodes.get_episode_owner_snapshot(uid, conversation.id)
    except Exception as error:
        # An unreadable owner must not stall finalization: a persistent read
        # failure would recreate the unbounded wait this bound removes. Proceed
        # as main does, unfenced by the extra permit, and count the fallback.
        _unavailable('owner_unavailable', error)
        return
    if not owner or owner.get('status') != 'live' or conversation.id not in owned_member_ids(owner):
        return
    detail_lease = None
    try:
        detail_lease = demand_processing.client().get(_key(uid, conversation.id))
    except Exception as error:
        _unavailable('lease_unavailable', error)
    if detail_lease:
        # The detail worker owns this obligation; this finalizer must not pay.
        raise LiveMemberNotesDeferred('live_episode_notes', time.time() + 60)
    if not live_member_notes.claim(
        uid, conversation.id, finalization_fence, getattr(conversation, 'sync_content_revision', None)
    ):
        raise LiveMemberNotesDeferred('live_episode_notes', time.time() + 60)
    record_fallback(
        component='conversation_finalization', from_mode='none', to_mode='none', reason='other', outcome='degraded'
    )


def open_recording(uid: str, row: dict) -> None:
    if (
        not waits(uid, {'id': row.get('id')})
        or row.get('status') == 'in_progress'
        or not row.get('transcript_segments')
    ):
        return
    now = time.time()
    # Reuse the durable enrichment obligation and its ordinary revision/claim
    # fences. A GET never performs model work on the request thread.
    try:
        ENRICHMENT_OUTBOX.enqueue(
            outbox.key(uid, row['id']),
            uid,
            {'conversation_id': row['id'], 'language': row.get('language') or 'en'},
            now,
            coalesce='min',
            now=now,
        )
        # Publish the lease only after durable custody exists. Failed enqueue
        # leaves the next detail read free to retry immediately.
        demand_processing.client().set(_key(uid, row['id']), '1', ex=DETAIL_LEASE_SECONDS)
    except Exception as error:
        _unavailable('escalation_unavailable', error)

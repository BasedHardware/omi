"""Default-on live-member notes gate; explicit recording detail is a narrow escalation.

Lifecycle: ops_kill; owner home-overlap; permanent env kill switch.
"""

import logging
import time

from config.home_processing import live_member_notes_enabled
from database import episodes
from database.outbox_firestore import ENRICHMENT_OUTBOX
from utils.conversations import demand_processing
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.summary_delivery import PROCESS_CONTEXT
from utils.enrichment import outbox
from utils.episodes.policy import owned_member_ids
from utils.sync import processing_hold, stage
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
# Cover the full bounded hold, plus one quiet window for worker delivery.
DETAIL_LEASE_SECONDS = processing_hold.MAX_HOLD_SECONDS + processing_hold.QUIET_SECONDS
EXPLICIT = frozenset(
    {
        ProcessingTrigger.FIRST_OPEN,
        ProcessingTrigger.USER_REPROCESS,
        ProcessingTrigger.CLIENT_FINALIZE,
        ProcessingTrigger.BACKLOG_CHOICE,
        ProcessingTrigger.MERGE,
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
        and waits(uid, {'id': getattr(conversation, 'id', None)}, trigger)
    ):
        if PROCESS_CONTEXT.get() is None and finalization_fence is None:
            # Legacy direct sync has no durable notes owner yet. Enroll it before
            # yielding; the same key coalesces with any concurrent outbox writer.
            outbox.mark(uid, conversation.id, getattr(conversation, 'language', None) or 'en', sync_hold=True)
        raise LiveMemberNotesDeferred('live_episode_notes', time.time() + 60)


def open_recording(uid: str, row: dict) -> None:
    if not waits(uid, row) or row.get('status') == 'in_progress' or not row.get('transcript_segments'):
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

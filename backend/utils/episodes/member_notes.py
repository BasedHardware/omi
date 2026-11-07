"""Dark live-member notes gate; explicit recording detail is a narrow escalation.

Lifecycle: rollout; owner home-overlap; review 2026-11-21.
"""

import time

from config.home_processing import live_member_notes_enabled
from database import episodes
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.sync import processing_hold, stage

EXPLICIT = frozenset(
    {
        ProcessingTrigger.FIRST_OPEN,
        ProcessingTrigger.USER_REPROCESS,
        ProcessingTrigger.CLIENT_FINALIZE,
        ProcessingTrigger.BACKLOG_CHOICE,
        ProcessingTrigger.MERGE,
    }
)


def _key(uid, cid):
    return stage.redis_key(f'home-member-detail:{uid}:{cid}')


def waits(uid: str, row: dict, trigger=ProcessingTrigger.SYNC_UPDATE) -> bool:
    if not live_member_notes_enabled(uid) or trigger in EXPLICIT or not row.get('id'):
        return False
    owner = episodes.get_episode_owner_snapshot(uid, row['id'])
    if not owner or owner.get('status') != 'live' or row['id'] not in (owner.get('conversation_ids') or []):
        return False
    from utils.conversations.demand_processing import client

    # Unlike owner-wide attention, this lease names just the detail being read.
    return not bool(client().get(_key(uid, row['id'])))


def before_notes(uid, conversation, trigger, *, finalization_fence=None):
    if live_member_notes_enabled(uid) and waits(uid, {'id': getattr(conversation, 'id', None)}, trigger):
        from utils.conversations.summary_delivery import PROCESS_CONTEXT
        from utils.enrichment import outbox

        if PROCESS_CONTEXT.get() is None and finalization_fence is None:
            # Legacy direct sync has no durable notes owner yet. Enroll it before
            # yielding; the same key coalesces with any concurrent outbox writer.
            outbox.mark(uid, conversation.id, getattr(conversation, 'language', None) or 'en', sync_hold=True)
        raise processing_hold.ProcessingDeferred('live_episode_notes', time.time() + 60)


def open_recording(uid: str, row: dict) -> None:
    if not waits(uid, row) or row.get('status') == 'in_progress' or not row.get('transcript_segments'):
        return
    from utils.conversations.demand_processing import client
    from database.outbox_firestore import ENRICHMENT_OUTBOX
    from utils.enrichment.outbox import key

    client().set(_key(uid, row['id']), '1', ex=300)
    now = time.time()
    # Reuse the durable enrichment obligation and its ordinary revision/claim
    # fences. A GET never performs model work on the request thread.
    ENRICHMENT_OUTBOX.enqueue(
        key(uid, row['id']),
        uid,
        {'conversation_id': row['id'], 'language': row.get('language') or 'en'},
        now,
        coalesce='min',
        now=now,
    )

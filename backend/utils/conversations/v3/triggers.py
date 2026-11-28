"""Lightweight capture outbox and named-task trigger; no model or builder imports."""

import hashlib
import logging
import math
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from config import reliability_experiments
from config.conversations_v3 import SPEECH_LANDED_FIELD, conversations_v3_enabled, v3_intake_held_out
from database import conversations_v3 as store
from database.helpers import set_data_protection_level
from utils.cloud_tasks import enqueue_named_task
from utils.conversations.v3 import metrics
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# Reliability experiment instant_live_text: a refused wake is followed up at the end of a slot this long.
FOLLOW_UP_SLOT_SECONDS = 15


def mark_new(uid, row, *, continuation=False):
    """``continuation``: a v3 rotation successor of a recording row, the same capture, not new intake."""
    if (
        getattr(row.get('source'), 'value', row.get('source')) in {'omi', 'phone'}
        and not row.get('imported')
        and not row.get('v3_derived')
        and row.get('data_protection_level') != 'private'
        and conversations_v3_enabled(uid)
        # Holdout (SCA-2918): a held-out owner's new rows stay legacy; stored v3 rows keep draining,
        # and so does a capture in flight, whose rotation successor stays v3.
        and (continuation or not v3_intake_held_out(uid))
    ):
        _mark_resolved(uid, row)


def committed_sync_assignment(uid, assigned, *, attempts=3):
    """Wake reconcile for a recording a batch projection created or appended to. Post-commit, never raises.

    The assignment and its receipt are durable, so a failure must not replay the unit. A created
    recording is already stored v3_pending (``mark_new``) and the sweep finds it. An append owes its
    reconcile only through ``changed``'s ``mark_pending``, so that write is retried; if every attempt
    fails the append waits for the owner's next change, and the degraded branch is counted.
    """
    if not assigned.get('recording'):
        return
    failure = 'none'
    for attempt in range(attempts):
        try:
            changed(uid, assigned['id'])
            return
        except Exception as error:
            failure = type(error).__name__
            if attempt + 1 < attempts:
                time.sleep(0.2 * (2**attempt))
    logger.error('event=batch_projection action=v3_wake outcome=error exception_type=%s', failure)
    record_fallback(
        component='other', from_mode='dispatch', to_mode='none', reason='enqueue_failed', outcome='degraded'
    )


@set_data_protection_level(data_arg_name='row')
def _mark_resolved(uid, row):
    if row.get('data_protection_level') != 'private':
        row.update(
            recording=True,
            terminal_no_derived_effects=True,
            v3_pending=True,
            v3_pending_since=datetime.now(timezone.utc),
            **{SPEECH_LANDED_FIELD: datetime.now(timezone.utc)},
            structured={},
        )


def task_base():
    base = os.getenv('CONVERSATIONS_V3_TASKS_URL', '').rstrip('/')
    if not base:
        target = urlsplit(os.getenv('SYNC_TASKS_HANDLER_URL', ''))
        base = target.scheme + '://' + target.netloc if target.scheme and target.netloc else ''
    if not base:
        raise RuntimeError('conversations_v3_task_target_unconfigured')
    return base


def enqueue(uid, *, at=None, manual_end_id=None, native_manual_ready=None, native_rearm=False, wake_key=None):
    # A fractional silence deadline must have elapsed when reconcile runs.
    # Truncating can wake it early and defer a finished group for another minute.
    scheduled = math.ceil(at.timestamp()) if at is not None else int(datetime.now(timezone.utc).timestamp())
    minute = scheduled // 60
    prefix = 'conversations-v3-' + hashlib.sha256(uid.encode()).hexdigest()[:32]
    task_id = f'{prefix}-{minute}'
    payload = {'uid': uid}
    if native_manual_ready is not None:
        cid, upload_revision = native_manual_ready
        recording_key = hashlib.sha256(cid.encode()).hexdigest()[:32]
        wake = 'native-rearm' if native_rearm else 'native-ready'
        task_id = f'{prefix}-{wake}-{recording_key}-{upload_revision}'
        payload['trigger'] = 'native_manual_ready'
    elif manual_end_id:
        # A live task may already have completed in this minute. Its retained
        # Cloud Tasks name must not swallow the user's later explicit close.
        task_id += '-end-' + hashlib.sha256(manual_end_id.encode()).hexdigest()[:32]
    if wake_key:
        # A builder continuation: an earlier same-minute wake may run (busy) under this pass's lease.
        task_id += '-wake-' + hashlib.sha256(wake_key.encode()).hexdigest()[:32]
    base = task_base()
    queue = os.getenv('CONVERSATIONS_V3_TASKS_QUEUE', 'conversations-v3')
    url = base + '/v1/conversations-v3/reconcile'
    created = enqueue_named_task(queue, url, task_id, payload, schedule_at=scheduled)
    if (
        created is False
        and at is None
        and not manual_end_id
        and native_manual_ready is None
        and not wake_key
        and reliability_experiments.enabled('instant_live_text', uid)
    ):
        # Experiment instant_live_text: this minute's name is taken. Its task may have read the owner's
        # speech before this write (it ran or is running) or may be scheduled for later in the minute,
        # so the write would wait for the owner's next scheduled wake. One task at the end of the
        # current slot starts after every write of that slot; further writes of the slot share its name.
        # Only write-driven wakes do this: the builder's own scheduled wakes (at=) never chain.
        slot_end = (scheduled // FOLLOW_UP_SLOT_SECONDS + 1) * FOLLOW_UP_SLOT_SECONDS
        if enqueue_named_task(queue, url, f'{task_id}-late-{slot_end}', {'uid': uid}, schedule_at=slot_end):
            logger.info('event=v3_wake action=late_follow_up outcome=enqueued')


def wake_native_manual_ready(uid: str, cid: str, upload_revision: int, *, rearm: bool = False) -> None:
    """Dispatch only after the existing v3 outbox marker commits."""
    try:
        enqueue(uid, native_manual_ready=(cid, upload_revision), **({'native_rearm': True} if rearm else {}))
    except Exception as error:
        metrics.RECONCILES.labels('dispatch_error').inc()
        logger.warning('v3 native manual dispatch deferred exception_type=%s', type(error).__name__)
        record_fallback(
            component='other', from_mode='dispatch', to_mode='sweeper', reason='enqueue_failed', outcome='degraded'
        )


def changed(uid, cid, *, manual_end=False):
    should_enqueue = store.mark_pending(uid, cid, manual_end=manual_end)
    if should_enqueue and manual_end:
        # Positive proof for an untagged legacy client is recorded only after
        # mark_pending committed the server's manual-end marker.
        from utils.conversations.v3 import finish_home_sli

        finish_home_sli.observe_legacy_manual_end(uid, cid)
    if should_enqueue:
        enqueue_pending(uid, manual_end_id=cid if manual_end else None)


def enqueue_pending(uid, *, manual_end_id=None):
    try:
        enqueue(uid, **({'manual_end_id': manual_end_id} if manual_end_id else {}))
    except Exception as error:
        metrics.RECONCILES.labels('dispatch_error').inc()
        logger.warning('v3 dispatch deferred exception_type=%s', type(error).__name__)
        record_fallback(
            component='other', from_mode='dispatch', to_mode='sweeper', reason='enqueue_failed', outcome='degraded'
        )

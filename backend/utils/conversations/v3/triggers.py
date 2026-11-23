"""Lightweight capture outbox and named-task trigger; no model or builder imports."""

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from config.conversations_v3 import SPEECH_LANDED_FIELD, conversations_v3_enabled
from database import conversations_v3 as store
from database.helpers import set_data_protection_level
from utils.cloud_tasks import enqueue_named_task
from utils.conversations.v3 import metrics
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def mark_new(uid, row):
    if (
        getattr(row.get('source'), 'value', row.get('source')) in {'omi', 'phone'}
        and not row.get('imported')
        and not row.get('v3_derived')
        and row.get('data_protection_level') != 'private'
        and conversations_v3_enabled(uid)
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


def enqueue(uid, *, at=None, manual_end_id=None):
    instant = at or datetime.now(timezone.utc)
    minute = int(instant.timestamp()) // 60
    task_id = 'conversations-v3-' + hashlib.sha256(uid.encode()).hexdigest()[:32] + '-' + str(minute)
    if manual_end_id:
        # A live task may already have completed in this minute. Its retained
        # Cloud Tasks name must not swallow the user's later explicit close.
        task_id += '-end-' + hashlib.sha256(manual_end_id.encode()).hexdigest()[:32]
    base = task_base()
    enqueue_named_task(
        os.getenv('CONVERSATIONS_V3_TASKS_QUEUE', 'conversations-v3'),
        base + '/v1/conversations-v3/reconcile',
        task_id,
        {'uid': uid},
        schedule_at=int(instant.timestamp()),
    )


def changed(uid, cid, *, manual_end=False):
    if store.mark_pending(uid, cid, manual_end=manual_end):
        try:
            enqueue(uid, **({'manual_end_id': cid} if manual_end else {}))
        except Exception as error:
            metrics.RECONCILES.labels('dispatch_error').inc()
            logger.warning('v3 dispatch deferred exception_type=%s', type(error).__name__)
            record_fallback(
                component='other', from_mode='dispatch', to_mode='sweeper', reason='enqueue_failed', outcome='degraded'
            )

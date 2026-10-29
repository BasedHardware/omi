"""One push when an account's first summary is ready.

``process_conversation`` calls :func:`hand_off` first in its derived-effects bundle (so a failing app or
memory step cannot drop it), which queues the decision off the processing path for a summary that pass
made appear. The account decides once, in ``users/{uid}/notification_markers/first_summary_push``
(``database.first_summary_push``):

- Only the account's first ready summary is pushed. Unprocessed rows (a sync batch) do not count, and
  an earlier-created conversation that already has a summary means it is not the first. When that
  earlier summary was written moments ago, its own decision is still running, so this one steps aside
  without deciding; an older one records ``not_first``.
- The conversation must still be visible, the reader must not have asked for it in the app, and
  server-side notifications must be on.
- An atomic claim lets one decision send. The claim then records what the dispatch did, so ``sent``
  means FCM accepted it on at least one device.

Copy follows the summary's output language. Tapping the push opens the conversation (``navigate_to``),
on its summary.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

import database.conversations as conversations_db
import database.first_summary_push as push_db
import database.users as users_db
from utils.conversations.first_summary_copy import first_summary_copy
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.summary_delivery import present as summary_present
from utils.executors import postprocess_executor, submit_with_context
from utils.llm.output_language import resolve_output_language
from utils.notification_dispatch import (
    NotificationDispatchOutcome,
    NotificationDispatchStatus,
    NotificationIntent,
    NotificationKind,
    dispatch_notification,
)

logger = logging.getLogger(__name__)

# How many of the account's oldest conversations are checked for an earlier summary.
HISTORY_WINDOW = 10
# An earlier summary written more recently than this may still be deciding for itself.
SETTLE_SECONDS = 600

# The reader asked for this result in the app, so it is already in front of them.
IN_APP_TRIGGERS = frozenset(
    {
        ProcessingTrigger.FIRST_OPEN,
        ProcessingTrigger.BACKLOG_CHOICE,
        ProcessingTrigger.USER_REPROCESS,
        ProcessingTrigger.MERGE,
    }
)


def first_summary_intent(uid: str, conversation_id: str, title: str, language: str) -> NotificationIntent:
    headline, untitled = first_summary_copy(language)
    return NotificationIntent(
        user_id=uid,
        title=headline,
        body=(title or '').strip() or untitled,
        source='first_summary',
        kind=NotificationKind.FIRST_SUMMARY,
        data={
            'type': 'first_summary',
            'conversation_id': conversation_id,
            'navigate_to': f'/conversation/{conversation_id}',
        },
    )


def hand_off(uid: str, conversation: Any, trigger: ProcessingTrigger, *, first_observation: bool) -> None:
    """Queue the decision when this pass made the summary appear.

    ``first_observation`` is ``process_conversation``'s own record that no earlier pass processed this
    conversation, so a regenerated summary (reprocess, sync append, merge refresh) never counts.
    """
    if not first_observation or getattr(conversation, 'discarded', False):
        return
    if summary_present(getattr(conversation, 'structured', None)):
        submit_with_context(postprocess_executor, maybe_send_first_summary_push, uid, conversation, trigger)


def _ready(row: Optional[Mapping[str, Any]]) -> bool:
    return summary_present((row or {}).get('structured'))


def _created_before(row: Mapping[str, Any], target: Mapping[str, Any]) -> bool:
    created, target_created = row.get('created_at'), target.get('created_at')
    if created is None or target_created is None:
        return True  # Unordered: assume the other summary came first.
    return (created, row['id']) < (target_created, target['id'])


def _settled(row: Mapping[str, Any], now: datetime) -> bool:
    written = row.get('updated_at')
    return written is None or written <= now - timedelta(seconds=SETTLE_SECONDS)


def _earlier_summaries(uid: str, target: Mapping[str, Any]) -> list:
    rows = push_db.oldest_conversation_summaries(uid, HISTORY_WINDOW)
    return [row for row in rows if row['id'] != target['id'] and _ready(row) and _created_before(row, target)]


def _decide(uid: str, conversation_id: str, outcome: str, **detail: Any) -> str:
    decision = {'outcome': outcome, 'conversation_id': conversation_id, **detail}
    if not push_db.try_decide(uid, decision):
        return 'already_decided'
    logger.info('first_summary_push uid=%s conversation=%s outcome=%s', uid, conversation_id, outcome)
    return outcome


def _dispatch_result(dispatch: NotificationDispatchOutcome) -> dict:
    if dispatch.status is NotificationDispatchStatus.DISPATCHED:
        delivered = dispatch.delivered or 0
        if delivered > 0:
            return {'outcome': 'sent', 'delivered': delivered}
        return {'outcome': 'undelivered', 'delivered': 0, 'reason': 'no_device_accepted'}
    if dispatch.status is NotificationDispatchStatus.SUPPRESSED:
        return {'outcome': 'suppressed', 'reason': dispatch.reason or 'policy'}
    return {'outcome': 'failed', 'reason': dispatch.reason or 'delivery_failed', 'retryable': True}


def maybe_send_first_summary_push(uid: str, conversation: Any, trigger: ProcessingTrigger) -> str:
    """Push the account's first summary once. Returns what happened, for logs and tests."""
    try:
        if getattr(conversation, 'discarded', False) or not summary_present(getattr(conversation, 'structured', None)):
            return 'no_summary'
        if push_db.get_decision(uid) is not None:
            return 'already_decided'
        cid = conversation.id
        stored = conversations_db.get_conversation(uid, cid)
        if not (
            conversations_db.is_visible_conversation(stored) and stored.get('status') == 'completed' and _ready(stored)
        ):
            return 'not_visible'
        target = {**stored, 'id': cid}
        earlier = _earlier_summaries(uid, target)
        if earlier:
            now = datetime.now(timezone.utc)
            if not any(_settled(row, now) for row in earlier):
                return 'deferred'
            return _decide(uid, cid, 'not_first')
        if trigger in IN_APP_TRIGGERS:
            return _decide(uid, cid, 'in_app')
        if users_db.get_notification_settings(uid).get('enabled') is False:
            return _decide(uid, cid, 'suppressed', reason='notifications_disabled')
        language = resolve_output_language(uid, target.get('language'))
        if not push_db.try_decide(uid, {'outcome': 'claimed', 'conversation_id': cid, 'language': language}):
            return 'already_decided'
        title = (target.get('structured') or {}).get('title') or ''
        result = _dispatch_result(dispatch_notification(first_summary_intent(uid, cid, title, language)))
        push_db.settle(uid, result)
        logger.info(
            'first_summary_push uid=%s conversation=%s outcome=%s delivered=%s reason=%s',
            uid,
            cid,
            result['outcome'],
            result.get('delivered'),
            result.get('reason'),
        )
        return result['outcome']
    except Exception as error:  # noqa: BLE001 — a push must never fail conversation processing
        logger.warning('first_summary_push failed uid=%s type=%s', uid, type(error).__name__)
        return 'error'

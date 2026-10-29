"""One push when an account's first summary is ready.

``process_conversation`` calls this off the processing path for each conversation whose summary
appeared in that pass. The account decides once, in
``users/{uid}/notification_markers/first_summary_push``: the summary is pushed only when it belongs
to the account's only completed conversation, the reader did not ask for it in the app, and
server-side notifications are on. Every later summary finds the marker and does nothing.
Tapping the push opens the conversation (``navigate_to``), on its summary.
"""

import logging
from typing import Any

import database.conversations as conversations_db
import database.notifications as notification_db
import database.users as users_db
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.summary_delivery import present as summary_present
from utils.notification_dispatch import NotificationIntent, NotificationKind, dispatch_notification

logger = logging.getLogger(__name__)

FIRST_SUMMARY_TITLE = 'Your first summary is ready'
FIRST_SUMMARY_FALLBACK_BODY = 'Tap to read it.'

# The reader asked for this result in the app, so it is already in front of them.
IN_APP_TRIGGERS = frozenset(
    {
        ProcessingTrigger.FIRST_OPEN,
        ProcessingTrigger.BACKLOG_CHOICE,
        ProcessingTrigger.USER_REPROCESS,
        ProcessingTrigger.MERGE,
    }
)


def first_summary_intent(uid: str, conversation: Any) -> NotificationIntent:
    title = (getattr(conversation.structured, 'title', '') or '').strip()
    return NotificationIntent(
        user_id=uid,
        title=FIRST_SUMMARY_TITLE,
        body=title or FIRST_SUMMARY_FALLBACK_BODY,
        source='first_summary',
        kind=NotificationKind.FIRST_SUMMARY,
        data={
            'type': 'first_summary',
            'conversation_id': conversation.id,
            'navigate_to': f'/conversation/{conversation.id}',
        },
    )


def maybe_send_first_summary_push(uid: str, conversation: Any, trigger: ProcessingTrigger) -> str:
    """Push the account's first summary once. Returns what happened, for logs and tests."""
    try:
        if getattr(conversation, 'discarded', False) or not summary_present(getattr(conversation, 'structured', None)):
            return 'no_summary'
        if notification_db.has_first_summary_push_marker(uid):
            return 'already_decided'
        visible = conversations_db.get_conversations_count(uid, statuses=['completed'])
        if visible == 0:
            # Hidden from the list (a tombstone or duplicate): not a summary the reader can open.
            return 'not_visible'
        if visible > 1:
            outcome = 'not_first'
        elif trigger in IN_APP_TRIGGERS:
            outcome = 'in_app'
        elif users_db.get_notification_settings(uid).get('enabled') is False:
            outcome = 'notifications_disabled'
        else:
            outcome = 'sent'
        if not notification_db.try_mark_first_summary_push(uid, outcome, conversation.id):
            return 'already_decided'
        if outcome == 'sent':
            result = dispatch_notification(first_summary_intent(uid, conversation))
            logger.info(
                'first_summary_push uid=%s conversation=%s outcome=sent dispatch=%s delivered=%s',
                uid,
                conversation.id,
                result.status.value,
                result.delivered,
            )
        else:
            logger.info('first_summary_push uid=%s conversation=%s outcome=%s', uid, conversation.id, outcome)
        return outcome
    except Exception as error:  # noqa: BLE001 — a push must never fail conversation processing
        logger.warning('first_summary_push failed uid=%s type=%s', uid, type(error).__name__)
        return 'error'

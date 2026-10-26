"""Review-source service functions for open-loop cards.

The Review routes (PR 3) call these over the per-local-day cards document the
daily pass wrote (``users/{uid}/open_loop_cards/{date}``); each answer also
applies to the underlying loop:

- ``done``  → loop resolved. The linked task is completed **only** through a
  strong link — the model asserted the task as the loop's origin
  (``task_link == 'model'``) *and* the answered card's text names the task
  (strong links render the task's own description; see ``store.card_view``).
  Heuristic-only links stay ask-only: Done resolves the loop, never the task.
  Completion goes through the same path the app's toggle endpoint uses
  (``mark_action_item_completed`` + reminder reconciliation #5085), so
  ``completed_at`` and the client-scheduled reminder behave exactly as when
  the owner taps Done in the app.
- ``remind`` → loop snoozed two days (``snoozed_until``), status unchanged.
- ``drop``  → loop dropped, and the card is kept on the loop as a negative
  example future ranking can learn from.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from config.refactor_modes import serving_for, shadow_or_serve
import database.action_items as action_items_db
import database.open_loops as open_loops_db
from utils.notifications import sync_action_item_reminder
from utils.open_loops import store
from utils.other import daily_recap

logger = logging.getLogger(__name__)

CARD_ACTIONS = ('done', 'remind', 'drop')
CARD_STATE_BY_ACTION = {'done': 'done', 'remind': 'remind', 'drop': 'dropped'}
PENDING_STATE = open_loops_db.CARD_STATE_PENDING
# Before noon local time the recap (and therefore the pass) has only finished
# the previous local day — that is the day whose pending cards to list.
DEFAULT_DAY_NOON_SPLIT_HOUR = 12
# When the resolved day's pass did not run (or left nothing pending), fall back
# to the most recent of the previous days that still has pending cards — one
# missed pass must not blank the whole surface for a day.
OWNER_FALLBACK_DAYS = 1


def _zone(tz: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(tz) if tz else ZoneInfo('UTC')
    except Exception:
        return ZoneInfo('UTC')


def recap_completed_day(tz: Optional[str], now: Optional[datetime] = None) -> str:
    """The local day the legacy recap most recently completed — the noon-split
    rule the recap job itself uses (``_display_date_for_now``): before noon local
    time, yesterday is the last day whose recap and cards exist."""
    moment = now or store.now_utc()
    local = moment.astimezone(_zone(tz))
    day = local.date() - timedelta(days=1) if local.hour < DEFAULT_DAY_NOON_SPLIT_HOUR else local.date()
    return day.isoformat()


def cards_display_day(uid: Optional[str], tz: Optional[str], now: Optional[datetime] = None) -> str:
    """The local day the daily pass most recently dated cards to — the producer's
    rule, not the reader's: ``daily_recap.scheduled_date`` over the noon-split
    legacy date. Uids serving ``CALLS_RECAP_MODE`` date every run to
    ``completed_day`` (always yesterday, no noon split — the pass runs ~01:00
    local), everyone else to the noon-split day. The branch mirrors
    ``scheduled_date`` instead of calling it so a Review read never moves the
    producer's recap-timing shadow counters."""
    moment = now or store.now_utc()
    legacy = recap_completed_day(tz, moment)
    if not shadow_or_serve(daily_recap.FLAG) or not serving_for(daily_recap.FLAG, uid):
        return legacy
    return daily_recap.completed_day(tz, moment).isoformat()


def _local_date_str(uid: str, tz: Optional[str], now: Optional[datetime], date_str: Optional[str]) -> str:
    return date_str or cards_display_day(uid, tz, now)


def list_pending_cards(
    uid: str,
    *,
    limit: int = 3,
    date_str: Optional[str] = None,
    tz: Optional[str] = None,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> List[Dict[str, Any]]:
    """One day's unanswered cards, in the order the pass ranked them.

    Without ``date_str``, the day is the producer's most recent one (see
    :func:`cards_display_day`); older pending cards age out with the day, and
    their loops either re-surface after the cooldown or expire.
    """
    cards = open_loops_db.get_cards(uid, _local_date_str(uid, tz, now, date_str), firestore_client=firestore_client)
    if not cards:
        return []
    return [card for card in cards if card.get('state') == PENDING_STATE][: max(0, limit)]


def list_owner_pending_cards(
    uid: str,
    *,
    tz: Optional[str] = None,
    now: Optional[datetime] = None,
    limit: int = 3,
    firestore_client: Any = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """``(day, pending cards)`` for the owner's Review listing.

    The day is resolved exactly as the pass dated it (``cards_display_day``);
    when that day has no cards document yet (the pass has not run), the most
    recent of the previous
    ``OWNER_FALLBACK_DAYS`` days that still has pending cards is listed
    instead, so the answer endpoint's date path stays the day the cards
    actually live in.
    """
    day = cards_display_day(uid, tz, now)
    cards = open_loops_db.get_cards(uid, day, firestore_client=firestore_client)
    if cards is not None:
        # The pass ran for this day: an empty or fully answered day stays empty.
        # Falling back here would resurface yesterday's unanswered cards.
        return day, [card for card in cards if card.get('state') == PENDING_STATE][: max(0, limit)]
    base = date.fromisoformat(day)
    for offset in range(1, OWNER_FALLBACK_DAYS + 1):
        candidate = (base - timedelta(days=offset)).isoformat()
        pending = list_pending_cards(uid, limit=limit, date_str=candidate, firestore_client=firestore_client)
        if pending:
            return candidate, pending
    return day, []


def answer_card(
    uid: str,
    card_id: str,
    action: str,
    *,
    date_str: Optional[str] = None,
    tz: Optional[str] = None,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Optional[Dict[str, Any]]:
    """Apply one owner answer (done|remind|drop) to a pending card.

    The card's state change is one Firestore transaction
    (``open_loops_db.transition_card_state``): two answers in flight — on two
    cards, or a double tap on one — serialize, each preserving the other's
    committed answer, and a card that is no longer pending answers as None
    (the route's 409). The loop update runs only after this call's own
    transition committed, which also makes it idempotent for a repeated
    answer: a replay never re-resolves, re-snoozes or records a second
    negative example. Task completion remains best-effort — a failing task
    update never rolls back the loop transition, it logs; the next daily pass
    re-raises the still-open task anyway.
    """
    if action not in CARD_ACTIONS:
        return None
    moment = now or store.now_utc()
    day = _local_date_str(uid, tz, now, date_str)
    card = open_loops_db.transition_card_state(
        uid, day, str(card_id), CARD_STATE_BY_ACTION[action], moment.isoformat(), firestore_client=firestore_client
    )
    if card is None:
        return None

    try:
        _record_answer_on_loop(uid, card, action, moment, tz, firestore_client)
    except Exception:
        # The card committed as answered but its loop did not record it. Put the
        # card back to pending so the owner's retry applies the answer instead of
        # hitting a 409 that silently loses it; the route returns a 500.
        try:
            open_loops_db.transition_card_state(
                uid,
                day,
                str(card_id),
                PENDING_STATE,
                None,
                from_state=CARD_STATE_BY_ACTION[action],
                firestore_client=firestore_client,
            )
        except Exception:
            logger.exception('open_loop_card_revert_failed card_id=%s date=%s', card_id, day)
        raise
    return card


def _record_answer_on_loop(
    uid: str, card: Dict[str, Any], action: str, moment: datetime, tz: Optional[str], firestore_client: Any
) -> None:
    loops = open_loops_db.get_loops(uid, firestore_client=firestore_client)
    loop = next((l for l in loops if str(l.get('id')) == str(card.get('loop_id'))), None)
    if loop is None or loop.get('status') in store.TERMINAL_STATUSES:
        # Already resolved, dropped or expired since the card was written: the
        # card answer stands, but it must not re-resolve the loop or complete
        # its task a second time.
        return
    open_loops_db.upsert_loop(
        uid, _apply_answer_to_loop(uid, loop, card, action, moment, tz), firestore_client=firestore_client
    )


def _complete_linked_task(uid: str, task_id: str, loop_id: Any) -> None:
    """Complete a strongly linked task through the app's own path.

    The same two steps as the app's ``PATCH /v1/action-items/{id}/completed``:
    ``mark_action_item_completed`` stamps ``completed_at``, then the reminder
    reconciliation (#5085) cancels the client's scheduled reminder from the
    task's final state. A raw ``update_action_item({'completed': True})``
    would do neither.
    """
    try:
        if not action_items_db.mark_action_item_completed(uid, task_id, True):
            logger.error(
                'open_loop_card_task_completion_failed loop_id=%s task_id=%s error=not_updated', loop_id, task_id
            )
            return
        updated = action_items_db.get_action_item(uid, task_id) or {}
        sync_action_item_reminder(
            user_id=uid,
            action_item_id=task_id,
            description=updated.get('description', ''),
            completed=bool(updated.get('completed')),
            due_at=updated.get('due_at'),
            status=updated.get('status'),
            deleted=bool(updated.get('deleted')),
        )
    except Exception as error:
        logger.error(
            'open_loop_card_task_completion_failed loop_id=%s task_id=%s error=%s',
            loop_id,
            task_id,
            error,
            exc_info=error,
        )


def _apply_answer_to_loop(
    uid: str, loop: Dict[str, Any], card: Dict[str, Any], action: str, moment: datetime, tz: Optional[str]
) -> Dict[str, Any]:
    today = local_today(tz, moment)
    if action == 'done':
        loop = store.append_history(loop, today, 'resolved', 'owner answered done')
        loop['last_activity_at'] = moment.isoformat()
        linked_task_id = loop.get('linked_task_id')
        if linked_task_id:
            strong_link = loop.get('task_link') == 'model' and store.text_names_task(
                card.get('question'), loop.get('linked_task_title')
            )
            if strong_link:
                _complete_linked_task(uid, str(linked_task_id), loop.get('id'))
            else:
                # Ask-only link: the card never claimed to be about the task,
                # so Done is evidence about the loop, not the task.
                logger.info(
                    'open_loop_task_completion_skipped_ask_only loop_id=%s task_id=%s link=%s',
                    loop.get('id'),
                    linked_task_id,
                    loop.get('task_link'),
                )
        return loop
    if action == 'remind':
        loop['snoozed_until'] = (today + timedelta(days=store.SNOOZE_DAYS)).isoformat()
        return loop
    # drop: terminal, and the card stays as a negative example for ranking.
    negative = {'date': today.isoformat(), 'question': card.get('question'), 'value': card.get('value')}
    loop = store.append_history(loop, today, 'dropped', 'owner dropped the card')
    loop['last_activity_at'] = moment.isoformat()
    loop['negative_examples'] = (list(loop.get('negative_examples') or []) + [negative])[-3:]
    return loop


def local_today(tz: Optional[str], now: Optional[datetime] = None):
    """The current local date in ``tz`` (UTC when absent/unusable)."""
    return (now or datetime.now(timezone.utc)).astimezone(_zone(tz)).date()

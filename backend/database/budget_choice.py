"""One bounded choice record per account; no content, event history, or quota mutations."""

import logging
from typing import Any

from google.cloud import firestore

from config.held_content import CHOICES, current_choice
from database._client import get_firestore_client, run_transactional

logger = logging.getLogger(__name__)


class BudgetChoiceConflict(ValueError):
    """The account already chose differently for this budget period."""


def _sanitize_uid(uid: Any) -> str:
    """A uid arriving from headers or tokens can carry whitespace; written
    unsanitized it silently skews the document path."""
    return uid.strip() if isinstance(uid, str) else ''


def _sanitize_period(period: Any) -> str:
    return period.strip() if isinstance(period, str) else ''


def _reference(client: Any, uid: str) -> Any:
    clean = _sanitize_uid(uid)
    return client.collection('users').document(clean).collection('budget_choice').document('current')


def get_choice(uid: str, period: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    uid = _sanitize_uid(uid)
    period = _sanitize_period(period)
    if not uid or not period:
        return None
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        snapshot = _reference(client, uid).get()
        record = snapshot.to_dict() if snapshot.exists else None
        return current_choice(record, period)
    except Exception:
        logger.warning('budget_choice read failed', exc_info=True)
        return None


@firestore.transactional
def _store(transaction: Any, ref: Any, period: str, choice: str, dont_ask_again: bool) -> dict[str, Any]:
    snapshot = ref.get(transaction=transaction)
    raw = snapshot.to_dict() or {}
    if isinstance(raw.get('period'), str) and raw['period'] > period:
        raise BudgetChoiceConflict('budget_period_changed')
    existing = current_choice(raw, period)
    proposed = {'period': period, 'choice': choice, 'dont_ask_again': dont_ask_again}
    if existing:
        if existing != proposed:
            raise BudgetChoiceConflict('choice_already_recorded')
        return existing
    transaction.set(ref, proposed)
    return proposed


def set_choice(
    uid: str, period: str, choice: str, dont_ask_again: bool, *, firestore_client: Any = None
) -> dict[str, Any]:
    uid = _sanitize_uid(uid)
    period = _sanitize_period(period)
    if not uid:
        raise ValueError('invalid_uid')
    if not period:
        raise ValueError('invalid_budget_period')
    if choice not in CHOICES or type(dont_ask_again) is not bool:
        raise ValueError('invalid_budget_choice')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return run_transactional(client, _store, _reference(client, uid), period, choice, dont_ask_again)

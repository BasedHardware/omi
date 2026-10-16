"""One bounded choice record per account; no content, event history, or quota mutations."""

from typing import Any

from google.cloud import firestore

from config.held_content import CHOICES, current_choice
from database._client import get_firestore_client, run_transactional


class BudgetChoiceConflict(ValueError):
    """The account already chose differently for this budget period."""


def _reference(client: Any, uid: str) -> Any:
    clean_uid = uid.strip() if isinstance(uid, str) else ''
    if not clean_uid:
        raise ValueError('invalid_uid')
    return client.collection('users').document(clean_uid).collection('budget_choice').document('current')


def get_choice(uid: str, period: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    clean_uid = uid.strip() if isinstance(uid, str) else ''
    clean_period = period.strip() if isinstance(period, str) else ''
    if not clean_uid or not clean_period:
        return None
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        doc = _reference(client, clean_uid).get()
        data = doc.to_dict() if hasattr(doc, 'to_dict') else None
        return current_choice(data if isinstance(data, dict) else None, clean_period)
    except Exception:
        return None


@firestore.transactional
def _store(transaction: Any, ref: Any, period: str, choice: str, dont_ask_again: bool) -> dict[str, Any]:
    doc = ref.get(transaction=transaction)
    raw = doc.to_dict() if hasattr(doc, 'to_dict') else (doc if isinstance(doc, dict) else {})
    raw = raw or {}
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
    clean_uid = uid.strip() if isinstance(uid, str) else ''
    if not clean_uid:
        raise ValueError('invalid_uid')
    clean_period = period.strip() if isinstance(period, str) else ''
    if not clean_period:
        raise ValueError('invalid_budget_period')
    if not isinstance(choice, str) or choice not in CHOICES or type(dont_ask_again) is not bool:
        raise ValueError('invalid_budget_choice')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return run_transactional(client, _store, _reference(client, clean_uid), clean_period, choice, dont_ask_again)

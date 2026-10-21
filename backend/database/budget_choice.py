"""One bounded choice record per account; no content, event history, or quota mutations."""

from typing import Any

from google.cloud import firestore

from config.held_content import CHOICES, budget_period, current_choice
from database._client import get_firestore_client, run_transactional


class BudgetChoiceConflict(ValueError):
    """The account already chose differently for this budget period."""


def _reference(client: Any, uid: str) -> Any:
    return client.collection('users').document(uid).collection('budget_choice').document('current')


def get_choice(uid: str, period: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return current_choice(_reference(client, uid).get().to_dict(), period)


@firestore.transactional
def _store(transaction: Any, ref: Any, period: str, choice: str, dont_ask_again: bool) -> dict[str, Any]:
    raw = ref.get(transaction=transaction).to_dict() or {}
    # Allowance reads and transaction retries can cross midnight after HTTP admission.
    # Even an idempotent replay must not acknowledge an expired budget period.
    if period != budget_period():
        raise BudgetChoiceConflict('budget_period_changed')
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
    if choice not in CHOICES or type(dont_ask_again) is not bool:
        raise ValueError('invalid_budget_choice')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return run_transactional(client, _store, _reference(client, uid), period, choice, dont_ask_again)

"""
Coding Agent wallet & per-turn usage ledger in Firestore.

Wallet:  users/{uid}/agent_code/wallet
           -> {balance_cents: int, updated_at: ts}

Ledger:  users/{uid}/agent_code_usage/{turn_id}
           -> {session_id, model, input_tokens, output_tokens,
               cost_cents (paid OpenRouter), charge_cents (user-paid), created_at}

Grants:  users/{uid}/agent_code_grants/{grant_id}
           -> {amount_cents, reason, granted_by_hash, created_at}
"""

import uuid
from typing import Optional

from google.cloud import firestore

from ._client import db


def _wallet_ref(uid: str):
    return db.collection("users").document(uid).collection("agent_code").document("wallet")


def get_balance_cents(uid: str) -> int:
    doc = _wallet_ref(uid).get()
    if not doc.exists:
        return 0
    return int((doc.to_dict() or {}).get("balance_cents", 0))


def credit_balance_cents(uid: str, amount_cents: int) -> int:
    if amount_cents <= 0:
        return get_balance_cents(uid)
    _wallet_ref(uid).set(
        {
            "balance_cents": firestore.Increment(amount_cents),
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    return get_balance_cents(uid)


def debit_balance_cents(uid: str, amount_cents: int) -> int:
    if amount_cents <= 0:
        return get_balance_cents(uid)
    _wallet_ref(uid).set(
        {
            "balance_cents": firestore.Increment(-amount_cents),
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    return get_balance_cents(uid)


def record_turn(
    uid: str,
    session_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_cents: int,
    charge_cents: int,
    turn_id: Optional[str] = None,
) -> str:
    turn_id = turn_id or str(uuid.uuid4())
    db.collection("users").document(uid).collection("agent_code_usage").document(turn_id).set(
        {
            "session_id": session_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_cents": cost_cents,
            "charge_cents": charge_cents,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )
    return turn_id


def record_grant(
    uid: str,
    amount_cents: int,
    reason: str,
    granted_by_hash: str,
    grant_id: Optional[str] = None,
) -> str:
    """Write an audit row for an admin credit grant.

    Stored at users/{uid}/agent_code_grants/{grant_id}.
    Returns the grant_id (generated if not supplied).
    """
    grant_id = grant_id or str(uuid.uuid4())
    db.collection("users").document(uid).collection("agent_code_grants").document(grant_id).set(
        {
            "amount_cents": amount_cents,
            "reason": reason,
            "granted_by_hash": granted_by_hash,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )
    return grant_id

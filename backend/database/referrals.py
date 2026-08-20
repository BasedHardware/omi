from __future__ import annotations

from typing import Any

from google.cloud import firestore

from database._client import get_customer_firestore_client, run_transactional
from utils.referrals import referral_claim_patch


def claim_referral_trial(
    referred_uid: str,
    referrer_uid: str,
    *,
    is_new_user: bool,
    firestore_client: Any | None = None,
) -> bool:
    """Atomically grant the referred account its one-time 30-day Omi Pro entitlement."""
    client = firestore_client or get_customer_firestore_client()
    user_ref = client.collection('users').document(referred_uid)

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        snapshot = user_ref.get(transaction=transaction)
        patch = referral_claim_patch(
            referred_uid=referred_uid,
            referrer_uid=referrer_uid,
            is_new_user=is_new_user,
            user_data=snapshot.to_dict() if snapshot.exists else None,
        )
        if patch is None:
            return False
        transaction.set(user_ref, patch, merge=True)
        return True

    return bool(run_transactional(client, apply))

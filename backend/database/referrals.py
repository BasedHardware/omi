from __future__ import annotations

import logging
from typing import Any

from google.cloud import firestore

from database._client import get_customer_firestore_client, run_transactional
from utils.referrals import referral_claim_patch

logger = logging.getLogger(__name__)


def claim_referral_trial(
    referred_uid: str,
    referrer_uid: str,
    *,
    is_new_user: bool,
    firestore_client: Any | None = None,
) -> tuple[bool, str]:
    """Atomically grant the referred account its one-time 30-day Operator entitlement."""
    if not referred_uid or not isinstance(referred_uid, str) or not referred_uid.strip():
        return False, "invalid_referred_uid"
    if not referrer_uid or not isinstance(referrer_uid, str) or not referrer_uid.strip():
        return False, "invalid_referrer_uid"

    clean_referred_uid = referred_uid.strip()
    clean_referrer_uid = referrer_uid.strip()

    try:
        client = firestore_client or get_customer_firestore_client()
        user_ref = client.collection('users').document(clean_referred_uid)

        @firestore.transactional
        def apply(transaction: Any) -> tuple[bool, str]:
            snapshot = user_ref.get(transaction=transaction)
            patch, reason = referral_claim_patch(
                referred_uid=clean_referred_uid,
                referrer_uid=clean_referrer_uid,
                is_new_user=is_new_user,
                user_data=snapshot.to_dict() if snapshot.exists else None,
            )
            if patch is None:
                return False, reason
            transaction.set(user_ref, patch, merge=True)
            return True, reason

        return run_transactional(client, apply)
    except Exception as exc:
        logger.warning(
            "referral_claim_failed uid=%s referrer=%s error=%s",
            clean_referred_uid,
            clean_referrer_uid,
            exc,
        )
        return False, "transaction_failed"

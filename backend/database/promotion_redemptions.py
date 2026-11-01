"""Promotion codes redeemed by Omi onto an existing subscription.

Stripe counts a redemption only when a code goes through its own checkout or API
validation. A code Omi applies as a coupon is not counted there, so one row per
promotion code id here is what keeps that code single-use.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from google.api_core.exceptions import AlreadyExists, Conflict

from database._client import get_firestore_client

COLLECTION = 'promotion_code_redemptions'


def claim(
    promotion_code_id: str,
    *,
    uid: str,
    subscription_id: str,
    coupon_id: str,
    firestore_client: Optional[Any] = None,
) -> bool:
    client = firestore_client or get_firestore_client()
    try:
        client.collection(COLLECTION).document(promotion_code_id).create(
            {
                'uid': uid,
                'subscription_id': subscription_id,
                'coupon_id': coupon_id,
                'redeemed_at': datetime.now(timezone.utc),
            }
        )
    except (AlreadyExists, Conflict):
        return False
    return True


def release(promotion_code_id: str, *, firestore_client: Optional[Any] = None) -> None:
    client = firestore_client or get_firestore_client()
    client.collection(COLLECTION).document(promotion_code_id).delete()

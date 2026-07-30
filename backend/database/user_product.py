"""Product-surface cohort fields from `X-App-Product` (orthogonal to OS platform)."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import firestore

from database._client import db
from database.redis_db import try_acquire_user_product_write_lock

logger = logging.getLogger(__name__)

# Unknown values are ignored — do not invent aliases from OS.
_PRODUCT_ALLOWLIST = frozenset(
    {
        'context-for-claude',
        'omi-desktop',
        'omi-mobile',
        'omi-web',
    }
)


def normalize_product(raw: Optional[str]) -> Optional[str]:
    """Return a canonical product id for a raw `X-App-Product` header, or None."""
    if not raw:
        return None
    product = raw.strip().lower()
    if product not in _PRODUCT_ALLOWLIST:
        return None
    return product


def record_user_product(uid: str, raw_product: Optional[str]) -> None:
    """Write product-surface cohort fields from an `X-App-Product` header value.

    Same throttle / fail-open contract as `record_user_platform`. Users can
    belong to multiple products (`products_used` ArrayUnion) — e.g. Omi Desktop
    and Context for Claude on the same account.
    """
    product = normalize_product(raw_product)
    if not product:
        return

    try:
        if not try_acquire_user_product_write_lock(uid, product):
            return

        now = datetime.now(timezone.utc)
        user_ref = db.collection('users').document(uid)

        updates: dict[str, Any] = {
            'last_active_product': product,
            f'last_active_at_product_{product.replace("-", "_")}': now,
            'products_used': firestore.ArrayUnion([product]),
        }

        snapshot = user_ref.get()
        if snapshot.exists:
            data = snapshot.to_dict() or {}
            if not data.get('signup_product'):
                updates['signup_product'] = product
                updates['signup_product_at'] = data.get('created_at') or now
        else:
            updates['signup_product'] = product
            updates['signup_product_at'] = now

        user_ref.set(updates, merge=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("record_user_product failed for uid=%s: %s", uid, e)

"""Omi account ↔ GoAffPro affiliate links.

`users/{uid}.affiliate` holds the link on the account, and
`affiliate_links/{affiliate_id}` is the reverse record. Both are written in one
transaction so an affiliate belongs to at most one Omi account and an account
to at most one affiliate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from google.cloud import firestore

from database._client import get_customer_firestore_client, run_transactional

LINKS_COLLECTION = 'affiliate_links'

LinkMethod = Literal['email_match', 'affiliate_login', 'joined']
LinkOutcome = Literal['linked', 'already_linked', 'affiliate_taken', 'account_has_other']


def get_linked_affiliate_id(uid: str, *, firestore_client: Any | None = None) -> Optional[str]:
    client = firestore_client or get_customer_firestore_client()
    snapshot = client.collection('users').document(uid).get(field_paths=['affiliate'])
    if not snapshot.exists:
        return None
    link = (snapshot.to_dict() or {}).get('affiliate') or {}
    affiliate_id = link.get('affiliate_id')
    return str(affiliate_id) if affiliate_id else None


def link_affiliate(
    uid: str, affiliate_id: str, method: LinkMethod, *, firestore_client: Any | None = None
) -> LinkOutcome:
    client = firestore_client or get_customer_firestore_client()
    user_ref = client.collection('users').document(uid)
    link_ref = client.collection(LINKS_COLLECTION).document(affiliate_id)

    @firestore.transactional
    def apply(transaction: Any) -> LinkOutcome:
        link_snapshot = link_ref.get(transaction=transaction)
        user_snapshot = user_ref.get(transaction=transaction)
        owner = (link_snapshot.to_dict() or {}).get('uid') if link_snapshot.exists else None
        current = (
            ((user_snapshot.to_dict() or {}).get('affiliate') or {}).get('affiliate_id')
            if user_snapshot.exists
            else None
        )
        if owner and owner != uid:
            return 'affiliate_taken'
        if current and str(current) != affiliate_id:
            return 'account_has_other'
        if owner == uid and current:
            return 'already_linked'
        now = datetime.now(timezone.utc)
        transaction.set(link_ref, {'uid': uid, 'method': method, 'linked_at': now})
        transaction.set(
            user_ref, {'affiliate': {'affiliate_id': affiliate_id, 'method': method, 'linked_at': now}}, merge=True
        )
        return 'linked'

    return run_transactional(client, apply)


def delete_affiliate_link(uid: str, *, firestore_client: Any | None = None) -> None:
    """Drop the reverse record during account deletion; the GoAffPro account itself stays."""
    client = firestore_client or get_customer_firestore_client()
    affiliate_id = get_linked_affiliate_id(uid, firestore_client=client)
    if not affiliate_id:
        return
    link_ref = client.collection(LINKS_COLLECTION).document(affiliate_id)
    snapshot = link_ref.get()
    if snapshot.exists and (snapshot.to_dict() or {}).get('uid') == uid:
        link_ref.delete()

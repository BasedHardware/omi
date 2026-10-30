"""Durable delivery receipts and leases using the existing Firestore transaction pattern.

No client is constructed at import. Completion means the legacy handler returned,
not that every ancillary effect succeeded. Only explicitly safe event types are
eligible for suppression; handlers with swallowed persistence errors stay out.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from google.cloud import firestore

RETENTION_DAYS = 90
LEASE_SECONDS = 300
EVENT_COLLECTION = 'stripe_webhook_events'
ORDER_COLLECTION = 'stripe_webhook_subscription_order'


@dataclass(frozen=True)
class Claim:
    outcome: str
    token: str = ''
    out_of_order: bool = False


def _key(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _refs(client, event):
    event_id = event.get('id')
    if not isinstance(event_id, str) or not event_id or len(event_id) > 255:
        raise ValueError('invalid event id')
    obj = event.get('data', {}).get('object', {})
    kind = event.get('type', '')
    sub_id = obj.get('id') if kind.startswith('customer.subscription.') else obj.get('subscription')
    if isinstance(sub_id, dict):
        sub_id = sub_id.get('id')
    if not isinstance(sub_id, str) or not sub_id:
        sub_id = None
    receipt = client.collection(EVENT_COLLECTION).document(_key(event_id))
    watermark = client.collection(ORDER_COLLECTION).document(_key(sub_id)) if sub_id else None
    return receipt, watermark, sub_id


def _client(client):
    if client is not None:
        return client
    from database._client import get_firestore_client

    return get_firestore_client()


def claim_event(event: dict[str, Any], token: str, *, now: datetime | None = None, client=None) -> Claim:
    now = now or datetime.now(timezone.utc)
    client = _client(client)
    receipt, watermark, sub_id = _refs(client, event)
    created = event.get('created')
    if type(created) is not int:
        raise ValueError('event created must be an integer')

    @firestore.transactional
    def claim(transaction):
        snapshot = receipt.get(transaction=transaction)
        existing = (snapshot.to_dict() or {}) if snapshot.exists else {}
        if existing.get('outcome') == 'acknowledged' and existing.get('expires_at', now) > now:
            return Claim('duplicate')
        if existing.get('outcome') == 'processing' and existing.get('lease_until', now) > now:
            return Claim('busy')
        order_snapshot = watermark.get(transaction=transaction) if watermark else None
        order = (order_snapshot.to_dict() or {}) if order_snapshot is not None and order_snapshot.exists else {}
        latest = order.get('latest_created', -1)
        out_of_order = created < latest
        expiry = now + timedelta(days=RETENTION_DAYS)
        transaction.set(
            receipt,
            {
                'event_id': event['id'],
                'event_type': str(event['type'])[:128],
                'event_created': created,
                'subscription_id': sub_id,
                'outcome': 'processing',
                'token': token,
                'lease_until': now + timedelta(seconds=LEASE_SECONDS),
                'attempt': int(existing.get('attempt', 0)) + 1,
                'out_of_order': out_of_order,
                'expires_at': expiry,
            },
        )
        return Claim('claimed', token, out_of_order)

    return claim(client.transaction())


def finish_event(
    event: dict[str, Any], token: str, *, succeeded: bool, now: datetime | None = None, client=None
) -> bool:
    """Fence completion to the lease owner; return whether newer events were seen.

    Crash recovery is at-least-once: effects outside this transaction may replay
    after an expired lease. The token prevents an old worker completing a new
    worker's receipt, but cannot fence unrelated legacy writes.
    """
    now = now or datetime.now(timezone.utc)
    client = _client(client)
    receipt, watermark, _ = _refs(client, event)

    @firestore.transactional
    def finish(transaction):
        snapshot = receipt.get(transaction=transaction)
        existing = (snapshot.to_dict() or {}) if snapshot.exists else {}
        if existing.get('token') != token or existing.get('outcome') != 'processing':
            raise RuntimeError('event lease ownership lost')
        order_snapshot = watermark.get(transaction=transaction) if watermark else None
        order = (order_snapshot.to_dict() or {}) if order_snapshot is not None and order_snapshot.exists else {}
        out_of_order = existing.get('out_of_order', False) or existing['event_created'] < order.get(
            'latest_created', -1
        )
        transaction.update(
            receipt,
            {
                'outcome': 'acknowledged' if succeeded else 'failed',
                'completed_at': now,
                'lease_until': now,
                'out_of_order': out_of_order,
            },
        )
        if succeeded and watermark:
            transaction.set(
                watermark,
                {
                    'latest_created': max(existing['event_created'], order.get('latest_created', -1)),
                    'expires_at': now + timedelta(days=RETENTION_DAYS),
                },
            )
        return bool(out_of_order)

    return finish(client.transaction())


def observe_event(event: dict[str, Any], *, now: datetime | None = None, client=None) -> None:
    """Best-effort receipt for legacy handlers whose return cannot prove success.

    These receipts are deliberately ineligible for duplicate suppression.
    No full payload, customer, UID, signature or exception text is retained.
    """
    now = now or datetime.now(timezone.utc)
    client = _client(client)
    receipt, _, sub_id = _refs(client, event)
    receipt.set(
        {
            'event_id': event['id'],
            'event_type': str(event['type'])[:128],
            'event_created': event.get('created'),
            'subscription_id': sub_id,
            'outcome': 'legacy_unprotected',
            'observed_at': now,
            'expires_at': now + timedelta(days=RETENTION_DAYS),
        }
    )

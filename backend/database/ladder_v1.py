"""Atomic, per-UID daily reservations shared by MCP and developer API keys."""

from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from config.rate_card import price_request
from database import _client


@firestore.transactional
def _reserve(transaction: Any, ref: Any, cap: int, reset_at: int) -> dict:
    data = ref.get(transaction=transaction).to_dict() or {}
    used = int(data.get('requests', 0))
    allowed = used < cap
    if allowed:
        used += 1
        transaction.set(
            ref,
            {
                'requests': used,
                'micro_units': int(data.get('micro_units', 0)) + price_request('mcp_api')['micro_units'],
                'reset_at': reset_at,
            },
        )
    return {
        'allowed': allowed,
        'used': used,
        'limit': cap,
        'reset_at': reset_at,
        'state': 'cap' if not allowed else 'nudge' if used * 100 >= cap * 80 else 'within',
    }


def reserve_daily_request(uid: str, cap: int, *, now: datetime | None = None, firestore_client: Any = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    client = firestore_client if firestore_client is not None else _client.get_customer_firestore_client()
    ref = client.collection('users').document(uid).collection('ladder_v1_api_days').document(now.date().isoformat())
    return _client.run_transactional(client, _reserve, ref, cap, int(reset.timestamp()))

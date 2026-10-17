"""Token-fenced, growing live captures made from immutable encrypted PCM parts."""

import time
from typing import Any
from uuid import uuid4

from google.cloud import firestore
from database._client import get_firestore_client
from database.legal_holds import external_write_fence
from utils.sync import cap_hold

CAPTURE_SECONDS = 60
MAX_CAPTURE_PARTS = 120


def new_group(start: float, channel: int, rate: int, owner: str | None, month: str) -> dict[str, Any]:
    return {
        'id': uuid4().hex,
        'token': uuid4().hex,
        'start': start,
        'channel': channel,
        'rate': rate,
        'owner': owner,
        'month': month,
        'seconds': 0.0,
    }


def append(uid: str, group: dict[str, Any], fields: dict[str, Any], seconds: float) -> float | None:
    cap_hold.ensure_summary(uid)
    client = get_firestore_client()
    ref = cap_hold.holds(uid).document(group['id'])
    total_ref = cap_hold.summary_ref(uid)

    @firestore.transactional
    def commit(tx: Any) -> float | None:
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() if snapshot.exists else None
        parts = (row or {}).get('audio_parts') or []
        if row is not None and fields['audio_path'] in parts:
            return row['seconds']  # The previous commit's reply was lost.
        if len(parts) >= MAX_CAPTURE_PARTS:
            return None
        if row and (row.get('lease_token') != group['token'] or row.get('state') != 'held' or 'piece_plan' in row):
            return None  # Recovery already owns this capture; start a successor.
        total = total_ref.get(transaction=tx)
        current = total.to_dict() if total.exists else None
        now = time.time()
        duration = (row or {}).get('seconds', 0) + seconds
        updates = {
            'seconds': duration,
            'audio_parts': [*parts, fields['audio_path']],
            'lease_token': group['token'],
            'lease_until': now + 1800,
            'next_attempt_at': now + 1800,
        }
        if row:
            tx.update(ref, updates)
        else:
            tx.create(ref, {**cap_hold.hold_manifest(fields, seconds, now, int(group['start'])), **updates})
        tx.set(total_ref, cap_hold.summary_after(current, seconds, 0 if row else 1))
        return duration

    with external_write_fence(uid):
        return commit(client.transaction())

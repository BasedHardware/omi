"""Reap abandoned pre-admission staging without expiring accepted audio."""

from datetime import datetime, timedelta
import hashlib
from typing import Any

from database.batch_pipeline_store import Store

# Cloud Run requests have a one-hour maximum; allow an additional hour for
# detached bounded storage/transaction leaves after an interrupted upload.
ORPHAN_GRACE = timedelta(hours=2)


def artifact_id(segment_id: str, uri: str) -> str:
    reserved = uri.split('#', 1)[0]
    return hashlib.sha256(f'{segment_id}\0{reserved}'.encode()).hexdigest()


def unsettled(client: Any, namespace: str, before: datetime, limit: int = 100) -> list[str]:
    docs = (
        client.collection(f'{namespace}_artifacts')
        .where('write_pending_until', '<=', before)
        .order_by('write_pending_until')
        .limit(max(1, min(limit, 100)))
        .stream()
    )
    return [doc.id for doc in docs]


def reap(store: Any, now: datetime, *, limit: int = 100) -> int:
    keys = unsettled(store.client, store.namespace, now - ORPHAN_GRACE, limit)
    return sum(reap_one(store, key, now) for key in keys)


def reap_one(store: Store, key: str, now: datetime) -> bool:
    def commit(tx):
        row = tx.get('artifacts', key)
        deadline = row.get('write_pending_until')
        if not isinstance(deadline, datetime) or deadline + ORPHAN_GRACE > now or row.get('erasure_requested'):
            return False
        job = tx.get('jobs', row['segment_id'])
        uri = row['uri'].split('#', 1)[0]
        attached = job.get('audio_uri') if row['kind'] == 'audio' else (job.get('result') or {}).get('result_uri')
        if attached and attached.split('#', 1)[0] == uri:
            row.pop('write_pending_until', None)
        elif job.get('state') == 'leased' and row['kind'] != 'audio' and job.get('lease_until', 0) > now.timestamp():
            return False  # A current model batch may not have submitted results yet.
        else:
            row.pop('write_pending_until', None)
            row['cleanup_after'] = now
        tx.put('artifacts', key, row)
        return True

    return store.run(commit)

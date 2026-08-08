"""Raw storage for X (Twitter) posts ingested by the X connector.

Unlike the legacy persona flow (which fetched tweets, distilled a few memories,
and threw the raw tweets away), the X connector keeps every post as a
first-class source item under `users/{uid}/x_posts`. Documents are keyed by the
tweet id so re-syncs are idempotent (a post is never stored twice). Memory
extraction + vector indexing run on top of this raw store, mirroring how
conversations are kept raw and then mined for memories.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from database.store import get_document_store

logger = logging.getLogger(__name__)

users_collection = 'users'
x_posts_collection = 'x_posts'
MEMORY_EXTRACTION_PENDING = 'pending'
MEMORY_EXTRACTION_COMPLETED = 'completed'

# Post "kinds" stored under the same collection, distinguished by the `kind` field.
KIND_TWEET = 'tweet'
KIND_BOOKMARK = 'bookmark'
KIND_LIKE = 'like'


def _store():
    return get_document_store()


def _posts_path(uid: str) -> str:
    return f'{users_collection}/{uid}/{x_posts_collection}'


def save_x_posts(uid: str, posts: List[Dict[str, Any]]) -> int:
    """Idempotently store raw X posts. Returns the number of NEW posts written.

    Each post dict must contain at least: id (tweet id, str), text, created_at,
    kind. We dedupe on the document id (the tweet id), so calling this repeatedly
    with overlapping pages only ever inserts each post once.
    """
    if not posts:
        return 0

    coll = _posts_path(uid)
    # Find which ids already exist so we can report an accurate delta and avoid
    # clobbering `ingested_at` on re-sync.
    ids = [str(p['id']) for p in posts if p.get('id') is not None]
    existing: set[str] = set()
    # get_many is efficient for the modest page sizes the connector pulls (<=100).
    for snap in _store().get_many(coll, ids):
        if snap.exists:
            existing.add(str(snap.id))

    now = datetime.now(timezone.utc)
    batch = _store().batch()
    new_count = 0
    for p in posts:
        pid = str(p.get('id')) if p.get('id') is not None else None
        if not pid:
            continue
        doc: Dict[str, Any] = dict(p)
        doc['id'] = pid
        doc['updated_at'] = now
        if pid not in existing:
            doc['ingested_at'] = now
            # The raw post is the durable extraction source. It stays pending
            # until every memory write for its extraction batch succeeds.
            doc['memory_extraction_status'] = MEMORY_EXTRACTION_PENDING
            new_count += 1
        batch.set(f'{coll}/{pid}', doc, merge=True)
    batch.commit()
    logger.info(f'save_x_posts uid={uid} received={len(posts)} new={new_count}')
    return new_count


def get_pending_memory_extraction_posts(uid: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Return one bounded, stable batch of raw posts not yet mined for memories.

    Rows created before this ledger field are intentionally pending: replaying
    source rows incrementally is safer than silently treating a historical raw
    import as successfully extracted.
    """
    bounded_limit = max(1, min(limit, 500))
    pending: List[Dict[str, Any]] = []
    for snapshot in _store().query(_posts_path(uid)):
        raw = snapshot.to_dict()
        if not isinstance(raw, dict) or raw.get('memory_extraction_status') == MEMORY_EXTRACTION_COMPLETED:
            continue
        row = cast(Dict[str, Any], raw)
        row.setdefault('id', str(snapshot.id))
        pending.append(row)

    pending.sort(key=lambda row: (str(row.get('ingested_at') or row.get('created_at') or ''), str(row.get('id') or '')))
    return pending[:bounded_limit]


def mark_memory_extraction_completed(uid: str, post_ids: List[str]) -> None:
    """Acknowledge extraction only after its canonical/legacy memory writes succeed."""
    if not post_ids:
        return
    now = datetime.now(timezone.utc)
    coll = _posts_path(uid)
    batch = _store().batch()
    for post_id in post_ids:
        batch.set(
            f'{coll}/{str(post_id)}',
            {
                'memory_extraction_status': MEMORY_EXTRACTION_COMPLETED,
                'memory_extracted_at': now,
                'updated_at': now,
            },
            merge=True,
        )
    batch.commit()


def get_x_posts(uid: str, limit: int = 100, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return stored posts, newest first. Optionally filter by kind.

    A kind filter + order_by would require a composite index, so when filtering
    by kind we use the single-field equality query (auto-indexed) and sort in
    Python — post volumes per user are small enough for this to be cheap.
    """
    coll = _posts_path(uid)
    if kind:
        docs: List[Dict[str, Any]] = []
        for d in _store().query(coll, filters=[('kind', '==', kind)]):
            raw: object = d.to_dict()
            if isinstance(raw, dict):
                docs.append(cast(Dict[str, Any], raw))
        docs.sort(key=lambda x: str(x.get('created_at') or ''), reverse=True)
        return docs[:limit]
    out: List[Dict[str, Any]] = []
    for d in _store().query(coll, order_by='created_at', direction='desc', limit=limit):
        raw = d.to_dict()
        if isinstance(raw, dict):
            out.append(cast(Dict[str, Any], raw))
    return out


def get_x_posts_by_ids(uid: str, ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch specific posts by id (used by semantic search to hydrate matches)."""
    if not ids:
        return []
    out: List[Dict[str, Any]] = []
    for snap in _store().get_many(_posts_path(uid), [str(i) for i in ids]):
        if snap.exists:
            raw: object = snap.to_dict()
            if isinstance(raw, dict):
                out.append(cast(Dict[str, Any], raw))
    return out


def count_x_posts(uid: str) -> int:
    """Total number of stored X posts for the user."""
    return _store().count(_posts_path(uid))


def get_newest_tweet_id(uid: str) -> Optional[str]:
    """Highest stored tweet id for incremental sync (X `since_id`).

    Tweet ids are snowflake ids — lexicographically larger ids are newer once
    zero-padded, but they're numeric strings of equal-ish length so we compare
    as ints to be safe.
    """
    docs = _store().query(_posts_path(uid), filters=[('kind', '==', KIND_TWEET)])
    best: Optional[int] = None
    for d in docs:
        try:
            v = int(d.id)
        except (TypeError, ValueError):
            continue
        if best is None or v > best:
            best = v
    return str(best) if best is not None else None

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

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db

logger = logging.getLogger(__name__)

users_collection = 'users'
x_posts_collection = 'x_posts'
MEMORY_EXTRACTION_PENDING = 'pending'
MEMORY_EXTRACTION_COMPLETED = 'completed'

# Post "kinds" stored under the same collection, distinguished by the `kind` field.
KIND_TWEET = 'tweet'
KIND_BOOKMARK = 'bookmark'
KIND_LIKE = 'like'

# Firestore rejects a commit with more than 500 mutations, so writes are chunked.
BATCH_LIMIT = 500


def _clean_uid(uid: Any) -> str:
    """Validate a user id before it becomes a Firestore document path segment.

    An empty or whitespace-only id otherwise reaches Firestore as an empty
    document id and raises an unhandled ``ValueError`` mid-write.
    """
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError('uid is required')
    return uid.strip()


def _has_uid(uid: Any) -> bool:
    return isinstance(uid, str) and bool(uid.strip())


def _clean_post_id(value: Any) -> str:
    """Normalize a post id to a non-empty string, or '' when unusable."""
    if value is None:
        return ''
    return str(value).strip()


def _posts_ref(uid: str) -> Any:
    return db.collection(users_collection).document(uid).collection(x_posts_collection)


def save_x_posts(uid: str, posts: List[Any]) -> int:
    """Idempotently store raw X posts. Returns the number of NEW posts written.

    Each post dict must contain at least: id (tweet id, str), text, created_at,
    kind. We dedupe on the document id (the tweet id), so calling this repeatedly
    with overlapping pages only ever inserts each post once. Entries that are not
    dicts, or that carry no usable id, are skipped instead of aborting the write.
    """
    if not posts:
        return 0

    uid = _clean_uid(uid)
    coll = _posts_ref(uid)
    # Find which ids already exist so we can report an accurate delta and avoid
    # clobbering `ingested_at` on re-sync.
    ids = [i for i in (_clean_post_id(p.get('id')) for p in posts if isinstance(p, dict)) if i]
    existing: set[str] = set()
    # get_all is efficient for the modest page sizes the connector pulls (<=100).
    for snap in db.get_all([coll.document(i) for i in ids]):
        if getattr(snap, "exists", False):
            existing.add(str(snap.id))

    now = datetime.now(timezone.utc)
    batch = db.batch()
    batch_count = 0
    new_count = 0
    for p in posts:
        if not isinstance(p, dict):
            continue
        pid = _clean_post_id(p.get('id'))
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
        batch.set(coll.document(pid), doc, merge=True)
        batch_count += 1
        if batch_count >= BATCH_LIMIT:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count > 0:
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
    if not _has_uid(uid):
        return []
    pending: List[Dict[str, Any]] = []
    for snapshot in _posts_ref(uid).stream():
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
    uid = _clean_uid(uid)
    clean_ids = [i for i in (_clean_post_id(pid) for pid in post_ids) if i]
    if not clean_ids:
        return
    coll = _posts_ref(uid)
    now = datetime.now(timezone.utc)
    batch = db.batch()
    batch_count = 0
    for post_id in clean_ids:
        batch.set(
            coll.document(post_id),
            {
                'memory_extraction_status': MEMORY_EXTRACTION_COMPLETED,
                'memory_extracted_at': now,
                'updated_at': now,
            },
            merge=True,
        )
        batch_count += 1
        if batch_count >= BATCH_LIMIT:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count > 0:
        batch.commit()


def get_x_posts(uid: str, limit: int = 100, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return stored posts, newest first. Optionally filter by kind.

    A kind filter + order_by would require a composite index, so when filtering
    by kind we use the single-field equality query (auto-indexed) and sort in
    Python — post volumes per user are small enough for this to be cheap.
    """
    if not _has_uid(uid):
        return []
    coll = _posts_ref(uid)
    if kind:
        docs: List[Dict[str, Any]] = []
        for d in coll.where(filter=FieldFilter('kind', '==', kind)).stream():
            raw: object = d.to_dict()
            if isinstance(raw, dict):
                docs.append(cast(Dict[str, Any], raw))
        docs.sort(key=lambda x: str(x.get('created_at') or ''), reverse=True)
        return docs[:limit]
    query = coll.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
    out: List[Dict[str, Any]] = []
    for d in query.stream():
        raw = d.to_dict()
        if isinstance(raw, dict):
            out.append(cast(Dict[str, Any], raw))
    return out


def get_x_posts_by_ids(uid: str, ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch specific posts by id (used by semantic search to hydrate matches)."""
    if not ids or not _has_uid(uid):
        return []
    clean_ids = [i for i in (_clean_post_id(i) for i in ids) if i]
    if not clean_ids:
        return []
    coll = _posts_ref(uid)
    out: List[Dict[str, Any]] = []
    for snap in db.get_all([coll.document(str(i)) for i in clean_ids]):
        if getattr(snap, "exists", False):
            raw: object = snap.to_dict()
            if isinstance(raw, dict):
                out.append(cast(Dict[str, Any], raw))
    return out


def count_x_posts(uid: str) -> int:
    """Total number of stored X posts for the user."""
    if not _has_uid(uid):
        return 0
    agg = _posts_ref(uid).count().get()
    # Firestore aggregation returns a list of AggregationResult rows.
    try:
        return int(agg[0][0].value)
    except Exception:
        return len(list(_posts_ref(uid).stream()))


def get_newest_tweet_id(uid: str) -> Optional[str]:
    """Highest stored tweet id for incremental sync (X `since_id`).

    Tweet ids are snowflake ids — lexicographically larger ids are newer once
    zero-padded, but they're numeric strings of equal-ish length so we compare
    as ints to be safe.
    """
    if not _has_uid(uid):
        return None
    docs = list(_posts_ref(uid).where(filter=FieldFilter('kind', '==', KIND_TWEET)).stream())
    best: Optional[int] = None
    for d in docs:
        try:
            v = int(d.id)
        except (TypeError, ValueError):
            continue
        if best is None or v > best:
            best = v
    return str(best) if best is not None else None

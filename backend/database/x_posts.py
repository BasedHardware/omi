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


# Validation & Persistence Design:
# - Loud writes: Mutator functions (e.g. save_x_posts) validate inputs strictly and raise ValueError
#   on invalid uid or malformed payloads to prevent corrupt records from reaching the data layer.
# - Quiet reads: Reader and counter functions (e.g. get_x_posts, get_x_post_counts) gracefully
#   degrade on invalid uid returning safe defaults ([], 0, None) so read paths never trigger unhandled 500s.


def _posts_ref(uid: str) -> Any:
    clean_uid = uid.strip() if isinstance(uid, str) else ''
    return db.collection(users_collection).document(clean_uid).collection(x_posts_collection)


def save_x_posts(uid: str, posts: List[Dict[str, Any]]) -> int:
    """Idempotently store raw X posts. Returns the number of NEW posts written.

    Each post dict must contain at least: id (tweet id, str), text, created_at,
    kind. We dedupe on the document id (the tweet id), so calling this repeatedly
    with overlapping pages only ever inserts each post once.

    Batch Atomicity Trade-off:
    Commits in chunks of 500 operations to satisfy Firestore batch write limits.
    A failure mid-sequence leaves earlier committed chunks written (no cross-chunk
    rollback), which is strictly preferred over an all-or-nothing failure for >500 items.
    """
    if not uid or not isinstance(uid, str) or not uid.strip():
        raise ValueError('uid must be a non-empty string')
    if not isinstance(posts, list):
        raise ValueError('posts must be a list')
    if not posts:
        return 0

    clean_uid = uid.strip()
    coll = _posts_ref(clean_uid)
    # Find which ids already exist so we can report an accurate delta and avoid
    # clobbering `ingested_at` on re-sync.
    valid_posts: List[Dict[str, Any]] = [
        p for p in posts if isinstance(p, dict) and p.get('id') is not None and str(p.get('id')).strip()
    ]
    if not valid_posts:
        return 0

    ids = [str(p['id']).strip() for p in valid_posts]
    existing: set[str] = set()
    # get_all is efficient for the modest page sizes the connector pulls (<=100).
    for snap in db.get_all([coll.document(i) for i in ids]):
        if getattr(snap, "exists", False):
            existing.add(str(snap.id))

    now = datetime.now(timezone.utc)
    batch = db.batch()
    batch_count = 0
    new_count = 0
    for p in valid_posts:
        pid = str(p['id']).strip()
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
        if batch_count >= 500:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count > 0:
        batch.commit()
    logger.info(f'save_x_posts uid={clean_uid} received={len(posts)} new={new_count}')
    return new_count


def get_pending_memory_extraction_posts(uid: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Return one bounded, stable batch of raw posts not yet mined for memories.

    Rows created before this ledger field are intentionally pending: replaying
    source rows incrementally is safer than silently treating a historical raw
    import as successfully extracted.
    """
    if not uid or not isinstance(uid, str) or not uid.strip():
        return []
    bounded_limit = max(1, min(limit, 500))
    pending: List[Dict[str, Any]] = []
    for snapshot in _posts_ref(uid.strip()).stream():
        raw = snapshot.to_dict()
        if not isinstance(raw, dict) or raw.get('memory_extraction_status') == MEMORY_EXTRACTION_COMPLETED:
            continue
        row = cast(Dict[str, Any], raw)
        row.setdefault('id', str(snapshot.id))
        pending.append(row)

    pending.sort(key=lambda row: (str(row.get('ingested_at') or row.get('created_at') or ''), str(row.get('id') or '')))
    return pending[:bounded_limit]


def mark_memory_extraction_completed(uid: str, post_ids: List[str]) -> None:
    """Acknowledge extraction only after its canonical/legacy memory writes succeed.

    Batch Atomicity Trade-off:
    Commits in chunks of 500 operations to satisfy Firestore batch write limits.
    Chunks commit independently without cross-chunk rollback if an intermediate chunk fails.
    """
    if not uid or not isinstance(uid, str) or not uid.strip():
        return
    if not post_ids or not isinstance(post_ids, list):
        return
    clean_ids = [str(post_id).strip() for post_id in post_ids if post_id and str(post_id).strip()]
    if not clean_ids:
        return
    now = datetime.now(timezone.utc)
    batch = db.batch()
    batch_count = 0
    coll = _posts_ref(uid.strip())
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
        if batch_count >= 500:
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
    if not uid or not isinstance(uid, str) or not uid.strip():
        return []
    bounded_limit = max(1, min(limit, 500))
    coll = _posts_ref(uid.strip())
    if kind:
        docs: List[Dict[str, Any]] = []
        for d in coll.where(filter=FieldFilter('kind', '==', kind)).stream():
            raw: object = d.to_dict()
            if isinstance(raw, dict):
                docs.append(cast(Dict[str, Any], raw))
        docs.sort(key=lambda x: str(x.get('created_at') or ''), reverse=True)
        return docs[:bounded_limit]
    query = coll.order_by('created_at', direction=firestore.Query.DESCENDING).limit(bounded_limit)
    out: List[Dict[str, Any]] = []
    for d in query.stream():
        raw = d.to_dict()
        if isinstance(raw, dict):
            out.append(cast(Dict[str, Any], raw))
    return out


def get_x_posts_by_ids(uid: str, ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch specific posts by id (used by semantic search to hydrate matches)."""
    if not uid or not isinstance(uid, str) or not uid.strip():
        return []
    if not ids or not isinstance(ids, list):
        return []
    clean_ids = [str(i).strip() for i in ids if i and str(i).strip()]
    if not clean_ids:
        return []
    coll = _posts_ref(uid.strip())
    out: List[Dict[str, Any]] = []
    for snap in db.get_all([coll.document(i) for i in clean_ids]):
        if getattr(snap, "exists", False):
            raw: object = snap.to_dict()
            if isinstance(raw, dict):
                out.append(cast(Dict[str, Any], raw))
    return out


def count_x_posts(uid: str) -> int:
    """Total number of stored X posts for the user."""
    if not uid or not isinstance(uid, str) or not uid.strip():
        return 0
    coll = _posts_ref(uid.strip())
    agg = coll.count().get()
    # Firestore aggregation returns a list of AggregationResult rows.
    try:
        return int(agg[0][0].value)
    except Exception:
        return len(list(coll.stream()))


def get_newest_tweet_id(uid: str) -> Optional[str]:
    """Highest stored tweet id for incremental sync (X `since_id`).

    Tweet ids are snowflake ids — lexicographically larger ids are newer once
    zero-padded, but they're numeric strings of equal-ish length so we compare
    as ints to be safe.
    """
    if not uid or not isinstance(uid, str) or not uid.strip():
        return None
    docs = list(_posts_ref(uid.strip()).where(filter=FieldFilter('kind', '==', KIND_TWEET)).stream())
    best: Optional[int] = None
    for d in docs:
        try:
            v = int(d.id)
        except (TypeError, ValueError):
            continue
        if best is None or v > best:
            best = v
    return str(best) if best is not None else None

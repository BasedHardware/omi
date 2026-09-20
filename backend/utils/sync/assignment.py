"""Atomic sync intake and conservative, speaker-independent relevance policy.

The assignment index contains only interval metadata, never transcript text.
Firestore retries the whole read/append/write operation on contention. There is
no expiring lock that lets a late worker overwrite a newer transcript.
"""

from copy import deepcopy
import re
from typing import TYPE_CHECKING, Callable, Optional

from utils.sync.merge_dedupe import dedupe_segments_for_merge
from utils.sync.assignment_index import AssignmentIndex
from utils.conversation_continuity import intervals_connect

if TYPE_CHECKING:
    from google.cloud.firestore_v1 import transaction as firestore_transaction
    from google.cloud.firestore_v1.document import DocumentReference


def needs_fragment_review(segments: list[dict]) -> bool:
    """Defer only short, filler-only content. Unknown language/content stays kept.

    Speaker IDs, profiles, and is_user are intentionally not consulted. Even a
    false positive keeps a visible transcript, and subsequent content is assessed
    over the entire merged recording, allowing automatic promotion.
    """
    words = re.findall(r"[^\W_]+", ' '.join(s.get('text', '') for s in segments).casefold())
    duration = sum(max(0, s['end'] - s['start']) for s in segments)
    return (
        bool(words)
        and len(words) <= 12
        and duration <= 15
        and set(words)
        <= {'mm', 'hmm', 'hm', 'mhm', 'huh', 'uh', 'um', 'hmmh', 'mmh', 'hmmmh', 'hmmmmm', 'ha', 'haha', 'hahaha'}
    )


def compatible_capture(left: dict, right: dict) -> bool:
    # Unknown is a partition, not a wildcard: wildcard equality is non-transitive.
    return all(left.get(key) == right.get(key) for key in ('source', 'client_device_id', 'sync_capture_id')) and bool(
        left.get('is_locked')
    ) == bool(right.get('is_locked'))


def interval_matches(row: dict, incoming: dict) -> bool:
    return compatible_capture(row, incoming) and intervals_connect(
        row['started_at'].timestamp(),
        row['finished_at'].timestamp(),
        incoming['started_at'].timestamp(),
        incoming['finished_at'].timestamp(),
    )


def auto_mergeable(row: dict) -> bool:
    """Only unattended sync rows may donate content or change visible identity.

    Explicit targets retain their identity. Shared/curated/photo-bearing records
    remain intact rather than exposing private donors or orphaning user edits.
    """
    return bool(row.get('sync_content_revision')) and not (
        row.get('sync_live_target')
        or row.get('has_photos')
        or row.get('user_title')
        or row.get('starred')
        or row.get('folder_user_set')
        or row.get('visibility', 'private') not in (None, 'private')
    )


def assign_in_transaction(
    transaction: 'firestore_transaction.Transaction',
    user_ref: 'DocumentReference',
    incoming: dict,
    *,
    candidate_id: Optional[str] = None,
    target_id: Optional[str] = None,
    decode: Callable[[dict], dict],
    encode: Callable[[dict], dict],
    invalidate: Callable[[dict], None],
) -> tuple[dict, bool, list[dict]]:
    """Production transaction body; injected codecs preserve encryption in adapters.

    The user-level index document is read AND written by every intake, including
    the empty-index case. Concurrent jobs cannot both commit an absent target.
    The outside legacy lookup is only a hint; all documents are reread here.
    """
    incoming = deepcopy(incoming)
    index = AssignmentIndex(transaction, user_ref)
    collection = user_ref.collection('conversations')
    read = {}

    def load(cid):
        if cid not in read:
            read[cid] = collection.document(cid).get(transaction=transaction).to_dict()
        return read[cid]

    # Read the incoming key too: retries and deleted canonical anchors must never
    # overwrite a tombstone. Redirects are server-authored, not user deletions.
    own = load(incoming['id'])
    if own and own.get('deleted') and not own.get('sync_merged_into'):
        raise ValueError('sync anchor was deleted')
    if own and not own.get('deleted') and not auto_mergeable(own) and not target_id:
        raise ValueError('sync anchor is user managed')
    # A retry of an absorbed chunk follows its lineage. Otherwise deleting the
    # survivor and replaying a donor could recreate that donor's tombstone.
    if own and own.get('sync_merged_into') and not target_id:
        target_id = own['id']
    target = load(target_id) if target_id else None
    seen = set()
    while target and target.get('sync_merged_into'):
        if target['id'] in seen:
            raise ValueError('sync redirect cycle')
        seen.add(target['id'])
        target_id = target['sync_merged_into']
        target = load(target_id)
    if seen and (not target or target.get('deleted')):
        raise ValueError('sync capture lineage was deleted')
    if target_id and not target:
        incoming['id'] = target_id
        incoming['sync_capture_id'] = target_id
    elif target and not target.get('deleted'):
        incoming['sync_capture_id'] = target.get('sync_capture_id')
        if not compatible_capture(target, incoming):
            raise ValueError('sync target provenance mismatch')
    else:
        target_id = None

    matched = {}
    extent = deepcopy(incoming)
    if target_id and target:
        matched[target_id] = target
        extent['started_at'] = min(extent['started_at'], target['started_at'])
        extent['finished_at'] = max(extent['finished_at'], target['finished_at'])
    while True:
        ids = {row['id'] for row in index.read(extent) if interval_matches(row, extent)}
        ids.update(cid for cid in (candidate_id, incoming['id']) if cid)
        before = len(matched)
        for cid in sorted(ids - matched.keys()):
            raw = load(cid)
            if raw and not raw.get('deleted') and interval_matches(raw, extent):
                # Live conversations are explicit targets only. Their lifecycle,
                # photos and recording bindings are not owned by sync intake.
                if not auto_mergeable(raw) and cid != target_id:
                    continue
                matched[cid] = raw
                extent['started_at'] = min(extent['started_at'], raw['started_at'])
                extent['finished_at'] = max(extent['finished_at'], raw['finished_at'])
        if len(matched) == before:
            break

    canonical = target_id or min([incoming['id'], *matched])
    current = matched.get(canonical)
    created = current is None
    records = [decode(raw) for _, raw in sorted(matched.items())]
    result = deepcopy(next((row for row in records if row['id'] == canonical), records[0] if records else incoming))
    result['id'] = canonical
    result['sync_capture_id'] = incoming.get('sync_capture_id')
    result['sync_live_target'] = bool(
        target and (target.get('sync_live_target') or not target.get('sync_content_revision'))
    )
    if not result['sync_live_target']:
        result['created_at'] = extent['started_at']
    origin = extent['started_at'].timestamp()
    existing = []
    for row in records:
        new = deepcopy(row.get('transcript_segments', []))
        for segment in new:
            segment['timestamp'] = row['started_at'].timestamp() + segment['start']
            duration = segment['end'] - segment['start']
            segment['start'] = segment['timestamp'] - origin
            segment['end'] = segment['start'] + duration
        existing += dedupe_segments_for_merge(origin, existing, new, text_match_slop_seconds=0)
    new = deepcopy(incoming['transcript_segments'])
    for segment in new:
        segment['timestamp'] = incoming['started_at'].timestamp() + segment['start']
    survivors = dedupe_segments_for_merge(
        origin, existing, new, text_match_slop_seconds=600 if target and not target.get('sync_content_revision') else 0
    )
    segments = existing + deepcopy(survivors)
    segments.sort(key=lambda s: (s['timestamp'], s['end'] - s['start'], s.get('text', '')))
    for segment in segments:
        duration = segment['end'] - segment['start']
        segment['start'] = segment.pop('timestamp') - origin
        segment['end'] = segment['start'] + duration
    result.update(started_at=extent['started_at'], finished_at=extent['finished_at'], transcript_segments=segments)
    result['has_content'] = bool(segments)
    result['discarded'] = False  # sync relevance demotes visibly; it never discards capture
    result['sync_content_revision'] = max([row.get('sync_content_revision') or 0 for row in records] + [0]) + 1
    result['sync_relevance'] = 'review' if not segments or needs_fragment_review(segments) else 'keep'
    result['is_locked'] = bool(incoming.get('is_locked'))
    result['private_cloud_sync_enabled'] = any(row.get('private_cloud_sync_enabled') for row in [incoming, *records])
    # A codec must never be downgraded when bridge donors have mixed protection.
    result['data_protection_level'] = (
        'enhanced'
        if any((row.get('data_protection_level') or 'enhanced') == 'enhanced' for row in [incoming, *records])
        else incoming['data_protection_level']
    )
    ancestors = {cid for row in records for cid in row.get('sync_merged_from', [])}
    ancestors.update(cid for cid in matched if cid != canonical)
    result['sync_merged_from'] = sorted(ancestors)
    if incoming.get('geolocation') and not result.get('geolocation'):
        result['geolocation'] = incoming['geolocation']

    # Read all occupied day buckets before the first write.
    index.read(extent)
    payload = encode(result)
    payload.pop('photos', None)
    if created:
        # DELETE_FIELD is invalid in a Firestore set without merge. New anchors
        # inherit content, never a donor's client processing projection.
        clears = {}
        invalidate(clears)
        for field in clears:
            payload.pop(field, None)
        transaction.set(collection.document(canonical), payload)
    else:
        invalidate(payload)
        transaction.update(collection.document(canonical), payload)
    for cid, row in matched.items():
        if cid != canonical:
            transaction.update(
                collection.document(cid),
                {
                    'deleted': True,
                    'sync_merged_into': canonical,
                    'sync_content_revision': (row.get('sync_content_revision') or 0) + 1,
                },
            )
    index.write(result, set(matched) | {canonical})
    return result, created, survivors

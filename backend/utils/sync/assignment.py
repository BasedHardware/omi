"""Atomic sync intake and conservative, speaker-independent relevance policy.

The assignment index contains only recent interval metadata, never transcript text.
Firestore retries the whole read/append/write operation on contention. There is
no expiring lock that lets a late worker overwrite a newer transcript.
"""

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import TYPE_CHECKING, Callable, Optional

from utils.sync.merge_dedupe import dedupe_segments_for_merge

if TYPE_CHECKING:
    from google.cloud.firestore_v1 import transaction as firestore_transaction
    from google.cloud.firestore_v1.document import DocumentReference

ASSIGNMENT_GAP_SECONDS = 120
MAX_RECENT_ASSIGNMENTS = 128


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
    return left.get('source') == right.get('source') and not (
        left.get('client_device_id')
        and right.get('client_device_id')
        and left['client_device_id'] != right['client_device_id']
    )


def interval_matches(row: dict, incoming: dict) -> bool:
    return (
        compatible_capture(row, incoming)
        and row['finished_at'].timestamp() + ASSIGNMENT_GAP_SECONDS >= incoming['started_at'].timestamp()
        and row['started_at'].timestamp() - ASSIGNMENT_GAP_SECONDS <= incoming['finished_at'].timestamp()
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
    index_ref = user_ref.collection('sync_assignment').document('recent')
    index = index_ref.get(transaction=transaction).to_dict() or {}
    entries = index.get('entries', [])
    ids = [entry['id'] for entry in reversed(entries) if interval_matches(entry, incoming)]
    if candidate_id and candidate_id not in ids:
        ids.append(candidate_id)
    if target_id:
        ids = [target_id] + [cid for cid in ids if cid != target_id]

    current = None
    for cid in ids:
        raw = user_ref.collection('conversations').document(cid).get(transaction=transaction).to_dict()
        if raw and not raw.get('deleted') and (cid == target_id or interval_matches(raw, incoming)):
            current = decode(raw)
            break

    created = current is None
    result = deepcopy(incoming if created else current)
    origin = result['started_at'].timestamp()
    incoming_origin = incoming['started_at'].timestamp()
    existing = [] if created else deepcopy(result['transcript_segments'])
    for segment in existing:
        segment['timestamp'] = origin + segment['start']
    new = deepcopy(incoming['transcript_segments'])
    for segment in new:
        segment['timestamp'] = incoming_origin + segment['start']
    # Separate WAL chunks may contain identical narration. Only absolute range
    # dedupe is appropriate for sync-owned recordings; retain live clock-slop
    # matching for a legacy/live target.
    survivors = dedupe_segments_for_merge(
        origin, existing, new, text_match_slop_seconds=0 if result.get('sync_content_revision') or created else 600
    )
    segments = existing + deepcopy(survivors)
    segments.sort(key=lambda s: s['timestamp'])
    origin = min(origin, incoming_origin)
    for segment in segments:
        duration = segment['end'] - segment['start']
        segment['start'] = segment.pop('timestamp') - origin
        segment['end'] = segment['start'] + duration
    result['started_at'] = datetime.fromtimestamp(origin, timezone.utc)
    result['finished_at'] = max(result['finished_at'], incoming['finished_at'])
    result['transcript_segments'] = segments
    result['has_content'] = bool(segments)
    result['sync_content_revision'] = (result.get('sync_content_revision') or 0) + 1
    result['sync_relevance'] = 'review' if needs_fragment_review(segments) else 'keep'
    result['is_locked'] = bool(result.get('is_locked') or incoming.get('is_locked'))
    if incoming.get('geolocation') and not result.get('geolocation'):
        result['geolocation'] = incoming['geolocation']

    entry = {key: result.get(key) for key in ('id', 'started_at', 'finished_at', 'source', 'client_device_id')}
    entries = [row for row in entries if row['id'] != result['id']] + [entry]
    ref = user_ref.collection('conversations').document(result['id'])
    if created:
        payload = encode(result)
        payload.pop('photos', None)
        payload.pop('updated_at', None)
        transaction.set(ref, payload)
    else:
        fields = (
            'started_at',
            'finished_at',
            'transcript_segments',
            'has_content',
            'sync_content_revision',
            'sync_relevance',
            'is_locked',
            'geolocation',
        )
        payload = encode({key: result[key] for key in fields if key in result})
        invalidate(payload)
        transaction.update(ref, payload)
    transaction.set(index_ref, {'entries': entries[-MAX_RECENT_ASSIGNMENTS:]})
    return result, created, survivors

"""Atomic sync intake and conservative, speaker-independent relevance policy.

The assignment index contains only interval metadata, never transcript text.
Firestore retries the whole read/append/write operation on contention. There is
no expiring lock that lets a late worker overwrite a newer transcript.
"""

from copy import deepcopy
from typing import TYPE_CHECKING, Callable, Optional

from utils.manual_speaker_assignments import apply_manual_assignments

from utils.conversations.fragment_visibility import is_low_signal_sync_fragment
from utils.conversations.relevance import sync_intake_decision
from utils.conversations.relevance_rules import deterministic_relevance
from utils.sync.merge_dedupe import dedupe_segments_for_merge
from utils.sync.assignment_index import AssignmentIndex
from utils.sync.assignment_errors import SyncAssignmentSuperseded, SyncAssignmentConflict
from utils.conversation_continuity import intervals_connect
from utils.stt.speaker_identity import ConversationSpeakerIdAllocator

if TYPE_CHECKING:
    from google.cloud.firestore_v1 import transaction as firestore_transaction
    from google.cloud.firestore_v1.document import DocumentReference


def needs_fragment_review(segments: list[dict]) -> bool:
    """Whether the deterministic relevance rules discard this transcript outright.

    Speaker IDs, profiles, and is_user are intentionally not consulted. Even a
    false positive keeps a recoverable transcript, and subsequent content is assessed
    over the entire merged recording, allowing automatic promotion. Everything
    the rules cannot settle stays ``keep`` here and is assessed by the
    relevance step when the sync pipeline processes it.
    """
    verdict, rule = fragment_rule(segments)
    # Segments with no recognized words are unknown content here, not filler:
    # intake keeps them, and the relevance step settles them when processed.
    return verdict == 'discard' and rule != 'empty_transcript'


def fragment_rule(segments: list[dict]) -> tuple[Optional[str], str]:
    return deterministic_relevance(
        [s.get('text', '') for s in segments],
        sum(max(0, s['end'] - s['start']) for s in segments),
    )


def compatible_capture(left: dict, right: dict) -> bool:
    # Unknown is a partition, not a wildcard: wildcard equality is non-transitive.
    return all(left.get(key) == right.get(key) for key in ('source', 'client_device_id')) and bool(
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

    Explicit live targets retain their identity. Shared/curated/photo-bearing records
    remain intact rather than exposing private donors or orphaning user edits.
    """
    return bool(row.get('sync_content_revision')) and not (
        row.get('sync_live_target')
        or row.get('has_photos')
        or row.get('user_title')
        or row.get('starred')
        or row.get('folder_user_set')
        or row.get('sync_relevance_user_kept')
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
    read: dict[str, dict | None] = {}

    def load(cid: str) -> dict | None:
        if cid not in read:
            read[cid] = collection.document(cid).get(transaction=transaction).to_dict()
        return read[cid]

    # Read the incoming key too: retries and deleted canonical anchors must never
    # overwrite a tombstone. Redirects are server-authored, not user deletions.
    own = load(incoming['id'])
    if own and own.get('deleted') and not own.get('sync_merged_into'):
        raise SyncAssignmentSuperseded('sync anchor was deleted')

    def resolve(cid: str | None) -> tuple[str | None, dict | None]:
        row = load(cid) if cid else None
        seen = set()
        while row and row.get('sync_merged_into'):
            if row['id'] in seen:
                raise SyncAssignmentConflict('sync redirect cycle')
            seen.add(row['id'])
            redirect_id: str = row['sync_merged_into']
            cid, row = redirect_id, load(redirect_id)
        if seen and (not row or row.get('deleted')):
            raise SyncAssignmentSuperseded('sync capture lineage was deleted')
        return cid, row

    # Check retry lineage independently of client hints: changing a target must
    # never allow an absorbed chunk to resurrect its user-deleted survivor.
    own_id, own_anchor = resolve(incoming['id'])
    target = load(target_id) if target_id else None
    target_hint = target_id
    if target and not target.get('deleted'):
        # Explicit capture proof is authoritative even before live STT produced
        # words. Only timestamp hints must exclude live-owned rows.
        if not compatible_capture(target, incoming):
            raise SyncAssignmentConflict('sync target provenance mismatch')
    else:
        # Missing/tombstoned explicit targets fall back to temporal assignment.
        # The independent retry-lineage check above still fences user deletion.
        target_id, target = None, None
    if own_anchor and not auto_mergeable(own_anchor) and own_id != target_id:
        raise SyncAssignmentSuperseded('sync anchor is user managed')

    if target_id and own_anchor and own_id != target_id and own_anchor.get('manual_speaker_assignments'):
        raise SyncAssignmentSuperseded('sync anchor has manual speaker assignments')

    receipt_owner = target_id or (own_id if own_anchor and own_anchor.get('manual_speaker_assignments') else None)
    matched = {}
    extent = deepcopy(incoming)
    if target_id and target:
        matched[target_id] = target
        extent['started_at'] = min(extent['started_at'], target['started_at'])
        extent['finished_at'] = max(extent['finished_at'], target['finished_at'])
    while True:
        ids = {row['id'] for row in index.read(extent) if interval_matches(row, extent)}
        ids.update(cid for cid in (candidate_id, incoming['id'], own_id, target_hint) if cid)
        before = len(matched)
        candidates = []
        for cid in sorted(ids - matched.keys()):
            raw = load(cid)
            if raw and not raw.get('deleted') and interval_matches(raw, extent):
                # Live and user-managed rows can only be explicit targets.
                if not auto_mergeable(raw) and cid != target_id:
                    continue
                candidates.append((cid, raw))
        if receipt_owner is None:
            labeled = [(cid, raw) for cid, raw in candidates if raw.get('manual_speaker_assignments')]
            if labeled:
                receipt_owner = min(labeled, key=lambda item: (item[1]['started_at'], item[0]))[0]
        for cid, raw in candidates:
            # Excluded receipts must not extend the search or survivor's timestamps.
            if raw.get('manual_speaker_assignments') and cid != receipt_owner:
                continue
            matched[cid] = raw
            extent['started_at'] = min(extent['started_at'], raw['started_at'])
            extent['finished_at'] = max(extent['finished_at'], raw['finished_at'])
        if len(matched) == before:
            break

    canonical = (
        target_id
        or (receipt_owner if receipt_owner in matched else None)
        or (min(matched, key=lambda cid: (matched[cid]['started_at'], cid)) if matched else incoming['id'])
    )
    current = matched.get(canonical)
    created = current is None
    records = [decode(raw) for _, raw in sorted(matched.items())]
    result = deepcopy(next((row for row in records if row['id'] == canonical), records[0] if records else incoming))
    result['id'] = canonical
    result['sync_live_target'] = bool(
        target and (target.get('sync_live_target') or not target.get('sync_content_revision'))
    )
    if not result['sync_live_target']:
        result['created_at'] = extent['started_at']
    origin = extent['started_at'].timestamp()
    existing = []
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate(result.get('transcript_segments', []) if current else [])
    for row in sorted(records, key=lambda row: row['id'] != canonical):
        new = deepcopy(row.get('transcript_segments', []))
        for segment in new:
            segment['timestamp'] = row['started_at'].timestamp() + segment['start']
            duration = segment['end'] - segment['start']
            segment['start'] = segment['timestamp'] - origin
            segment['end'] = segment['start'] + duration
        retained = dedupe_segments_for_merge(origin, existing, new, text_match_slop_seconds=0)
        if row['id'] != canonical:
            for segment in retained:
                if not segment.get('speaker_id_scope'):
                    segment['speaker_id_scope'] = f"legacy-conversation:{row['id']}:{segment.get('speaker_id')}"
                allocator.assign(segment)
        existing += retained
    new = deepcopy(incoming['transcript_segments'])
    for segment in new:
        segment['timestamp'] = incoming['started_at'].timestamp() + segment['start']
    survivors = dedupe_segments_for_merge(
        origin, existing, new, text_match_slop_seconds=600 if target and not target.get('sync_content_revision') else 0
    )
    for segment in survivors:
        allocator.assign(segment)
    segments = existing + deepcopy(survivors)
    segments.sort(key=lambda s: (s['timestamp'], s['end'] - s['start'], s.get('text', '')))
    for segment in segments:
        duration = segment['end'] - segment['start']
        segment['start'] = segment.pop('timestamp') - origin
        segment['end'] = segment['start'] + duration
    result.update(
        started_at=extent['started_at'],
        finished_at=extent['finished_at'],
        transcript_segments=apply_manual_assignments(segments, result.get('manual_speaker_assignments') or {}),
    )
    result['has_content'] = bool(segments)
    result['sync_content_revision'] = max([row.get('sync_content_revision') or 0 for row in records] + [0]) + 1
    result['sync_relevance'] = (
        'review'
        if not result.get('sync_relevance_user_kept') and (not segments or needs_fragment_review(segments))
        else 'keep'
    )
    # Discard is a recoverable list filter, never a deletion of captured speech.
    # Meaningful later intake automatically promotes the complete recording.
    result['discarded'] = is_low_signal_sync_fragment(result)
    if result['discarded']:
        result['relevance_decision'] = sync_intake_decision(fragment_rule(segments)[1])
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
                    # Hide the redirect from discarded==False list indexes. Distinct
                    # from user discard: include_discarded=True readers still drop
                    # these rows via is_soft_deleted, and restore must not revive them.
                    'discarded': True,
                    'sync_merged_into': canonical,
                    'sync_content_revision': (row.get('sync_content_revision') or 0) + 1,
                },
            )
    index.write(result, set(matched) | {canonical})
    return result, created, survivors

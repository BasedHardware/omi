"""Atomic sync intake and conservative, speaker-independent relevance policy.

The assignment index contains only interval metadata, never transcript text.
Firestore retries the whole read/append/write operation on contention. There is
no expiring lock that lets a late worker overwrite a newer transcript.
"""

from copy import deepcopy
from datetime import datetime
import logging
import math
from typing import TYPE_CHECKING, Any, Callable, NamedTuple, Optional, TypeVar

from config.conversation_smart_merge import smart_merge_flatten_enabled
from config.sync_lineage import sync_lineage_resolve_active_for
from config.sync_live_dedupe import sync_live_dedupe_active_for
from config.sync_assignment_recovery import sync_assignment_recovery_enabled
from database._client import firestore_document_kind, firestore_error_document_path, is_document_size_limit_error
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes
from utils.observability.fallback import record_fallback
from utils.manual_speaker_assignments import apply_manual_assignments
from utils.capture_evidence import bounded_envelope, merge_track_receipts

from config import merge_ancestry
import config.speaker_match_scores as match_scores
from utils.conversations.fragment_visibility import is_low_signal_sync_fragment
from utils.conversations.relevance import sync_intake_decision
from utils.conversations.smart_merge_policy import user_managed as _policy_user_managed
from utils.conversations.relevance_rules import deterministic_relevance
from utils.sync.capture_repeat_evidence import capture_covered_indices
from utils.sync.live_speech_dedupe import (
    MAX_LIVE_SEGMENTS,
    append_alignment_method,
    bounded_span_seconds,
    drop_covered_repeats,
    drop_proven_exact_retries,
    pinned_audio_timeline,
)
from utils.sync.merge_dedupe import dedupe_segments_for_merge
from utils.sync.assignment_index import AssignmentIndex
from utils.sync.assignment_errors import SyncAssignmentSuperseded, SyncAssignmentConflict
from utils.conversation_continuity import intervals_connect
from utils.stt.speaker_identity import ConversationSpeakerIdAllocator

if TYPE_CHECKING:
    from google.cloud.firestore_v1 import transaction as firestore_transaction
    from google.cloud.firestore_v1.document import DocumentReference

logger = logging.getLogger(__name__)
_T = TypeVar('_T')

# Firestore rejects any write that leaves a document above 1 MiB
# (FIRESTORE_MAX_DOCUMENT_BYTES), and a temporal merge only ever grows the
# canonical conversation. When the canonical's next write is estimated above
# this budget, the incoming chunk starts (or joins) another conversation
# instead. The estimate follows Firestore's documented storage-size rules on
# the encoded payload, so it is exact for the value types sync writes; the
# 124 KiB headroom covers the estimate's remaining blind spots (the document
# name in test doubles, SDK values without a documented size) and the few bytes
# a later dedupe-only retry adds without needing a rollover.
SYNC_CONVERSATION_BYTE_BUDGET = FIRESTORE_MAX_DOCUMENT_BYTES - 124 * 1024  # 900 KiB


def capture_mismatch(left: dict, right: dict) -> str:
    """Which partition fields differ, as one of eight fixed tokens.

    ``none`` exactly when ``compatible_capture`` holds: every field is compared
    for equality, so two locked captures match. Never exposes field values.
    """
    fields = [
        name for key, name in (('source', 'source'), ('client_device_id', 'device')) if left.get(key) != right.get(key)
    ]
    if bool(left.get('is_locked')) != bool(right.get('is_locked')):
        fields.append('lock')
    return '_'.join(fields) or 'none'


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
        (row.get('smart_merge') or {}).get('role') == 'survivor'
        or row.get('sync_live_target')
        or row.get('has_photos')
        or row.get('user_title')
        or row.get('starred')
        or row.get('folder_user_set')
        or row.get('sync_relevance_user_kept')
        or row.get('visibility', 'private') not in (None, 'private')
    )


def _row_epoch(value: Any) -> float:
    return value.timestamp() if isinstance(value, datetime) else float(value)


def _lineage_span_delta_bucket(
    stamp_fallback: bool, live_target_id: Optional[str], current: Optional[dict], result: dict
) -> str:
    """Fixed extent-growth bucket for a stamp-fallback append to the explicit live row.

    Growth compares row ``started_at``/``finished_at`` only — never transcript
    sums, ids or text. A rollover elsewhere leaves the live extent unchanged,
    which is a zero growth, not a stretch of the new sync row.
    """
    if not stamp_fallback:
        return 'none'
    if not live_target_id:
        return 'unknown'
    if current is None or result.get('id') != live_target_id:
        return '0'
    try:
        grown_end = _row_epoch(result.get('finished_at'))
        grown_start = _row_epoch(result.get('started_at'))
        prior_end = _row_epoch(current.get('finished_at'))
        prior_start = _row_epoch(current.get('started_at'))
    except Exception:
        return 'unknown'
    endpoints = (grown_end, grown_start, prior_end, prior_start)
    if not all(map(math.isfinite, endpoints)) or grown_end < grown_start or prior_end < prior_start:
        return 'unknown'
    growth = (grown_end - grown_start) - (prior_end - prior_start)
    if growth <= 0:
        return '0'
    if growth <= 60:
        return '0_60'
    if growth <= 300:
        return '60_300'
    return 'gt_300'


def _smart_merge_lineage(row: dict | None) -> bool:
    return bool(row and (row.get('smart_merge') or {}).get('role') in ('donor', 'survivor'))


class _Plan(NamedTuple):
    """One complete, unwritten assignment: what the transaction would commit."""

    canonical: str
    matched: dict[str, dict]
    result: dict
    created: bool
    survivors: list[dict]
    # Indices into incoming['transcript_segments'] that this plan found new.
    kept: tuple[int, ...]
    payload: dict
    ancestor_updates: dict[str, dict]
    estimated_bytes: int

    @property
    def grows(self) -> bool:
        """Whether the write adds speech or absorbs another conversation."""
        return bool(self.survivors) or any(cid != self.canonical for cid in self.matched)


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
    full_ids: frozenset[str] = frozenset(),
) -> tuple[dict, bool, list[dict]]:
    """Production transaction body; injected codecs preserve encryption in adapters.

    The user-level index document is read AND written by every intake, including
    the empty-index case. Concurrent jobs cannot both commit an absent target.
    The outside legacy lookup is only a hint; all documents are reread here.

    ``full_ids`` names conversations a previous attempt proved cannot grow (the
    commit hit Firestore's document-size limit). They and any canonical whose
    write is estimated above ``SYNC_CONVERSATION_BYTE_BUDGET`` are left
    untouched: the chunk's new speech goes to another conversation instead.
    """
    incoming = deepcopy(incoming)
    lineage_binding = incoming.pop('_sync_lineage_binding', None)
    index = AssignmentIndex(transaction, user_ref)
    collection = user_ref.collection('conversations')
    read: dict[str, dict | None] = {}

    def load(cid: str) -> dict | None:
        if cid not in read:
            read[cid] = collection.document(cid).get(transaction=transaction).to_dict()
        return read[cid]

    # Read the incoming key too: retries and deleted canonical anchors must never
    # overwrite a tombstone. Redirects are server-authored, not user deletions.
    flatten = smart_merge_flatten_enabled()

    own = load(incoming['id'])
    if own and own.get('deleted') and not own.get('sync_merged_into'):
        if flatten and (own.get('smart_merge') or {}).get('role') == 'donor':
            raise SyncAssignmentConflict('smart merge donor tombstone lacks a redirect', subtype='other')
        raise SyncAssignmentSuperseded('sync anchor was deleted')

    def resolve(cid: str | None, *, one_hop: bool = False) -> tuple[str | None, dict | None]:
        row = load(cid) if cid else None
        seen = set()
        has_smart_state = False
        while row and row.get('sync_merged_into'):
            if row['id'] in seen:
                raise SyncAssignmentConflict('sync redirect cycle', subtype='redirect_cycle')
            has_smart_state = has_smart_state or (one_hop and _smart_merge_lineage(row))
            seen.add(row['id'])
            redirect_id: str = row['sync_merged_into']
            cid, row = redirect_id, load(redirect_id)
            has_smart_state = has_smart_state or (one_hop and _smart_merge_lineage(row))
            if has_smart_state and (len(seen) > 1 or (row and row.get('sync_merged_into') and row['id'] not in seen)):
                raise SyncAssignmentConflict('sync redirect chain exceeds one hop', subtype='other')
        if seen and (not row or row.get('deleted') or (has_smart_state and row.get('discarded'))):
            raise SyncAssignmentSuperseded('sync capture lineage was deleted')
        return cid, row

    # Check retry lineage independently of client hints: changing a target must
    # never allow an absorbed chunk to resurrect its user-deleted survivor.
    own_id, own_anchor = resolve(incoming['id'], one_hop=flatten)
    target = load(target_id) if target_id else None
    redirected = False
    if flatten:
        if target and target.get('sync_merged_into'):
            redirect_id = target['sync_merged_into']
            nxt = load(redirect_id)
            smart_lineage = _smart_merge_lineage(target) or _smart_merge_lineage(nxt)
            if smart_lineage:
                if redirect_id == target_id:
                    raise SyncAssignmentConflict('sync redirect cycle', subtype='redirect_cycle')
                if nxt and nxt.get('sync_merged_into'):
                    raise SyncAssignmentConflict('sync redirect chain exceeds one hop', subtype='other')
                if not nxt or nxt.get('deleted') or nxt.get('discarded'):
                    raise SyncAssignmentSuperseded('sync target survivor was deleted')
                target_id, target = redirect_id, nxt
                redirected = True
            else:
                target_id, target = None, None
        elif target and target.get('deleted') and (target.get('smart_merge') or {}).get('role') == 'donor':
            raise SyncAssignmentConflict('smart merge donor tombstone lacks a redirect', subtype='other')
    elif target and target.get('deleted') and (target.get('smart_merge') or {}).get('role') == 'donor':
        # A live conversation folded into its predecessor (database/smart_merge.py)
        # redirects its late repair audio to the survivor; temporal fallback would
        # recreate the donor as a duplicate row. A deleted survivor supersedes it.
        target_id, target = resolve(target_id)
    target_hint = target_id
    if target and not target.get('deleted'):
        # Explicit capture proof is authoritative even before live STT produced
        # words. Only timestamp hints must exclude live-owned rows.
        mismatch = capture_mismatch(target, incoming)
        if mismatch != 'none':
            if redirected:
                raise SyncAssignmentConflict('sync target provenance mismatch', subtype='provenance_mismatch')
            recover = sync_assignment_recovery_enabled()
            logger.warning(
                'event=sync_assignment_target outcome=%s mismatch=%s',
                'temporal_recovery' if recover else 'rejected',
                mismatch,
            )
            if not recover:
                raise SyncAssignmentConflict('sync target provenance mismatch', subtype='provenance_mismatch')
            record_fallback(
                component='sync_dispatch',
                from_mode='explicit_target',
                to_mode='temporal_assignment',
                reason='policy',
                outcome='degraded',
                log=logger,
            )
            target_id, target = None, None
    else:
        # Missing/tombstoned explicit targets fall back to temporal assignment.
        # The independent retry-lineage check above still fences user deletion.
        target_id, target = None, None
    stamp_fallback_live = bool(
        lineage_binding == 'stamp_fallback'
        and target_id
        and target is not None
        and sync_live_dedupe_active_for(user_ref.id)
    )
    anchor_mismatch = capture_mismatch(own_anchor, incoming) if own_anchor else 'none'
    if anchor_mismatch != 'none':
        logger.warning('event=sync_assignment_target outcome=anchor_rejected mismatch=%s', anchor_mismatch)
        # The stored retry anchor changed source, device or lock state since it
        # was written. It can no longer match temporally, so continuing would
        # replace it with a new row. An unchanged anchor (locked or not) is a
        # plain retry and deduplicates below.
        raise SyncAssignmentConflict('sync anchor provenance mismatch', subtype='provenance_mismatch')

    live_stats: Optional[dict] = None

    def plan(excluded: frozenset[str], segment_indices: tuple[int, ...]) -> _Plan:
        """Choose, merge and encode without writing; ``excluded`` rows stay untouched.

        An excluded conversation is never this chunk's target, donor or bridge,
        and every fence below re-runs without it.
        """
        nonlocal live_stats
        plan_target_id = target_id if target_id not in excluded else None
        plan_target = target if plan_target_id else None
        if own_anchor and not auto_mergeable(own_anchor) and own_id != plan_target_id:
            raise SyncAssignmentSuperseded('sync anchor is user managed')

        if plan_target_id and own_anchor and own_id != plan_target_id and own_anchor.get('manual_speaker_assignments'):
            raise SyncAssignmentSuperseded('sync anchor has manual speaker assignments')

        receipt_owner = plan_target_id or (
            own_id if own_anchor and own_anchor.get('manual_speaker_assignments') else None
        )
        matched = {}
        extent = deepcopy(incoming)
        if plan_target_id and plan_target:
            matched[plan_target_id] = plan_target
            extent['started_at'] = min(extent['started_at'], plan_target['started_at'])
            extent['finished_at'] = max(extent['finished_at'], plan_target['finished_at'])
        while True:
            ids = {row['id'] for row in index.read(extent) if interval_matches(row, extent)}
            ids.update(cid for cid in (candidate_id, incoming['id'], own_id, target_hint) if cid)
            ids -= excluded
            before = len(matched)
            candidates = []
            for cid in sorted(ids - matched.keys()):
                raw = load(cid)
                if raw and not raw.get('deleted') and interval_matches(raw, extent):
                    # Live and user-managed rows can only be explicit targets.
                    if not auto_mergeable(raw) and cid != plan_target_id:
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
            plan_target_id
            or (receipt_owner if receipt_owner in matched else None)
            or (min(matched, key=lambda cid: (matched[cid]['started_at'], cid)) if matched else incoming['id'])
        )
        current = matched.get(canonical)
        created = current is None
        records = [decode(raw) for _, raw in sorted(matched.items())]
        result = deepcopy(next((row for row in records if row['id'] == canonical), records[0] if records else incoming))
        try:
            contributions = [r for record in records for r in record.get(match_scores.FIELD) or []]
            if contributions:
                result[match_scores.FIELD] = match_scores.merge(None, contributions)
        except Exception:
            # Preserve the canonical's existing blob; skip only the donor merge.
            match_scores.record_failure(logger, reason='malformed_doc')
        result['id'] = canonical
        smart_live_target = bool(plan_target and (plan_target.get('smart_merge') or {}).get('role') == 'survivor')
        result['sync_live_target'] = bool(
            plan_target
            and (
                plan_target.get('sync_live_target') or smart_live_target or not plan_target.get('sync_content_revision')
            )
        )
        if not result['sync_live_target']:
            result['created_at'] = extent['started_at']
        capture_start = extent['started_at']
        pinned_live_origin = bool(
            result['sync_live_target']
            and plan_target
            and isinstance(plan_target.get('audio_timeline'), dict)
            and plan_target.get('audio_timeline')
            and sync_lineage_resolve_active_for(user_ref.id)
        )
        if pinned_live_origin and plan_target:
            # Live keeps emitting offsets against this durable first-audio pin.
            # Rebasing the row on an early safety WAL would move all future live
            # words. Preserve the pin and represent buffered pre-pin speech with
            # its exact (possibly negative) relative offset instead.
            capture_start = plan_target['started_at']
        origin = capture_start.timestamp()
        existing = []
        allocator = ConversationSpeakerIdAllocator()
        allocator.hydrate(result.get('transcript_segments', []) if current else [])
        for row in sorted(records, key=lambda row: row['id'] != canonical):
            new = deepcopy(row.get('transcript_segments', []))
            for segment in new:
                if row['id'] == canonical and not result['sync_live_target'] and not segment.get('speaker_id_scope'):
                    # A pre-scope sync survivor is still audio-aligned. Leave its
                    # visible ID intact (manual receipts may name it), but give
                    # conversation resolution the provenance it needs.
                    segment['speaker_id_scope'] = f"legacy-conversation:{row['id']}:{segment.get('speaker_id')}"
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
        new = [deepcopy(incoming['transcript_segments'][i]) for i in segment_indices]
        for segment in new:
            segment['timestamp'] = incoming['started_at'].timestamp() + segment['start']
        indexed_new = list(zip(segment_indices, new))
        live_row = next((row for row in records if row['id'] == canonical), None)
        live_dedupe = bool(
            plan_target is not None
            and canonical == plan_target_id
            and live_row is not None
            and result['sync_live_target']
            and sync_live_dedupe_active_for(user_ref.id)
        )
        if live_dedupe and plan_target is not None and live_row is not None:
            verified = capture_covered_indices(
                new,
                incoming.get('capture_evidence'),
                live_row.get('capture_evidence'),
            )
            lexical_kept, dedupe_report = drop_covered_repeats(
                new,
                live_row.get('transcript_segments', []),
                live_origin=plan_target['started_at'].timestamp(),
                live_pinned=pinned_audio_timeline(plan_target.get('audio_timeline')),
                verified_capture_indices=verified,
            )
            live_origin = plan_target['started_at'].timestamp()
            raw_live_segments = live_row.get('transcript_segments') or []
            if len(raw_live_segments) > MAX_LIVE_SEGMENTS:
                survivors, exact_retries, sync_retry = list(lexical_kept), 0, False
            else:
                live_stored = [
                    dict(segment, timestamp=live_origin + segment['start'])
                    for segment in raw_live_segments
                    if isinstance(segment.get('start'), (int, float))
                ]
                lexical_kept_ids = {id(segment) for segment in lexical_kept}
                survivors, exact_retries, sync_retry = drop_proven_exact_retries(
                    [(index, segment) for index, segment in enumerate(new) if id(segment) in lexical_kept_ids],
                    live_stored,
                    verified_indices=verified,
                )
            live_stats = {
                'report': dedupe_report,
                'exact_retries': exact_retries,
                'sync_retry': sync_retry,
            }
        else:
            survivors = dedupe_segments_for_merge(
                origin,
                existing,
                new,
                text_match_slop_seconds=(
                    600 if plan_target and (smart_live_target or not plan_target.get('sync_content_revision')) else 0
                ),
                # A bound safety WAL can mix one duplicate with genuinely new speech.
                # Near-exact text, duration, and time are enough to drop that one line;
                # broader clock-offset matches still require the batch gate.
                single_match_slop_seconds=2 if plan_target and result['sync_live_target'] else 0,
            )
        surviving = {id(segment) for segment in survivors}
        kept = tuple(i for i, segment in indexed_new if id(segment) in surviving)
        for segment in survivors:
            allocator.assign(segment)
        segments = existing + deepcopy(survivors)
        segments.sort(key=lambda s: (s['timestamp'], s['end'] - s['start'], s.get('text', '')))
        for segment in segments:
            duration = segment['end'] - segment['start']
            segment['start'] = segment.pop('timestamp') - origin
            segment['end'] = segment['start'] + duration
            if pinned_live_origin and segment['start'] < 0:
                # Speech before the live first-audio pin stays in the transcript,
                # but released clients cannot seek negative v2 offsets. Do not
                # claim playback alignment for that line.
                segment['audio_alignment'] = 'unplaced'
                segment['audio_capture_run'] = None
        result.update(
            started_at=capture_start,
            finished_at=extent['finished_at'],
            transcript_segments=apply_manual_assignments(segments, result.get('manual_speaker_assignments') or {}),
        )
        if incoming.get('capture_evidence') is not None:
            contributors = [row.get('capture_evidence') or {} for row in records] + [incoming['capture_evidence']]
            mapped = [receipt for item in contributors for receipt in item.get('receipts') or []]
            if mapped:
                combined = merge_track_receipts([], mapped)
                if any(
                    item.get('capability') != 'source_position' or item.get('coverage') == 'incomplete'
                    for item in contributors
                ):
                    combined['coverage'] = 'incomplete'
                result['capture_evidence'] = bounded_envelope(combined)
            else:
                result['capture_evidence'] = incoming['capture_evidence']
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
        result['private_cloud_sync_enabled'] = any(
            row.get('private_cloud_sync_enabled') for row in [incoming, *records]
        )
        # A codec must never be downgraded when bridge donors have mixed protection.
        result['data_protection_level'] = (
            'enhanced'
            if any((row.get('data_protection_level') or 'enhanced') == 'enhanced' for row in [incoming, *records])
            else incoming['data_protection_level']
        )
        ancestor_updates: dict[str, dict] = {}
        flatten_donors = (
            {cid: raw for cid, raw in matched.items() if cid != canonical} if flatten and smart_live_target else {}
        )
        if flatten_donors:
            survivor_row = dict(current or {}, id=canonical)
            reason, union_ids = merge_ancestry.ancestry_union(survivor_row, flatten_donors)
            if reason is not None:
                raise SyncAssignmentConflict('sync ancestry flatten rejected', subtype='other')
            ancestor_rows = {aid: load(aid) for aid in union_ids if aid not in flatten_donors}
            reason, union, ancestor_updates = merge_ancestry.flatten_updates(
                survivor_row, flatten_donors, ancestor_rows, user_managed=_policy_user_managed
            )
            if reason is not None:
                raise SyncAssignmentConflict('sync ancestry flatten rejected', subtype='other')
            ancestors = set(union)
        else:
            ancestors = {cid for row in records for cid in row.get('sync_merged_from', [])}
            ancestors.update(cid for cid in matched if cid != canonical)
        result['sync_merged_from'] = sorted(ancestors)
        if incoming.get('geolocation') and not result.get('geolocation'):
            result['geolocation'] = incoming['geolocation']

        # Read all occupied day buckets before the first write.
        index.read(extent)
        payload = encode(result)
        payload.pop('photos', None)
        return _Plan(
            canonical,
            matched,
            result,
            created,
            survivors,
            kept,
            payload,
            ancestor_updates,
            _stored_document_bytes(collection.document(canonical), payload, current, invalidate),
        )

    # Every plan is read-only, so a full canonical can be dropped and the
    # assignment re-planned inside the same transaction before any write. The
    # decision is made only from the complete encoded plan against the budget,
    # so a write that fits behaves exactly as before. Each accepted rollover is
    # itself re-checked (a chain of full rows costs one plan per row, which only
    # an account at the ceiling pays). The loop terminates: a plan never
    # matches or targets an excluded row, so every pass excludes at least one
    # new conversation from the finite set this transaction can read.
    excluded: frozenset[str] = frozenset()
    chosen = plan(excluded, tuple(range(len(incoming['transcript_segments']))))
    if (
        live_stats is not None
        and not chosen.survivors
        and not chosen.created
        and chosen.canonical == target_id
        and target is not None
    ):
        # Every incoming segment repeated speech already on the explicit live
        # target. Acknowledge without any writes; a sync-scoped retry still
        # completes the enrichment the earlier commit owed.
        no_op = decode(chosen.matched[chosen.canonical])
        no_op['id'] = chosen.canonical
        no_op['sync_live_target'] = chosen.result['sync_live_target']
        no_op.setdefault('sync_relevance', 'keep')
        no_op['_sync_lineage_repeat_only'] = True
        if live_stats['sync_retry']:
            no_op['_sync_lineage_completion_pending'] = True
        no_op['_sync_lineage_dedupe'] = {
            'appended_seconds': 0.0,
            'dropped_as_repeat_seconds': bounded_span_seconds(incoming['transcript_segments']),
            'alignment_method': append_alignment_method(live_stats['report'], live_stats['exact_retries']),
            'repeat_only': True,
            'span_delta_bucket': _lineage_span_delta_bucket(
                stamp_fallback_live, target_id, chosen.matched.get(chosen.canonical), no_op
            ),
        }
        return no_op, False, []
    trigger = None
    while True:
        drop = (set(chosen.matched) | {chosen.canonical}) & full_ids
        if chosen.grows and chosen.estimated_bytes > SYNC_CONVERSATION_BYTE_BUDGET:
            drop.add(chosen.canonical)
        if not drop:
            break
        trigger = trigger or ('commit_limit' if drop & full_ids else 'estimate')
        try:
            # Only speech the full plan found new moves on, so text already in
            # the full conversation is not duplicated into the rollover.
            rollover: _Plan | None = plan(excluded | drop, chosen.kept)
        except (SyncAssignmentSuperseded, SyncAssignmentConflict):
            rollover = None
        if (
            rollover is None
            or rollover.canonical in excluded | drop
            # Never overwrite an existing (tombstone) document or create an empty row.
            or (rollover.created and (read.get(rollover.canonical) is not None or not rollover.survivors))
        ):
            # No safe home for the speech: keep the write unchanged, so the
            # commit and its size-limit backstop decide exactly as before.
            logger.warning('event=sync_assignment_target outcome=size_rollover_unavailable trigger=%s', trigger)
            trigger = 'unavailable'
            break
        excluded, chosen = excluded | drop, rollover
    if trigger != 'unavailable' and excluded:
        # One event per committed plan, however many full rows it stepped past.
        logger.warning(
            'event=sync_assignment_target outcome=size_rollover trigger=%s created=%s excluded=%d',
            trigger,
            str(chosen.created).lower(),
            len(excluded),
        )
        record_fallback(
            component='sync_dispatch',
            from_mode='canonical_append',
            to_mode='size_rollover',
            reason='policy',
            outcome='degraded',
            log=logger,
        )

    canonical, matched, result, created, survivors = (
        chosen.canonical,
        chosen.matched,
        chosen.result,
        chosen.created,
        chosen.survivors,
    )
    payload = chosen.payload
    if created:
        # DELETE_FIELD is invalid in a Firestore set without merge. New anchors
        # inherit content, never a donor's client processing projection.
        clears: dict = {}
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
    for ancestor_id, patch in chosen.ancestor_updates.items():
        transaction.update(collection.document(ancestor_id), patch)
    index.write(result, set(matched) | {canonical})
    if live_stats is not None:
        # Transient telemetry only: the encoded plan already committed above.
        appended = bounded_span_seconds(survivors)
        result['_sync_lineage_dedupe'] = {
            'appended_seconds': appended,
            'dropped_as_repeat_seconds': max(0.0, bounded_span_seconds(incoming['transcript_segments']) - appended),
            'alignment_method': append_alignment_method(live_stats['report'], live_stats['exact_retries']),
            'repeat_only': False,
            'span_delta_bucket': _lineage_span_delta_bucket(
                stamp_fallback_live, target_id, matched.get(canonical), result
            ),
        }
    elif stamp_fallback_live and canonical == target_id and not created and result.get('sync_live_target'):
        result['_sync_lineage_stamp_append'] = _lineage_span_delta_bucket(
            True, target_id, matched.get(canonical), result
        )
    return result, created, survivors


def _stored_document_bytes(
    reference: Any, payload: dict, current: dict | None, invalidate: Callable[[dict], None]
) -> int:
    """Estimated size of the canonical document after this write commits.

    A create stores the payload; an update replaces the named top-level fields
    of the stored (encoded) row and removes the invalidated projection fields.
    """
    stored = dict(payload) if current is None else {**current, **payload}
    clears: dict = {}
    invalidate(clears)
    for field in clears:
        stored.pop(field, None)
    path = getattr(reference, 'path', None)
    return estimate_firestore_document_bytes(stored, path if isinstance(path, str) else None)


def size_limited_conversation(error: BaseException, canonical: Optional[str]) -> tuple[Optional[str], str]:
    """``(conversation id that cannot grow, bounded doc kind)`` for a size-limit commit rejection.

    Only a conversation can be routed around: the one the message names (the
    canonical, or a donor whose redirect write was rejected), or the attempted
    canonical when the message names no document. An index document yields no
    id, so that failure stands. The kind is stamped on the error for the
    pipeline's ``sync_persistence_exception`` line; ids and paths are never logged.
    """
    if not is_document_size_limit_error(error):
        return None, 'none'
    kind = firestore_document_kind(error)
    path = firestore_error_document_path(error)
    named: Optional[str] = None
    if kind == 'conversation' and path:
        named = path[-1]
        if named != canonical:
            kind = 'donor'
    elif kind == 'none' and '/documents/' not in str(error):
        # Only a message that names no document at all is attributed to the
        # canonical; an unparseable path could be an index document.
        named = canonical
    setattr(error, 'sync_firestore_doc_kind', kind)
    return named, kind


def run_with_size_limit_backstop(
    run: Callable[[frozenset[str]], _T], attempted_canonical: Callable[[], Optional[str]]
) -> _T:
    """Run the assignment transaction; after a size-limit rejection, retry exactly once.

    ``run(full_ids)`` runs one complete transaction. The retry marks the
    rejected conversation full, so ``assign_in_transaction`` re-plans without
    it and re-runs every fence; an identical later retry finds the rollover row
    by interval and deduplicates. A second rejection is raised unchanged and
    counts as a strike exactly as before.
    """
    try:
        return run(frozenset())
    except Exception as error:
        full_id, kind = size_limited_conversation(error, attempted_canonical())
        if full_id is None:
            raise
    logger.warning('event=sync_assignment_target outcome=size_limit_retry firestore_doc_kind=%s', kind)
    record_fallback(
        component='sync_dispatch',
        from_mode='canonical_append',
        to_mode='size_limit_retry',
        reason='other',
        outcome='degraded',
        log=logger,
    )
    try:
        return run(frozenset({full_id}))
    except Exception as error:
        size_limited_conversation(error, attempted_canonical())
        raise
